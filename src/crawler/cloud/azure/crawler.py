from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Iterator, Tuple
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from scrapling.spiders import Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from models.cloud.product import CloudProduct


class AzureCrawler(BaseCloudCrawler):
    """Microsoft Azure catalogue crawler.

    Attributes:
        LEARN_URL (ClassVar[str]): The Microsoft Learn directory of every Azure product documentation.

    Notes:
        The main source is the product cards of the https://azure.microsoft.com/en-us/products/ page (generally
        available products). The Microsoft Learn directory completes it with the products missing from the page.
    """

    LEARN_URL: ClassVar[str] = "https://learn.microsoft.com/en-us/azure/?product=all"

    name = "azure"
    catalogue_url: ClassVar[str] = "https://azure.microsoft.com/en-us/products/"
    complement_urls: ClassVar[Tuple[str, ...]] = (LEARN_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Microsoft Azure ", "Azure AI ", "Microsoft ", "Azure ")

    ############################
    # Internal Helpers Methods #
    ############################

    def _products_page_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products page, skipping the empty cards.

        Args:
            response (Response): The products page.

        Yields:
            Iterator[CloudProduct]: Each valid product card, a product being listed in each of its categories.
        """
        cards = response.css("div.content-card-list div.card")
        self.logger.debug("%d product cards in %s.", len(cards), response.url)
        for card in cards:
            heading = card.css(".card-body h3").first
            description = card.css(".card-body [data-oc-token-text] p").first
            if heading is None or description is None:
                self.logger.debug("Skipping a product card without name or description.")
                continue
            link = card.css('a[data-bi-cn="Product"]').first or card.css("a[href]").first
            url = urljoin(response.url, link.attrib.get("href", "")) if link is not None else None
            name = heading.get_all_text(separator=" ", strip=True)
            if product := self._build_product(name, description.get_all_text(separator=" ", strip=True), url):
                yield product

    def _learn_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the Microsoft Learn directory, skipping the "All ... services" cards.

        Args:
            response (Response): The Microsoft Learn directory.

        Yields:
            Iterator[CloudProduct]: Each valid product card.
        """
        cards = response.css('div[data-bi-name="product-card"]')
        self.logger.debug("%d documentation cards in %s.", len(cards), response.url)
        for card in cards:
            title = card.css("a.card-title").first
            description = card.css(".card-content-description").first
            if title is None or description is None:
                continue
            name = self._clean_text(title.get_all_text(separator=" ", strip=True))
            if name.casefold().startswith("all "):
                self.logger.debug("Skipping the documentation card %r, not a product.", name)
                continue
            url = urljoin(response.url, title.attrib.get("href", ""))
            if product := self._build_product(name, description.get_all_text(separator=" ", strip=True), url):
                yield product

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products page or of the Microsoft Learn directory.

        Args:
            response (Response): The catalogue page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.
        """
        if urlparse(response.url).netloc == urlparse(self.LEARN_URL).netloc:
            return self._learn_products(response)
        return self._products_page_products(response)
