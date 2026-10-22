from __future__ import annotations

# Standard Library Imports.
import re
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Sequence, Set, Tuple, Union
from urllib.parse import urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.ovh.enums import OvhHostPrefix, OvhMenuKey, OvhMenuUniverse, OvhNextDataField
from crawler.exception import CatalogueFormatError
from models.cloud.products.product import CloudProduct


class OVHcloudCrawler(BaseCloudCrawler):
    """OVHcloud catalogue crawler.

    Attributes:
        SITEMAP_URL (ClassVar[str]): The sitemap of the website, listing the product pages.
        NOT_PRODUCT_LABEL (ClassVar[re.Pattern[str]]): The menu labels which are links, not products.
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The menu links to use cases, guides and documentation.
        SITEMAP_PRODUCT_PAGE (ClassVar[re.Pattern[str]]): The sitemap pages of the product universes.
        SITEMAP_NOT_PRODUCT (ClassVar[re.Pattern[str]]): The sitemap pages which are not product pages.
        LOCALE (ClassVar[re.Pattern[str]]): The locale segment of the website paths, e.g. `/en-gb/`.
        COLUMN_LABEL (ClassVar[re.Pattern[str]]): The labels of the menu columns, e.g. `[Column 1]`, which are not
            categories.
        category_urls (Set[str]): The URL keys of the menu categories, whose pages are not product pages.

    Notes:
        OVHcloud has no catalogue page. The main source is the products menu embedded in every page (Next.js
        data, `props.pageProps.itemsDesktop`): a tree of universes, columns and groups whose leaves are products,
        once the categories, the use cases, the "About us" section and the "coming soon" entries are filtered out.
        A product is filed under the labels of its parent entries (e.g. `AI` then `Inference Solutions`), the
        columns aside, and under those of every entry listing it.
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
    COLUMN_LABEL: ClassVar[re.Pattern[str]] = re.compile(r"^\[[^\]]*\]$")

    name = "ovhcloud"
    catalogue_url: ClassVar[str] = "https://www.ovhcloud.com/en-gb/public-cloud/"
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    dates_sitemaps: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
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
        return f"{link.netloc.removeprefix(OvhHostPrefix.WWW)}{self.LOCALE.sub('', link.path).rstrip('/')}"

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
        page_props = self._as_object(self._as_object(data.get(OvhNextDataField.PROPS)).get(OvhNextDataField.PAGE_PROPS))
        menu = self._as_object(page_props.get(OvhNextDataField.ITEMS_DESKTOP))
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
            if node.get(OvhMenuKey.LEVEL) == 1 and node.get(OvhMenuKey.CHILDREN):
                labels.add(self._clean_text(self._as_text(node.get(OvhMenuKey.LABEL))).casefold())
                if link := self._as_text(node.get(OvhMenuKey.LINK)):
                    links.add(self._url_key(link))
        return labels, links

    def _leaves(
        self, value: JsonValue, top: Optional[Dict[str, JsonValue]] = None, path: Tuple[str, ...] = ()
    ) -> Iterator[Tuple[Dict[str, JsonValue], Dict[str, JsonValue], Tuple[str, ...]]]:
        """Walk the menu entries without children, with their top level entry and the labels of their parents.

        Args:
            value (JsonValue): A menu (sub)tree.
            top (Optional[Dict[str, JsonValue]]): The top level entry of the subtree, if already reached.
            path (Tuple[str, ...]): The labels of the entries above the subtree, top level first.

        Yields:
            Tuple[Dict[str, JsonValue], Dict[str, JsonValue], Tuple[str, ...]]: Each leaf, its top level entry and
                the labels of its parents, top level first.
        """
        if isinstance(value, list):
            for child in value:
                yield from self._leaves(child, top, path)
            return
        if not isinstance(value, dict):
            return
        if OvhMenuKey.LEVEL not in value:
            for child in value.values():
                yield from self._leaves(child, top, path)
            return
        top = top if top is not None else value
        children = value.get(OvhMenuKey.CHILDREN)
        if children:
            yield from self._leaves(
                children, top, (*path, self._clean_text(self._as_text(value.get(OvhMenuKey.LABEL))))
            )
        else:
            yield value, top, path

    def _leaf_categories(self, labels: Sequence[str], name: Optional[str]) -> List[str]:
        """Get the categories of a product from the labels of the entries listing it, without the columns.

        Args:
            labels (Sequence[str]): The labels of the parents of its leaves, top level first.
            name (Optional[str]): The product name, which is not one of its categories.

        Returns:
            List[str]: The category labels, in order, e.g. `["AI", "Inference Solutions"]`, without blank, column
                or repeated (case-insensitive) labels.
        """
        categories: List[str] = []
        known = {self._clean_text(name).casefold()}
        for label in labels:
            if label and not self.COLUMN_LABEL.match(label) and label.casefold() not in known:
                categories.append(label)
                known.add(label.casefold())
        return categories

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
        label = self._clean_text(self._as_text(leaf.get(OvhMenuKey.LABEL)))
        link = self._as_text(leaf.get(OvhMenuKey.LINK)) or ""
        reasons = {
            "about us": "/about-us" in (self._as_text(top.get(OvhMenuKey.LINK)) or ""),
            "coming soon": leaf.get(OvhMenuKey.COMING_SOON) is True,
            "link label": bool(self.NOT_PRODUCT_LABEL.search(label)),
            "use case or documentation": bool(self.NOT_PRODUCT_LINK.search(link)),
            "category": label.casefold() in categories[0]
            or (universe == OvhMenuUniverse.HOME and bool(link) and self._url_key(link) in categories[1]),
        }
        if failed := [reason for reason, matched in reasons.items() if matched]:
            self.logger.debug("Skipping the menu entry %r (%s).", label, ", ".join(failed))
            return False
        return True

    def _menu_entries(self, response: Response) -> List[Tuple[Dict[str, JsonValue], List[str]]]:
        """Gather the product leaves of the menu with all their categories, a product being listed in several ones.

        Args:
            response (Response): A page of the website.

        Returns:
            List[Tuple[Dict[str, JsonValue], List[str]]]: The first leaf of each product, by order of appearance,
                and the categories of all its leaves.

        Raises:
            CatalogueFormatError: If the page has no products menu.

        Notes:
            The leaves of a product are matched by name or by link, as the streamed products are.
        """
        menu = self._menu(response)
        categories = self._categories(menu)
        self.category_urls.update(categories[1])
        entries: List[Tuple[Dict[str, JsonValue], List[str]]] = []
        positions: Dict[str, int] = {}
        for universe, tree in menu.items():
            for leaf, top, path in self._leaves(tree):
                description = self._as_text(leaf.get(OvhMenuKey.DESCRIPTION))
                if not (description or "").strip() or not self._is_product_leaf(leaf, top, universe, categories):
                    continue
                link = self._as_text(leaf.get(OvhMenuKey.LINK))
                keys = [f"name:{self._name_key(self._as_text(leaf.get(OvhMenuKey.LABEL)) or '')}"]
                keys += [f"url:{self._url_key(link)}"] if link and link.strip() else []
                position = next((positions[key] for key in keys if key in positions), None)
                if position is None:
                    position = len(entries)
                    entries.append((leaf, []))
                    self.logger.debug("Menu product %r found.", leaf.get(OvhMenuKey.LABEL))
                else:
                    self.logger.debug(
                        "Menu product %r listed again, its categories are merged.", leaf.get(OvhMenuKey.LABEL)
                    )
                first, known = entries[position]
                entries[position] = (
                    first,
                    self._leaf_categories([*known, *path], self._as_text(first.get(OvhMenuKey.LABEL))),
                )
                positions.update(dict.fromkeys(keys, position))
        return entries

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the menu: the leaves with a description, not filtered out, with their categories.

        Args:
            response (Response): A page of the website.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menu, once.

        Raises:
            CatalogueFormatError: If the page has no products menu.
        """
        for leaf, categories in self._menu_entries(response):
            label, link = self._as_text(leaf.get(OvhMenuKey.LABEL)), self._as_text(leaf.get(OvhMenuKey.LINK))
            description = self._as_text(leaf.get(OvhMenuKey.DESCRIPTION))
            if product := self._build_product(label, description, link, categories=categories):
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
        if response.url == self.SITEMAP_URL and self.PAGE_DATES not in response.meta:
            for request in self._sitemap_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
