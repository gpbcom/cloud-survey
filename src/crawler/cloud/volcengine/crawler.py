from __future__ import annotations

# Standard Library Imports.
from typing import AsyncGenerator, ClassVar, Iterator, Optional, Tuple
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from models.cloud.product import CloudProduct


class VolcanoEngineCrawler(BaseCloudCrawler):
    """Volcano Engine (火山引擎) catalogue crawler.

    Attributes:
        PRODUCT_CARDS (ClassVar[str]): The CSS selector of the product card links, waited for in the browser.
        PRODUCT_HOST (ClassVar[str]): The host of the product pages.
        PRODUCT_PATH (ClassVar[str]): The path prefix of the product pages.

    Notes:
        The only source is the product cards of the https://www.volcengine.com/product/list page, rendered by
        JavaScript (the crawler waits for the cards). Their class names end with a generated suffix, e.g.
        `product-card-f4_h`, so they are matched by prefix. Each card is in the page twice. The cards linking to the
        console, the API explorer, the SDKs or the documentation are not products. The query strings (`utm_*`
        tracking, disallowed by robots.txt) are removed from the links. The names and descriptions are in Chinese.
    """

    PRODUCT_CARDS: ClassVar[str] = 'div[class*="product-card-"] > a'
    PRODUCT_HOST: ClassVar[str] = "www.volcengine.com"
    PRODUCT_PATH: ClassVar[str] = "/product/"

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

    def _card_product(self, response: Response, card: Selector) -> Optional[CloudProduct]:
        """Extract the product of a card: its title without the tags (e.g. `公测中`) and its description.

        Args:
            response (Response): The catalogue page.
            card (Selector): The card link.

        Returns:
            Optional[CloudProduct]: The product, `None` when the card is not a valid product.
        """
        title = card.css('[class*="product-title-"]').first
        description = card.css('[class*="product-description-"]').first
        name = self._clean_text(title.text) if title is not None else ""
        href = card.attrib.get("href", "")
        url = self._product_url(response, href)
        if url is None:
            self.logger.debug("Skipping the card %r, %s is not a product page.", name, href)
            return None
        text = description.get_all_text(separator=" ", strip=True) if description is not None else None
        return self._build_product(name, text, url)

    def _catalogue_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the catalogue cards.

        Args:
            response (Response): The catalogue page.

        Yields:
            Iterator[CloudProduct]: Each valid product card, every card being in the page twice.
        """
        cards = response.css(self.PRODUCT_CARDS)
        self.logger.debug("%d product cards in %s.", len(cards), response.url)
        for card in cards:
            if product := self._card_product(response, card):
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
