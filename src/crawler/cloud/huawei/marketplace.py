from __future__ import annotations

# Standard Library Imports.
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.huawei.enums import (
    HuaweiDelivery,
    HuaweiListingField,
    HuaweiMarketplaceCategory,
    HuaweiMarketplaceHeader,
    HuaweiMarketplaceLanguage,
    HuaweiMarketplaceMeta,
    HuaweiSearchFlow,
    HuaweiSearchPageField,
    HuaweiSearchParameter,
)
from crawler.enums import HttpMethod
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_software import MarketplaceSoftware


class HuaweiMarketplaceCrawler(BaseMarketplaceCrawler):
    """Huawei Cloud KooGallery (international marketplace) crawler.

    Attributes:
        API_URL (ClassVar[str]): The search API of the marketplace pages (`POST`).
        SITE_URL (ClassVar[str]): The marketplace website, the listing links being relative to it.
        PAGE_SIZE (ClassVar[int]): The listings read per page, the API maximum.
        HEADERS (ClassVar[Dict[str, str]]): The request headers (`HuaweiMarketplaceHeader`), asking for the English
            texts.
        PAGE (ClassVar[HuaweiMarketplaceMeta]): The meta key holding the page number, from 1.
        EXCLUDED_CATEGORIES (ClassVar[FrozenSet[HuaweiMarketplaceCategory]]): The top categories which hold no
            software (services, data products and hardware), casefolded.
        EXCLUDED_DELIVERIES (ClassVar[FrozenSet[HuaweiDelivery]]): The delivery methods of the offers which are not
            software (services, hardware), casefolded.
        DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery method of each marketplace delivery code or
            English label (`HuaweiDelivery`), casefolded.
        DELIVERY_FIELDS (ClassVar[Tuple[HuaweiListingField, ...]]): The listing fields giving the delivery, the
            code first.
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The search API, the first page being requested with a `POST` body.

    Notes:
        The marketplace pages search the listings through a JSON API (`POST`, `flow_id` 101002, an empty keyword):
        each page (`offset`, `limit` 100) gives the `total` and the listings (`pagination.items`). A listing gives
        its English title, abstract, publisher (`corporation_name`), top category (`type_name_en`), sub-category
        (`content_type_desc_en`), delivery (`delivery_code`, else `delivery_code_en`) and relative page link (`url`).
        The category path is the sub-category under the top category, without identifier: the listing gives no
        category code.
        The professional services, hardware and data categories are skipped, so are the service and hardware
        deliveries (a few services are filed under a software category). The API host has no `robots.txt`.
    """

    API_URL: ClassVar[str] = (
        "https://searchrec.marketplace-intl.huaweicloud.com/rest/mkp/v1/mkpsearchengineservice/search"
    )
    SITE_URL: ClassVar[str] = "https://marketplace.huaweicloud.com"
    PAGE_SIZE: ClassVar[int] = 100
    HEADERS: ClassVar[Dict[str, str]] = {HuaweiMarketplaceHeader.LANGUAGE: HuaweiMarketplaceLanguage.ENGLISH}
    PAGE: ClassVar[HuaweiMarketplaceMeta] = HuaweiMarketplaceMeta.PAGE
    EXCLUDED_CATEGORIES: ClassVar[FrozenSet[HuaweiMarketplaceCategory]] = frozenset(HuaweiMarketplaceCategory)
    EXCLUDED_DELIVERIES: ClassVar[FrozenSet[HuaweiDelivery]] = frozenset(
        {
            HuaweiDelivery.MANUAL_SERVICE,
            HuaweiDelivery.SERVICE,
            HuaweiDelivery.PROFESSIONAL_SERVICES,
            HuaweiDelivery.HARDWARE,
        }
    )
    DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        HuaweiDelivery.LICENSE: DeliveryMethod.DOWNLOAD,
        HuaweiDelivery.VM_IMAGE: DeliveryMethod.VIRTUAL_MACHINE,
        HuaweiDelivery.IMAGE: DeliveryMethod.VIRTUAL_MACHINE,
        HuaweiDelivery.CLOUD_SERVER: DeliveryMethod.VIRTUAL_MACHINE,
        HuaweiDelivery.SAAS: DeliveryMethod.SAAS,
    }
    DELIVERY_FIELDS: ClassVar[Tuple[HuaweiListingField, ...]] = (
        HuaweiListingField.DELIVERY_CODE,
        HuaweiListingField.DELIVERY_CODE_EN,
    )

    name = "huawei-marketplace"
    catalogue_url: ClassVar[str] = API_URL

    ############################
    # Internal Helpers Methods #
    ############################

    def _search_request(self, page: int) -> Request:
        """Build the search request of a page of listings.

        Args:
            page (int): The page number, from 1.

        Returns:
            Request: The `POST` request, whose page may be empty after the first one.
        """
        body: Dict[str, JsonValue] = {
            HuaweiSearchParameter.AGGREGATIONS: {},
            HuaweiSearchParameter.FILTER: {},
            HuaweiSearchParameter.FLOW_ID: HuaweiSearchFlow.MARKETPLACE,
            HuaweiSearchParameter.KEYWORD: "",
            HuaweiSearchParameter.LIMIT: self.PAGE_SIZE,
            HuaweiSearchParameter.OFFSET: (page - 1) * self.PAGE_SIZE,
        }
        meta: Dict[str, JsonValue] = {self.PAGE: page}
        if page > 1:
            meta[self.MAY_BE_EMPTY] = True
        return self._api_request(
            self.API_URL,
            HttpMethod.POST,
            json=body,
            headers=dict(self.HEADERS),
            meta=meta,
            priority=self.PRIMARY_PRIORITY,
        )

    def _catalogue_request(self) -> Request:
        """Build the search request of the first page.

        Returns:
            Request: The `POST` request of the first page.
        """
        return self._search_request(1)

    def _search_page(self, response: Response) -> Tuple[List[JsonValue], int]:
        """Read a search page: its listings and the total number of listings.

        Args:
            response (Response): The search page.

        Returns:
            Tuple[List[JsonValue], int]: The listings (none past the last page) and the total.

        Raises:
            CatalogueFormatError: If the page is not a JSON object or has no total.
        """
        data = self._as_object(self._json_body(response))
        total = data.get(HuaweiSearchPageField.TOTAL)
        if not isinstance(total, int):
            self.logger.error("The %s search page %s has no listings total.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the search page has no listings total")
        listings = self._as_object(data.get(HuaweiSearchPageField.PAGINATION)).get(HuaweiSearchPageField.ITEMS)
        return (listings if isinstance(listings, list) else []), total

    def _delivery(self, listing: Dict[str, JsonValue]) -> Optional[DeliveryMethod]:
        """Get the delivery method of a listing.

        Args:
            listing (Dict[str, JsonValue]): The listing.

        Returns:
            Optional[DeliveryMethod]: The delivery method, `None` for a service or hardware (not a software).
        """
        codes = [self._clean_text(self._as_text(listing.get(field))).casefold() for field in self.DELIVERY_FIELDS]
        if any(code in self.EXCLUDED_DELIVERIES for code in codes):
            return None
        return next((self.DELIVERIES[code] for code in codes if code in self.DELIVERIES), DeliveryMethod.OTHER)

    def _listing_software(self, listing: Dict[str, JsonValue]) -> Optional[MarketplaceSoftware]:
        """Build the software of a listing, unless it is a service, hardware or a data product.

        Args:
            listing (Dict[str, JsonValue]): The listing.

        Returns:
            Optional[MarketplaceSoftware]: The software, with its listing (`onshelf_time`) and update (`update_time`)
                dates in epoch milliseconds, `None` for a skipped (logged) or invalid listing.
        """
        name = self._as_text(listing.get(HuaweiListingField.TITLE))
        category = self._as_text(listing.get(HuaweiListingField.CATEGORY))
        if self._clean_text(category).casefold() in self.EXCLUDED_CATEGORIES:
            self.logger.debug("Skipping the %s listing %r, not a software (category %s).", self.name, name, category)
            return None
        delivery = self._delivery(listing)
        if delivery is None:
            self.logger.debug(
                "Skipping the %s listing %r, not a software (delivery %s).",
                self.name,
                name,
                listing.get(HuaweiListingField.DELIVERY_CODE_EN),
            )
            return None
        link = self._as_text(listing.get(HuaweiListingField.URL))
        subcategory = self._as_text(listing.get(HuaweiListingField.SUBCATEGORY))
        return self._build_software(
            name,
            self._as_text(listing.get(HuaweiListingField.ABSTRACT)),
            f"{self.SITE_URL}/{link.lstrip('/')}" if link else None,
            self._as_text(listing.get(HuaweiListingField.PUBLISHER)),
            delivery,
            [category, subcategory],
            marketplace_category_paths=[self._category([category, subcategory])],
            added_at=self._parse_date(listing.get(HuaweiListingField.LISTED_AT), name),
            updated_at=self._parse_date(listing.get(HuaweiListingField.UPDATED_AT), name),
        )

    def _next_request(self, response: Response) -> Optional[Request]:
        """Build the request of the page after a search page, if there are more listings and pages may be read.

        Args:
            response (Response): The search page.

        Returns:
            Optional[Request]: The next page request, `None` after the last page or at the page limit.

        Raises:
            CatalogueFormatError: If the page is not a JSON object or has no total.
        """
        listings, total = self._search_page(response)
        page = response.meta.get(self.PAGE)
        number = page if isinstance(page, int) else 1
        if not listings or number * self.PAGE_SIZE >= total:
            self.logger.info("Last %s search page reached (page %d, %d listings).", self.name, number, total)
            return None
        if not self._within_page_limit(number + 1):
            return None
        self.logger.info("Requesting the %s search page %d (%d listings).", self.name, number + 1, total)
        return self._search_request(number + 1)

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a search page.

        Args:
            response (Response): The search page.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid software of the page.

        Raises:
            CatalogueFormatError: If the page is not a JSON object or has no total.
        """
        listings, total = self._search_page(response)
        self.logger.info("%s search page %s: %d listings (%d in total).", self.name, response.url, len(listings), total)
        for listing in map(self._as_object, listings):
            if (software := self._listing_software(listing)) is not None:
                yield software

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the software of a search page, then request the next page.

        Args:
            response (Response): The search page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each software not streamed yet, then the next page request.

        Raises:
            CatalogueFormatError: If the page is not a JSON object or has no total.
            EmptyCatalogueError: If the first page holds no software.
        """
        async for item in super().parse(response):
            yield item
        if (request := self._next_request(response)) is not None:
            yield request
