from __future__ import annotations

# Standard Library Imports.
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Union
from urllib.parse import quote

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.stackit.enums import StackitDeliveryMethod, StackitProductField, StackitRequestMeta
from crawler.exception import CatalogueFormatError, EmptyCatalogueError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class STACKITMarketplaceCrawler(BaseMarketplaceCrawler):
    """STACKIT marketplace crawler.

    Attributes:
        API_URL (ClassVar[str]): The catalog products API, the product details being under it.
        PAGE_SIZE (ClassVar[int]): The number of products per listing page, at most 100.
        PRODUCT_URL (ClassVar[str]): The product page URL template, filled with the product identifier.
        PAGE (ClassVar[StackitRequestMeta]): The meta key holding the number of a listing page.
        PRODUCT (ClassVar[StackitRequestMeta]): The meta key marking a product detail, holding the product identifier.
        EXCLUDED_DELIVERIES (ClassVar[FrozenSet[StackitDeliveryMethod]]): The delivery methods of the offers which
            are not software.
        DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery method of each marketplace delivery method,
            keyed by `StackitDeliveryMethod` members.

    Notes:
        The catalog API lists the products by pages of 100 (`items`), the next page being requested with the
        `cursor` of the previous one until it gives none. The professional services are skipped. The listing gives
        no category: the detail of each kept product (`/v1/catalog/products/{productId}`) is requested, and the
        software is built from it, with its `categories` (its `industries` are verticals, not kinds of software, and
        are left out).
    """

    API_URL: ClassVar[str] = "https://stackit-marketplace.api.stackit.cloud/v1/catalog/products"
    PAGE_SIZE: ClassVar[int] = 100
    PRODUCT_URL: ClassVar[str] = "https://marketplace.stackit.cloud/en/products/{product}"
    PAGE: ClassVar[StackitRequestMeta] = StackitRequestMeta.PAGE
    PRODUCT: ClassVar[StackitRequestMeta] = StackitRequestMeta.PRODUCT
    EXCLUDED_DELIVERIES: ClassVar[FrozenSet[StackitDeliveryMethod]] = frozenset(
        {StackitDeliveryMethod.PROFESSIONAL_SERVICE}
    )
    DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        StackitDeliveryMethod.SAAS: DeliveryMethod.SAAS,
        StackitDeliveryMethod.CONTAINER_IMAGE: DeliveryMethod.CONTAINER,
        StackitDeliveryMethod.CLOUD_IMAGE: DeliveryMethod.VIRTUAL_MACHINE,
    }

    name = "stackit-marketplace"
    catalogue_url: ClassVar[str] = f"{API_URL}?limit={PAGE_SIZE}&locale=en"

    ############################
    # Internal Helpers Methods #
    ############################

    def _json_object(self, response: Response) -> Dict[str, JsonValue]:
        """Read a JSON object response of the API.

        Args:
            response (Response): The API response.

        Returns:
            Dict[str, JsonValue]: The JSON object.

        Raises:
            CatalogueFormatError: If the response is not a JSON object.
        """
        data = self._json_body(response)
        if not isinstance(data, dict):
            self.logger.error("The %s API response %s is not a JSON object.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the response is not a JSON object")
        return data

    def _product_request(self, product: Dict[str, JsonValue]) -> Optional[Request]:
        """Build the detail request of a listed product, if it is a software not streamed yet.

        Args:
            product (Dict[str, JsonValue]): The listed product.

        Returns:
            Optional[Request]: The detail request, `None` for a product skipped (logged).
        """
        identifier, name = (
            self._as_text(product.get(StackitProductField.PRODUCT_ID)),
            self._as_text(product.get(StackitProductField.NAME)),
        )
        delivery = self._as_text(product.get(StackitProductField.DELIVERY_METHOD))
        if not identifier:
            self.logger.debug("Skipping the %s product %r without identifier.", self.name, name)
            return None
        if delivery in self.EXCLUDED_DELIVERIES:
            self.logger.debug("Skipping the %s product %r, not a software (%s).", self.name, name, delivery)
            return None
        if self.PRODUCT_URL.format(product=identifier).casefold() in self.software_categories:
            self.logger.debug("Not requesting the %s product %r again.", self.name, name)
            return None
        return Request(
            f"{self.API_URL}/{quote(identifier, safe='')}?locale=en",
            meta={self.PRODUCT: identifier, self.MAY_BE_EMPTY: True},
        )

    def _listing_requests(self, response: Response) -> Iterator[Request]:
        """Read a listing page: the detail requests of its software, then the next page request if any.

        Args:
            response (Response): The listing page.

        Yields:
            Iterator[Request]: Each product detail request, then the next listing page request.

        Raises:
            CatalogueFormatError: If the page has no products list.
            EmptyCatalogueError: If the page lists no product at all.
        """
        data = self._json_object(response)
        products = data.get(StackitProductField.ITEMS)
        if not isinstance(products, list):
            self.logger.error("The %s listing page %s has no products list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the page has no products list")
        if not products and not response.meta.get(self.MAY_BE_EMPTY):
            self.logger.error("The %s listing page %s lists no product.", self.name, response.url)
            raise EmptyCatalogueError(self.name, response.url)
        page = response.meta.get(self.PAGE)
        number = page if isinstance(page, int) else 1
        requests = [request for request in map(self._product_request, map(self._as_object, products)) if request]
        self.logger.info(
            "%s listing page %d: %d products (%s in total), %d details requested.",
            self.name,
            number,
            len(products),
            data.get(StackitProductField.TOTAL_COUNT),
            len(requests),
        )
        yield from requests
        cursor = self._as_text(data.get(StackitProductField.CURSOR))
        if cursor and self._within_page_limit(number + 1):
            self.logger.info("Requesting the %s listing page %d.", self.name, number + 1)
            yield Request(
                f"{self.catalogue_url}&cursor={quote(cursor, safe='')}",
                priority=self.PRIMARY_PRIORITY,
                meta={self.PAGE: number + 1, self.MAY_BE_EMPTY: True},
            )

    def _categories(self, product: Dict[str, JsonValue]) -> List[str]:
        """Read the categories of a product detail.

        Args:
            product (Dict[str, JsonValue]): The product detail.

        Returns:
            List[str]: The category labels.
        """
        categories = product.get(StackitProductField.CATEGORIES)
        if not isinstance(categories, list):
            return []
        return [label for label in (self._as_text(category) for category in categories) if label]

    def _category_paths(self, categories: List[str]) -> List[Optional[MarketplaceCategory]]:
        """Build the marketplace category paths of a product detail.

        Args:
            categories (List[str]): The category labels of the product detail.

        Returns:
            List[Optional[MarketplaceCategory]]: One single-level path per category, without identifier (the API
                gives none, nor any parent category).
        """
        self.logger.debug("%d %s category paths built.", len(categories), self.name)
        return [self._category([label]) for label in categories]

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a product detail.

        Args:
            response (Response): The product detail, requested with the `PRODUCT` meta.

        Yields:
            Iterator[MarketplaceSoftware]: The software, unless the detail is invalid or not a software.
        """
        if response.status >= 400:
            self.logger.debug("Skipping the %s product detail %s (HTTP %s).", self.name, response.url, response.status)
            return
        product = self._json_object(response)
        name, delivery = (
            self._as_text(product.get(StackitProductField.NAME)),
            self._as_text(product.get(StackitProductField.DELIVERY_METHOD)) or "",
        )
        if delivery in self.EXCLUDED_DELIVERIES:
            self.logger.debug("Skipping the %s product %r, not a software (%s).", self.name, name, delivery)
            return
        identifier = self._as_text(product.get(StackitProductField.PRODUCT_ID)) or str(
            response.meta.get(self.PRODUCT, "")
        )
        categories = self._categories(product)
        software = self._build_software(
            name,
            self._as_text(product.get(StackitProductField.SUMMARY)),
            self.PRODUCT_URL.format(product=identifier) if identifier else None,
            self._as_text(self._as_object(product.get(StackitProductField.VENDOR)).get(StackitProductField.NAME)),
            self.DELIVERIES.get(delivery, DeliveryMethod.OTHER),
            categories,
            marketplace_category_paths=self._category_paths(categories),
        )
        if software is not None:
            yield software

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the software of a product detail, or request the details and the next page of a listing page.

        Args:
            response (Response): A listing page, or a product detail (`PRODUCT` meta).

        Yields:
            Union[Dict[str, JsonValue], Request]: The software of a product detail, or the requests of a listing
                page.
        """
        if self.PRODUCT in response.meta:
            async for item in super().parse(response):
                yield item
            return
        self.logger.debug("Parsing the %s listing page %s (HTTP %s).", self.name, response.url, response.status)
        for request in self._listing_requests(response):
            yield request
