from __future__ import annotations

# Standard Library Imports.
import re
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError
from models.cloud.product import CloudProduct


class HuaweiCloudCrawler(BaseCloudCrawler):
    """Huawei Cloud (international website, in English) catalogue crawler.

    Attributes:
        DOCS_URL (ClassVar[str]): The documentation catalogue JSON, listing the documented services by category.
        DOCS_HOST (ClassVar[str]): The documentation website, whose pages describe the services without description.
        PRODUCT_CARDS (ClassVar[str]): The CSS selector of the product cards of the products page (desktop copy).
        DOCS_EXCLUDED_CATEGORIES (ClassVar[FrozenSet[str]]): The documentation categories which are not services.
        DOCS_EXCLUDED_CODES (ClassVar[FrozenSet[str]]): The documentation entries which are guides, not services.
        DOCS_NOT_PRODUCT (ClassVar[re.Pattern[str]]): The documentation pages which are not services (decision
            guides).

    Notes:
        The main source is the https://www.huaweicloud.com/intl/en-us/product/ page, whose cards give the name,
        description and link of each product. The page holds a desktop and a mobile copy of every card: only the
        desktop copy is read. The documentation catalogue JSON completes it with the documented services missing
        from the products page, its solutions, cloud adoption, ecosystem, user support and miscellaneous
        categories, decision guides, SDK and signing guides excluded. The documentation page of a service without
        description is read for its meta description.
    """

    DOCS_URL: ClassVar[str] = (
        "https://portal.huaweicloud.com/rest/cbc/portaldocdataservice/v1/books/items?appId=INTL-EN_US"
    )
    DOCS_HOST: ClassVar[str] = "support.huaweicloud.com"
    PRODUCT_CARDS: ClassVar[str] = "div.second-content.second-pc a.card"
    DOCS_EXCLUDED_CATEGORIES: ClassVar[FrozenSet[str]] = frozenset(
        {"Solutions", "Cloud Transformation", "Cloud Ecosystem", "User Support", "Others"}
    )
    DOCS_EXCLUDED_CODES: ClassVar[FrozenSet[str]] = frozenset({"sdk", "apisign", "securityInfo"})
    DOCS_NOT_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(r"/how-to-choose-")

    name = "huawei"
    catalogue_url: ClassVar[str] = "https://www.huaweicloud.com/intl/en-us/product/"
    complement_urls: ClassVar[Tuple[str, ...]] = (DOCS_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Huawei Cloud ", "HUAWEI CLOUD ", "Huawei ")

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler, allowing the documentation pages.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.allowed_domains.add(self.DOCS_HOST)

    ############################
    # Internal Helpers Methods #
    ############################

    def _is_docs_catalogue(self, response: Response) -> bool:
        """Tell whether a response is the documentation catalogue JSON.

        Args:
            response (Response): The response.

        Returns:
            bool: Whether it comes from the documentation catalogue host.
        """
        return urlparse(response.url).netloc == urlparse(self.DOCS_URL).netloc

    def _card_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the desktop cards of the products page.

        Args:
            response (Response): The products page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the page, the featured ones first.
        """
        cards = response.css(self.PRODUCT_CARDS)
        self.logger.debug("%d product cards in %s.", len(cards), response.url)
        for card in cards:
            title, description = card.css(".card-title").first, card.css(".card-description").first
            if product := self._build_product(
                title.get_all_text(separator=" ", strip=True) if title is not None else None,
                description.get_all_text(separator=" ", strip=True) if description is not None else None,
                urljoin(response.url, card.attrib.get("href", "")),
            ):
                yield product

    def _docs_categories(self, response: Response) -> List[JsonValue]:
        """Read the categories of the documentation catalogue.

        Args:
            response (Response): The documentation catalogue JSON.

        Returns:
            List[JsonValue]: The categories.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no `data` list.
        """
        categories = self._as_object(self._json_body(response)).get("data")
        if not isinstance(categories, list):
            self.logger.error("The %s documentation catalogue %s has no `data` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the `data` list is missing")
        self.logger.debug("%d documentation categories in %s.", len(categories), response.url)
        return categories

    def _docs_entries(self, response: Response) -> Iterator[Tuple[str, Optional[str], Optional[str]]]:
        """Walk the documented services, skipping the excluded categories, the guides and the SDK entries.

        Args:
            response (Response): The documentation catalogue JSON.

        Yields:
            Tuple[str, Optional[str], Optional[str]]: The name, description and documentation URL of each service.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no `data` list.
        """
        for category in self._docs_categories(response):
            fields = self._as_object(category)
            category_name = self._as_text(fields.get("name"))
            if category_name in self.DOCS_EXCLUDED_CATEGORIES:
                self.logger.debug("Skipping the documentation category %r, not services.", category_name)
                continue
            products = fields.get("products")
            for entry in products if isinstance(products, list) else []:
                item = self._as_object(entry)
                title, uri = self._clean_text(self._as_text(item.get("title"))), self._as_text(item.get("uri"))
                code = self._as_text(item.get("code"))
                if code in self.DOCS_EXCLUDED_CODES or self.DOCS_NOT_PRODUCT.search(uri or ""):
                    self.logger.debug("Skipping the documentation entry %r (%s), not a service.", title, code)
                    continue
                yield title, self._as_text(item.get("description")), uri

    def _docs_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the documented services which have a description.

        Args:
            response (Response): The documentation catalogue JSON.

        Yields:
            Iterator[CloudProduct]: Each valid documented service with a description.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no `data` list.
        """
        for title, description, uri in self._docs_entries(response):
            if self._clean_text(description) and (product := self._build_product(title, description, uri)):
                yield product

    def _docs_page_requests(self, response: Response) -> List[Request]:
        """Request the documentation pages of the new documented services without description.

        Args:
            response (Response): The documentation catalogue JSON.

        Returns:
            List[Request]: The documentation page requests, named after the catalogue titles.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no `data` list.
        """
        requests: List[Request] = []
        for title, description, uri in self._docs_entries(response):
            if self._clean_text(description) or not title or not uri:
                continue
            if self._name_key(title) in self.seen_products:
                self.logger.debug("Not requesting the documentation of %r, already streamed.", title)
                continue
            if (request := self._product_page_request(uri, title)) is not None:
                requests.append(request)
        self.logger.info("%d %s documentation pages to read for their description.", len(requests), self.name)
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products page or of the documentation catalogue.

        Args:
            response (Response): The products page or the documentation catalogue JSON.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.

        Raises:
            CatalogueFormatError: If the documentation catalogue is not JSON or has no `data` list.
        """
        if self._is_docs_catalogue(response):
            return self._docs_products(response)
        return self._card_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the products of a page, then request the documentation pages of the services without description.

        The documentation pages are read by the base crawler.

        Args:
            response (Response): The products page, the documentation catalogue JSON or a documentation page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, then the documentation page requests.

        Raises:
            EmptyCatalogueError: If the products page or the documentation catalogue holds no valid product.
            CatalogueFormatError: If the documentation catalogue is not JSON or has no `data` list.
        """
        async for item in super().parse(response):
            yield item
        if self.PRODUCT_PAGE not in response.meta and self._is_docs_catalogue(response):
            for request in self._docs_page_requests(response):
                yield request
