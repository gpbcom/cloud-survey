from __future__ import annotations

# Standard Library Imports.
import math
import re
from functools import partial
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import parse_qs, urljoin, urlparse

# Third Party Imports.
from patchright.async_api import Page
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.alibaba.enums import (
    AlibabaCardDelivery,
    AlibabaCardInfo,
    AlibabaMarketplaceMeta,
    AlibabaMarketplaceQuery,
    AlibabaMarketplaceTop,
    AlibabaMenuClass,
    AlibabaProductCodePrefix,
)
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class AlibabaMarketplaceCrawler(BaseMarketplaceCrawler):
    """Alibaba Cloud international marketplace crawler.

    Attributes:
        HOST (ClassVar[str]): The international marketplace website.
        PAGE_SIZE (ClassVar[int]): The number of products per result page, the largest one the website offers.
        TOP (ClassVar[AlibabaMarketplaceMeta]): The meta key holding the identifier of the top category of a result
            page.
        PAGE (ClassVar[AlibabaMarketplaceMeta]): The meta key holding the number of a result page.
        EXCLUDED_TOPS (ClassVar[FrozenSet[AlibabaMarketplaceTop]]): The top categories which are not software.
        MENU (ClassVar[str]): The category menu groups, a top category followed by its sub-categories.
        CARD (ClassVar[str]): The product cards of a result page, without the advertised one.
        TITLE (ClassVar[str]): The product link of a card.
        CURRENT (ClassVar[str]): The current page button of the pagination.
        SIZE_SELECTOR (ClassVar[str]): The page size drop-down of the pagination.
        SIZE_OPTION (ClassVar[str]): The page size options of the drop-down.
        JUMP_INPUT (ClassVar[str]): The page number box of the pagination, shown when there are many pages.
        JUMP_BUTTON (ClassVar[str]): The button going to the page number of the box.
        SIZE_APPLIED (ClassVar[str]): The script telling whether a result page shows its products by `PAGE_SIZE`.
        PAGE_SHOWN (ClassVar[str]): The script telling whether a result page shows another page of products.
        PRODUCT_PATH (ClassVar[re.Pattern[str]]): The product page path: its leaf category and product code.
        DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery of each card delivery method
            (`AlibabaCardDelivery`).
        CODE_DELIVERIES (ClassVar[Tuple[Tuple[AlibabaProductCodePrefix, Optional[DeliveryMethod]], ...]]): The
            delivery given by the product code prefix, when a card has no known delivery method, `None` for a
            service.
        category_names (Dict[str, str]): The category names, by category identifier.
        category_parents (Dict[str, str]): The top category identifier of each sub-category of the menu, by
            sub-category identifier.

    Notes:
        The product list API and the `?page=` URLs are disallowed by `robots.txt`, and the sitemap is broken: the
        stealth browser renders the result pages instead. The top categories are read from the category menu of the
        products page (https://marketplace.alibabacloud.com/products), without the professional services. Each result
        page of a top category is one browser request (`/products?categoryId=<top>`), whose page action shows 50
        products per page and goes to the requested page. A card gives the product name, description, publisher
        ("By ..."), delivery method (image, SaaS, API or service, the services being skipped) and its page, whose
        path holds the leaf category, named after the menu. A product is given the path of its leaf category under
        the menu top category of that leaf (which may not be the queried top category, then given as a path too).
    """

    HOST: ClassVar[str] = "https://marketplace.alibabacloud.com"
    PAGE_SIZE: ClassVar[int] = 50
    TOP: ClassVar[AlibabaMarketplaceMeta] = AlibabaMarketplaceMeta.TOP
    PAGE: ClassVar[AlibabaMarketplaceMeta] = AlibabaMarketplaceMeta.PAGE
    EXCLUDED_TOPS: ClassVar[FrozenSet[AlibabaMarketplaceTop]] = frozenset({AlibabaMarketplaceTop.PROFESSIONAL_SERVICE})
    MENU: ClassVar[str] = "ul.menu_item"
    CARD: ClassVar[str] = ".product-list-item:not(.advertising)"
    TITLE: ClassVar[str] = ".list-item-title a"
    CURRENT: ClassVar[str] = ".next-pagination-item.next-current"
    SIZE_SELECTOR: ClassVar[str] = ".next-pagination-size-selector-dropdown"
    SIZE_OPTION: ClassVar[str] = ".next-menu-item"
    JUMP_INPUT: ClassVar[str] = ".next-pagination-jump-input input"
    JUMP_BUTTON: ClassVar[str] = ".next-pagination-jump-go"
    SIZE_APPLIED: ClassVar[str] = (
        "([card, size]) => { const total = document.querySelector('.next-pagination-total');"
        " const count = total ? parseInt(total.textContent.replace(/\\D/g, '') || '0', 10) : 0;"
        " return document.querySelectorAll(card).length === Math.min(size, count); }"
    )
    PAGE_SHOWN: ClassVar[str] = (
        "([number, first]) => { const current = document.querySelector('.next-pagination-item.next-current');"
        " const title = document.querySelector('.list-item-title a');"
        " return !!current && current.textContent.trim() === String(number) && !!title"
        " && title.textContent !== first; }"
    )
    PRODUCT_PATH: ClassVar[re.Pattern[str]] = re.compile(r"/products/(\d+)/([a-z]+)\d+\.html$")
    DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        AlibabaCardDelivery.IMAGE: DeliveryMethod.VIRTUAL_MACHINE,
        AlibabaCardDelivery.SAAS: DeliveryMethod.SAAS,
        AlibabaCardDelivery.API: DeliveryMethod.API,
    }
    CODE_DELIVERIES: ClassVar[Tuple[Tuple[AlibabaProductCodePrefix, Optional[DeliveryMethod]], ...]] = (
        (AlibabaProductCodePrefix.SERVICE, None),
        (AlibabaProductCodePrefix.IMAGE, DeliveryMethod.VIRTUAL_MACHINE),
        (AlibabaProductCodePrefix.SAAS, DeliveryMethod.SAAS),
        (AlibabaProductCodePrefix.API, DeliveryMethod.API),
    )

    name = "alibaba-marketplace"
    catalogue_url: ClassVar[str] = f"{HOST}/products"

    def __init__(
        self,
        crawldir: Optional[Union[str, Path]] = None,
        interval: float = 300.0,
        classifier: Optional[SoftwareClassifier] = None,
    ) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
            classifier (Optional[SoftwareClassifier]): The software classifier, the project rules by default.
        """
        super().__init__(crawldir=crawldir, interval=interval, classifier=classifier)
        self.category_names: Dict[str, str] = {}
        self.category_parents: Dict[str, str] = {}

    ############################
    # Internal Helpers Methods #
    ############################

    def _catalogue_request(self) -> Request:
        """Build the request of the products page, whose category menu gives the top categories.

        Returns:
            Request: The browser request.
        """
        return Request(
            self.catalogue_url,
            sid=self._browser_session_id(),
            priority=self.PRIMARY_PRIORITY,
            wait_selector=self.MENU,
        )

    async def _show_page(self, number: int, page: Page) -> None:
        """Show the products of a result page by `PAGE_SIZE`, and go to a page (page action).

        Args:
            number (int): The page number, the first page being 1.
            page (Page): The browser page.
        """
        await page.locator(self.SIZE_SELECTOR).click()
        await page.locator(self.SIZE_OPTION, has_text=str(self.PAGE_SIZE)).first.click()
        await page.wait_for_function(self.SIZE_APPLIED, arg=[self.CARD, self.PAGE_SIZE])
        self.logger.debug("The %s result page shows %d products per page.", self.name, self.PAGE_SIZE)
        if number == 1:
            return
        first = await page.locator(self.TITLE).first.text_content()
        jump = page.locator(self.JUMP_INPUT)
        if await jump.count():
            self.logger.debug("Jumping to the %s result page %d.", self.name, number)
            await jump.fill(str(number))
            await page.locator(self.JUMP_BUTTON).click()
        else:
            self.logger.debug("No page jump box, clicking the %s pagination button %d.", self.name, number)
            await page.locator(f"button.next-pagination-item[aria-label^='Page {number},']").click()
        await page.wait_for_function(self.PAGE_SHOWN, arg=[number, first])

    def _page_request(self, top: str, number: int) -> Request:
        """Build the browser request of a result page of a top category.

        Args:
            top (str): The top category identifier.
            number (int): The page number, the first page being 1.

        Returns:
            Request: The request, never filtered as a duplicate since every page of a category has the same URL.
        """
        return Request(
            f"{self.HOST}/products?categoryId={top}",
            sid=self._browser_session_id(),
            dont_filter=True,
            meta={self.TOP: top, self.PAGE: number},
            wait_selector=self.CARD,
            page_action=partial(self._show_page, number),
        )

    def _category_id(self, href: Optional[str]) -> Optional[str]:
        """Read the category identifier of a category link.

        Args:
            href (Optional[str]): The link, e.g. `https://marketplace.alibabacloud.com/products?categoryId=56682004`.

        Returns:
            Optional[str]: The identifier, `None` when the link has none.
        """
        values = parse_qs(urlparse(href or "").query).get(AlibabaMarketplaceQuery.CATEGORY_ID)
        return values[0] if values else None

    def _read_menu(self, response: Response) -> List[Tuple[str, str]]:
        """Read the category menu of a page, remembering the category names.

        Args:
            response (Response): A marketplace page.

        Returns:
            List[Tuple[str, str]]: The top categories, as identifier and name, in menu order.
        """
        tops: List[Tuple[str, str]] = []
        for group in response.css(self.MENU):
            parent: Optional[str] = None
            for item in group.css("li"):
                link = item.css("a").first
                identifier = self._category_id(link.attrib.get(HtmlAttribute.HREF)) if link is not None else None
                label = self._clean_text(link.get_all_text(separator=" ", strip=True)) if link is not None else ""
                if identifier is None or not label:
                    continue
                self.category_names[identifier] = label
                if AlibabaMenuClass.TITLE in str(item.attrib.get(HtmlAttribute.CLASS, "")).split():
                    tops.append((identifier, label))
                    parent = identifier
                elif parent is not None:
                    self.category_parents[identifier] = parent
        self.logger.debug("%d categories in the menu of %s.", len(self.category_names), response.url)
        return tops

    def _top_requests(self, response: Response) -> Iterator[Request]:
        """Request the first result page of each software top category of the menu.

        Args:
            response (Response): The products page.

        Yields:
            Request: The first result page requests.

        Raises:
            CatalogueFormatError: If the page has no category menu.
        """
        tops = self._read_menu(response)
        if not tops:
            self.logger.error("The %s products page %s has no category menu.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the category menu is missing")
        for identifier, label in tops:
            if label in self.EXCLUDED_TOPS:
                self.logger.debug("Skipping the top category %r (not software).", label)
                continue
            self.logger.info("Requesting the %s top category %r (%s).", self.name, label, identifier)
            yield self._page_request(identifier, 1)

    def _total(self, response: Response) -> int:
        """Read the number of products of a top category, given by the pagination.

        Args:
            response (Response): A result page.

        Returns:
            int: The number of products, 0 when the page has no pagination.
        """
        text = response.css(".next-pagination-total::text").get() or ""
        digits = re.sub(r"\D", "", text)
        if not digits:
            self.logger.warning("The %s result page %s has no pagination total, counting 0.", self.name, response.url)
            return 0
        return int(digits)

    def _check_page(self, response: Response, number: int, total: int) -> None:
        """Check that a result page shows the requested page, by `PAGE_SIZE`.

        Args:
            response (Response): The result page.
            number (int): The requested page number.
            total (int): The number of products of the top category.

        Raises:
            CatalogueFormatError: If the page shows another page, or another number of products (the page action
                failed).
        """
        current = response.css(self.CURRENT).first
        shown = self._clean_text(current.get_all_text(strip=True)) if current is not None else "1"
        cards = len(response.css(self.CARD))
        expected = max(0, min(self.PAGE_SIZE, total - (number - 1) * self.PAGE_SIZE))
        if shown != str(number) or cards != expected:
            self.logger.error(
                "The %s result page %s shows the page %s with %d products, not the page %d with %d products.",
                self.name,
                response.url,
                shown,
                cards,
                number,
                expected,
            )
            raise CatalogueFormatError(self.name, response.url, f"the page {number} is not shown")

    def _next_requests(self, response: Response) -> Iterator[Request]:
        """Request the next result pages of a top category, from its first page.

        Args:
            response (Response): The first result page of a top category.

        Yields:
            Request: The next result pages requests, within the page limit.
        """
        top = str(response.meta.get(self.TOP))
        pages = math.ceil(self._total(response) / self.PAGE_SIZE)
        self.logger.info("%d result pages in the %s top category %s.", pages, self.name, top)
        for number in range(2, pages + 1):
            if not self._within_page_limit(number):
                break
            yield self._page_request(top, number)

    def _delivery(self, info: List[str], code: str) -> Optional[DeliveryMethod]:
        """Get the delivery of a product, from its card delivery method, else from its product code.

        Args:
            info (List[str]): The card details, e.g. `Delivery Method: Image`.
            code (str): The product code prefix, e.g. `sgcmjj`.

        Returns:
            Optional[DeliveryMethod]: The delivery, `None` for a service (`OTHER` when unknown).
        """
        method = next(
            (line.split(":", 1)[1].strip() for line in info if line.startswith(AlibabaCardInfo.DELIVERY_METHOD)), ""
        )
        if method.casefold() == AlibabaCardDelivery.SERVICE:
            self.logger.debug("The %s product %s is a service.", self.name, code)
            return None
        if delivery := self.DELIVERIES.get(method.casefold()):
            return delivery
        delivery = next((delivery for prefix, delivery in self.CODE_DELIVERIES if prefix in code), DeliveryMethod.OTHER)
        self.logger.debug(
            "Delivery %s of the %s product %s, from its code (method %r).", delivery, self.name, code, method
        )
        return delivery

    def _category_paths(self, top: str, leaf: str) -> List[Optional[MarketplaceCategory]]:
        """Get the category paths of a product, from its queried top category and its leaf category.

        Args:
            top (str): The top category identifier of the result page.
            leaf (str): The leaf category identifier of the product page path, empty when unknown.

        Returns:
            List[Optional[MarketplaceCategory]]: The leaf category under its menu top category (identified by the
                leaf), and the queried top category (identified by itself), dropped when above the leaf.
        """
        paths: List[Optional[MarketplaceCategory]] = [self._category([self.category_names.get(top)], top)]
        if leaf and leaf in self.category_names:
            parent = self.category_parents.get(leaf)
            names = [self.category_names.get(parent) if parent else None, self.category_names[leaf]]
            paths.append(self._category(names, leaf))
        else:
            self.logger.debug("No leaf category path for %r under the %s top category %s.", leaf, self.name, top)
        return paths

    def _card_software(self, card: Selector, top: str) -> Optional[MarketplaceSoftware]:
        """Build the software of a product card.

        Args:
            card (Selector): The product card.
            top (str): The top category identifier of the result page.

        Returns:
            Optional[MarketplaceSoftware]: The software, `None` for a service or an invalid card.
        """
        link = card.css(self.TITLE).first
        if link is None:
            self.logger.debug("Skipping a product card without link.")
            return None
        name = self._clean_text(link.get_all_text(separator=" ", strip=True))
        url = urljoin(self.HOST, urlparse(link.attrib.get(HtmlAttribute.HREF, "")).path)
        leaf, code = match.groups() if (match := self.PRODUCT_PATH.search(url)) else ("", "")
        info = [
            self._clean_text(item.get_all_text(separator=" ", strip=True)) for item in card.css(".list-item-info li")
        ]
        delivery = self._delivery(info, code)
        if delivery is None:
            self.logger.debug("Skipping the product %r (service).", name)
            return None
        if leaf and leaf not in self.category_names:
            self.logger.debug("Unknown leaf category %s of the product %r.", leaf, name)
        describe = card.css(".list-item-describe").first
        company = card.css("a.list-item-company").first
        publisher = company.get_all_text(separator=" ", strip=True) if company is not None else None
        return self._build_software(
            name,
            describe.get_all_text(separator=" ", strip=True) if describe is not None else None,
            url=url,
            publisher=re.sub(r"^By\s+", "", self._clean_text(publisher)),
            delivery=delivery,
            marketplace_categories=[self.category_names.get(top), self.category_names.get(leaf)],
            marketplace_category_paths=self._category_paths(top, leaf),
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a result page of a top category.

        Args:
            response (Response): The result page (`TOP` and `PAGE` meta).

        Yields:
            MarketplaceSoftware: Each valid software of the page, without the services.

        Raises:
            CatalogueFormatError: If the page does not show the requested page by `PAGE_SIZE`.
        """
        self._read_menu(response)
        top, number = str(response.meta.get(self.TOP)), int(str(response.meta.get(self.PAGE, 1)))
        self._check_page(response, number, self._total(response))
        found = 0
        for card in response.css(self.CARD):
            if (software := self._card_software(card, top)) is not None:
                found += 1
                yield software
        self.logger.info("%d software on the %s result page %d of the category %s.", found, self.name, number, top)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Request the top categories from the products page, or stream the software of a result page.

        Args:
            response (Response): The products page, or a result page (`TOP` meta).

        Yields:
            Union[Dict[str, JsonValue], Request]: The first result page requests of the products page, the next
                result pages requests of a first page, then the software of a result page.

        Raises:
            CatalogueFormatError: If the products page has no category menu, or if a result page does not show the
                requested page.
        """
        if self.TOP not in response.meta:
            self.logger.debug("Reading the %s top categories of %s.", self.name, response.url)
            for request in self._top_requests(response):
                yield request
            return
        if response.meta.get(self.PAGE) == 1:
            self.logger.debug(
                "Requesting the next %s result pages of the category %s.", self.name, response.meta.get(self.TOP)
            )
            for request in self._next_requests(response):
                yield request
        async for item in super().parse(response):
            yield item
