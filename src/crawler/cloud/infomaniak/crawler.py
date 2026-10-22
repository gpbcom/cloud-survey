from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, Iterator, List, Optional, Tuple
from urllib.parse import urljoin

# Third Party Imports.
from scrapling.parser import Selector
from scrapling.spiders import Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.enums import HtmlAttribute
from models.cloud.products.product import CloudProduct


class InfomaniakCrawler(BaseCloudCrawler):
    """Infomaniak catalogue crawler.

    Attributes:
        PRODUCT_LINK (ClassVar[str]): The products menu links (generated CSS module class names, matched by prefix).
        NAME_ELEMENT (ClassVar[str]): The product name element of a menu link.
        DESCRIPTION_ELEMENT (ClassVar[str]): The product description element of a menu link.
        PRODUCTS_NAV (ClassVar[str]): The products menu, listing its groups and, in the same order, their panels.
        GROUP_TITLE (ClassVar[str]): The title of a products menu group.
        GROUP_PANELS (ClassVar[str]): The container of the panels of the products menu groups, one child per group.

    Notes:
        Infomaniak has no catalogue page. The source is the products menu embedded in the
        https://www.infomaniak.com/en home page: every group (collaboration, websites and domains, cloud computing,
        events and marketing, streaming) is read, each link giving a product name, a description and its page. A
        product is filed under the title of its group (e.g. `Cloud Computing`), and under those of every group
        listing it.
    """

    PRODUCT_LINK: ClassVar[str] = '[class*="DisplayProductsLink-module--productsLink--"]'
    NAME_ELEMENT: ClassVar[str] = '[class*="DisplayProductsLink-module--productsLinkContentTitle--"]'
    DESCRIPTION_ELEMENT: ClassVar[str] = '[class*="DisplayProductsLink-module--productsLinkContentDesc--"]'
    PRODUCTS_NAV: ClassVar[str] = '[class*="DisplayProductsNav-module--productsNav--"]'
    GROUP_TITLE: ClassVar[str] = '[class*="DisplayProductsNav-module--productsNavLeftItemTitle--"]'
    GROUP_PANELS: ClassVar[str] = '[class*="DisplayProductsNav-module--productsNavRight--"]'

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

    def _grouped_links(self, response: Response) -> List[Tuple[Selector, Optional[str]]]:
        """List the products menu links with the title of their group.

        Args:
            response (Response): The home page.

        Returns:
            List[Tuple[Selector, Optional[str]]]: Each menu link and its group, `None` when the menu has no groups.

        Notes:
            The menu lists its group titles (left) and, in the same order, one panel of links per group (the
            children of the right side).
        """
        links: List[Tuple[Selector, Optional[str]]] = []
        for nav in response.css(self.PRODUCTS_NAV):
            titles = [
                self._clean_text(title.get_all_text(separator=" ", strip=True)) for title in nav.css(self.GROUP_TITLE)
            ]
            right = nav.css(self.GROUP_PANELS).first
            for index, panel in enumerate(right.children if right is not None else []):
                title = titles[index] if index < len(titles) else None
                links.extend((link, title) for link in panel.css(self.PRODUCT_LINK))
        if not links:
            self.logger.debug("No products menu groups on %s, its products are not categorized.", response.url)
            links = [(link, None) for link in response.css(self.PRODUCT_LINK)]
        return links

    def _menu_entries(self, response: Response) -> List[Tuple[Optional[str], Optional[str], Optional[str], List[str]]]:
        """Gather the products of the menu links with all their groups, a product being listed in several groups.

        Args:
            response (Response): The home page.

        Returns:
            List[Tuple[Optional[str], Optional[str], Optional[str], List[str]]]: The name, description and URL of the
                first link of each product, by order of appearance, and the groups of all its links.

        Notes:
            The links of a product are matched by name or by URL, as the streamed products are.
        """
        links = self._grouped_links(response)
        self.logger.debug("%d products menu links found on %s.", len(links), response.url)
        entries: List[Tuple[Optional[str], Optional[str], Optional[str], List[str]]] = []
        positions: Dict[str, int] = {}
        for link, group in links:
            href = link.attrib.get(HtmlAttribute.HREF)
            url = urljoin(response.url, href) if href else None
            name, description = self._text(link, self.NAME_ELEMENT), self._text(link, self.DESCRIPTION_ELEMENT)
            keys = ([f"name:{self._name_key(name)}"] if name else []) + ([f"url:{self._url_key(url)}"] if url else [])
            position = next((positions[key] for key in keys if key in positions), None)
            if position is None:
                position = len(entries)
                entries.append((name, description, url, []))
            else:
                self.logger.debug("Menu product %r listed again, in the group %r.", name, group)
            if group:
                entries[position][3].append(group)
            positions.update(dict.fromkeys(keys, position))
        return entries

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products menu, filed under their groups.

        Args:
            response (Response): The home page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menu, once.
        """
        for name, description, url, groups in self._menu_entries(response):
            if product := self._build_product(name, description, url, categories=groups):
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
