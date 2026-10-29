from __future__ import annotations

# Standard Library Imports.
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.ctyun.enums import (
    ChinaTelecomDynamicCode,
    ChinaTelecomDynamicField,
    ChinaTelecomDynamicObject,
    ChinaTelecomDynamicParameter,
    ChinaTelecomDynamicType,
    ChinaTelecomHomeTab,
)
from crawler.enums import HtmlAttribute
from models.cloud.enums import DateCaveat, PriceModel
from models.cloud.products.product import CloudProduct


class ChinaTelecomCloudCrawler(BaseCloudCrawler):
    """China Telecom Cloud (天翼云, eSurfing Cloud) catalogue crawler.

    Attributes:
        HOME_URL (ClassVar[str]): The home page, whose product cards complete the catalogue.
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The links which are not product pages: marketplace offers,
            topics, news and product families.
        PARENTHESES (ClassVar[re.Pattern[str]]): The parentheses (ASCII or fullwidth) around the edition of a product.
        CATALOGUE_SECTIONS (ClassVar[str]): The CSS selector of the category sections of the products page.
        CATALOGUE_SECTION_TITLE (ClassVar[str]): The CSS selector of the category title of a section.
        HOME_WRAPPERS (ClassVar[str]): The CSS selector of the home page sections, one of them holding the product tabs.
        HOME_TABS (ClassVar[str]): The CSS selector of the tab titles of a home page section.
        HOME_PANELS (ClassVar[str]): The CSS selector of the product panels of a home page section, one per tab.
        MARKETING_TABS (ClassVar[FrozenSet[ChinaTelecomHomeTab]]): The home page tabs which are not categories.
        DYNAMIC_URL (ClassVar[str]): The product updates API (产品动态), listing the dated updates of a documentation
            book (JSON).
        BOOK_LINKS (ClassVar[str]): The CSS selector of the documentation links of a product page.
        BOOK_ID (ClassVar[re.Pattern[str]]): The documentation book identifier of a documentation link, 8 digits.
        MIN_BOOK_LINKS (ClassVar[int]): From how many links a book is the product's own: the site-wide menus link a
            few other books once or twice per page.
        NOT_FOUND_TITLE (ClassVar[re.Pattern[str]]): The title of the page served for a missing page (`404页面`).
        RELEASE_DATE_FORMAT (ClassVar[str]): The format of the update release dates, e.g. `2019-09-19`.
        dates_launches (ClassVar[bool]): The launch of each product is read from its product updates.
        launch_feed_start (ClassVar[Optional[datetime]]): The first months of the product updates, whose earliest
            entries may postdate the launch of the products already offered then.
        UNPRICED_REASON (ClassVar[Optional[str]]): Why the provider has no public price.
        UNPRICED_MODEL (ClassVar[PriceModel]): How its products are priced (not published).

    Notes:
        The main source is the server-rendered https://www.ctyun.cn/products/ page: its `a.link` cards holding a
        `.product-name`, whose `title` attributes hold the full name and description. The product cards of the
        home page complete it. The marketplace offers (`market.ctyun.cn`) are not provider products. No link gets a
        query string, as robots.txt disallows them. Many products only differ by their edition between (fullwidth)
        parentheses, e.g. `云防火墙(原生版)` and `云防火墙`: the edition is kept when comparing names. The names and
        descriptions are in Chinese. The products page files its cards under categories (e.g. `计算`), the home page
        under tabs (e.g. `息壤智算`) paired with their panels by position, the `热门产品` tab excepted: a product gets
        every category of the page it is first streamed from.
        The catalogue dates no product: each product is dated (`dates_launches`) by its product updates (产品动态),
        listed by the `DYNAMIC_URL` API for the documentation book of the product. The book is the one most linked by
        the product page (`/document/<bookId>/...`), at least `MIN_BOOK_LINKS` times. The launch is the earliest
        launch update (type `1`, e.g. `分布式消息服务MQTT推广使用`), else the earliest update. A missing product page is
        served with HTTP 404 or as a `404页面` page, and an unknown book with no update: neither dates the product.
        The updates before `launch_feed_start` are qualified `FEED_START`.
        China Telecom Cloud shows its prices to signed-in customers only: in price mode its products page is read as
        the evidence, and each live product is stated not public.
    """

    HOME_URL: ClassVar[str] = "https://www.ctyun.cn/"
    NOT_PRODUCT_LINK: ClassVar[re.Pattern[str]] = re.compile(
        r"market\.ctyun\.cn|/products/topic/|/products/news|/products/poly-", re.IGNORECASE
    )
    PARENTHESES: ClassVar[re.Pattern[str]] = re.compile(r"[()\uff08\uff09]")
    CATALOGUE_SECTIONS: ClassVar[str] = "section.list"
    CATALOGUE_SECTION_TITLE: ClassVar[str] = ".title .name"
    HOME_WRAPPERS: ClassVar[str] = "div.ctdp-section-wrapper__main"
    HOME_TABS: ClassVar[str] = ".newHomeTab .tabItems span"
    HOME_PANELS: ClassVar[str] = "div.productSection"
    MARKETING_TABS: ClassVar[FrozenSet[ChinaTelecomHomeTab]] = frozenset({ChinaTelecomHomeTab.POPULAR_PRODUCTS})
    DYNAMIC_URL: ClassVar[str] = "https://www.ctyun.cn/v1/portal/product/dynamic/Get"
    BOOK_LINKS: ClassVar[str] = 'a[href*="/document/"]'
    BOOK_ID: ClassVar[re.Pattern[str]] = re.compile(r"/document/(\d{8})(?:[/?#]|$)")
    MIN_BOOK_LINKS: ClassVar[int] = 3
    NOT_FOUND_TITLE: ClassVar[re.Pattern[str]] = re.compile(r"^\s*404")
    RELEASE_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    UNPRICED_REASON: ClassVar[Optional[str]] = (
        "China Telecom Cloud shows its prices to signed-in customers only (its price calculator needs a login)."
    )
    UNPRICED_MODEL: ClassVar[PriceModel] = PriceModel.NOT_PUBLIC

    name = "ctyun"
    catalogue_url: ClassVar[str] = "https://www.ctyun.cn/products/"
    complement_urls: ClassVar[Tuple[str, ...]] = (HOME_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("天翼云", "中国电信", "eSurfing Cloud ")
    dates_launches: ClassVar[bool] = True
    launch_feed_start: ClassVar[Optional[datetime]] = datetime(2020, 6, 1, tzinfo=UTC)

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)

    ############################
    # Internal Helpers Methods #
    ############################

    def _name_key(self, name: str) -> str:
        """Normalize a product name to compare it, keeping its edition between parentheses.

        Args:
            name (str): The product name, e.g. `云防火墙(原生版)`.

        Returns:
            str: The comparison key, e.g. `云防火墙原生版`, distinct from the `云防火墙` one.
        """
        return super()._name_key(self.PARENTHESES.sub(" ", name))

    def _text(self, element: Optional[Selector]) -> Optional[str]:
        """Read the text of a card element: its `title` attribute (the untruncated text), else its content.

        Args:
            element (Optional[Selector]): The card element.

        Returns:
            Optional[str]: The text, `None` when the element is missing.
        """
        if element is None:
            return None
        return element.attrib.get(HtmlAttribute.TITLE) or element.get_all_text(separator=" ", strip=True)

    def _catalogue_name(self, card: Selector) -> Optional[str]:
        """Read the product name of a products page card.

        Args:
            card (Selector): The card link.

        Returns:
            Optional[str]: The product name, `None` when the card has none.
        """
        return self._text(card.css(".product-name").first)

    def _home_name(self, card: Selector) -> Optional[str]:
        """Read the product name of a home page card.

        Args:
            card (Selector): The card link.

        Returns:
            Optional[str]: The product name, `None` when the card has none.
        """
        return self._text(card.css(".product-card__title").first)

    def _catalogue_categories(self, response: Response) -> Dict[str, List[str]]:
        """Gather the categories of the products page cards, by product name (`_name_key`).

        Args:
            response (Response): The products page.

        Returns:
            Dict[str, List[str]]: The categories of each product, in page order.
        """
        categories: Dict[str, List[str]] = {}
        for section in response.css(self.CATALOGUE_SECTIONS):
            category = self._clean_text(self._text(section.css(self.CATALOGUE_SECTION_TITLE).first))
            for card in section.css("a.link"):
                name = self._clean_text(self._catalogue_name(card))
                if name:
                    categories.setdefault(self._name_key(name), []).append(category)
        self.logger.debug("%d categorized products in %s.", len(categories), response.url)
        return categories

    def _home_categories(self, response: Response) -> Dict[str, List[str]]:
        """Gather the tabs of the home page cards, by product name (`_name_key`).

        Args:
            response (Response): The home page.

        Returns:
            Dict[str, List[str]]: The tabs of each product, in page order, the marketing tabs excepted.
        """
        categories: Dict[str, List[str]] = {}
        for wrapper in response.css(self.HOME_WRAPPERS):
            tabs, panels = wrapper.css(self.HOME_TABS), wrapper.css(self.HOME_PANELS)
            if not panels:
                continue
            if len(tabs) != len(panels):
                self.logger.warning(
                    "The %s home page %s has %d product tabs for %d panels, their categories are ignored.",
                    self.name,
                    response.url,
                    len(tabs),
                    len(panels),
                )
                continue
            for tab, panel in zip(tabs, panels, strict=True):
                category = self._clean_text(tab.get_all_text(separator=" ", strip=True))
                if category in self.MARKETING_TABS:
                    continue
                for card in panel.css("a.product-card"):
                    name = self._clean_text(self._home_name(card))
                    if name:
                        categories.setdefault(self._name_key(name), []).append(category)
        self.logger.debug("%d categorized home page products in %s.", len(categories), response.url)
        return categories

    def _card_product(
        self,
        response: Response,
        card: Selector,
        name: Optional[str],
        description: Optional[str],
        categories: Dict[str, List[str]],
    ) -> Optional[CloudProduct]:
        """Build the product of a card, unless its link is not a product page.

        Args:
            response (Response): The page of the card, its link being relative to it.
            card (Selector): The card link.
            name (Optional[str]): The product name.
            description (Optional[str]): The product description.
            categories (Dict[str, List[str]]): The categories of each product of the page, by `_name_key`.

        Returns:
            Optional[CloudProduct]: The product, `None` for a marketplace, topic or news link, or an invalid card.
        """
        href = card.attrib.get(HtmlAttribute.HREF, "").strip()
        if self.NOT_PRODUCT_LINK.search(href):
            self.logger.debug("Skipping the card %r, %s is not a product page.", name, href)
            return None
        return self._build_product(
            name,
            description,
            urljoin(response.url, href) if href else None,
            categories=categories.get(self._name_key(self._clean_text(name)), []),
        )

    def _catalogue_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products page: the `a.link` cards holding a product name.

        Args:
            response (Response): The products page.

        Yields:
            Iterator[CloudProduct]: Each valid product card.
        """
        cards = [card for card in response.css("a.link") if card.css(".product-name").first is not None]
        self.logger.debug("%d product cards in %s.", len(cards), response.url)
        categories = self._catalogue_categories(response)
        for card in cards:
            description = self._text(card.css(".product-note").first)
            if product := self._card_product(response, card, self._catalogue_name(card), description, categories):
                yield product

    def _home_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the home page cards.

        Args:
            response (Response): The home page.

        Yields:
            Iterator[CloudProduct]: Each valid product card.
        """
        cards = response.css("a.product-card")
        self.logger.debug("%d home page product cards in %s.", len(cards), response.url)
        categories = self._home_categories(response)
        for card in cards:
            description = self._text(card.css(".product-card__intro").first)
            if product := self._card_product(response, card, self._home_name(card), description, categories):
                yield product

    def _book_id(self, response: Response) -> Optional[str]:
        """Find the documentation book of a product: the one its product page links the most.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The book identifier, e.g. `10005536`, `None` for a missing page (`404页面`) or a page
                linking no book at least `MIN_BOOK_LINKS` times.
        """
        if self.NOT_FOUND_TITLE.search(response.css("title::text").get() or ""):
            self.logger.debug("The %s product page %s is missing.", self.name, response.url)
            return None
        links = (link.attrib.get(HtmlAttribute.HREF, "") for link in response.css(self.BOOK_LINKS))
        books = Counter(match.group(1) for match in (self.BOOK_ID.search(href) for href in links) if match)
        book, count = books.most_common(1)[0] if books else (None, 0)
        if book is None or count < self.MIN_BOOK_LINKS:
            self.logger.debug("The %s product page %s links no documentation book.", self.name, response.url)
            return None
        self.logger.debug(
            "The %s product page %s documents the book %s (%d links).", self.name, response.url, book, count
        )
        return book

    def _release_date(self, text: JsonValue) -> Optional[datetime]:
        """Parse the release date of a product update.

        Args:
            text (JsonValue): The release date, e.g. `2019-09-19`.

        Returns:
            Optional[datetime]: The date in UTC, `None` when unreadable or implausible.
        """
        if not isinstance(text, str):
            return None
        try:
            parsed = datetime.strptime(text.strip(), self.RELEASE_DATE_FORMAT).replace(tzinfo=UTC)
        except ValueError:
            return None
        return parsed if self.EARLIEST_DATE <= parsed <= datetime.now(UTC) else None

    def _first_update(self, payload: JsonValue, book: str) -> Optional[datetime]:
        """Read the launch of a product from the updates of its documentation book.

        Args:
            payload (JsonValue): The product updates API response.
            book (str): The documentation book identifier.

        Returns:
            Optional[datetime]: The earliest launch update, else the earliest update, `None` when the book has no
                readable update or the call failed.
        """
        if not isinstance(payload, dict) or payload.get(ChinaTelecomDynamicField.CODE) != ChinaTelecomDynamicCode.OK:
            self.logger.debug("The %s product updates of the book %s cannot be read.", self.name, book)
            return None
        updates = payload.get(ChinaTelecomDynamicField.LIST)
        launches: List[datetime] = []
        dates: List[datetime] = []
        for update in updates if isinstance(updates, list) else []:
            if not isinstance(update, dict):
                continue
            date = self._release_date(update.get(ChinaTelecomDynamicField.RELEASE_DATE))
            if date is None:
                continue
            dates.append(date)
            if update.get(ChinaTelecomDynamicField.TYPE) == ChinaTelecomDynamicType.LAUNCH:
                self.logger.debug("Launch update of the book %s: %r.", book, update.get(ChinaTelecomDynamicField.TITLE))
                launches.append(date)
        if not dates:
            self.logger.debug("No dated %s product update for the book %s.", self.name, book)
            return None
        return min(launches or dates)

    async def _launch_source(self, product: CloudProduct) -> Optional[Tuple[datetime, DateCaveat]]:
        """Read the launch of a product from the product updates of the documentation book of its product page.

        Args:
            product (CloudProduct): The product, undated.

        Returns:
            Optional[Tuple[datetime, DateCaveat]]: The launch and its caveat, `None` when the product has no product
                page, its page links no documentation book, or the book has no dated update.

        Raises:
            CatalogueFormatError: If the product updates API answer is not JSON.
        """
        page = await self._fetch_launch_page(product.url) if product.url else None
        book = self._book_id(page) if page is not None else None
        if book is None:
            return None
        params: Dict[str, str] = {
            ChinaTelecomDynamicParameter.OBJECT_TYPE: ChinaTelecomDynamicObject.BOOK,
            ChinaTelecomDynamicParameter.OBJECT_ID: book,
        }
        response = await self._fetch_launch_page(self.DYNAMIC_URL, params=params)
        launched = self._first_update(self._json_body(response), book) if response is not None else None
        if launched is None:
            return None
        self.logger.debug("%r first updated in the book %s on %s.", product.name, book, launched.date())
        return self._announced(launched)

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products page or of the home page.

        Args:
            response (Response): The catalogue page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page, duplicates included.
        """
        if urlparse(response.url).path.strip("/") == "":
            return self._home_products(response)
        return self._catalogue_products(response)
