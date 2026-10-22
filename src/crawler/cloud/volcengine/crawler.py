from __future__ import annotations

# Standard Library Imports.
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.enums import HtmlAttribute
from models.cloud.products.product import CloudProduct


class VolcanoEngineCrawler(BaseCloudCrawler):
    """Volcano Engine (火山引擎) catalogue crawler.

    Attributes:
        PRODUCT_CARDS (ClassVar[str]): The CSS selector of the product card links, waited for in the browser.
        PRODUCT_HOST (ClassVar[str]): The host of the product pages.
        PRODUCT_PATH (ClassVar[str]): The path prefix of the product pages.
        CATEGORY_BLOCKS (ClassVar[str]): The CSS selector of the category blocks (one per tab, in both copies).
        CATEGORY_TITLE (ClassVar[str]): The CSS selector of the category title of a block.
        SUB_CATEGORIES (ClassVar[str]): The CSS selector of the sub-category groups of a block.
        SUB_CATEGORY_TITLE (ClassVar[str]): The CSS selector of the sub-category title of a group.

    Notes:
        The only source is the product cards of the https://www.volcengine.com/product/list page, rendered by
        JavaScript (the crawler waits for the cards). Their class names end with a generated suffix, e.g.
        `product-card-f4_h`, so they are matched by prefix. Each card is in the page twice. The cards linking to the
        console, the API explorer, the SDKs or the documentation are not products. The query strings (`utm_*`
        tracking, disallowed by robots.txt) are removed from the links. The names and descriptions are in Chinese.
        The cards are grouped by category (e.g. `计算`) and sub-category (e.g. `弹性计算`): a product gets the labels
        of every group it is listed in.
    """

    PRODUCT_CARDS: ClassVar[str] = 'div[class*="product-card-"] > a'
    PRODUCT_HOST: ClassVar[str] = "www.volcengine.com"
    PRODUCT_PATH: ClassVar[str] = "/product/"
    CATEGORY_BLOCKS: ClassVar[str] = 'div[class^="block-"]'
    CATEGORY_TITLE: ClassVar[str] = '[class*="tabs-title-"]'
    SUB_CATEGORIES: ClassVar[str] = 'div[class^="secondLevel"]:not([class*="secondLevel-title"])'
    SUB_CATEGORY_TITLE: ClassVar[str] = '[class*="secondLevel-title"]'

    name = "volcengine"
    catalogue_url: ClassVar[str] = "https://www.volcengine.com/product/list"
    name_prefixes: ClassVar[Tuple[str, ...]] = ("火山引擎", "Volcano Engine ")

    ############################
    # Internal Helpers Methods #
    ############################

    def _product_url(self, response: Response, href: str) -> Optional[str]:
        """Get the product page of a card link, without query string nor fragment.

        Args:
            response (Response): The catalogue page, the links being relative to it.
            href (str): The card link.

        Returns:
            Optional[str]: The absolute product page URL, `None` when the link is missing or is not a product page.
        """
        link = urlparse(urljoin(response.url, href.strip()))
        if not href.strip() or link.netloc != self.PRODUCT_HOST or not link.path.startswith(self.PRODUCT_PATH):
            return None
        return link._replace(query="", fragment="").geturl()

    def _title(self, element: Selector, selector: str) -> str:
        """Read the text of the first element matching a CSS selector within an element.

        Args:
            element (Selector): The element.
            selector (str): The CSS selector.

        Returns:
            str: The text, empty when no element matches.
        """
        match = element.css(selector).first
        return self._clean_text(match.get_all_text(separator=" ", strip=True)) if match is not None else ""

    def _card_categories(self, response: Response) -> Dict[str, List[str]]:
        """Gather the category and sub-category labels of the product cards, by product page.

        Args:
            response (Response): The catalogue page.

        Returns:
            Dict[str, List[str]]: The labels of each product page (as cleaned by `_product_url`), in page order.
        """
        categories: Dict[str, List[str]] = {}
        for block in response.css(self.CATEGORY_BLOCKS):
            category = self._title(block, self.CATEGORY_TITLE)
            for group in block.css(self.SUB_CATEGORIES):
                labels = [category, self._title(group, self.SUB_CATEGORY_TITLE)]
                for card in group.css(self.PRODUCT_CARDS):
                    if url := self._product_url(response, card.attrib.get(HtmlAttribute.HREF, "")):
                        categories.setdefault(url, []).extend(labels)
        self.logger.debug("%d categorized product pages in %s.", len(categories), response.url)
        return categories

    def _card_product(
        self, response: Response, card: Selector, categories: Dict[str, List[str]]
    ) -> Optional[CloudProduct]:
        """Extract the product of a card: its title without the tags (e.g. `公测中`) and its description.

        Args:
            response (Response): The catalogue page.
            card (Selector): The card link.
            categories (Dict[str, List[str]]): The category labels of each product page.

        Returns:
            Optional[CloudProduct]: The product, `None` when the card is not a valid product.
        """
        title = card.css('[class*="product-title-"]').first
        description = card.css('[class*="product-description-"]').first
        name = self._clean_text(title.text) if title is not None else ""
        href = card.attrib.get(HtmlAttribute.HREF, "")
        url = self._product_url(response, href)
        if url is None:
            self.logger.debug("Skipping the card %r, %s is not a product page.", name, href)
            return None
        text = description.get_all_text(separator=" ", strip=True) if description is not None else None
        return self._build_product(name, text, url, categories=categories.get(url, []))

    def _catalogue_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the catalogue cards.

        Args:
            response (Response): The catalogue page.

        Yields:
            Iterator[CloudProduct]: Each valid product card, every card being in the page twice.
        """
        cards = response.css(self.PRODUCT_CARDS)
        self.logger.debug("%d product cards in %s.", len(cards), response.url)
        categories = self._card_categories(response)
        for card in cards:
            if product := self._card_product(response, card, categories):
                yield product

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Start the crawl from the catalogue page, waiting for its product cards to be rendered.

        Yields:
            Request: The catalogue page request.
        """
        self.logger.debug("Requesting the %s catalogue page %s.", self.name, self.catalogue_url)
        yield Request(
            self.catalogue_url, priority=self.PRIMARY_PRIORITY, wait_selector=self.PRODUCT_CARDS, network_idle=True
        )

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the catalogue page.

        Args:
            response (Response): The catalogue page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page, duplicates included.
        """
        return self._catalogue_products(response)
