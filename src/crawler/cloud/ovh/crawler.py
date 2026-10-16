from __future__ import annotations

# Standard Library Imports.
import re
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError
from models.cloud.product import CloudProduct


class OVHcloudCrawler(BaseCloudCrawler):
    """OVHcloud catalogue crawler.

    Attributes:
        SITEMAP_URL (ClassVar[str]): The sitemap of the website, listing the product pages.
        NOT_PRODUCT_LABEL (ClassVar[re.Pattern[str]]): The menu labels which are links, not products.
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The menu links to use cases, guides and documentation.
        SITEMAP_PRODUCT_PAGE (ClassVar[re.Pattern[str]]): The sitemap pages of the product universes.
        SITEMAP_NOT_PRODUCT (ClassVar[re.Pattern[str]]): The sitemap pages which are not product pages.
        LOCALE (ClassVar[re.Pattern[str]]): The locale segment of the website paths, e.g. `/en-gb/`.
        category_urls (Set[str]): The URL keys of the menu categories, whose pages are not product pages.

    Notes:
        OVHcloud has no catalogue page. The main source is the products menu embedded in every page (Next.js
        data, `props.pageProps.itemsDesktop`): a tree of universes, columns and groups whose leaves are products,
        once the categories, the use cases, the "About us" section and the "coming soon" entries are filtered out.
        The sitemap completes it with the product pages missing from the menu, dated by their sitemap last
        modification (`lastmod`). The menu products are undated.
    """

    SITEMAP_URL: ClassVar[str] = "https://www.ovhcloud.com/en/www.ovhcloud.com_en_sitemap.xml"
    NOT_PRODUCT_LABEL: ClassVar[re.Pattern[str]] = re.compile(
        r"^(all |compare |see the |search for |renew |transfer |how do i|create |host your|what is )", re.IGNORECASE
    )
    NOT_PRODUCT_LINK: ClassVar[re.Pattern[str]] = re.compile(
        r"/use-cases/|/uc-|use-cases-|docs\.ovhcloud\.com|/learn/|/architecture-center/", re.IGNORECASE
    )
    SITEMAP_PRODUCT_PAGE: ClassVar[re.Pattern[str]] = re.compile(
        r"^https://www\.ovhcloud\.com/[a-z]{2}(-[a-z]{2})?/(public-cloud|hosted-private-cloud|storage-solutions|"
        r"network|security|identity-security-operations|emails|public-vcf-aas)/[^?#]+$"
    )
    SITEMAP_NOT_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(
        r"uc-|use-case|price|pricing|configurator|faq|free-|journey-|what-|why-|how-|interview|options|classes|"
        r"config/|definition|choosing|technical-overview|services-included|safety|security-features|partnership|"
        r"migration|create-|comparison|compare|regions|availability|architecture|management-interfaces|"
        r"project-management|discover|partners|applications-services",
        re.IGNORECASE,
    )
    LOCALE: ClassVar[re.Pattern[str]] = re.compile(r"^/[a-z]{2}(-[a-z]{2})?(?=/)")

    name = "ovhcloud"
    catalogue_url: ClassVar[str] = "https://www.ovhcloud.com/en-gb/public-cloud/"
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("OVHcloud ",)

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.category_urls: Set[str] = set()

    ############################
    # Internal Helpers Methods #
    ############################

    def _url_key(self, url: str) -> str:
        """Compare the website pages whatever their locale (`/en/` and `/en-gb/` pages are the same product).

        Args:
            url (str): The absolute product URL.

        Returns:
            str: The generic URL key, without the locale segment.
        """
        link = urlparse(url.casefold())
        return f"{link.netloc.removeprefix('www.')}{self.LOCALE.sub('', link.path).rstrip('/')}"

    def _menu(self, response: Response) -> Dict[str, JsonValue]:
        """Read the products menu embedded in a page.

        Args:
            response (Response): A page of the website.

        Returns:
            Dict[str, JsonValue]: The menu, by universe.

        Raises:
            CatalogueFormatError: If the page has no products menu.
        """
        data = self._next_data(response)
        menu = self._as_object(self._as_object(self._as_object(data.get("props")).get("pageProps")).get("itemsDesktop"))
        if not menu:
            self.logger.error("The %s page %s has no products menu.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the products menu (`itemsDesktop`) is missing")
        self.logger.debug("Products menu of %s found, with the universes %s.", response.url, ", ".join(menu))
        return menu

    def _categories(self, menu: Dict[str, JsonValue]) -> Tuple[Set[str], Set[str]]:
        """Get the labels and links of the menu categories: the top level entries holding products.

        Args:
            menu (Dict[str, JsonValue]): The menu, by universe.

        Returns:
            Tuple[Set[str], Set[str]]: The category labels (case-insensitive) and URL keys.
        """
        labels: Set[str] = set()
        links: Set[str] = set()
        for node in self._walk_objects(menu):
            if node.get("level") == 1 and node.get("children"):
                labels.add(self._clean_text(self._as_text(node.get("label"))).casefold())
                if link := self._as_text(node.get("link")):
                    links.add(self._url_key(link))
        return labels, links

    def _leaves(
        self, value: JsonValue, top: Optional[Dict[str, JsonValue]] = None
    ) -> Iterator[Tuple[Dict[str, JsonValue], Dict[str, JsonValue]]]:
        """Walk the menu entries without children, with their top level entry.

        Args:
            value (JsonValue): A menu (sub)tree.
            top (Optional[Dict[str, JsonValue]]): The top level entry of the subtree, if already reached.

        Yields:
            Tuple[Dict[str, JsonValue], Dict[str, JsonValue]]: Each leaf and its top level entry.
        """
        if isinstance(value, list):
            for child in value:
                yield from self._leaves(child, top)
            return
        if not isinstance(value, dict):
            return
        if "level" not in value:
            for child in value.values():
                yield from self._leaves(child, top)
            return
        top = top if top is not None else value
        children = value.get("children")
        if children:
            yield from self._leaves(children, top)
        else:
            yield value, top

    def _is_product_leaf(
        self,
        leaf: Dict[str, JsonValue],
        top: Dict[str, JsonValue],
        universe: str,
        categories: Tuple[Set[str], Set[str]],
    ) -> bool:
        """Tell whether a menu leaf is a product.

        Args:
            leaf (Dict[str, JsonValue]): The menu leaf.
            top (Dict[str, JsonValue]): Its top level entry.
            universe (str): Its menu universe, e.g. `public-cloud`.
            categories (Tuple[Set[str], Set[str]]): The category labels and URL keys of the menu.

        Returns:
            bool: Whether the leaf is a product, not a category,
                a use case, an "About us" page or a coming entry.
        """
        label = self._clean_text(self._as_text(leaf.get("label")))
        link = self._as_text(leaf.get("link")) or ""
        reasons = {
            "about us": "/about-us" in (self._as_text(top.get("link")) or ""),
            "coming soon": leaf.get("comingSoon") is True,
            "link label": bool(self.NOT_PRODUCT_LABEL.search(label)),
            "use case or documentation": bool(self.NOT_PRODUCT_LINK.search(link)),
            "category": label.casefold() in categories[0]
            or (universe == "home" and bool(link) and self._url_key(link) in categories[1]),
        }
        if failed := [reason for reason, matched in reasons.items() if matched]:
            self.logger.debug("Skipping the menu entry %r (%s).", label, ", ".join(failed))
            return False
        return True

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the menu: the leaves with a description, not filtered out.

        Args:
            response (Response): A page of the website.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menu.

        Raises:
            CatalogueFormatError: If the page has no products menu.
        """
        menu = self._menu(response)
        categories = self._categories(menu)
        self.category_urls.update(categories[1])
        for universe, tree in menu.items():
            for leaf, top in self._leaves(tree):
                description = self._as_text(leaf.get("description"))
                if not (description or "").strip() or not self._is_product_leaf(leaf, top, universe, categories):
                    continue
                label, link = self._as_text(leaf.get("label")), self._as_text(leaf.get("link"))
                if product := self._build_product(label, description, link):
                    yield product

    def _sitemap_requests(self, response: Response) -> List[Request]:
        """Request the product pages of the sitemap which were not found in the menu, with their last modification.

        Args:
            response (Response): The sitemap.

        Returns:
            List[Request]: The product page requests.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        entries = self._sitemap_entries(response)
        pages = [
            url
            for url in entries
            if self.SITEMAP_PRODUCT_PAGE.match(url)
            and not self.SITEMAP_NOT_PRODUCT.search(url)
            and self._url_key(url) not in self.category_urls
        ]
        requests = [
            request for url in pages if (request := self._product_page_request(url, updated=entries[url])) is not None
        ]
        self.logger.info(
            "%d %s product pages to check in the sitemap (%d pages).", len(requests), self.name, len(entries)
        )
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the menu embedded in a page.

        Args:
            response (Response): A page of the website.

        Returns:
            Iterator[CloudProduct]: The valid products of the menu.

        Raises:
            CatalogueFormatError: If the page has no products menu.
        """
        return self._menu_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the menu products, request the sitemap product pages, or stream a sitemap product page.

        The product pages are read by the base crawler.

        Args:
            response (Response): The menu page, the sitemap or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, or the product page requests.

        Raises:
            CatalogueFormatError: If a page has no products menu,
                or if the sitemap lists no page.
        """
        if response.url == self.SITEMAP_URL:
            for request in self._sitemap_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
