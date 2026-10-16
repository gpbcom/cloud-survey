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


class STACKITCrawler(BaseCloudCrawler):
    """STACKIT catalogue crawler.

    Attributes:
        SITEMAP_URL (ClassVar[str]): The sitemap of the English website, listing the product pages.
        SITEMAP_PRODUCT_PAGE (ClassVar[re.Pattern[str]]): The sitemap product pages, e.g.
            `/en/products/<category>/stackit-<slug>`, not the category pages nor their sub-pages.
        TITLE_TAGLINE (ClassVar[re.Pattern[str]]): The tagline following the product name in the page titles.

    Notes:
        The main source is the https://stackit.com/en/products page: a grid of product tiles
        (`article.digits-base-tile`), each with a name, a short description and a product page link. The English
        sitemap completes it: its product pages missing from the grid (e.g. the products without category) are
        requested and read from their title and meta description, dated by their sitemap last modification
        (`lastmod`). The grid products are undated. The `www.` host redirects to `stackit.com`.
    """

    SITEMAP_URL: ClassVar[str] = "https://stackit.com/en/sitemap/default.xml"
    SITEMAP_PRODUCT_PAGE: ClassVar[re.Pattern[str]] = re.compile(
        r"^https://(?:www\.)?stackit\.com/en/products/(?:[\w-]+/)?stackit-[\w-]+/?$", re.IGNORECASE
    )
    TITLE_TAGLINE: ClassVar[re.Pattern[str]] = re.compile(r"\s*(?:\||:\s|\s[-\u2013]\s).*$")

    name = "stackit"
    catalogue_url: ClassVar[str] = "https://stackit.com/en/products"
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("STACKIT ",)

    ############################
    # Internal Helpers Methods #
    ############################

    def _page_title(self, title: str) -> str:
        """Clean the product name read from a product page title: the tagline is removed.

        Args:
            title (str): The page title, e.g. `STACKIT DNS: Highly available and fast domain resolution`.

        Returns:
            str: The product name, e.g. `STACKIT DNS`.
        """
        return self._clean_text(self.TITLE_TAGLINE.sub("", self._clean_text(title)))

    def _tile_product(self, tile: Selector, page_url: str) -> Optional[CloudProduct]:
        """Extract the product of a product tile.

        Args:
            tile (Selector): The product tile (`article.digits-base-tile`).
            page_url (str): The catalogue page URL, the tile links being relative to it.

        Returns:
            Optional[CloudProduct]: The product, `None` when the tile has no name or is invalid.
        """
        name = " ".join(line.get_all_text(separator=" ", strip=True) for line in tile.css(".digits-tile__title-line"))
        if not self._clean_text(name):
            self.logger.debug("Skipping a product tile without name.")
            return None
        details = tile.css("p.digits-tile__details").first
        description = details.get_all_text(separator=" ", strip=True) if details is not None else None
        link = tile.css("a.digits-base-tile__link::attr(href)").get()
        return self._build_product(name, description, urljoin(page_url, link) if link else None)

    def _tiles_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the product tiles grid.

        Args:
            response (Response): The products page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the grid.
        """
        tiles = response.css("article.digits-base-tile")
        self.logger.debug("%d product tiles found on %s.", len(tiles), response.url)
        for tile in tiles:
            if product := self._tile_product(tile, response.url):
                yield product

    def _sitemap_requests(self, response: Response) -> List[Request]:
        """Request the product pages of the sitemap missing from the product tiles, with their last modification.

        Args:
            response (Response): The sitemap.

        Returns:
            List[Request]: The product page requests.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        entries = self._sitemap_entries(response)
        pages = [url for url in entries if self.SITEMAP_PRODUCT_PAGE.match(url)]
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
        """Extract the products of the product tiles grid.

        Args:
            response (Response): The products page.

        Returns:
            Iterator[CloudProduct]: The valid products of the grid.
        """
        return self._tiles_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the grid products, request the sitemap product pages, or stream a sitemap product page.

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
