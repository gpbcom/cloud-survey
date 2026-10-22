from __future__ import annotations

# Standard Library Imports.
import re
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.krystal.enums import KrystalFooterColumn, KrystalSitemapSection
from crawler.enums import HtmlAttribute
from models.cloud.products.product import CloudProduct


class KrystalCrawler(BaseCloudCrawler):
    """Krystal catalogue crawler, including its Katapult cloud.

    Attributes:
        SITE_URL (ClassVar[str]): The website root, the links being relative to it.
        SITEMAP_PAGE_URL (ClassVar[str]): The HTML sitemap, listing the hosting, server and domain products.
        SITEMAP_URL (ClassVar[str]): The XML sitemap, listing every page of the website.
        PRODUCT_SECTIONS (ClassVar[str]): The CSS selector of the product sections of the cloud products page.
        PRODUCT_CARDS (ClassVar[str]): The CSS selector of the product cards of a product section.
        SITEMAP_SECTIONS (ClassVar[FrozenSet[KrystalSitemapSection]]): The HTML sitemap sections listing products.
        FOOTER_COLUMNS (ClassVar[FrozenSet[KrystalFooterColumn]]): The footer columns listing products.
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The links which are not product pages (anchors, the cloud
            overview, pricing and technology pages).
        RENAMED (ClassVar[Dict[str, str]]): The product names replacing the action labels of the HTML sitemap, by path.
        SITEMAP_PRODUCTS (ClassVar[Dict[str, str]]): The product pages only listed by the XML sitemap, with their
            names, by path.

    Notes:
        The main source is the https://krystal.io/cloud/products page, whose cards list the Katapult cloud products
        (name, description and link). The HTML sitemap (https://krystal.io/sitemap) adds the products of its
        "Website Hosting", "Servers" and "Domain Names" sections, then the "Services" and "Cloud" footer columns
        link to the remaining product pages. Last, the XML sitemap gives the product pages linked from nowhere else
        (`SITEMAP_PRODUCTS`). The product pages are read for their description, the product name being the listing
        label, as their titles are marketing slogans.
        The catalogue categories of a product are the titles of the sections listing it (e.g. `Compute` on the
        cloud products page, `Website Hosting` on the HTML sitemap), else of the footer columns listing it (e.g.
        `Services`). The products only listed by the XML sitemap have none.
    """

    SITE_URL: ClassVar[str] = "https://krystal.io/"
    SITEMAP_PAGE_URL: ClassVar[str] = "https://krystal.io/sitemap"
    SITEMAP_URL: ClassVar[str] = "https://krystal.io/sitemap.xml"
    PRODUCT_SECTIONS: ClassVar[str] = "main section"
    PRODUCT_CARDS: ClassVar[str] = "ul > li > a[href]"
    SITEMAP_SECTIONS: ClassVar[FrozenSet[KrystalSitemapSection]] = frozenset(
        {KrystalSitemapSection.WEBSITE_HOSTING, KrystalSitemapSection.SERVERS, KrystalSitemapSection.DOMAIN_NAMES}
    )
    FOOTER_COLUMNS: ClassVar[FrozenSet[KrystalFooterColumn]] = frozenset(
        {KrystalFooterColumn.SERVICES, KrystalFooterColumn.CLOUD}
    )
    NOT_PRODUCT_LINK: ClassVar[re.Pattern[str]] = re.compile(r"#|^/cloud/?$|/pricing\b|/technology\b")
    RENAMED: ClassVar[Dict[str, str]] = {"/domains": "Domain names"}
    SITEMAP_PRODUCTS: ClassVar[Dict[str, str]] = {
        "/ai-website-builder": "AI Website Builder",
        "/voip": "VoIP",
        "/intelligent-wordpress-protection": "Intelligent WordPress Protection",
    }

    name = "krystal"
    catalogue_url: ClassVar[str] = "https://krystal.io/cloud/products"
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_PAGE_URL, SITEMAP_URL)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Krystal Cloud ", "Krystal ", "Katapult ")

    ############################
    # Internal Helpers Methods #
    ############################

    def _text(self, element: Optional[Selector]) -> Optional[str]:
        """Read the text of an optional element.

        Args:
            element (Optional[Selector]): The element.

        Returns:
            Optional[str]: Its text, `None` when the element is missing.
        """
        return element.get_all_text(separator=" ", strip=True) if element is not None else None

    def _is_product_link(self, href: str, label: Optional[str]) -> bool:
        """Tell whether a listing link is a product page.

        Args:
            href (str): The link, as written in the page.
            label (Optional[str]): The listing label, for the log.

        Returns:
            bool: Whether the link is not an anchor, the cloud overview, a pricing or a technology page.
        """
        if not href or self.NOT_PRODUCT_LINK.search(href):
            self.logger.debug("Skipping the link %r (%s), not a product page.", label, href)
            return False
        return True

    def _card_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the cards of the cloud products page.

        Args:
            response (Response): The cloud products page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the page, once, with the titles of all its sections.
        """
        entries: Dict[str, Tuple[Optional[str], Optional[str], str, List[str]]] = {}
        for section in response.css(self.PRODUCT_SECTIONS):
            title = self._clean_text(self._text(section.css("h2").first))
            cards = section.css(self.PRODUCT_CARDS)
            self.logger.debug("%d product cards in the section %r of %s.", len(cards), title, response.url)
            for card in cards:
                url = urljoin(self.SITE_URL, card.attrib.get(HtmlAttribute.HREF, ""))
                if (key := self._url_key(url)) in entries:
                    entries[key][3].append(title)
                    continue
                entries[key] = (self._text(card.css("h3").first), self._text(card.css("p").first), url, [title])
        for name, description, url, titles in entries.values():
            if product := self._build_product(name, description, url, categories=titles):
                yield product

    def _sitemap_page_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the product sections of the HTML sitemap.

        Args:
            response (Response): The HTML sitemap.

        Yields:
            Iterator[CloudProduct]: Each valid product of the product sections.
        """
        for section in response.css("main section"):
            title = self._clean_text(self._text(section.css("h2").first))
            if title not in self.SITEMAP_SECTIONS:
                self.logger.debug("Skipping the sitemap section %r, not a product section.", title)
                continue
            for card in section.css("div.col-span-2"):
                name, href = self._text(card.css("h3").first), card.css("a::attr(href)").get() or ""
                if not self._is_product_link(href, name):
                    continue
                path = urlparse(href).path.rstrip("/")
                description = self._text(card.css("p").first)
                if product := self._build_product(
                    self.RENAMED.get(path, name), description, urljoin(self.SITE_URL, href), categories=[title]
                ):
                    yield product

    def _footer_requests(self, response: Response) -> List[Request]:
        """Request the product pages of the footer product columns which were not streamed yet.

        Args:
            response (Response): A page of the website.

        Returns:
            List[Request]: The product page requests, named after the footer labels, with their footer columns.
        """
        requests: Dict[str, Request] = {}
        for column in response.css("footer div.space-y-4"):
            title = self._clean_text(self._text(column.css("p").first))
            if title not in self.FOOTER_COLUMNS:
                continue
            for link in column.css("ul li a[href]"):
                label, href = self._clean_text(self._text(link)), link.attrib.get(HtmlAttribute.HREF, "")
                url = urljoin(self.SITE_URL, href)
                if (key := self._url_key(url)) in requests:
                    requests[key].meta[self.PRODUCT_CATEGORIES].append(title)
                    continue
                if self._is_product_link(href, label) and (
                    request := self._product_page_request(url, label, categories=[title])
                ):
                    requests[key] = request
        self.logger.info("%d %s product pages to read from the footer of %s.", len(requests), self.name, response.url)
        return list(requests.values())

    def _sitemap_requests(self, response: Response) -> List[Request]:
        """Request the product pages only listed by the XML sitemap.

        Args:
            response (Response): The XML sitemap.

        Returns:
            List[Request]: The product page requests, named after `SITEMAP_PRODUCTS`.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        requests: List[Request] = []
        urls = self._sitemap_urls(response)
        for url in urls:
            path = urlparse(url).path.rstrip("/")
            if path in self.SITEMAP_PRODUCTS and (
                request := self._product_page_request(url, self.SITEMAP_PRODUCTS[path])
            ):
                requests.append(request)
        self.logger.info(
            "%d %s product pages to read from the sitemap (%d pages).", len(requests), self.name, len(urls)
        )
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the cloud products page or of the HTML sitemap.

        Args:
            response (Response): The cloud products page or the HTML sitemap.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.
        """
        if self._url_key(response.url) == self._url_key(self.SITEMAP_PAGE_URL):
            return self._sitemap_page_products(response)
        return self._card_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the products of a listing, then request the product pages of the footer or of the XML sitemap.

        Args:
            response (Response): The cloud products page, the HTML sitemap, the XML sitemap or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, or the product page requests.

        Raises:
            EmptyCatalogueError: If the cloud products page or the HTML sitemap holds no valid product.
            CatalogueFormatError: If the XML sitemap lists no page.
        """
        key = self._url_key(response.url)
        if self.PRODUCT_PAGE not in response.meta and key == self._url_key(self.SITEMAP_URL):
            for request in self._sitemap_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
        if self.PRODUCT_PAGE not in response.meta and key == self._url_key(self.SITEMAP_PAGE_URL):
            for request in self._footer_requests(response):
                yield request
