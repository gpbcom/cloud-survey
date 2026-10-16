from __future__ import annotations

# Standard Library Imports.
import re
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from models.cloud.product import CloudProduct


class TCloudPublicCrawler(BaseCloudCrawler):
    """T Cloud Public (formerly Open Telekom Cloud) catalogue crawler.

    Attributes:
        SITEMAP_URL (ClassVar[str]): The sitemap of the website, listing the product pages.
        SITEMAP_PRODUCT_PAGE (ClassVar[re.Pattern[str]]): The sitemap pages of the core services, capturing the slug.
        NOT_PRODUCT_SLUG (ClassVar[re.Pattern[str]]): The core services pages which are not products: dashboards,
            price display, documentation, certifications and professional services.
        TITLE_SUFFIX (ClassVar[re.Pattern[str]]): The brand suffix of the page titles.

    Notes:
        The main source is the https://www.t-cloud-public.com/en/products-services/core-services page: a table
        per category whose rows link a core service page and describe it in a tooltip
        (`scale-tooltip div[slot=content]`). The sitemap completes it: its core services pages missing from the
        tables are requested and read from their first heading (the page titles are marketing taglines) and meta
        description, dated by their sitemap last modification (`lastmod`). The table products are undated.
    """

    SITEMAP_URL: ClassVar[str] = "https://www.t-cloud-public.com/en/sitemap.xml"
    SITEMAP_PRODUCT_PAGE: ClassVar[re.Pattern[str]] = re.compile(
        r"^https://www\.t-cloud-public\.com/en/products-services/core-services/([\w-]+)/?$", re.IGNORECASE
    )
    NOT_PRODUCT_SLUG: ClassVar[re.Pattern[str]] = re.compile(
        r"dashboard|price|pricing|documentation|certification|professional-services", re.IGNORECASE
    )
    TITLE_SUFFIX: ClassVar[re.Pattern[str]] = re.compile(r"\s*\|\s*(?:T Cloud Public|Open Telekom Cloud)\s*$")

    name = "tcloud"
    catalogue_url: ClassVar[str] = "https://www.t-cloud-public.com/en/products-services/core-services"
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("T Cloud Public ", "Open Telekom Cloud ")

    ############################
    # Internal Helpers Methods #
    ############################

    def _page_title(self, title: str) -> str:
        """Clean the product name read from a product page title: the brand suffix is removed.

        Args:
            title (str): The page title, e.g. `Bare Metal Server | T Cloud Public`.

        Returns:
            str: The product name, e.g. `Bare Metal Server`.
        """
        return self._clean_text(self.TITLE_SUFFIX.sub("", self._clean_text(title)))

    def _page_name(self, response: Response) -> Optional[str]:
        """Read the product name of a product page: its first heading, else its Open Graph title.

        The Open Graph titles are marketing taglines, e.g. `Virtual machines from the cloud`.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The product name, `None` when the page has none.
        """
        heading = response.css("h1").first
        title = heading.get_all_text(separator=" ", strip=True) if heading is not None else None
        if title:
            return self._page_title(title)
        return super()._page_name(response)

    def _row_product(self, row: Selector, page_url: str) -> Optional[CloudProduct]:
        """Extract the product of a services table row.

        Args:
            row (Selector): The table row.
            page_url (str): The catalogue page URL, the row links being relative to it.

        Returns:
            Optional[CloudProduct]: The product, `None` for a row without core service link or an invalid one.
        """
        link = next(iter(row.css('a[href*="/core-services/"]')), None)
        if link is None:
            self.logger.debug("Skipping a services table row without core service link.")
            return None
        tooltip = row.css("scale-tooltip div[slot=content]").first
        description = tooltip.get_all_text(separator=" ", strip=True) if tooltip is not None else None
        name = link.get_all_text(separator=" ", strip=True)
        return self._build_product(name, description, urljoin(page_url, str(link.attrib["href"])))

    def _table_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the services tables.

        Args:
            response (Response): The core services page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the tables.
        """
        rows = response.css("tr")
        self.logger.debug("%d services table rows found on %s.", len(rows), response.url)
        for row in rows:
            if product := self._row_product(row, response.url):
                yield product

    def _is_product_page(self, url: str) -> bool:
        """Tell whether a sitemap page is a core service product page.

        Args:
            url (str): The sitemap page URL.

        Returns:
            bool: Whether the page is a core service page which is not a tool, documentation or service page.
        """
        page = self.SITEMAP_PRODUCT_PAGE.match(url)
        if page is None:
            return False
        if self.NOT_PRODUCT_SLUG.search(page.group(1)):
            self.logger.debug("Skipping the sitemap page %s, not a product.", url)
            return False
        return True

    def _sitemap_requests(self, response: Response) -> List[Request]:
        """Request the core service pages of the sitemap missing from the tables, with their last modification.

        Args:
            response (Response): The sitemap.

        Returns:
            List[Request]: The product page requests.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        entries = self._sitemap_entries(response)
        pages = [url for url in entries if self._is_product_page(url)]
        requests = [
            request for url in pages if (request := self._product_page_request(url, updated=entries[url])) is not None
        ]
        self.logger.info(
            "%d %s product pages to check in the sitemap (%d product pages, %d pages).",
            len(requests),
            self.name,
            len(pages),
            len(entries),
        )
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the services tables.

        Args:
            response (Response): The core services page.

        Returns:
            Iterator[CloudProduct]: The valid products of the tables.
        """
        return self._table_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the table products, request the sitemap product pages, or stream a sitemap product page.

        Args:
            response (Response): The core services page, the sitemap or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, or the product page requests.

        Raises:
            EmptyCatalogueError: If the core services page holds no valid product.
            CatalogueFormatError: If the sitemap lists no page.
        """
        if response.url == self.SITEMAP_URL:
            for request in self._sitemap_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
