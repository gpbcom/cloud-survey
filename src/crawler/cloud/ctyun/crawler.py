from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Iterator, Optional, Tuple
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from scrapling.parser import Selector
from scrapling.spiders import Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from models.cloud.product import CloudProduct


class ChinaTelecomCloudCrawler(BaseCloudCrawler):
    """China Telecom Cloud (天翼云, eSurfing Cloud) catalogue crawler.

    Attributes:
        HOME_URL (ClassVar[str]): The home page, whose product cards complete the catalogue.
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The links which are not product pages: marketplace offers,
            topics, news and product families.
        PARENTHESES (ClassVar[re.Pattern[str]]): The parentheses (ASCII or fullwidth) around the edition of a product.

    Notes:
        The main source is the server-rendered https://www.ctyun.cn/products/ page: its `a.link` cards holding a
        `.product-name`, whose `title` attributes hold the full name and description. The product cards of the
        home page complete it. The marketplace offers (`market.ctyun.cn`) are not provider products. No link gets a
        query string, as robots.txt disallows them. Many products only differ by their edition between (fullwidth)
        parentheses, e.g. `云防火墙(原生版)` and `云防火墙`: the edition is kept when comparing names. The names and
        descriptions are in Chinese.
    """

    HOME_URL: ClassVar[str] = "https://www.ctyun.cn/"
    NOT_PRODUCT_LINK: ClassVar[re.Pattern[str]] = re.compile(
        r"market\.ctyun\.cn|/products/topic/|/products/news|/products/poly-", re.IGNORECASE
    )
    PARENTHESES: ClassVar[re.Pattern[str]] = re.compile(r"[()\uff08\uff09]")

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
        return element.attrib.get("title") or element.get_all_text(separator=" ", strip=True)

    def _card_product(
        self, response: Response, card: Selector, name: Optional[str], description: Optional[str]
    ) -> Optional[CloudProduct]:
        """Build the product of a card, unless its link is not a product page.

        Args:
            response (Response): The page of the card, its link being relative to it.
            card (Selector): The card link.
            name (Optional[str]): The product name.
            description (Optional[str]): The product description.

        Returns:
            Optional[CloudProduct]: The product, `None` for a marketplace, topic or news link, or an invalid card.
        """
        href = card.attrib.get("href", "").strip()
        if self.NOT_PRODUCT_LINK.search(href):
            self.logger.debug("Skipping the card %r, %s is not a product page.", name, href)
            return None
        return self._build_product(name, description, urljoin(response.url, href) if href else None)

    def _catalogue_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products page: the `a.link` cards holding a product name.

        Args:
            response (Response): The products page.

        Yields:
            Iterator[CloudProduct]: Each valid product card.
        """
        cards = [card for card in response.css("a.link") if card.css(".product-name").first is not None]
        self.logger.debug("%d product cards in %s.", len(cards), response.url)
        for card in cards:
            name = self._text(card.css(".product-name").first)
            if product := self._card_product(response, card, name, self._text(card.css(".product-note").first)):
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
        for card in cards:
            name = self._text(card.css(".product-card__title").first)
            description = self._text(card.css(".product-card__intro").first)
            if product := self._card_product(response, card, name, description):
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
