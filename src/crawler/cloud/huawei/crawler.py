from __future__ import annotations

# Standard Library Imports.
import re
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.huawei.enums import (
    HuaweiDocsCatalogueField,
    HuaweiDocsCategory,
    HuaweiDocsCategoryField,
    HuaweiDocsCode,
    HuaweiDocsEntryField,
    HuaweiProductSection,
)
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from models.cloud.products.product import CloudProduct


class HuaweiCloudCrawler(BaseCloudCrawler):
    """Huawei Cloud (international website, in English) catalogue crawler.

    Attributes:
        DOCS_URL (ClassVar[str]): The documentation catalogue JSON, listing the documented services by category.
        DOCS_HOST (ClassVar[str]): The documentation website, whose pages describe the services without description.
        PRODUCT_CARDS (ClassVar[str]): The CSS selector of the product cards of the products page (desktop copy).
        SECTIONS (ClassVar[str]): The CSS selector of the category sections of the products page.
        SECTION_TITLE (ClassVar[str]): The CSS selector of the category title of a section.
        SUB_SECTIONS (ClassVar[str]): The CSS selector of the sub-category groups of a section (desktop copy).
        SUB_SECTION_TITLE (ClassVar[str]): The CSS selector of the sub-category title of a group, absent from the
            sections without sub-categories.
        CARD (ClassVar[str]): The CSS selector of a product card within a group.
        MARKETING_SECTIONS (ClassVar[FrozenSet[HuaweiProductSection]]): The sections of the products page which are
            not categories.
        DOCS_EXCLUDED_CATEGORIES (ClassVar[FrozenSet[HuaweiDocsCategory]]): The documentation categories which are
            not services.
        DOCS_EXCLUDED_CODES (ClassVar[FrozenSet[HuaweiDocsCode]]): The documentation entries which are guides, not
            services.
        DOCS_NOT_PRODUCT (ClassVar[re.Pattern[str]]): The documentation pages which are not services (decision
            guides).

    Notes:
        The main source is the https://www.huaweicloud.com/intl/en-us/product/ page, whose cards give the name,
        description and link of each product. The page holds a desktop and a mobile copy of every card: only the
        desktop copy is read. The documentation catalogue JSON completes it with the documented services missing
        from the products page, its solutions, cloud adoption, ecosystem, user support and miscellaneous
        categories, decision guides, SDK and signing guides excluded. The documentation page of a service without
        description is read for its meta description.
        The products page files its cards under categories (e.g. `Compute`), some split into sub-categories (e.g.
        `Containers & Middleware` > `Containers`): a product gets every category it is listed under, the `Featured`
        section excepted. A documented service gets its documentation category.
    """

    DOCS_URL: ClassVar[str] = (
        "https://portal.huaweicloud.com/rest/cbc/portaldocdataservice/v1/books/items?appId=INTL-EN_US"
    )
    DOCS_HOST: ClassVar[str] = "support.huaweicloud.com"
    PRODUCT_CARDS: ClassVar[str] = "div.second-content.second-pc a.card"
    SECTIONS: ClassVar[str] = "div.first-content"
    SECTION_TITLE: ClassVar[str] = ".first-title"
    SUB_SECTIONS: ClassVar[str] = "div.second-content.second-pc div.second-flex"
    SUB_SECTION_TITLE: ClassVar[str] = ".second-title"
    CARD: ClassVar[str] = "a.card"
    MARKETING_SECTIONS: ClassVar[FrozenSet[HuaweiProductSection]] = frozenset({HuaweiProductSection.FEATURED})
    DOCS_EXCLUDED_CATEGORIES: ClassVar[FrozenSet[HuaweiDocsCategory]] = frozenset(HuaweiDocsCategory)
    DOCS_EXCLUDED_CODES: ClassVar[FrozenSet[HuaweiDocsCode]] = frozenset(HuaweiDocsCode)
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

    def _first_text(self, element: Selector, selector: str) -> Optional[str]:
        """Read the text of the first element matching a CSS selector within an element.

        Args:
            element (Selector): The element.
            selector (str): The CSS selector.

        Returns:
            Optional[str]: The text, `None` when no element matches.
        """
        match = element.css(selector).first
        return match.get_all_text(separator=" ", strip=True) if match is not None else None

    def _card_categories(self, response: Response) -> Dict[str, List[str]]:
        """Gather the categories of the desktop cards of the products page, by card link.

        Args:
            response (Response): The products page.

        Returns:
            Dict[str, List[str]]: The category and sub-category labels of each card link (`_url_key`), in page order.

        Notes:
            A product listed in several sections gets the categories of all of them, the marketing sections excepted.
        """
        categories: Dict[str, List[str]] = {}
        for section in response.css(self.SECTIONS):
            category = self._clean_text(self._first_text(section, self.SECTION_TITLE))
            if not category or category in self.MARKETING_SECTIONS:
                self.logger.debug("Skipping the section %r of %s, not a category.", category, response.url)
                continue
            for group in section.css(self.SUB_SECTIONS):
                labels = [category, self._clean_text(self._first_text(group, self.SUB_SECTION_TITLE))]
                for card in group.css(self.CARD):
                    link = self._url_key(urljoin(response.url, card.attrib.get(HtmlAttribute.HREF, "")))
                    categories.setdefault(link, []).extend(labels)
        self.logger.debug("%d categorized product cards in %s.", len(categories), response.url)
        return categories

    def _card_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the desktop cards of the products page.

        Args:
            response (Response): The products page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the page, the featured ones first.
        """
        cards = response.css(self.PRODUCT_CARDS)
        self.logger.debug("%d product cards in %s.", len(cards), response.url)
        categories = self._card_categories(response)
        for card in cards:
            url = urljoin(response.url, card.attrib.get(HtmlAttribute.HREF, ""))
            if product := self._build_product(
                self._first_text(card, ".card-title"),
                self._first_text(card, ".card-description"),
                url,
                categories=categories.get(self._url_key(url), []),
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
        categories = self._as_object(self._json_body(response)).get(HuaweiDocsCatalogueField.DATA)
        if not isinstance(categories, list):
            self.logger.error("The %s documentation catalogue %s has no `data` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the `data` list is missing")
        self.logger.debug("%d documentation categories in %s.", len(categories), response.url)
        return categories

    def _docs_entries(self, response: Response) -> Iterator[Tuple[str, Optional[str], Optional[str], str]]:
        """Walk the documented services, skipping the excluded categories, the guides and the SDK entries.

        Args:
            response (Response): The documentation catalogue JSON.

        Yields:
            Tuple[str, Optional[str], Optional[str], str]: The name, description, documentation URL and category of
                each service.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no `data` list.
        """
        for category in self._docs_categories(response):
            fields = self._as_object(category)
            category_name = self._as_text(fields.get(HuaweiDocsCategoryField.NAME))
            if category_name in self.DOCS_EXCLUDED_CATEGORIES:
                self.logger.debug("Skipping the documentation category %r, not services.", category_name)
                continue
            products = fields.get(HuaweiDocsCategoryField.PRODUCTS)
            for entry in products if isinstance(products, list) else []:
                item = self._as_object(entry)
                title, uri = (
                    self._clean_text(self._as_text(item.get(HuaweiDocsEntryField.TITLE))),
                    self._as_text(item.get(HuaweiDocsEntryField.URI)),
                )
                code = self._as_text(item.get(HuaweiDocsEntryField.CODE))
                if code in self.DOCS_EXCLUDED_CODES or self.DOCS_NOT_PRODUCT.search(uri or ""):
                    self.logger.debug("Skipping the documentation entry %r (%s), not a service.", title, code)
                    continue
                yield (
                    title,
                    self._as_text(item.get(HuaweiDocsEntryField.DESCRIPTION)),
                    uri,
                    self._clean_text(category_name),
                )

    def _docs_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the documented services which have a description.

        Args:
            response (Response): The documentation catalogue JSON.

        Yields:
            Iterator[CloudProduct]: Each valid documented service with a description.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no `data` list.

        Notes:
            A service documented in several categories gets all of them.
        """
        entries = list(self._docs_entries(response))
        categories: Dict[str, List[str]] = {}
        for title, _, _, category in entries:
            categories.setdefault(self._name_key(title), []).append(category)
        for title, description, uri, _ in entries:
            if self._clean_text(description) and (
                product := self._build_product(title, description, uri, categories=categories[self._name_key(title)])
            ):
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
        for title, description, uri, _ in self._docs_entries(response):
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
