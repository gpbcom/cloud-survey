from __future__ import annotations

# Standard Library Imports.
import re
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from models.cloud.product import CloudProduct


class GcoreCrawler(BaseCloudCrawler):
    """Gcore catalogue crawler.

    Attributes:
        SITEMAP_URL (ClassVar[str]): The main sitemap of the website, listing the product pages.
        EXCLUDED_TABS (ClassVar[Tuple[str, ...]]): The menu tabs listing use cases, not products (case-insensitive).
        PRODUCT_PATHS (ClassVar[Tuple[str, ...]]): The sitemap paths of the product pages missing from the menu.
        TITLE_SUFFIX (ClassVar[re.Pattern[str]]): The tagline or brand suffix of a page heading or title.

    Notes:
        The main source is the products menu of the https://gcore.com/ home page: its tabbed menus (Edge Network,
        AI, Cloud, Security) list the products with a name and a short description. The "By industry" and "By need"
        tabs (use cases) are skipped. The main sitemap completes it with an allowlist of product pages (compute,
        hosting, security and services pages missing from the menu), read for their heading and meta description.
        The `robots.txt` of the website declares `Content-Signal: ai-train=no, search=yes, ai-input=no` and is
        obeyed.
    """

    SITEMAP_URL: ClassVar[str] = "https://gcore.com/sitemap-main.xml"
    EXCLUDED_TABS: ClassVar[Tuple[str, ...]] = ("by industry", "by need")
    PRODUCT_PATHS: ClassVar[Tuple[str, ...]] = (
        "/cloud/virtual-machines",
        "/cloud/faas",
        "/cloud/file-shares",
        "/cloud/load-balancers",
        "/cloud/managed-kubernetes",
        "/cloud/managed-logging",
        "/cloud/marketplace",
        "/cloud/recovery",
        "/container-registry",
        "/hosting/dedicated",
        "/hosting/vds",
        "/hosting/dedicated/gpu",
        "/security/waap",
        "/public-dns",
        "/streaming-platform/video-hosting",
        "/cdn/video-cdn",
        "/ddos-protection/servers",
        "/gcore-fastnetmon-ddos-protection",
        "/pentest",
        "/support-as-a-service",
        "/whitelabel",
        "/internet-peering",
        "/it-infrastructure-management",
        "/development",
    )
    TITLE_SUFFIX: ClassVar[re.Pattern[str]] = re.compile(r"\s+[|\u2013-]\s+.*$|:\s.*$")

    name = "gcore"
    catalogue_url: ClassVar[str] = "https://gcore.com/"
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Gcore ",)

    ############################
    # Internal Helpers Methods #
    ############################

    def _page_title(self, title: str) -> str:
        """Clean the product name read from a product page, removing its tagline or `| Gcore` suffix.

        Args:
            title (str): The page heading or title, e.g. `VDS Hosting - Buy virtual dedicated servers`.

        Returns:
            str: The product name, e.g. `VDS Hosting`.
        """
        return self.TITLE_SUFFIX.sub("", self._clean_text(title))

    def _page_name(self, response: Response) -> Optional[str]:
        """Read the product name of a product page: its first heading, else its Open Graph title.

        The Open Graph titles of the website are marketing sentences, the headings name the products.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The product name, `None` when the page has none.
        """
        heading = response.css("h1").first
        title = self._clean_text(heading.get_all_text(separator=" ", strip=True)) if heading is not None else None
        title = title or self._meta_content(response, "og:title")
        return self._page_title(title) if title else None

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the tabbed menus, skipping the use case tabs.

        Each menu lists its tab labels (`.gc-tabbed-menu__rail-label`) and, in the same order, one grid of links
        per tab (`.gc-tabbed-menu__grid`).

        Args:
            response (Response): The home page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menus.
        """
        menus = response.css(".gc-tabbed-menu")
        self.logger.debug("%d tabbed menus in %s.", len(menus), response.url)
        for menu in menus:
            tabs = [
                self._clean_text(tab.get_all_text(separator=" ", strip=True))
                for tab in menu.css(".gc-tabbed-menu__rail-label")
            ]
            for index, grid in enumerate(menu.css(".gc-tabbed-menu__grid")):
                tab = tabs[index] if index < len(tabs) else ""
                if tab.casefold() in self.EXCLUDED_TABS:
                    self.logger.debug("Skipping the menu tab %r, use cases not products.", tab)
                    continue
                for link in grid.css("a.gc-menu-link-item"):
                    label = link.css(".gc-menu-link-item__label").first
                    description = link.css(".gc-menu-link-item__description").first
                    if label is None or description is None:
                        self.logger.debug("Skipping a menu link without name or description in the tab %r.", tab)
                        continue
                    url = urljoin(response.url, link.attrib.get("href", ""))
                    name = label.get_all_text(separator=" ", strip=True)
                    if product := self._build_product(name, description.get_all_text(separator=" ", strip=True), url):
                        yield product

    def _sitemap_requests(self, response: Response) -> List[Request]:
        """Request the allowlisted product pages of the sitemap which were not found in the menu.

        Args:
            response (Response): The sitemap.

        Returns:
            List[Request]: The product page requests.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        urls = self._sitemap_urls(response)
        requests: List[Request] = []
        for url in urls:
            if urlparse(url).path.rstrip("/") not in self.PRODUCT_PATHS:
                self.logger.debug("Skipping the sitemap page %s, not an allowlisted product page.", url)
                continue
            if (request := self._product_page_request(url)) is not None:
                requests.append(request)
        self.logger.info("%d %s product pages to check in the sitemap (%d pages).", len(requests), self.name, len(urls))
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the home page menus.

        Args:
            response (Response): The home page.

        Returns:
            Iterator[CloudProduct]: The valid products of the menus.
        """
        return self._menu_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the menu products, request the sitemap product pages, or stream a sitemap product page.

        The product pages are read by the base crawler.

        Args:
            response (Response): The home page, the sitemap or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, or the product page requests.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
            EmptyCatalogueError: If the home page menus hold no product.
        """
        if response.url == self.SITEMAP_URL:
            for request in self._sitemap_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
