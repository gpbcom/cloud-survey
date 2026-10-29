from __future__ import annotations

# Standard Library Imports.
import re
from pathlib import Path
from typing import ClassVar, Dict, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from scrapling.parser import Selector
from scrapling.spiders import Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.gigas.enums import GigasMenuMarkup
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel
from models.cloud.products.product import CloudProduct


class GigasCrawler(BaseCloudCrawler):
    """Gigas catalogue crawler.

    Attributes:
        ADDONS_URL (ClassVar[str]): The page listing the add-ons of the cloud plans.
        NOT_PRODUCT_GROUP (ClassVar[re.Pattern[str]]): The main menu groups which do not list products.
        ADDON_NAME (ClassVar[re.Pattern[str]]): The product name given between parentheses by an add-on title.
        SPACE_BEFORE_PUNCTUATION (ClassVar[re.Pattern[str]]): The spaces left before a punctuation mark when the
            texts of the emphasized parts of a description are joined.
        SEGMENT (ClassVar[GigasMenuMarkup]): The class of the heading (a link or a label) of a menu column.
        listing_categories (Dict[str, List[str]]): The menu categories of the listing pages linked by the menu (the
            add-ons page), by normalized URL, given to the products they list.
        UNPRICED_REASON (ClassVar[Optional[str]]): Why the provider has no public price.
        UNPRICED_MODEL (ClassVar[PriceModel]): How its products are priced (on request).

    Notes:
        The main source is the main menu of the https://gigas.com/en/ home page: its product groups (cloud, security,
        artificial intelligence) list the products (`a.dropdown-item-main`, name and description). The industries,
        company and partners groups are skipped, as well as the category entries (the parent pages of other entries)
        and the add-ons page link. The add-ons page completes it with the add-ons of the cloud plans.
        The catalogue categories of a menu product are its menu group (e.g. `Cloud`), then the heading of its menu
        column (e.g. `Solutions`), unless it is that heading. Those of an add-on are the menu group and the label of
        the add-ons page link (`Cloud`, `Cloud Addons`), when the menu was read first.
        Gigas publishes no price: in price mode its home page is read as the evidence, and each live product is
        priced on request (a quote).
    """

    ADDONS_URL: ClassVar[str] = "https://gigas.com/en/addons-cloud.html"
    NOT_PRODUCT_GROUP: ClassVar[re.Pattern[str]] = re.compile(
        r"industr|about|compan|partner|resource|contact", re.IGNORECASE
    )
    ADDON_NAME: ClassVar[re.Pattern[str]] = re.compile(r"\(([^()]+)\)\s*$")
    SPACE_BEFORE_PUNCTUATION: ClassVar[re.Pattern[str]] = re.compile(r"\s+([.,:!?])")
    SEGMENT: ClassVar[GigasMenuMarkup] = GigasMenuMarkup.SEGMENT

    UNPRICED_REASON: ClassVar[Optional[str]] = (
        "Gigas publishes no price: its cloud services are quoted on request (contact sales)."
    )
    UNPRICED_MODEL: ClassVar[PriceModel] = PriceModel.QUOTE

    name = "gigas"
    catalogue_url: ClassVar[str] = "https://gigas.com/en/"
    complement_urls: ClassVar[Tuple[str, ...]] = (ADDONS_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Gigas ",)

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.listing_categories: Dict[str, List[str]] = {}

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

    def _menu_links(self, response: Response) -> List[Tuple[Selector, str]]:
        """Get the entries of the main menu product groups.

        Args:
            response (Response): The home page.

        Returns:
            List[Tuple[Selector, str]]: The menu entries (`a.dropdown-item-main`) of the product groups, with the
                label of their group (empty when the group has none).

        Raises:
            CatalogueFormatError: If the page has no main menu.
        """
        groups = response.css("div.dropdown")
        links: List[Tuple[Selector, str]] = []
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
            links.extend((entry, label) for entry in entries)
        if not links:
            self.logger.error("The %s page %s has no products menu (`a.dropdown-item-main`).", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the products menu is missing")
        return links

    def _segment(self, link: Selector) -> Optional[str]:
        """Read the heading of the menu column of a menu entry, unless the entry is that heading.

        Args:
            link (Selector): The menu entry.

        Returns:
            Optional[str]: The column heading, e.g. `Solutions`, `None` when the column has none.
        """
        if self.SEGMENT in link.attrib.get(HtmlAttribute.CLASS, "").split() or link.parent is None:
            return None
        segment = link.parent.css(f":scope > .{self.SEGMENT}").first
        if segment is None:
            return None
        title = segment.css("p").first if segment.tag == GigasMenuMarkup.LINK else segment
        return self._clean_text(title.get_all_text(separator=" ", strip=True)) if title is not None else None

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
        urls = [urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, "")) for link, _ in links]
        paths: Set[str] = {self._page_path(url) for url in urls}
        listings = {self._url_key(url) for url in self.complement_urls}
        for (link, group), url in zip(links, urls, strict=True):
            title, text = link.css("p").first, link.css("span").first
            name = title.get_all_text(separator=" ", strip=True) if title is not None else None
            prefix = f"{self._page_path(url)}/"
            if self._url_key(url) in listings:
                self.logger.debug("Skipping the menu entry %r (%s), a listing page.", name, url)
                self.listing_categories[self._url_key(url)] = [group, self._clean_text(name)]
                continue
            if any(path.startswith(prefix) for path in paths):
                self.logger.debug("Skipping the menu entry %r (%s), a category page.", name, url)
                continue
            description = text.get_all_text(separator=" ", strip=True) if text is not None else None
            if product := self._build_product(name, description, url, categories=[group, self._segment(link)]):
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
        categories = self.listing_categories.get(self._url_key(response.url), [])
        self.logger.debug("%d links in the add-ons section of %s (%s).", len(links), response.url, categories)
        for link in links:
            title, text = link.css("h3").first, link.css("p").first
            if title is None:
                continue
            description: Optional[str] = None
            if text is not None:
                description = self.SPACE_BEFORE_PUNCTUATION.sub(r"\1", text.get_all_text(separator=" ", strip=True))
            name = self._addon_name(title.get_all_text(separator=" ", strip=True))
            url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, ""))
            if product := self._build_product(name, description, url, categories=categories):
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
