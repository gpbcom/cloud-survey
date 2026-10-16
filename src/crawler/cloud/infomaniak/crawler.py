from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Iterator, Optional, Tuple
from urllib.parse import urljoin

# Third Party Imports.
from scrapling.parser import Selector
from scrapling.spiders import Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from models.cloud.product import CloudProduct


class InfomaniakCrawler(BaseCloudCrawler):
    """Infomaniak catalogue crawler.

    Attributes:
        PRODUCT_LINK (ClassVar[str]): The products menu links (generated CSS module class names, matched by prefix).
        NAME_ELEMENT (ClassVar[str]): The product name element of a menu link.
        DESCRIPTION_ELEMENT (ClassVar[str]): The product description element of a menu link.

    Notes:
        Infomaniak has no catalogue page. The source is the products menu embedded in the
        https://www.infomaniak.com/en home page: every group (collaboration, websites and domains, cloud computing,
        events and marketing, streaming) is read, each link giving a product name, a description and its page.
    """

    PRODUCT_LINK: ClassVar[str] = '[class*="DisplayProductsLink-module--productsLink--"]'
    NAME_ELEMENT: ClassVar[str] = '[class*="DisplayProductsLink-module--productsLinkContentTitle--"]'
    DESCRIPTION_ELEMENT: ClassVar[str] = '[class*="DisplayProductsLink-module--productsLinkContentDesc--"]'

    name = "infomaniak"
    catalogue_url: ClassVar[str] = "https://www.infomaniak.com/en"
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Infomaniak ",)

    ############################
    # Internal Helpers Methods #
    ############################

    def _text(self, link: Selector, selector: str) -> Optional[str]:
        """Read the text of the first element of a menu link matching a selector.

        Args:
            link (Selector): The menu link.
            selector (str): The CSS selector of the element.

        Returns:
            Optional[str]: The element text, `None` when the link has no such element.
        """
        element = link.css(selector).first
        return element.get_all_text(separator=" ", strip=True) if element is not None else None

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products menu.

        Args:
            response (Response): The home page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menu.
        """
        links = response.css(self.PRODUCT_LINK)
        self.logger.debug("%d products menu links found on %s.", len(links), response.url)
        for link in links:
            href = link.attrib.get("href")
            name, description = self._text(link, self.NAME_ELEMENT), self._text(link, self.DESCRIPTION_ELEMENT)
            if product := self._build_product(name, description, urljoin(response.url, href) if href else None):
                yield product

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products menu.

        Args:
            response (Response): The home page.

        Returns:
            Iterator[CloudProduct]: The valid products of the menu.
        """
        return self._menu_products(response)
