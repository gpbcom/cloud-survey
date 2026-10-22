from __future__ import annotations

# Standard Library Imports.
import re
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.baidu.enums import (
    BaiduCatalogueCategoryField,
    BaiduCatalogueGroupField,
    BaiduCatalogueProductField,
    BaiduCatalogueSubCategoryField,
    BaiduNextDataField,
    BaiduPageTitle,
)
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError
from models.cloud.products.product import CloudProduct


class BaiduAICloudCrawler(BaseCloudCrawler):
    """Baidu AI Cloud (百度智能云) catalogue crawler.

    Attributes:
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The catalogue links which are not product pages: solutions,
            console pages and third-party marketplace offers.
        LINK_PADDING (ClassVar[re.Pattern[str]]): The spaces (raw or encoded) around some catalogue links.
        TITLE_SUFFIX (ClassVar[BaiduPageTitle]): The brand suffix of the page titles.

    Notes:
        The main source is the Next.js data of the https://cloud.baidu.com/products/index.html page
        (`props.pageProps.newProductsList`): a tree of top groups, categories and sub-categories (`list`) holding
        the products (`name`, `desc`, `link`). The sub-categories without products but with a link are products
        themselves: their pages are requested, named after the sub-category, and described by their meta
        description. The names and descriptions are in Chinese. A product gets the labels of the top group, category
        and sub-category (e.g. `云计算` > `计算`) of every sub-category it is listed under.
    """

    NOT_PRODUCT_LINK: ClassVar[re.Pattern[str]] = re.compile(
        r"/solution/|console\.bce\.baidu\.com|market\.baidu\.com", re.IGNORECASE
    )
    LINK_PADDING: ClassVar[re.Pattern[str]] = re.compile(r"^(?:\s|%20)+|(?:\s|%20)+$")
    TITLE_SUFFIX: ClassVar[BaiduPageTitle] = BaiduPageTitle.BRAND_SUFFIX

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

    def _sub_categories(self, response: Response) -> List[Tuple[List[str], Dict[str, JsonValue]]]:
        """Read the sub-categories of the catalogue, holding the products.

        Args:
            response (Response): The catalogue page.

        Returns:
            List[Tuple[List[str], Dict[str, JsonValue]]]: The sub-categories (`list` items) of every category of every
                top group, each with the labels of its top group, category and itself.

        Raises:
            CatalogueFormatError: If the page has no Next.js data or no `newProductsList` list.
        """
        props = self._as_object(self._next_data(response).get(BaiduNextDataField.PROPS))
        groups = self._as_object(props.get(BaiduNextDataField.PAGE_PROPS)).get(BaiduNextDataField.NEW_PRODUCTS_LIST)
        if not isinstance(groups, list) or not groups:
            self.logger.error("The %s page %s has no `newProductsList` catalogue.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the `newProductsList` catalogue is missing")
        sub_categories: List[Tuple[List[str], Dict[str, JsonValue]]] = []
        for group in groups:
            group_fields = self._as_object(group)
            for category in self._as_list(group_fields.get(BaiduCatalogueGroupField.CATEGORIES)):
                category_fields = self._as_object(category)
                for sub_category in self._as_list(category_fields.get(BaiduCatalogueCategoryField.LIST)):
                    sub_fields = self._as_object(sub_category)
                    labels = [
                        self._clean_text(self._as_text(group_fields.get(BaiduCatalogueGroupField.NAME))),
                        self._clean_text(self._as_text(category_fields.get(BaiduCatalogueCategoryField.CATEGORY))),
                        self._clean_text(self._as_text(sub_fields.get(BaiduCatalogueSubCategoryField.TYPE))),
                    ]
                    sub_categories.append((labels, sub_fields))
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

        Notes:
            A product listed in several sub-categories gets the labels of all of them.
        """
        entries = [
            (labels, self._as_object(entry))
            for labels, sub_category in self._sub_categories(response)
            for entry in self._as_list(sub_category.get(BaiduCatalogueSubCategoryField.PRODUCTS))
        ]
        categories: Dict[str, List[str]] = {}
        for labels, fields in entries:
            key = self._name_key(self._clean_text(self._as_text(fields.get(BaiduCatalogueProductField.NAME))))
            categories.setdefault(key, []).extend(labels)
        for _, fields in entries:
            name = self._as_text(fields.get(BaiduCatalogueProductField.NAME))
            link = self._link(self._as_text(fields.get(BaiduCatalogueProductField.LINK)))
            if not self._is_product_link(name, link):
                continue
            if product := self._build_product(
                name,
                self._as_text(fields.get(BaiduCatalogueProductField.DESC)),
                link,
                categories=categories[self._name_key(self._clean_text(name))],
            ):
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
        for _, sub_category in self._sub_categories(response):
            name = self._as_text(sub_category.get(BaiduCatalogueSubCategoryField.TYPE))
            link = self._link(self._as_text(sub_category.get(BaiduCatalogueSubCategoryField.LINK)))
            if (
                sub_category.get(BaiduCatalogueSubCategoryField.PRODUCTS)
                or not link
                or not self._is_product_link(name, link)
            ):
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
