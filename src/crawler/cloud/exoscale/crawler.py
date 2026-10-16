from __future__ import annotations

# Standard Library Imports.
import re
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from models.cloud.product import CloudProduct


class ExoscaleCrawler(BaseCloudCrawler):
    """Exoscale catalogue crawler.

    Attributes:
        SITEMAP_URL (ClassVar[str]): The sitemap of the website, listing the product pages.
        NOT_PRODUCT_NAME (ClassVar[re.Pattern[str]]): The menu entries which are overviews, not products.
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The menu links to compliance pages, not products.
        SITEMAP_PRODUCT_PAGE (ClassVar[re.Pattern[str]]): The top level pages of the website, capturing their slug:
            the product pages are top level pages, unlike the blog, the GPU models or the product features.
        SITEMAP_NOT_PRODUCT (ClassVar[re.Pattern[str]]): The top level pages which are not product pages.
        TITLE_BRAND (ClassVar[re.Pattern[str]]): The brand prefix or suffix of the page titles.
        not_product_urls (Set[str]): The URL keys of the menu entries filtered out, whose pages are not products.

    Notes:
        Exoscale has no catalogue page. The main source is the products mega menu embedded in every page
        (`#dropdown-products a.mega__item`, read from https://www.exoscale.com/products/): each entry gives a name
        (`b`), a description (`span`) and a product page, once the overviews and compliance entries are filtered
        out. Some entries link the documentation website. The sitemap completes it: its top level product pages
        missing from the menu are requested and read from their title and meta description.
    """

    SITEMAP_URL: ClassVar[str] = "https://www.exoscale.com/sitemap.xml"
    NOT_PRODUCT_NAME: ClassVar[re.Pattern[str]] = re.compile(r"\boverview\b", re.IGNORECASE)
    NOT_PRODUCT_LINK: ClassVar[re.Pattern[str]] = re.compile(r"/compliance/", re.IGNORECASE)
    SITEMAP_PRODUCT_PAGE: ClassVar[re.Pattern[str]] = re.compile(
        r"^https://www\.exoscale\.com/([\w-]+)/?$", re.IGNORECASE
    )
    SITEMAP_NOT_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?:about-us|abuse|academy|backup|blog|calculator|changelog|compare|compliance|contact|data-portability|"
        r"datacenters|docker-in-the-cloud|dpa|end-user-certificate-gpu|eusa|eyeson|faq|integration|jobs|"
        r"liquidcooling|lp|marketplace|newsletter|ocre|partner-programs|pricing|privacy|products|security|signup|sla|"
        r"support|sustainability|syslog|technology-providers|templates|terms|wp)$",
        re.IGNORECASE,
    )
    TITLE_BRAND: ClassVar[re.Pattern[str]] = re.compile(r"^Exoscale\s+|\s*\|\s*Exoscale\s*$", re.IGNORECASE)

    name = "exoscale"
    catalogue_url: ClassVar[str] = "https://www.exoscale.com/products/"
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Exoscale ",)

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.not_product_urls: Set[str] = set()

    ############################
    # Internal Helpers Methods #
    ############################

    def _page_title(self, title: str) -> str:
        """Clean the product name read from a product page title: the brand prefix or suffix is removed.

        Args:
            title (str): The page title, e.g. `Exoscale Scion Network`.

        Returns:
            str: The product name, e.g. `Scion Network`.
        """
        return self._clean_text(self.TITLE_BRAND.sub("", self._clean_text(title)))

    def _page_description(self, response: Response) -> Optional[str]:
        """Read the product description of a product page: its meta description, else its header texts.

        Some pages only repeat their title in their meta description: their header subtitle and text are read then.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The description, `None` when the page has none.
        """
        description = super()._page_description(response)
        title = self._meta_content(response, "og:title") or ""
        if description and description.casefold() != title.casefold():
            return description
        header = [
            element.get_all_text(separator="") for element in response.css(".page-header__subtitle, .page-header__text")
        ]
        return self._clean_text(" ".join(header)) or description

    def _text(self, entry: Selector, selector: str) -> Optional[str]:
        """Read the text of the first element of a menu entry matching a selector.

        Args:
            entry (Selector): The menu entry.
            selector (str): The CSS selector of the element.

        Returns:
            Optional[str]: The element text, `None` when the entry has no such element.
        """
        element = entry.css(selector).first
        return element.get_all_text(separator=" ", strip=True) if element is not None else None

    def _menu_product(self, entry: Selector, page_url: str) -> Optional[CloudProduct]:
        """Extract the product of a products menu entry.

        Args:
            entry (Selector): The menu entry (`a.mega__item`).
            page_url (str): The page URL, the menu links being relative to it.

        Returns:
            Optional[CloudProduct]: The product, `None` for an overview, a compliance page or an invalid entry.
        """
        name = self._text(entry, "b")
        href = entry.attrib.get("href")
        link = urljoin(page_url, href) if href else None
        reasons = {
            "overview": bool(self.NOT_PRODUCT_NAME.search(name or "")),
            "compliance page": bool(self.NOT_PRODUCT_LINK.search(link or "")),
        }
        if failed := [reason for reason, matched in reasons.items() if matched]:
            self.logger.debug("Skipping the menu entry %r (%s).", name, ", ".join(failed))
            if link:
                self.not_product_urls.add(self._url_key(link))
            return None
        return self._build_product(name, self._text(entry, "span"), link)

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products menu.

        Args:
            response (Response): A page of the website.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menu, duplicates included.
        """
        entries = response.css("#dropdown-products a.mega__item")
        self.logger.debug("%d products menu entries found on %s.", len(entries), response.url)
        for entry in entries:
            if product := self._menu_product(entry, response.url):
                yield product

    def _is_product_page(self, url: str) -> bool:
        """Tell whether a sitemap page is a product page not filtered out of the menu.

        Args:
            url (str): The sitemap page URL.

        Returns:
            bool: Whether the page is a top level page which is not a company,
                legal, learning or menu overview page.
        """
        page = self.SITEMAP_PRODUCT_PAGE.match(url)
        if page is None:
            return False
        if self.SITEMAP_NOT_PRODUCT.match(page.group(1)) or self._url_key(url) in self.not_product_urls:
            self.logger.debug("Skipping the sitemap page %s, not a product.", url)
            return False
        return True

    def _sitemap_requests(self, response: Response) -> List[Request]:
        """Request the product pages of the sitemap which were not found in the products menu.

        Args:
            response (Response): The sitemap.

        Returns:
            List[Request]: The product page requests.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        urls = self._sitemap_urls(response)
        pages = [url for url in urls if self._is_product_page(url)]
        requests = [request for url in pages if (request := self._product_page_request(url)) is not None]
        self.logger.info(
            "%d %s product pages to check in the sitemap (%d product pages, %d pages).",
            len(requests),
            self.name,
            len(pages),
            len(urls),
        )
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products menu.

        Args:
            response (Response): A page of the website.

        Returns:
            Iterator[CloudProduct]: The valid products of the menu, duplicates included.
        """
        return self._menu_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the menu products, request the sitemap product pages, or stream a sitemap product page.

        The product pages are read by the base crawler.

        Args:
            response (Response): The products page, the sitemap or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, or the product page requests.

        Raises:
            EmptyCatalogueError: If the products page holds no valid product.
            CatalogueFormatError: If the sitemap lists no page.
        """
        if response.url == self.SITEMAP_URL:
            for request in self._sitemap_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
