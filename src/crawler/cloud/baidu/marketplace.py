from __future__ import annotations

# Standard Library Imports.
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import quote, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.baidu.enums import (
    BaiduMarketplaceCategory,
    BaiduMarketplaceCrumbField,
    BaiduMarketplaceDelivery,
    BaiduMarketplaceErrorCode,
    BaiduMarketplaceInfoField,
    BaiduMarketplaceKind,
    BaiduMarketplaceListedField,
    BaiduMarketplaceMeta,
    BaiduMarketplaceProductField,
    BaiduMarketplaceRelatedField,
    BaiduMarketplaceResponseField,
    BaiduMarketplaceResultField,
    BaiduMarketplaceSitemapPath,
    BaiduMarketplaceSubcategory,
    BaiduMarketplaceTreeField,
    BaiduMarketplaceVendorField,
)
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class BaiduMarketplaceCrawler(BaseMarketplaceCrawler):
    """Baidu AI Cloud marketplace (百度智能云云市场) crawler.

    Attributes:
        SITE_URL (ClassVar[str]): The marketplace website.
        CATEGORY_URL (ClassVar[str]): The category tree API.
        SITEMAP_URL (ClassVar[str]): The marketplace sitemap, listing the product pages.
        LIST_URL (ClassVar[str]): The first page of the products of a category, formatted with its identifier.
        DETAIL_URL (ClassVar[str]): The product detail API, formatted with the product identifier.
        RELATED_URL (ClassVar[str]): The related products API, formatted with the product identifier.
        PRODUCT_URL (ClassVar[str]): The product page, formatted with the product identifier.
        DETAILS_PER_PAGE (ClassVar[int]): The product details requested per page of the page limit.
        KIND (ClassVar[BaiduMarketplaceMeta]): The meta key holding the kind of a response (`CATEGORIES`, `LIST`,
            `SITEMAP`, `DETAIL` or `RELATED`).
        PRODUCT (ClassVar[BaiduMarketplaceMeta]): The meta key holding the product identifier of a detail or related
            response.
        SHARE (ClassVar[BaiduMarketplaceMeta]): The meta key holding how many products of a category page are
            requested, under a page limit (the details are shared between the categories).
        CATEGORIES (ClassVar[BaiduMarketplaceKind]): The kind of the category tree.
        LIST (ClassVar[BaiduMarketplaceKind]): The kind of a category products page.
        SITEMAP (ClassVar[BaiduMarketplaceKind]): The kind of the sitemap.
        DETAIL (ClassVar[BaiduMarketplaceKind]): The kind of a product detail.
        RELATED (ClassVar[BaiduMarketplaceKind]): The kind of the related products of a product.
        DELISTED (ClassVar[BaiduMarketplaceErrorCode]): The error code of the detail of a delisted product.
        LIST_PRIORITY (ClassVar[int]): The priority of the category products pages.
        DETAIL_PRIORITY (ClassVar[int]): The priority of the details of the products found by the category pages and
            the related products.
        RELATED_PRIORITY (ClassVar[int]): The priority of the related products requests.
        SITEMAP_PRIORITY (ClassVar[int]): The priority of the sitemap and of the details of its products, read last.
        EXCLUDED_CATEGORIES (ClassVar[FrozenSet[BaiduMarketplaceCategory]]): The top categories which hold no
            software (services and hardware).
        EXCLUDED_SUBCATEGORIES (ClassVar[FrozenSet[Tuple[BaiduMarketplaceCategory, BaiduMarketplaceSubcategory]]]):
            The (top category, sub-category) pairs which hold no software (services, consulting and hardware).
        API_CATEGORY (ClassVar[BaiduMarketplaceCategory]): The top category of the APIs, data lookups except its AI
            sub-category.
        AI_API_SUBCATEGORY (ClassVar[BaiduMarketplaceSubcategory]): The sub-category of the AI APIs, the only APIs
            kept.
        SECURITY_CATEGORY (ClassVar[BaiduMarketplaceCategory]): The top category of the security offers, whose
            manual ones are services.
        MANUAL_DELIVERY (ClassVar[BaiduMarketplaceDelivery]): The manual delivery method (人工交付), a service in the
            security category.
        DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery method of each marketplace delivery method
            (`BaiduMarketplaceDelivery`).
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The category tree API, the crawl starting point.
        complement_urls (ClassVar[Tuple[str, ...]]): The sitemap, read once the other sources are exhausted.
        requested_products (Set[str]): The identifiers of the products whose detail was requested.

    Notes:
        The `robots.txt` of the marketplace disallows every URL with a query string (`Disallow: /*?*`), so the
        paginated product list API is not used. The products are found by three robots-compliant sources, without
        query string: the first page (10 products) of the products of each category
        (`/api/market/web/list/{cid}/products`), the related products of each software found
        (`/api/market/web/product/{pid}/related`), and the sitemap (`/detail/{pid}` pages, stale: most of them are
        delisted, and the recent products are missing). The detail of each product
        (`/api/market/web/product/{pid}/detail`) gives its title, digest, delivery method, vendor and categories
        (`crumbInfo`). A delisted product has no detail, only the `OFFLINE` error code. The cloud services, company
        services (registration, accounting...), robots, AI hardware, security services (consulting, testing,
        incident handling, manual services), custom website building, website hosting, website, shop and marketing
        operation services (SEO, promotion) and industrial maintenance services are skipped. So are the data
        lookup APIs (weather, express tracking, identity checks...): data products, unlike the AI APIs which are
        kept. The offline (`OFFLINE` delivery method, 线下交付) and manual (`MAN_MADE`, 人工交付) deliveries are
        installed or set up by the vendor: they are downloads. The page limit caps the number of product details
        requested (`DETAILS_PER_PAGE` per page), shared between the categories. The names and descriptions are in
        Chinese.
    """

    SITE_URL: ClassVar[str] = "https://market.baidu.com"
    CATEGORY_URL: ClassVar[str] = f"{SITE_URL}/api/market/web/get_category"
    SITEMAP_URL: ClassVar[str] = f"{SITE_URL}/sitemap.xml"
    LIST_URL: ClassVar[str] = SITE_URL + "/api/market/web/list/{}/products"
    DETAIL_URL: ClassVar[str] = SITE_URL + "/api/market/web/product/{}/detail"
    RELATED_URL: ClassVar[str] = SITE_URL + "/api/market/web/product/{}/related"
    PRODUCT_URL: ClassVar[str] = SITE_URL + "/detail/{}"
    DETAILS_PER_PAGE: ClassVar[int] = 50
    KIND: ClassVar[BaiduMarketplaceMeta] = BaiduMarketplaceMeta.KIND
    PRODUCT: ClassVar[BaiduMarketplaceMeta] = BaiduMarketplaceMeta.PRODUCT
    SHARE: ClassVar[BaiduMarketplaceMeta] = BaiduMarketplaceMeta.SHARE
    CATEGORIES: ClassVar[BaiduMarketplaceKind] = BaiduMarketplaceKind.CATEGORIES
    LIST: ClassVar[BaiduMarketplaceKind] = BaiduMarketplaceKind.LIST
    SITEMAP: ClassVar[BaiduMarketplaceKind] = BaiduMarketplaceKind.SITEMAP
    DETAIL: ClassVar[BaiduMarketplaceKind] = BaiduMarketplaceKind.DETAIL
    RELATED: ClassVar[BaiduMarketplaceKind] = BaiduMarketplaceKind.RELATED
    DELISTED: ClassVar[BaiduMarketplaceErrorCode] = BaiduMarketplaceErrorCode.OFFLINE
    LIST_PRIORITY: ClassVar[int] = 8
    DETAIL_PRIORITY: ClassVar[int] = 6
    RELATED_PRIORITY: ClassVar[int] = 4
    SITEMAP_PRIORITY: ClassVar[int] = 0
    EXCLUDED_CATEGORIES: ClassVar[FrozenSet[BaiduMarketplaceCategory]] = frozenset(
        {
            BaiduMarketplaceCategory.CLOUD_SERVICES,
            BaiduMarketplaceCategory.COMPANY_SERVICES,
            BaiduMarketplaceCategory.ROBOTS,
        }
    )
    EXCLUDED_SUBCATEGORIES: ClassVar[FrozenSet[Tuple[BaiduMarketplaceCategory, BaiduMarketplaceSubcategory]]] = (
        frozenset(
            {
                (BaiduMarketplaceCategory.ARTIFICIAL_INTELLIGENCE, BaiduMarketplaceSubcategory.HARDWARE),
                (BaiduMarketplaceCategory.SECURITY_SERVICES, BaiduMarketplaceSubcategory.SECURITY_CONSULTING),
                (BaiduMarketplaceCategory.SECURITY_SERVICES, BaiduMarketplaceSubcategory.SECURITY_TESTING),
                (BaiduMarketplaceCategory.SECURITY_SERVICES, BaiduMarketplaceSubcategory.INCIDENT_HANDLING),
                (BaiduMarketplaceCategory.BLOCKCHAIN, BaiduMarketplaceSubcategory.SECURITY_SERVICES),
                (BaiduMarketplaceCategory.WEBSITE_PROMOTION, BaiduMarketplaceSubcategory.CUSTOM_WEBSITE),
                (BaiduMarketplaceCategory.WEBSITE_PROMOTION, BaiduMarketplaceSubcategory.CONTENT_MAINTENANCE),
                (BaiduMarketplaceCategory.WEBSITE_PROMOTION, BaiduMarketplaceSubcategory.SHOP_OPERATION),
                (BaiduMarketplaceCategory.WEBSITE_PROMOTION, BaiduMarketplaceSubcategory.MARKETING_PROMOTION),
                (BaiduMarketplaceCategory.WEBSITE_PROMOTION, BaiduMarketplaceSubcategory.WEBSITE_HOSTING),
                (BaiduMarketplaceCategory.INDUSTRIAL_APPLICATIONS, BaiduMarketplaceSubcategory.MAINTENANCE_SERVICES),
            }
        )
    )
    API_CATEGORY: ClassVar[BaiduMarketplaceCategory] = BaiduMarketplaceCategory.API_SERVICES
    AI_API_SUBCATEGORY: ClassVar[BaiduMarketplaceSubcategory] = BaiduMarketplaceSubcategory.ARTIFICIAL_INTELLIGENCE
    SECURITY_CATEGORY: ClassVar[BaiduMarketplaceCategory] = BaiduMarketplaceCategory.SECURITY_SERVICES
    MANUAL_DELIVERY: ClassVar[BaiduMarketplaceDelivery] = BaiduMarketplaceDelivery.MAN_MADE
    DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        BaiduMarketplaceDelivery.SAAS_AUTO: DeliveryMethod.SAAS,
        BaiduMarketplaceDelivery.SAAS: DeliveryMethod.SAAS,
        BaiduMarketplaceDelivery.API: DeliveryMethod.API,
        BaiduMarketplaceDelivery.MIRROR: DeliveryMethod.VIRTUAL_MACHINE,
        BaiduMarketplaceDelivery.OFFLINE: DeliveryMethod.DOWNLOAD,
        BaiduMarketplaceDelivery.MAN_MADE: DeliveryMethod.DOWNLOAD,
    }

    name = "baidu-marketplace"
    catalogue_url: ClassVar[str] = CATEGORY_URL
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)

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
        self.requested_products: Set[str] = set()

    ############################
    # Internal Helpers Methods #
    ############################

    def _catalogue_request(self) -> Request:
        """Build the request of the category tree, read first.

        Returns:
            Request: The category tree request.
        """
        return Request(self.CATEGORY_URL, priority=self.PRIMARY_PRIORITY, meta={self.KIND: self.CATEGORIES})

    def _complement_request(self, url: str) -> Request:
        """Build the request of the sitemap, read once the other sources are exhausted.

        Args:
            url (str): The sitemap URL.

        Returns:
            Request: The sitemap request.
        """
        return Request(url, priority=self.SITEMAP_PRIORITY, meta={self.KIND: self.SITEMAP})

    def _json_result(self, response: Response) -> Dict[str, JsonValue]:
        """Read the `result` of an API response.

        Args:
            response (Response): The API response.

        Returns:
            Dict[str, JsonValue]: The result, empty when it is not an object.

        Raises:
            CatalogueFormatError: If the response is not JSON.
        """
        return self._as_object(self._as_object(self._json_body(response)).get(BaiduMarketplaceResponseField.RESULT))

    def _excluded(self, category: str, subcategory: str) -> bool:
        """Tell whether a category holds no software (services, hardware, data lookup APIs).

        Args:
            category (str): The top category name.
            subcategory (str): The sub-category name, empty for a top category.

        Returns:
            bool: Whether the category is skipped.
        """
        excluded = (
            category in self.EXCLUDED_CATEGORIES
            or (category, subcategory) in self.EXCLUDED_SUBCATEGORIES
            or (category == self.API_CATEGORY and subcategory != self.AI_API_SUBCATEGORY)
        )
        if excluded:
            self.logger.debug("Skipping the %s category %r > %r, it holds no software.", self.name, category, subcategory)
        return excluded

    def _detail_request(self, pid: Optional[str], priority: int) -> Optional[Request]:
        """Build the detail request of a product, unless it was already requested or the page limit is reached.

        Args:
            pid (Optional[str]): The product identifier.
            priority (int): The request priority.

        Returns:
            Optional[Request]: The detail request, `None` when not requested.
        """
        if not pid or pid in self.requested_products:
            return None
        if self.page_limit is not None and len(self.requested_products) >= self.page_limit * self.DETAILS_PER_PAGE:
            self.logger.debug(
                "Page limit (%d) reached: the %s product %s is not requested.", self.page_limit, self.name, pid
            )
            return None
        self.requested_products.add(pid)
        return Request(
            self.DETAIL_URL.format(quote(pid, safe="")),
            priority=priority,
            meta={self.KIND: self.DETAIL, self.PRODUCT: pid, self.MAY_BE_EMPTY: True},
        )

    def _list_requests(self, response: Response) -> Iterator[Request]:
        """Request the first products page of each category of the category tree which may hold software.

        Args:
            response (Response): The category tree.

        Yields:
            Iterator[Request]: Each category products page request.

        Raises:
            CatalogueFormatError: If the response is not JSON or holds no category.
        """
        data = self._as_object(self._json_body(response)).get(BaiduMarketplaceResponseField.RESULT)
        if not isinstance(data, list) or not data:
            self.logger.error("The %s category tree %s holds no category.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the category tree holds no category")
        identifiers: List[int] = []
        for category in map(self._as_object, data):
            name = self._clean_text(self._as_text(category.get(BaiduMarketplaceTreeField.NAME)))
            children = category.get(BaiduMarketplaceTreeField.CHILDREN)
            for child in map(self._as_object, children if isinstance(children, list) else []):
                subname, cid = (
                    self._clean_text(self._as_text(child.get(BaiduMarketplaceTreeField.NAME))),
                    child.get(BaiduMarketplaceTreeField.CID),
                )
                if self._excluded(name, subname) or not isinstance(cid, int):
                    self.logger.debug("Not requesting the %s category %s/%s.", self.name, name, subname)
                    continue
                identifiers.append(cid)
        meta: Dict[str, JsonValue] = {self.KIND: self.LIST}
        if self.page_limit is not None and identifiers:
            meta[self.SHARE] = max(1, self.page_limit * self.DETAILS_PER_PAGE // len(identifiers))
        for cid in identifiers:
            yield Request(self.LIST_URL.format(cid), priority=self.LIST_PRIORITY, meta=dict(meta))

    def _listed_requests(self, response: Response) -> Iterator[Request]:
        """Request the detail of each product of a category products page.

        Args:
            response (Response): The category products page.

        Yields:
            Iterator[Request]: Each product detail request.

        Raises:
            CatalogueFormatError: If the response is not JSON.
        """
        products = self._json_result(response).get(BaiduMarketplaceResultField.RESULT)
        products = products if isinstance(products, list) else []
        share = response.meta.get(self.SHARE)
        listed = products[:share] if isinstance(share, int) else products
        self.logger.debug("%d %s products listed by %s, %d read.", len(products), self.name, response.url, len(listed))
        for product in map(self._as_object, listed):
            if (
                request := self._detail_request(
                    self._as_text(product.get(BaiduMarketplaceListedField.PID)), self.DETAIL_PRIORITY
                )
            ) is not None:
                yield request

    def _sitemap_requests(self, response: Response) -> Iterator[Request]:
        """Request the detail of each product page of the sitemap.

        Args:
            response (Response): The sitemap.

        Yields:
            Iterator[Request]: Each product detail request.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        pids = [
            path[1]
            for path in (urlparse(url).path.strip("/").split("/") for url in self._sitemap_urls(response))
            if len(path) == 2 and path[0] == BaiduMarketplaceSitemapPath.DETAIL
        ]
        self.logger.info("%d product pages in the %s sitemap %s.", len(pids), self.name, response.url)
        for pid in pids:
            if (request := self._detail_request(pid, self.SITEMAP_PRIORITY)) is not None:
                yield request

    def _related_requests(self, response: Response) -> Iterator[Request]:
        """Request the detail of each related product.

        Args:
            response (Response): The related products of a product.

        Yields:
            Iterator[Request]: Each product detail request.

        Raises:
            CatalogueFormatError: If the response is not JSON.
        """
        for related in self._json_result(response).values():
            for product in map(self._as_object, related if isinstance(related, list) else []):
                pid = self._as_text(product.get(BaiduMarketplaceRelatedField.PRODUCT_ID))
                if (request := self._detail_request(pid, self.DETAIL_PRIORITY)) is not None:
                    yield request

    def _follow_up_requests(self, response: Response) -> Iterator[Request]:
        """Read a response which holds no software: the category tree, a products page, the sitemap or related products.

        Args:
            response (Response): The response.

        Yields:
            Iterator[Request]: The requests of the categories or of the product details.

        Raises:
            CatalogueFormatError: If the response is not JSON (the sitemap: lists no page), or if the category tree
                holds no category.
        """
        kind = response.meta.get(self.KIND)
        if response.status >= 400:
            self.logger.warning(
                "The %s %s response %s failed (HTTP %s).", self.name, kind, response.url, response.status
            )
            return
        match kind:
            case self.CATEGORIES:
                yield from self._list_requests(response)
            case self.LIST:
                yield from self._listed_requests(response)
            case self.SITEMAP:
                yield from self._sitemap_requests(response)
            case self.RELATED:
                yield from self._related_requests(response)
            case _:
                self.logger.debug("No follow-up request for the %s %s response %s.", self.name, kind, response.url)

    def _product(self, response: Response) -> Optional[Dict[str, JsonValue]]:
        """Read the product of a product detail.

        Args:
            response (Response): The product detail.

        Returns:
            Optional[Dict[str, JsonValue]]: The product (`productInfo`, `vendorInfo`, `crumbInfo`), `None` for a
                delisted product or a missing detail.

        Raises:
            CatalogueFormatError: If the response is not JSON.
        """
        pid = response.meta.get(self.PRODUCT)
        if response.status >= 400:
            self.logger.debug("Skipping the %s product %s (HTTP %s).", self.name, pid, response.status)
            return None
        result = self._json_result(response)
        product = self._as_object(result.get(BaiduMarketplaceResultField.PRODUCT))
        if not self._as_object(product.get(BaiduMarketplaceProductField.PRODUCT_INFO)):
            error_code = result.get(BaiduMarketplaceResultField.ERR_CODE)
            reason = "delisted" if error_code == self.DELISTED else f"no detail ({error_code})"
            self.logger.debug("Skipping the %s product %s, %s.", self.name, pid, reason)
            return None
        return product

    def _categories(self, product: Dict[str, JsonValue]) -> List[str]:
        """Read the categories of a product, from its breadcrumb.

        Args:
            product (Dict[str, JsonValue]): The product.

        Returns:
            List[str]: The top category then the sub-category names.
        """
        crumbs = product.get(BaiduMarketplaceProductField.CRUMB_INFO)
        crumbs = crumbs if isinstance(crumbs, list) else []
        names = [
            self._clean_text(self._as_text(self._as_object(crumb).get(BaiduMarketplaceCrumbField.NAME)))
            for crumb in crumbs
        ]
        return [name for name in names if name]

    def _category_path(self, product: Dict[str, JsonValue]) -> Optional[MarketplaceCategory]:
        """Build the marketplace category path of a product, from its breadcrumb.

        Args:
            product (Dict[str, JsonValue]): The product.

        Returns:
            Optional[MarketplaceCategory]: The breadcrumb names from the top category to the leaf, identified by the
                `cid` of the last named crumb, `None` without a named crumb.
        """
        crumbs = product.get(BaiduMarketplaceProductField.CRUMB_INFO)
        named = [
            crumb
            for crumb in map(self._as_object, crumbs if isinstance(crumbs, list) else [])
            if self._clean_text(self._as_text(crumb.get(BaiduMarketplaceCrumbField.NAME)))
        ]
        if not named:
            self.logger.debug("No named crumb in the %s product breadcrumb %r.", self.name, crumbs)
            return None
        cid = named[-1].get(BaiduMarketplaceCrumbField.CID)
        return self._category(
            [self._as_text(crumb.get(BaiduMarketplaceCrumbField.NAME)) for crumb in named],
            cid if isinstance(cid, (str, int)) else None,
        )

    def _detail_software(self, response: Response) -> Optional[MarketplaceSoftware]:
        """Build the software of a product detail, unless the product is delisted or not a software.

        Args:
            response (Response): The product detail.

        Returns:
            Optional[MarketplaceSoftware]: The software, `None` for a skipped (logged) or invalid product.

        Raises:
            CatalogueFormatError: If the response is not JSON.
        """
        product = self._product(response)
        if product is None:
            return None
        info = self._as_object(product.get(BaiduMarketplaceProductField.PRODUCT_INFO))
        name = self._as_text(info.get(BaiduMarketplaceInfoField.TITLE))
        delivery = self._as_text(info.get(BaiduMarketplaceInfoField.DELIVERY_METHOD)) or ""
        categories = self._categories(product)
        category, subcategory = [*categories, "", ""][:2]
        if self._excluded(category, subcategory):
            self.logger.debug("Skipping the %s product %r, not a software (%s).", self.name, name, "/".join(categories))
            return None
        if category == self.SECURITY_CATEGORY and delivery == self.MANUAL_DELIVERY:
            self.logger.debug("Skipping the %s product %r, a security service (manual delivery).", self.name, name)
            return None
        pid = self._as_text(info.get(BaiduMarketplaceInfoField.PID)) or str(response.meta.get(self.PRODUCT, ""))
        return self._build_software(
            name,
            self._as_text(info.get(BaiduMarketplaceInfoField.DIGEST)),
            self.PRODUCT_URL.format(pid) if pid else None,
            self._as_text(
                self._as_object(product.get(BaiduMarketplaceProductField.VENDOR_INFO)).get(
                    BaiduMarketplaceVendorField.VENDOR_NAME
                )
            ),
            self.DELIVERIES.get(delivery, DeliveryMethod.OTHER),
            categories,
            marketplace_category_paths=[self._category_path(product)],
        )

    def _related_request(self, response: Response) -> Optional[Request]:
        """Build the related products request of a product detail whose software was streamed.

        Args:
            response (Response): The product detail.

        Returns:
            Optional[Request]: The related products request, `None` for a product which is not a streamed software,
                or once the page limit is reached.
        """
        pid = self._as_text(response.meta.get(self.PRODUCT))
        if not pid or self.PRODUCT_URL.format(pid).casefold() not in self.software_categories:
            return None
        if self.page_limit is not None and len(self.requested_products) >= self.page_limit * self.DETAILS_PER_PAGE:
            self.logger.debug("Not requesting the %s related products of %s, the page limit is reached.", self.name, pid)
            return None
        self.logger.debug("Requesting the %s products related to %s.", self.name, pid)
        return Request(
            self.RELATED_URL.format(quote(pid, safe="")),
            priority=self.RELATED_PRIORITY,
            meta={self.KIND: self.RELATED, self.PRODUCT: pid},
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    async def on_start(self, resuming: bool = False) -> None:
        """Forget the products requested by a previous crawl, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if not resuming:
            self.logger.debug(
                "Forgetting the %d %s products requested before.", len(self.requested_products), self.name
            )
            self.requested_products.clear()
        else:
            self.logger.info(
                "Resuming the %s crawl with %d products already requested.", self.name, len(self.requested_products)
            )

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a product detail.

        Args:
            response (Response): The product detail (`DETAIL` kind).

        Yields:
            Iterator[MarketplaceSoftware]: The software, unless the product is delisted, invalid or not a software.

        Raises:
            CatalogueFormatError: If the response is not JSON.
        """
        if (software := self._detail_software(response)) is not None:
            yield software

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the software of a product detail and request its related products, or follow another response.

        Args:
            response (Response): A product detail, the category tree, a category products page, the sitemap or the
                related products of a product.

        Yields:
            Union[Dict[str, JsonValue], Request]: The software of a product detail then its related products request,
                or the category and product detail requests of another response.

        Raises:
            CatalogueFormatError: If a response is not JSON (the sitemap: lists no page), or if the category tree
                holds no category.
        """
        if response.meta.get(self.KIND) == self.DETAIL:
            async for item in super().parse(response):
                yield item
            if (request := self._related_request(response)) is not None:
                yield request
            return
        self.logger.debug("Parsing the %s page %s (HTTP %s).", self.name, response.url, response.status)
        requests = list(self._follow_up_requests(response))
        self.logger.info("%s page %s read: %d requests.", self.name, response.url, len(requests))
        for request in requests:
            yield request
