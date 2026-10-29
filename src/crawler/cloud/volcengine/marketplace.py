from __future__ import annotations

# Standard Library Imports.
import re
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import quote

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.volcengine.enums import (
    VolcanoEngineApiAction,
    VolcanoEngineCategoryField,
    VolcanoEngineListParameter,
    VolcanoEngineMarketplaceMeta,
    VolcanoEngineProductBasicField,
    VolcanoEngineProductField,
    VolcanoEngineProductInfoField,
    VolcanoEngineProductTypeKeyword,
    VolcanoEngineResponseField,
    VolcanoEngineResultField,
    VolcanoEngineShopField,
)
from crawler.enums import HttpMethod
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class VolcanoEngineMarketplaceCrawler(BaseMarketplaceCrawler):
    """Volcano Engine marketplace (火山引擎云市场) crawler.

    Attributes:
        API_URL (ClassVar[str]): The marketplace portal API, formatted with the action.
        PRODUCT_URL (ClassVar[str]): The product page, formatted with the product identifier.
        PAGE_SIZE (ClassVar[int]): The products read per page.
        PAGE (ClassVar[VolcanoEngineMarketplaceMeta]): The meta key holding the page number, from 1.
        CATEGORIES (ClassVar[VolcanoEngineMarketplaceMeta]): The meta key marking the category tree response.
        SERVICE (ClassVar[re.Pattern[str]]): The titles of the services (deployment, migration, consulting...).
        API_TITLE (ClassVar[re.Pattern[str]]): The titles of the APIs, MCP servers and agent plugins.
        CHILD_DELIVERIES (ClassVar[Tuple[Tuple[VolcanoEngineProductTypeKeyword, DeliveryMethod], ...]]): The
            delivery method given by a keyword of the product type (`ChildProductName`, e.g. 云市场生态镜像产品),
            casefolded.
        DELIVERIES (ClassVar[Dict[int, DeliveryMethod]]): The delivery method of each delivery type (`DeliverType`).
        CATEGORY_LEVELS (ClassVar[Tuple[Tuple[VolcanoEngineProductBasicField, VolcanoEngineProductBasicField], ...]]):
            The name and identifier fields of the front categories of a product, the top category first.
        PUBLISHER_FIELDS (ClassVar[Tuple[VolcanoEngineShopField, ...]]): The shop fields naming the publisher, the
            verified company name first.
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The product list API, the first page being requested with a `POST` body.
        category_names (Dict[int, str]): The name of each front category, by identifier.

    Notes:
        The marketplace pages read the products through a JSON API (`POST`): `ListProduct` gives the products by
        pages (`Offset`, `Limit`) with the `Total`, and `QueryFrontCategory` the front category tree (read first,
        it names the categories of the products which only give their identifiers). A product gives its title,
        description, shop (`ProductInfo.Shop`, the verified company name being preferred to the shop name), front
        categories (`FrontendCategoryL1Name`, `FrontendCategoryL2Name`) and type (`ChildProductName`): the images
        are virtual machines, the MCP products APIs, the others mostly SaaS. The few deployment or consulting
        services are skipped. The `robots.txt` of the marketplace is an HTML page, without rules. The names and
        descriptions are in Chinese.
    """

    API_URL: ClassVar[str] = (
        "https://market.volcengine.com/eco_apis_sinf/agw/marketplace_portal/{action}?Action={action}&Version=2025-01-01"
    )
    PRODUCT_URL: ClassVar[str] = "https://market.volcengine.com/goods/detail?goodsId={}"
    PAGE_SIZE: ClassVar[int] = 100
    PAGE: ClassVar[VolcanoEngineMarketplaceMeta] = VolcanoEngineMarketplaceMeta.PAGE
    CATEGORIES: ClassVar[VolcanoEngineMarketplaceMeta] = VolcanoEngineMarketplaceMeta.CATEGORIES
    SERVICE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:部署|配置|迁移|代维|运维|实施|咨询)(?:[与和及、](?:部署|配置|迁移|代维|运维|实施|咨询))*服务"
    )
    API_TITLE: ClassVar[re.Pattern[str]] = re.compile(r"(?<![a-z])(?:api|mcp)(?![a-z])|插件", re.IGNORECASE)
    CHILD_DELIVERIES: ClassVar[Tuple[Tuple[VolcanoEngineProductTypeKeyword, DeliveryMethod], ...]] = (
        (VolcanoEngineProductTypeKeyword.IMAGE, DeliveryMethod.VIRTUAL_MACHINE),
        (VolcanoEngineProductTypeKeyword.MCP, DeliveryMethod.API),
        (VolcanoEngineProductTypeKeyword.SAAS, DeliveryMethod.SAAS),
    )
    DELIVERIES: ClassVar[Dict[int, DeliveryMethod]] = {
        1: DeliveryMethod.SAAS,
        2: DeliveryMethod.SAAS,
        4: DeliveryMethod.DOWNLOAD,
        5: DeliveryMethod.VIRTUAL_MACHINE,
    }
    CATEGORY_LEVELS: ClassVar[Tuple[Tuple[VolcanoEngineProductBasicField, VolcanoEngineProductBasicField], ...]] = (
        (VolcanoEngineProductBasicField.FRONTEND_CATEGORY_L1_NAME, VolcanoEngineProductBasicField.FRONTEND_CATEGORY_L1),
        (VolcanoEngineProductBasicField.FRONTEND_CATEGORY_L2_NAME, VolcanoEngineProductBasicField.FRONTEND_CATEGORY_L2),
    )
    PUBLISHER_FIELDS: ClassVar[Tuple[VolcanoEngineShopField, ...]] = (
        VolcanoEngineShopField.SRV_ACCOUNT_VERIFY_NAME,
        VolcanoEngineShopField.SHOP,
    )

    name = "volcengine-marketplace"
    catalogue_url: ClassVar[str] = API_URL.format(action=VolcanoEngineApiAction.LIST_PRODUCT)

    def __init__(
        self,
        crawldir: Optional[Union[str, Path]] = None,
        interval: float = 300.0,
        classifier: Optional[SoftwareClassifier] = None,
    ) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
            classifier (Optional[SoftwareClassifier]): The software classifier, the project rules by default.
        """
        super().__init__(crawldir=crawldir, interval=interval, classifier=classifier)
        self.category_names: Dict[int, str] = {}

    ############################
    # Internal Helpers Methods #
    ############################

    def _list_request(self, page: int) -> Request:
        """Build the request of a page of products.

        Args:
            page (int): The page number, from 1.

        Returns:
            Request: The `POST` request, whose page may be empty after the first one.
        """
        meta: Dict[str, JsonValue] = {self.PAGE: page}
        if page > 1:
            meta[self.MAY_BE_EMPTY] = True
        body: Dict[str, JsonValue] = {
            VolcanoEngineListParameter.OFFSET: (page - 1) * self.PAGE_SIZE,
            VolcanoEngineListParameter.LIMIT: self.PAGE_SIZE,
        }
        return self._api_request(
            self.catalogue_url, HttpMethod.POST, json=body, meta=meta, priority=self.PRIMARY_PRIORITY
        )

    def _catalogue_request(self) -> Request:
        """Build the request of the first page of products.

        Returns:
            Request: The `POST` request of the first page.
        """
        return self._list_request(1)

    def _category_request(self) -> Request:
        """Build the request of the front category tree, read before the products.

        Returns:
            Request: The `POST` request of the category tree.
        """
        return self._api_request(
            self.API_URL.format(action=VolcanoEngineApiAction.QUERY_FRONT_CATEGORY),
            HttpMethod.POST,
            json={},
            meta={self.CATEGORIES: True, self.MAY_BE_EMPTY: True},
            priority=self.PRIMARY_PRIORITY + 1,
        )

    def _result(self, response: Response) -> Dict[str, JsonValue]:
        """Read the `Result` of an API response.

        Args:
            response (Response): The API response.

        Returns:
            Dict[str, JsonValue]: The result.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no `List`.
        """
        result = self._as_object(self._as_object(self._json_body(response)).get(VolcanoEngineResponseField.RESULT))
        if not isinstance(result.get(VolcanoEngineResultField.LIST), list):
            self.logger.error("The %s API response %s has no `Result.List`.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the response has no `Result.List`")
        return result

    def _read_categories(self, response: Response) -> None:
        """Read the names of the front categories, top ones and sub-categories.

        Args:
            response (Response): The category tree.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no `List`.
        """
        categories = self._result(response).get(VolcanoEngineResultField.LIST)
        for category in self._walk_objects(categories):
            identifier, label = (
                category.get(VolcanoEngineCategoryField.ID),
                self._as_text(category.get(VolcanoEngineCategoryField.CATEGORY_NAME_CN)),
            )
            if isinstance(identifier, int) and label and self._clean_text(label):
                self.category_names[identifier] = self._clean_text(label)
        self.logger.info("%d %s front categories read from %s.", len(self.category_names), self.name, response.url)

    def _categories(self, basic: Dict[str, JsonValue]) -> List[str]:
        """Read the front categories of a product: their names, else the names of their identifiers.

        Args:
            basic (Dict[str, JsonValue]): The product basic information (`ProductBasic`).

        Returns:
            List[str]: The top category then the sub-category names, when known.
        """
        labels: List[str] = []
        for name_field, identifier_field in self.CATEGORY_LEVELS:
            label = self._clean_text(self._as_text(basic.get(name_field)))
            identifier = basic.get(identifier_field)
            if not label and isinstance(identifier, int):
                label = self.category_names.get(identifier, "")
            if label:
                labels.append(label)
        return labels

    def _category_path(self, basic: Dict[str, JsonValue]) -> Optional[MarketplaceCategory]:
        """Build the marketplace category path of a product, from its front categories.

        Args:
            basic (Dict[str, JsonValue]): The product basic information (`ProductBasic`).

        Returns:
            Optional[MarketplaceCategory]: The top category then the sub-category (named by the category tree when
                only their identifiers are given), identified by the deepest named one, `None` without a named one.
        """
        labels: List[str] = []
        category_id: Optional[int] = None
        for name_field, identifier_field in self.CATEGORY_LEVELS:
            label = self._clean_text(self._as_text(basic.get(name_field)))
            identifier = basic.get(identifier_field)
            if not label and isinstance(identifier, int):
                label = self.category_names.get(identifier, "")
            if label:
                labels.append(label)
                category_id = identifier if isinstance(identifier, int) else None
        if not labels:
            self.logger.debug(
                "No named front category for the %s product %r.",
                self.name,
                basic.get(VolcanoEngineProductBasicField.PRODUCT),
            )
            return None
        return self._category(labels, category_id)

    def _delivery(self, title: str, product_type: str, deliver_type: JsonValue) -> DeliveryMethod:
        """Get the delivery method of a product.

        Args:
            title (str): The product title.
            product_type (str): The product type (`ChildProductName`).
            deliver_type (JsonValue): The delivery type (`DeliverType`).

        Returns:
            DeliveryMethod: The delivery given by the product type, else by the title (APIs, plugins), else by the
                delivery type.
        """
        kind = product_type.casefold()
        for keyword, delivery in self.CHILD_DELIVERIES:
            if keyword in kind:
                return delivery
        if self.API_TITLE.search(title):
            return DeliveryMethod.API
        if isinstance(deliver_type, int):
            return self.DELIVERIES.get(deliver_type, DeliveryMethod.OTHER)
        return DeliveryMethod.OTHER

    def _product_software(self, product: Dict[str, JsonValue]) -> Optional[MarketplaceSoftware]:
        """Build the software of a product, unless it is a service.

        Args:
            product (Dict[str, JsonValue]): The product.

        Returns:
            Optional[MarketplaceSoftware]: The software, with its listing date (the `CreatedTime` epoch seconds of
                its `ProductBasic`, else of its `ProductInfo`), `None` for a skipped (logged) or invalid product.
        """
        basic, info = (
            self._as_object(product.get(VolcanoEngineProductField.PRODUCT_BASIC)),
            self._as_object(product.get(VolcanoEngineProductField.PRODUCT_INFO)),
        )
        title = self._clean_text(
            self._as_text(basic.get(VolcanoEngineProductBasicField.PRODUCT_TITLE))
            or self._as_text(basic.get(VolcanoEngineProductBasicField.ZH_NAME))
        )
        if self.SERVICE.search(title):
            self.logger.debug("Skipping the %s product %r, a service.", self.name, title)
            return None
        shop = self._as_object(info.get(VolcanoEngineProductInfoField.SHOP))
        publisher = next(
            (
                text
                for text in (self._as_text(shop.get(field)) for field in self.PUBLISHER_FIELDS)
                if text and text.strip()
            ),
            None,
        )
        identifier = self._as_text(basic.get(VolcanoEngineProductBasicField.PRODUCT)) or self._as_text(
            info.get(VolcanoEngineProductInfoField.PRODUCT)
        )
        return self._build_software(
            title,
            self._as_text(basic.get(VolcanoEngineProductBasicField.PRODUCT_DESC)),
            self.PRODUCT_URL.format(quote(identifier, safe="")) if identifier else None,
            publisher,
            self._delivery(
                title,
                self._as_text(info.get(VolcanoEngineProductInfoField.CHILD_PRODUCT_NAME)) or "",
                basic.get(VolcanoEngineProductBasicField.DELIVER_TYPE),
            ),
            self._categories(basic),
            marketplace_category_paths=[self._category_path(basic)],
            added_at=self._parse_date(
                basic.get(VolcanoEngineProductBasicField.CREATED_TIME)
                or info.get(VolcanoEngineProductInfoField.CREATED_TIME),
                title,
            ),
        )

    def _next_request(self, response: Response) -> Optional[Request]:
        """Build the request of the page after a page of products, if there are more products and pages may be read.

        Args:
            response (Response): The page of products.

        Returns:
            Optional[Request]: The next page request, `None` after the last page or at the page limit.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no `List`.
        """
        result = self._result(response)
        products, total = result.get(VolcanoEngineResultField.LIST), result.get(VolcanoEngineResultField.TOTAL)
        page = response.meta.get(self.PAGE)
        number = page if isinstance(page, int) else 1
        if not products or not isinstance(total, int) or number * self.PAGE_SIZE >= total:
            self.logger.info("Last %s page reached (page %d, %s products).", self.name, number, total)
            return None
        if not self._within_page_limit(number + 1):
            return None
        self.logger.info("Requesting the %s page %d (%d products).", self.name, number + 1, total)
        return self._list_request(number + 1)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def on_start(self, resuming: bool = False) -> None:
        """Forget the categories of a previous crawl, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if resuming:
            self.logger.info("%s crawl resumed: %d category names kept.", self.name, len(self.category_names))
            return
        self.logger.debug("%s crawl started: the category names are forgotten.", self.name)
        self.category_names.clear()

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Start the crawl from the front category tree, then the first page of products.

        Yields:
            Request: The category tree request (read first), then the first page request.
        """
        self.logger.debug("Requesting the %s front category tree.", self.name)
        yield self._category_request()
        async for request in super().start_requests():
            yield request

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a page of products.

        Args:
            response (Response): The page of products.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid software of the page.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no `List`.
        """
        result = self._result(response)
        products = result.get(VolcanoEngineResultField.LIST)
        products = products if isinstance(products, list) else []
        self.logger.info(
            "%s page %s: %d products (%s in total).",
            self.name,
            response.url,
            len(products),
            result.get(VolcanoEngineResultField.TOTAL),
        )
        for product in map(self._as_object, products):
            if (software := self._product_software(product)) is not None:
                yield software

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Read the category tree, or stream the software of a page of products then request the next page.

        Args:
            response (Response): The category tree (`CATEGORIES` meta) or a page of products.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each software not streamed yet, then the next page request.

        Raises:
            CatalogueFormatError: If a response is not JSON or has no `List`.
            EmptyCatalogueError: If the first page holds no software.
        """
        if response.meta.get(self.CATEGORIES):
            self.logger.debug("Reading the %s categories of %s.", self.name, response.url)
            self._read_categories(response)
            return
        self.logger.debug("Reading the %s listings page %s.", self.name, response.meta.get(self.PAGE))
        async for item in super().parse(response):
            yield item
        if (request := self._next_request(response)) is not None:
            yield request
