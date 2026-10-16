from __future__ import annotations

# Standard Library Imports.
import re
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError
from models.cloud.product import CloudProduct


class BaiduAICloudCrawler(BaseCloudCrawler):
    """Baidu AI Cloud (百度智能云) catalogue crawler.

    Attributes:
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The catalogue links which are not product pages: solutions,
            console pages and third-party marketplace offers.
        LINK_PADDING (ClassVar[re.Pattern[str]]): The spaces (raw or encoded) around some catalogue links.
        TITLE_SUFFIX (ClassVar[str]): The brand suffix of the page titles.

    Notes:
        The main source is the Next.js data of the https://cloud.baidu.com/products/index.html page
        (`props.pageProps.newProductsList`): a tree of top groups, categories and sub-categories (`list`) holding
        the products (`name`, `desc`, `link`). The sub-categories without products but with a link are products
        themselves: their pages are requested, named after the sub-category, and described by their meta
        description. The names and descriptions are in Chinese.
    """

    NOT_PRODUCT_LINK: ClassVar[re.Pattern[str]] = re.compile(
        r"/solution/|console\.bce\.baidu\.com|market\.baidu\.com", re.IGNORECASE
    )
    LINK_PADDING: ClassVar[re.Pattern[str]] = re.compile(r"^(?:\s|%20)+|(?:\s|%20)+$")
    TITLE_SUFFIX: ClassVar[str] = "-百度智能云"

    name = "baidu"
    catalogue_url: ClassVar[str] = "https://cloud.baidu.com/products/index.html"
    name_prefixes: ClassVar[Tuple[str, ...]] = ("百度智能云", "百度", "Baidu AI Cloud ", "Baidu ")

    ############################
    # Internal Helpers Methods #
    ############################

    def _page_title(self, title: str) -> str:
        """Clean the product name read from a product page title: the brand suffix and the SEO keywords are removed.

        Args:
            title (str): The page title, e.g. `云服务器BCC_云主机_虚拟主机-百度智能云`.

        Returns:
            str: The product name, e.g. `云服务器BCC`.
        """
        return self._clean_text(self._clean_text(title).removesuffix(self.TITLE_SUFFIX).split("_")[0])

    def _link(self, link: Optional[str]) -> Optional[str]:
        """Clean a catalogue link, some of them being padded with spaces.

        Args:
            link (Optional[str]): The raw catalogue link.

        Returns:
            Optional[str]: The link without padding, `None` when missing or empty.
        """
        return self.LINK_PADDING.sub("", link or "") or None

    def _as_list(self, value: JsonValue) -> List[JsonValue]:
        """Read a JSON value expected to be a list.

        Args:
            value (JsonValue): The JSON value.

        Returns:
            List[JsonValue]: The list, empty when the value is not a list.
        """
        return value if isinstance(value, list) else []

    def _is_product_link(self, name: Optional[str], link: Optional[str]) -> bool:
        """Tell whether a catalogue link is a product page, not a solution, console or marketplace page.

        Args:
            name (Optional[str]): The catalogue entry name, for the logs.
            link (Optional[str]): The cleaned catalogue link.

        Returns:
            bool: Whether the link is missing or is a product page.
        """
        if link and self.NOT_PRODUCT_LINK.search(link):
            self.logger.debug("Skipping the catalogue entry %r, %s is not a product page.", name, link)
            return False
        return True

    def _sub_categories(self, response: Response) -> List[Dict[str, JsonValue]]:
        """Read the sub-categories of the catalogue, holding the products.

        Args:
            response (Response): The catalogue page.

        Returns:
            List[Dict[str, JsonValue]]: The sub-categories (`list` items) of every category of every top group.

        Raises:
            CatalogueFormatError: If the page has no Next.js data or no `newProductsList` list.
        """
        groups = self._as_object(self._as_object(self._next_data(response).get("props")).get("pageProps")).get(
            "newProductsList"
        )
        if not isinstance(groups, list) or not groups:
            self.logger.error("The %s page %s has no `newProductsList` catalogue.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the `newProductsList` catalogue is missing")
        sub_categories = [
            self._as_object(sub_category)
            for group in groups
            for category in self._as_list(self._as_object(group).get("categories"))
            for sub_category in self._as_list(self._as_object(category).get("list"))
        ]
        self.logger.debug("%d sub-categories in the %s catalogue %s.", len(sub_categories), self.name, response.url)
        return sub_categories

    def _catalogue_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the catalogue sub-categories.

        Args:
            response (Response): The catalogue page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the catalogue, solutions and console links excluded.

        Raises:
            CatalogueFormatError: If the page has no Next.js data or no `newProductsList` list.
        """
        for sub_category in self._sub_categories(response):
            for entry in self._as_list(sub_category.get("products")):
                fields = self._as_object(entry)
                name = self._as_text(fields.get("name"))
                link = self._link(self._as_text(fields.get("link")))
                if not self._is_product_link(name, link):
                    continue
                if product := self._build_product(name, self._as_text(fields.get("desc")), link):
                    yield product

    def _page_requests(self, response: Response) -> List[Request]:
        """Request the pages of the sub-categories which are products: without products, but with a link.

        Args:
            response (Response): The catalogue page.

        Returns:
            List[Request]: The product page requests, named after their sub-category.

        Raises:
            CatalogueFormatError: If the page has no Next.js data or no `newProductsList` list.
        """
        requests: List[Request] = []
        for sub_category in self._sub_categories(response):
            name = self._as_text(sub_category.get("type"))
            link = self._link(self._as_text(sub_category.get("link")))
            if sub_category.get("products") or not link or not self._is_product_link(name, link):
                continue
            if urlparse(link).netloc not in self.allowed_domains:
                self.logger.debug("Not requesting the product page %s of %r, outside of the website.", link, name)
                continue
            if request := self._product_page_request(link, name):
                requests.append(request)
        self.logger.info("%d %s product pages to read for the sub-categories.", len(requests), self.name)
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the catalogue page.

        Args:
            response (Response): The catalogue page.

        Returns:
            Iterator[CloudProduct]: The valid products of the catalogue.

        Raises:
            CatalogueFormatError: If the page has no Next.js data or no `newProductsList` list.
        """
        return self._catalogue_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the catalogue products, then request the product pages of the sub-categories.

        Args:
            response (Response): The catalogue page or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, then the product page requests.

        Raises:
            CatalogueFormatError: If the catalogue page has no Next.js data or no `newProductsList` list.
        """
        async for item in super().parse(response):
            yield item
        if self.PRODUCT_PAGE in response.meta:
            return
        for request in self._page_requests(response):
            yield request
