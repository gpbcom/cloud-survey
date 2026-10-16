from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Iterator, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from scrapling.parser import Selector
from scrapling.spiders import Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError
from models.cloud.product import CloudProduct


class GigasCrawler(BaseCloudCrawler):
    """Gigas catalogue crawler.

    Attributes:
        ADDONS_URL (ClassVar[str]): The page listing the add-ons of the cloud plans.
        NOT_PRODUCT_GROUP (ClassVar[re.Pattern[str]]): The main menu groups which do not list products.
        ADDON_NAME (ClassVar[re.Pattern[str]]): The product name given between parentheses by an add-on title.
        SPACE_BEFORE_PUNCTUATION (ClassVar[re.Pattern[str]]): The spaces left before a punctuation mark when the
            texts of the emphasized parts of a description are joined.

    Notes:
        The main source is the main menu of the https://gigas.com/en/ home page: its product groups (cloud, security,
        artificial intelligence) list the products (`a.dropdown-item-main`, name and description). The industries,
        company and partners groups are skipped, as well as the category entries (the parent pages of other entries)
        and the add-ons page link. The add-ons page completes it with the add-ons of the cloud plans.
    """

    ADDONS_URL: ClassVar[str] = "https://gigas.com/en/addons-cloud.html"
    NOT_PRODUCT_GROUP: ClassVar[re.Pattern[str]] = re.compile(
        r"industr|about|compan|partner|resource|contact", re.IGNORECASE
    )
    ADDON_NAME: ClassVar[re.Pattern[str]] = re.compile(r"\(([^()]+)\)\s*$")
    SPACE_BEFORE_PUNCTUATION: ClassVar[re.Pattern[str]] = re.compile(r"\s+([.,:!?])")

    name = "gigas"
    catalogue_url: ClassVar[str] = "https://gigas.com/en/"
    complement_urls: ClassVar[Tuple[str, ...]] = (ADDONS_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Gigas ",)

    ############################
    # Internal Helpers Methods #
    ############################

    def _page_path(self, url: str) -> str:
        """Get the path of a website page, without its `.html` extension and trailing slash.

        Args:
            url (str): The absolute page URL.

        Returns:
            str: The page path, e.g. `/en/soluciones` for `https://gigas.com/en/soluciones.html`.
        """
        return urlparse(url).path.removesuffix(".html").rstrip("/").casefold()

    def _menu_links(self, response: Response) -> List[Selector]:
        """Get the entries of the main menu product groups.

        Args:
            response (Response): The home page.

        Returns:
            List[Selector]: The menu entries (`a.dropdown-item-main`) of the product groups.

        Raises:
            CatalogueFormatError: If the page has no main menu.
        """
        groups = response.css("div.dropdown")
        links: List[Selector] = []
        for group in groups:
            toggle = group.css("a.dropdown-toggle").first
            label = self._clean_text(toggle.get_all_text(separator=" ", strip=True)) if toggle is not None else ""
            entries = group.css("a.dropdown-item-main[href]")
            if not entries:
                continue
            if self.NOT_PRODUCT_GROUP.search(label):
                self.logger.debug("Skipping the menu group %r (%d entries), not products.", label, len(entries))
                continue
            self.logger.debug("Menu group %r: %d entries.", label, len(entries))
            links.extend(entries)
        if not links:
            self.logger.error("The %s page %s has no products menu (`a.dropdown-item-main`).", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the products menu is missing")
        return links

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the main menu, skipping the categories and the add-ons page link.

        Args:
            response (Response): The home page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menu.

        Raises:
            CatalogueFormatError: If the page has no main menu.
        """
        links = self._menu_links(response)
        urls = [urljoin(response.url, link.attrib.get("href", "")) for link in links]
        paths: Set[str] = {self._page_path(url) for url in urls}
        listings = {self._url_key(url) for url in self.complement_urls}
        for link, url in zip(links, urls, strict=True):
            title, text = link.css("p").first, link.css("span").first
            name = title.get_all_text(separator=" ", strip=True) if title is not None else None
            prefix = f"{self._page_path(url)}/"
            if self._url_key(url) in listings or any(path.startswith(prefix) for path in paths):
                self.logger.debug("Skipping the menu entry %r (%s), a category or listing page.", name, url)
                continue
            description = text.get_all_text(separator=" ", strip=True) if text is not None else None
            if product := self._build_product(name, description, url):
                yield product

    def _addon_name(self, title: str) -> str:
        """Get the product name of an add-on title, given between parentheses when there are some.

        Args:
            title (str): The add-on title, e.g. `Advanced protection (Firewall)`.

        Returns:
            str: The product name, e.g. `Firewall`.
        """
        match = self.ADDON_NAME.search(title)
        return self._clean_text(match.group(1)) if match else self._clean_text(title)

    def _addons_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the add-ons of the add-ons page: the links holding a title and a description.

        Args:
            response (Response): The add-ons page.

        Yields:
            Iterator[CloudProduct]: Each valid add-on.
        """
        links = response.css("#addons-comp a[href]")
        self.logger.debug("%d links in the add-ons section of %s.", len(links), response.url)
        for link in links:
            title, text = link.css("h3").first, link.css("p").first
            if title is None:
                continue
            description: Optional[str] = None
            if text is not None:
                description = self.SPACE_BEFORE_PUNCTUATION.sub(r"\1", text.get_all_text(separator=" ", strip=True))
            name = self._addon_name(title.get_all_text(separator=" ", strip=True))
            if product := self._build_product(name, description, urljoin(response.url, link.attrib.get("href", ""))):
                yield product

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the main menu or of the add-ons page.

        Args:
            response (Response): The home page or the add-ons page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.

        Raises:
            CatalogueFormatError: If the home page has no main menu.
        """
        if self._url_key(response.url) == self._url_key(self.ADDONS_URL):
            return self._addons_products(response)
        return self._menu_products(response)
