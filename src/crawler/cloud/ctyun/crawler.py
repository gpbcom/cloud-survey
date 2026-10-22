from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from scrapling.parser import Selector
from scrapling.spiders import Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.ctyun.enums import ChinaTelecomHomeTab
from crawler.enums import HtmlAttribute
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

    Notes:
        The main source is the server-rendered https://www.ctyun.cn/products/ page: its `a.link` cards holding a
        `.product-name`, whose `title` attributes hold the full name and description. The product cards of the
        home page complete it. The marketplace offers (`market.ctyun.cn`) are not provider products. No link gets a
        query string, as robots.txt disallows them. Many products only differ by their edition between (fullwidth)
        parentheses, e.g. `云防火墙(原生版)` and `云防火墙`: the edition is kept when comparing names. The names and
        descriptions are in Chinese. The products page files its cards under categories (e.g. `计算`), the home page
        under tabs (e.g. `息壤智算`) paired with their panels by position, the `热门产品` tab excepted: a product gets
        every category of the page it is first streamed from.
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

    name = "ctyun"
    catalogue_url: ClassVar[str] = "https://www.ctyun.cn/products/"
    complement_urls: ClassVar[Tuple[str, ...]] = (HOME_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("天翼云", "中国电信", "eSurfing Cloud ")

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
