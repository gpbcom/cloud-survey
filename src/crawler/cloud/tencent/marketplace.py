from __future__ import annotations

# Standard Library Imports.
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Set, Union
from zoneinfo import ZoneInfo

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.marketplace_software import MarketplaceSoftware


class TencentMarketplaceCrawler(BaseMarketplaceCrawler):
    """Tencent Cloud international marketplace crawler.

    Attributes:
        HOST (ClassVar[str]): The Tencent Cloud international website.
        CLASSES_URL (ClassVar[str]): The marketplace product classes, with their families (top categories).
        PRODUCTS_URL (ClassVar[str]): The marketplace product list, by page.
        MARKET_URL (ClassVar[str]): The marketplace home page, whose Next.js data holds the SPU goods.
        PAGE_SIZE (ClassVar[int]): The number of products requested per page.
        SOURCE (ClassVar[str]): The meta key telling the source of a page: `CLASSES`, `PRODUCTS` or `GOODS`.
        PAGE (ClassVar[str]): The meta key holding the number of a product list page.
        CLASSES (ClassVar[str]): The source of the product classes.
        PRODUCTS (ClassVar[str]): The source of the product list.
        GOODS (ClassVar[str]): The source of the SPU goods.
        SAAS_CATEGORY (ClassVar[str]): The product category of the SaaS products (`3` being the services).
        EXCLUDED_FAMILIES (ClassVar[FrozenSet[str]]): The product families which are not software.
        ONLINE (ClassVar[str]): The status of the SPU goods on sale.
        PLACEHOLDER_VENDORS (ClassVar[FrozenSet[str]]): The vendor accounts which hold the products of other
            publishers, not named as their publisher.
        PRODUCT_DATE (ClassVar[re.Pattern[str]]): The product identifiers starting with their creation time, e.g.
            `P20250925163210630227958` created on 2025-09-25 at 16:32:10.
        PRODUCT_TIMEZONE (ClassVar[ZoneInfo]): The timezone of the creation time of the product identifiers.
        class_families (Dict[str, str]): The family name of each product class name.
        listed_names (Set[str]): The normalized names of the listed products, to skip the same SPU goods.

    Notes:
        Every page is protected by the EdgeOne JavaScript challenge (`robots.txt` included): they are rendered by the
        stealth browser, waiting for the network to be idle. The crawl is a chain of three sources: the product
        classes (`/market/api/mid/listProductClassDics`), which give the family of each class, then the product list
        (`/market/api/mid/listProduct`, `prdList`), without the services (category `3`) and the professional
        services family, then the SPU goods of the marketplace home page (`__NEXT_DATA__`
        `props.pageProps.goodsInfo`), without the ones already listed. Every listed product belongs to the same
        vendor account (`PLACEHOLDER_VENDORS`), which is not their publisher: their publisher is left unknown, the
        product pages do not name it either. The SPU goods name their provider. No date is published: the creation
        date of a listed product is read from its identifier (`PRODUCT_DATE`), the SPU goods have none.
    """

    HOST: ClassVar[str] = "https://www.tencentcloud.com"
    CLASSES_URL: ClassVar[str] = f"{HOST}/market/api/mid/listProductClassDics"
    PRODUCTS_URL: ClassVar[str] = f"{HOST}/market/api/mid/listProduct?preview=0&pageIndex={{page}}&pageSize={{size}}"
    MARKET_URL: ClassVar[str] = f"{HOST}/market"
    PAGE_SIZE: ClassVar[int] = 100
    SOURCE: ClassVar[str] = "source"
    PAGE: ClassVar[str] = "page"
    CLASSES: ClassVar[str] = "classes"
    PRODUCTS: ClassVar[str] = "products"
    GOODS: ClassVar[str] = "goods"
    SAAS_CATEGORY: ClassVar[str] = "1"
    EXCLUDED_FAMILIES: ClassVar[FrozenSet[str]] = frozenset({"Professional Services"})
    ONLINE: ClassVar[str] = "onlined"
    PLACEHOLDER_VENDORS: ClassVar[FrozenSet[str]] = frozenset({"200022263022"})
    PRODUCT_DATE: ClassVar[re.Pattern[str]] = re.compile(r"^P(\d{14})\d+$")
    PRODUCT_TIMEZONE: ClassVar[ZoneInfo] = ZoneInfo("Asia/Shanghai")

    name = "tencent-marketplace"
    catalogue_url: ClassVar[str] = CLASSES_URL

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
        self.class_families: Dict[str, str] = {}
        self.listed_names: Set[str] = set()

    ############################
    # Internal Helpers Methods #
    ############################

    def _browser_request(self, url: str, source: str, page: Optional[int] = None) -> Request:
        """Build a browser request, passing the EdgeOne challenge.

        Args:
            url (str): The requested URL.
            source (str): The source of the page: `CLASSES`, `PRODUCTS` or `GOODS`.
            page (Optional[int]): The number of a product list page.

        Returns:
            Request: The request of the stealth browser, waiting for the network to be idle. The next product list
                pages and the home page may hold no new software.
        """
        meta: Dict[str, JsonValue] = {self.SOURCE: source}
        if page is not None:
            meta[self.PAGE] = page
        if source == self.GOODS or (page is not None and page > 1):
            meta[self.MAY_BE_EMPTY] = True
        return Request(
            url, sid=self._browser_session_id(), priority=self.PRIMARY_PRIORITY, meta=meta, network_idle=True
        )

    def _catalogue_request(self) -> Request:
        """Build the request of the product classes, the first source.

        Returns:
            Request: The browser request.
        """
        return self._browser_request(self.CLASSES_URL, self.CLASSES)

    def _products_request(self, page: int) -> Request:
        """Build the request of a product list page.

        Args:
            page (int): The page number, the first page being 1.

        Returns:
            Request: The browser request.
        """
        return self._browser_request(self.PRODUCTS_URL.format(page=page, size=self.PAGE_SIZE), self.PRODUCTS, page)

    def _as_list(self, value: JsonValue) -> List[JsonValue]:
        """Read a JSON value expected to be a list.

        Args:
            value (JsonValue): The JSON value.

        Returns:
            List[JsonValue]: The list, empty when the value is not a list.
        """
        return value if isinstance(value, list) else []

    def _read_classes(self, response: Response) -> None:
        """Read the family of each product class.

        Args:
            response (Response): The product classes.

        Raises:
            CatalogueFormatError: If the page is not JSON, or has no `data` list.
        """
        classes = self._as_object(self._json_body(response)).get("data")
        if not isinstance(classes, list):
            self.logger.error("The %s product classes %s have no `data` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the `data` list is missing")
        for entry in classes:
            item = self._as_object(entry)
            label, family = self._as_text(item.get("className")), self._as_text(item.get("familyName"))
            if label and family and not family.startswith("PCD"):
                self.class_families.setdefault(self._clean_text(label), self._clean_text(family))
        self.logger.info("%d %s product classes read.", len(self.class_families), self.name)

    def _products(self, response: Response) -> List[Dict[str, JsonValue]]:
        """Read the products of a product list page.

        Args:
            response (Response): The product list page.

        Returns:
            List[Dict[str, JsonValue]]: The products.

        Raises:
            CatalogueFormatError: If the page is not JSON, or has no `prdList` list.
        """
        products = self._as_object(self._json_body(response)).get("prdList")
        if not isinstance(products, list):
            self.logger.error("The %s product list %s has no `prdList` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the `prdList` list is missing")
        return [self._as_object(product) for product in products]

    def _classes(self, product: Dict[str, JsonValue]) -> List[str]:
        """Read the class names of a listed product.

        Args:
            product (Dict[str, JsonValue]): The product.

        Returns:
            List[str]: The class names, e.g. `Security`.
        """
        classes = [self._clean_text(label) for label in (self._as_text(product.get("classNames")) or "").split(",")]
        return [label for label in classes if label]

    def _service_reason(self, product: Dict[str, JsonValue]) -> Optional[str]:
        """Tell why a listed product is a service.

        Args:
            product (Dict[str, JsonValue]): The product.

        Returns:
            Optional[str]: The reason (service category, professional service class), `None` for a SaaS product.
        """
        if product.get("categoryID") != self.SAAS_CATEGORY:
            return f"category {product.get('categoryID')!r}, a service"
        if {self.class_families.get(label) for label in self._classes(product)} & self.EXCLUDED_FAMILIES:
            return "professional service"
        return None

    def _created_at(self, identifier: Optional[str], name: Optional[str]) -> Optional[datetime]:
        """Read the creation date of a listed product from its identifier.

        Args:
            identifier (Optional[str]): The product identifier, e.g. `P20250925163210630227958`.
            name (Optional[str]): The product name, for the logs.

        Returns:
            Optional[datetime]: The creation date in UTC, `None` when the identifier does not start with a valid date.

        Notes:
            The product list publishes no date, but its identifiers start with a `%Y%m%d%H%M%S` timestamp, assumed
            to be the creation time of the product in China Standard Time (`Asia/Shanghai`), the time of the Tencent
            Cloud servers: `P20250925163210630227958` is read as 2025-09-25T08:32:10Z. The SPU goods identifiers carry
            no date.
        """
        match = self.PRODUCT_DATE.match(identifier or "")
        if match is None:
            self.logger.debug("The product %r identifier %r holds no creation date.", name, identifier)
            return None
        try:
            created = datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
        except ValueError:
            self.logger.debug("Ignoring the invalid creation date of the product %r identifier %r.", name, identifier)
            return None
        return created.replace(tzinfo=self.PRODUCT_TIMEZONE).astimezone(UTC)

    def _product_software(
        self, product: Dict[str, JsonValue], url: Optional[str], identifier: Optional[str]
    ) -> Optional[MarketplaceSoftware]:
        """Build the software of a listed SaaS product.

        Args:
            product (Dict[str, JsonValue]): The product.
            url (Optional[str]): The product page.
            identifier (Optional[str]): The product identifier, which gives its creation date.

        Returns:
            Optional[MarketplaceSoftware]: The software, with its creation date when its identifier holds one, `None`
                for an invalid product.
        """
        classes = self._classes(product)
        families = [self.class_families[label] for label in classes if label in self.class_families]
        vendor = self._as_text(product.get("vendorID"))
        name = self._as_text(product.get("prdName"))
        software = self._build_software(
            name,
            self._as_text(product.get("introduce")),
            url=url,
            publisher=None if vendor in self.PLACEHOLDER_VENDORS else self._as_text(product.get("vendorName")),
            delivery=DeliveryMethod.SAAS,
            marketplace_categories=[*families, *classes],
            added_at=self._created_at(identifier, name),
        )
        if software is not None:
            self.listed_names.add(self._name_key(software.name))
        return software

    def _product_list(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a product list page, without the services.

        Args:
            response (Response): The product list page.

        Yields:
            MarketplaceSoftware: Each valid SaaS product.

        Raises:
            CatalogueFormatError: If the page is not JSON, or has no `prdList` list.

        Notes:
            A product may be listed once per class: it is a service when any of its listings is one, else its
            listings share the identifier (page and creation date) of the first one, so that their classes are merged.
        """
        products = self._products(response)
        services = {
            self._name_key(self._as_text(item.get("prdName")) or "") for item in products if self._service_reason(item)
        }
        identifiers: Dict[str, Optional[str]] = {}
        for product in products:
            name, identifier = self._as_text(product.get("prdName")), self._as_text(product.get("prdID"))
            if reason := self._service_reason(product):
                self.logger.debug("Skipping the product %r (%s).", name, reason)
                continue
            if self._name_key(name or "") in services:
                self.logger.debug("Skipping the product %r (also listed as a service).", name)
                continue
            first = identifiers.setdefault(self._name_key(name or ""), identifier)
            url = f"{self.HOST}/market/product/{first}" if first else None
            if (software := self._product_software(product, url, first)) is not None:
                yield software

    def _goods(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the SPU goods of the marketplace home page, without the listed products.

        Args:
            response (Response): The marketplace home page.

        Yields:
            MarketplaceSoftware: Each valid SPU goods on sale.

        Raises:
            CatalogueFormatError: If the page has no Next.js data, or no `props.pageProps.goodsInfo` list.
        """
        props = self._as_object(self._as_object(self._next_data(response).get("props")).get("pageProps"))
        goods = props.get("goodsInfo")
        if not isinstance(goods, list):
            self.logger.error("The %s page %s has no `goodsInfo` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "`props.pageProps.goodsInfo` is not a list")
        for entry in goods:
            item = self._as_object(entry)
            basic, detail = self._as_object(item.get("GoodsBasicInfo")), self._as_object(item.get("GoodsDetailInfo"))
            name, status = self._as_text(detail.get("GoodsName")) or "", basic.get("Status", self.ONLINE)
            if status != self.ONLINE:
                self.logger.debug("Skipping the goods %r (status %r).", name, status)
                continue
            if self._name_key(name) in self.listed_names:
                self.logger.debug("Skipping the goods %r (already listed).", name)
                continue
            spu = self._as_text(basic.get("SpuId"))
            categories = [
                self._as_object(category).get("CategoryName") for category in self._as_list(detail.get("CategoryList"))
            ]
            software = self._build_software(
                name,
                self._as_text(detail.get("GoodsDescription")),
                url=f"{self.HOST}/market/detail/{spu}" if spu else None,
                publisher=self._as_text(self._as_object(item.get("GoodsProviderInfo")).get("ProviderName")),
                delivery=DeliveryMethod.OTHER,
                marketplace_categories=[label for label in categories if isinstance(label, str)],
            )
            if software is not None:
                yield software

    def _next_requests(self, response: Response) -> Iterator[Request]:
        """Request the next product list page, else the marketplace home page.

        Args:
            response (Response): A product list page.

        Yields:
            Request: The next product list page request while pages are full, else the home page request.

        Raises:
            CatalogueFormatError: If the page is not JSON, or has no `prdList` list.
        """
        page = int(str(response.meta.get(self.PAGE, 1)))
        count = len(self._products(response))
        total = self._as_object(self._json_body(response)).get("pageCount")
        total_count = int(total) if isinstance(total, (int, str)) and str(total).isdigit() else count
        self.logger.info("%s product list page %d: %d products of %d.", self.name, page, count, total_count)
        if count == self.PAGE_SIZE and page * self.PAGE_SIZE < total_count and self._within_page_limit(page + 1):
            yield self._products_request(page + 1)
            return
        yield self._browser_request(self.MARKET_URL, self.GOODS)

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a product list page, or the SPU goods of the marketplace home page.

        Args:
            response (Response): The product list page (`PRODUCTS` source), or the home page (`GOODS` source).

        Returns:
            Iterator[MarketplaceSoftware]: The valid software of the page.

        Raises:
            CatalogueFormatError: If the page has no product list, or no SPU goods list.
        """
        if response.meta.get(self.SOURCE) == self.GOODS:
            return self._goods(response)
        return self._product_list(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Read the product classes, or stream the software of a product list page or of the home page.

        Args:
            response (Response): The product classes, a product list page or the marketplace home page.

        Yields:
            Union[Dict[str, JsonValue], Request]: The first product list page request of the product classes, the
                software of a product list page then the next page (or home page) request, the SPU goods.

        Raises:
            CatalogueFormatError: If a page is not in the expected format.
        """
        source = response.meta.get(self.SOURCE, self.CLASSES)
        if source == self.CLASSES:
            self._read_classes(response)
            yield self._products_request(1)
            return
        async for item in super().parse(response):
            yield item
        if source == self.PRODUCTS:
            for request in self._next_requests(response):
                yield request
