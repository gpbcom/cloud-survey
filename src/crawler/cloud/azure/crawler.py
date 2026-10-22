from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Iterator, Optional, Tuple
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from scrapling.parser import Selector
from scrapling.spiders import Response

# First Party Imports.
from crawler.cloud.azure.enums import AzureCssClass, AzureHtmlTag, AzureLearnLabel
from crawler.cloud.base import BaseCloudCrawler
from crawler.enums import HtmlAttribute
from models.cloud.products.product import CloudProduct


class AzureCrawler(BaseCloudCrawler):
    """Microsoft Azure catalogue crawler.

    Attributes:
        LEARN_URL (ClassVar[str]): The Microsoft Learn directory of every Azure product documentation.
        LEARN_SECTION_CLASS (ClassVar[AzureCssClass]): The class of the Microsoft Learn directory sections listing the
            products of a category under its `h3` heading.

    Notes:
        The main source is the product cards of the https://azure.microsoft.com/en-us/products/ page (generally
        available products). The Microsoft Learn directory completes it with the products missing from the page.
        Both pages list a product in each of its categories: the products page under the `h2` heading of each
        category, the Microsoft Learn directory in a section per category (besides its flat grid of cards).
        The categories of a product are gathered over the whole page before it is streamed.
    """

    LEARN_URL: ClassVar[str] = "https://learn.microsoft.com/en-us/azure/?product=all"
    LEARN_SECTION_CLASS: ClassVar[AzureCssClass] = AzureCssClass.BOX

    name = "azure"
    catalogue_url: ClassVar[str] = "https://azure.microsoft.com/en-us/products/"
    complement_urls: ClassVar[Tuple[str, ...]] = (LEARN_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Microsoft Azure ", "Azure AI ", "Microsoft ", "Azure ")

    ############################
    # Internal Helpers Methods #
    ############################

    def _products_page_cards(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the product cards of the products page, each with the category heading it is listed under.

        Args:
            response (Response): The products page.

        Yields:
            Iterator[CloudProduct]: Each valid product card, a product being listed in each of its categories.
        """
        elements = response.css("h2, div.content-card-list div.card")
        self.logger.debug("%d headings and product cards in %s.", len(elements), response.url)
        category: Optional[str] = None
        for element in elements:
            if element.tag == AzureHtmlTag.H2:
                category = element.get_all_text(separator=" ", strip=True)
                continue
            heading = element.css(".card-body h3").first
            description = element.css(".card-body [data-oc-token-text] p").first
            if heading is None or description is None:
                self.logger.debug("Skipping a product card without name or description.")
                continue
            link = element.css('a[data-bi-cn="Product"]').first or element.css("a[href]").first
            url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, "")) if link is not None else None
            name = heading.get_all_text(separator=" ", strip=True)
            text = description.get_all_text(separator=" ", strip=True)
            if product := self._build_product(name, text, url, categories=[category]):
                yield product

    def _products_page_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products page, skipping the empty cards.

        Args:
            response (Response): The products page.

        Yields:
            Iterator[CloudProduct]: Each valid product, with the categories of all its cards.
        """
        yield from self._merge_categories(self._products_page_cards(response))

    def _learn_category(self, card: Selector) -> Optional[str]:
        """Get the category of a Microsoft Learn directory card: the heading of the section holding it.

        Args:
            card (Selector): The documentation card.

        Returns:
            Optional[str]: The category, `None` when the card is not in a category section (flat grid).
        """
        for ancestor in card.iterancestors():
            classes = ancestor.attrib.get(HtmlAttribute.CLASS, "").split()
            if ancestor.tag == AzureHtmlTag.DIV and self.LEARN_SECTION_CLASS in classes:
                heading = ancestor.css("h3").first
                return heading.get_all_text(separator=" ", strip=True) if heading is not None else None
        return None

    def _learn_cards(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the cards of the Microsoft Learn directory, skipping the "All ... services" cards.

        Args:
            response (Response): The Microsoft Learn directory.

        Yields:
            Iterator[CloudProduct]: Each valid product card, with the category of its section, if any.
        """
        cards = response.css('div[data-bi-name="product-card"]')
        self.logger.debug("%d documentation cards in %s.", len(cards), response.url)
        for card in cards:
            title = card.css("a.card-title").first
            description = card.css(".card-content-description").first
            if title is None or description is None:
                continue
            name = self._clean_text(title.get_all_text(separator=" ", strip=True))
            if name.casefold().startswith(AzureLearnLabel.ALL_PREFIX):
                self.logger.debug("Skipping the documentation card %r, not a product.", name)
                continue
            url = urljoin(response.url, title.attrib.get(HtmlAttribute.HREF, ""))
            text = description.get_all_text(separator=" ", strip=True)
            if product := self._build_product(name, text, url, categories=[self._learn_category(card)]):
                yield product

    def _learn_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the Microsoft Learn directory.

        Args:
            response (Response): The Microsoft Learn directory.

        Yields:
            Iterator[CloudProduct]: Each valid product, with the categories of all its cards.
        """
        yield from self._merge_categories(self._learn_cards(response))

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
