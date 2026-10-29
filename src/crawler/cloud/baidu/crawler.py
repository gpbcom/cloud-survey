from __future__ import annotations

# Standard Library Imports.
import re
from decimal import Decimal
from pathlib import Path
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
    BaiduPriceField,
    BaiduProductType,
)
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class BaiduAICloudCrawler(BaseCloudCrawler):
    """Baidu AI Cloud (百度智能云) catalogue crawler.

    Attributes:
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The catalogue links which are not product pages: solutions,
            console pages and third-party marketplace offers.
        LINK_PADDING (ClassVar[re.Pattern[str]]): The spaces (raw or encoded) around some catalogue links.
        TITLE_SUFFIX (ClassVar[BaiduPageTitle]): The brand suffix of the page titles.
        CALCULATOR_URL (ClassVar[str]): The BCC page of the price calculator, the referrer its API expects.
        PRICE_HEADERS (ClassVar[Dict[str, str]]): The headers of the price session (the calculator as referrer).
        FLAVORS_URL (ClassVar[str]): The calculator API listing the BCC flavors of a region (POST, no key).
        PRICES_URL (ClassVar[str]): The calculator API pricing one BCC flavor (POST, no key).
        PRICE_REGIONS (ClassVar[Tuple[str, ...]]): The regions priced: Beijing (the mainland price) and Hong Kong.
        PREPAY_TERMS (ClassVar[Tuple[Tuple[int, PriceTerm], ...]]): The prepaid lengths priced: their months and
            term.
        INSTANCE_DEFAULTS (ClassVar[Dict[str, JsonValue]]): The fixed part of an instance to price (no accelerator
            card beyond its GPUs, the smallest system disk).
        SYSTEM_DISK (ClassVar[str]): The system disk storage type priced with the instance (the calculator prices
            every flavor with it, and refuses the types a flavor lists under other names).
        BCC_SERVICE (ClassVar[str]): The service of the CPU instances.
        GPU_SERVICE (ClassVar[str]): The service of the GPU instances.
        GPU_CATEGORY (ClassVar[str]): The product category of the GPU flavors.
        PRICE_NAV_URL (ClassVar[str]): The navigation of the product price pages (JSON: categories of products, each
            with its name and its price page or calculator).
        PRICE_PAGE_PATH (ClassVar[str]): The path of a product price page (the others being calculators).
        NAV_META (ClassVar[str]): The request meta marking the navigation request.
        REGION_META (ClassVar[str]): The request meta holding the region of a call.
        FLAVOR_META (ClassVar[str]): The request meta holding the flavor of a price call.
        MONTHS_META (ClassVar[str]): The request meta holding the prepaid months of a price call.
        price_pending (int): The calls not answered yet, in price mode.
        price_rows (int): The prices read, in price mode.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): The catalogue product pages are read too, for their prices.
        PAGE_TEXT_PRICES (ClassVar[bool]): A product page without price table is read for the prices in its text.

    Notes:
        The main source is the Next.js data of the https://cloud.baidu.com/products/index.html page
        (`props.pageProps.newProductsList`): a tree of top groups, categories and sub-categories (`list`) holding
        the products (`name`, `desc`, `link`). The sub-categories without products but with a link are products
        themselves: their pages are requested, named after the sub-category, and described by their meta
        description. The names and descriptions are in Chinese. A product gets the labels of the top group, category
        and sub-category (e.g. `云计算` > `计算`) of every sub-category it is listed under.
        In price mode it reads the BCC prices, in yuan, from the API of the price calculator: the flavors of each
        region, then one call per flavor and charge type (and prepaid length), the instance part of its answer
        being its price. Pay-as-you-go prices are per minute. Prepaid prices are for a month, then 1 and 3 years
        paid at once (per month, their factor being their months). A flavor priced in several zones is priced once.
        A flavor the API refuses to price is skipped. The API is one source, recorded once every call is answered.
        The product price pages listed by the price navigation (`product-price/<x>.html`, e.g. CDN, CFC, GPU
        servers) are read too, their tables priced by the base reader of product pages, named after the
        navigation entry.
    """

    NOT_PRODUCT_LINK: ClassVar[re.Pattern[str]] = re.compile(
        r"/solution/|console\.bce\.baidu\.com|market\.baidu\.com", re.IGNORECASE
    )
    LINK_PADDING: ClassVar[re.Pattern[str]] = re.compile(r"^(?:\s|%20)+|(?:\s|%20)+$")
    TITLE_SUFFIX: ClassVar[BaiduPageTitle] = BaiduPageTitle.BRAND_SUFFIX
    CALCULATOR_URL: ClassVar[str] = "https://cloud.baidu.com/price/calculator?product=bcc"
    PRICE_HEADERS: ClassVar[Dict[str, str]] = {"Referer": CALCULATOR_URL, "Origin": "https://cloud.baidu.com"}
    FLAVORS_URL: ClassVar[str] = "https://cloud.baidu.com/api/calculator/bccFlavor"
    PRICES_URL: ClassVar[str] = "https://cloud.baidu.com/api/calculator/bcc/instance/priceV2"
    PRICE_REGIONS: ClassVar[Tuple[str, ...]] = ("bj", "hkg")
    PREPAY_TERMS: ClassVar[Tuple[Tuple[int, PriceTerm], ...]] = (
        (1, PriceTerm.MONTH),
        (12, PriceTerm.ONE_YEAR),
        (36, PriceTerm.THREE_YEARS),
    )
    INSTANCE_DEFAULTS: ClassVar[Dict[str, JsonValue]] = {
        "rootDiskSizeInGb": 40,
        "kunlunCard": "",
        "kunlunCount": 0,
        "fpgaCard": "",
        "fpgaCount": 0,
        "containsFpga": True,
        "ephemeralSizeGb": 0,
    }
    SYSTEM_DISK: ClassVar[str] = "enhanced_ssd_pl1"
    BCC_SERVICE: ClassVar[str] = "云服务器 BCC"
    GPU_SERVICE: ClassVar[str] = "GPU云服务器"
    GPU_CATEGORY: ClassVar[str] = "gpu"
    PRICE_NAV_URL: ClassVar[str] = "https://bce.bdstatic.com/portal-cms/online/product-price/nav.js"
    PRICE_PAGE_PATH: ClassVar[str] = "/product-price/"
    NAV_META: ClassVar[str] = "price_nav"
    REGION_META: ClassVar[str] = "price_region"
    FLAVOR_META: ClassVar[str] = "price_flavor"
    MONTHS_META: ClassVar[str] = "price_months"

    PRODUCT_PAGE_PRICES: ClassVar[bool] = True
    PAGE_TEXT_PRICES: ClassVar[bool] = True
    name = "baidu"
    catalogue_url: ClassVar[str] = "https://cloud.baidu.com/products/index.html"
    name_prefixes: ClassVar[Tuple[str, ...]] = ("百度智能云", "百度", "Baidu AI Cloud ", "Baidu ")

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.price_pending = 0
        self.price_rows = 0

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
        self.logger.debug(
            "%d %s catalogue entries, %d distinct names, in %s.", len(entries), self.name, len(categories), response.url
        )
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

    def _api_result(self, response: Response) -> Optional[JsonValue]:
        """Read the result of a calculator API call.

        Args:
            response (Response): The answer.

        Returns:
            Optional[JsonValue]: Its result, or None when the API refused the call.

        Raises:
            CatalogueFormatError: If the answer is not a JSON object.
        """
        data = self._json_body(response)
        if not isinstance(data, dict):
            self.logger.error("The %s price calculator answered %s with no object.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the price calculator answered with no object")
        if data.get(BaiduPriceField.SUCCESS) is not True:
            return None
        return data.get(BaiduPriceField.RESULT)

    def _flavors(self, result: JsonValue) -> List[Dict[str, JsonValue]]:
        """Read the flavors of a region, each charge type of a specification once.

        Args:
            result (JsonValue): The result of the flavors call.

        Returns:
            List[Dict[str, JsonValue]]: The flavors, the first zone listing a specification and charge type kept.
        """
        flavors: Dict[Tuple[str, str], Dict[str, JsonValue]] = {}
        zones = result.get(BaiduPriceField.ZONE_RESOURCES) if isinstance(result, dict) else None
        for zone in zones if isinstance(zones, list) else []:
            resources = zone.get(BaiduPriceField.BCC_RESOURCES) if isinstance(zone, dict) else None
            groups = resources.get(BaiduPriceField.FLAVOR_GROUPS) if isinstance(resources, dict) else None
            for group in groups if isinstance(groups, list) else []:
                listed = group.get(BaiduPriceField.FLAVORS) if isinstance(group, dict) else None
                for flavor in listed if isinstance(listed, list) else []:
                    if not isinstance(flavor, dict):
                        continue
                    spec, kind = flavor.get(BaiduPriceField.SPEC), flavor.get(BaiduPriceField.PRODUCT_TYPE)
                    if isinstance(spec, str) and spec and isinstance(kind, str):
                        flavors.setdefault((spec, kind), flavor)
        return list(flavors.values())

    def _instance(self, flavor: Dict[str, JsonValue], kind: str) -> Dict[str, JsonValue]:
        """Build the instance to price of a flavor.

        Args:
            flavor (Dict[str, JsonValue]): The flavor.
            kind (str): Its charge type.

        Returns:
            Dict[str, JsonValue]: The `bcc` part of a price call.
        """
        return {
            **self.INSTANCE_DEFAULTS,
            "cpu": flavor.get(BaiduPriceField.CPU_COUNT),
            "memory": flavor.get(BaiduPriceField.MEMORY),
            "gpuCard": flavor.get(BaiduPriceField.GPU_CARD_TYPE) or "",
            "gpuCount": flavor.get(BaiduPriceField.GPU_CARD_COUNT) or 0,
            "productType": kind,
            "rootDiskStorageType": self.SYSTEM_DISK,
            "spec": flavor.get(BaiduPriceField.SPEC),
            "specId": flavor.get(BaiduPriceField.SPEC_ID),
            "instanceType": flavor.get(BaiduPriceField.INSTANCE_TYPE),
        }

    def _price_calls(self, flavor: Dict[str, JsonValue], region: str) -> Iterator[Request]:
        """Build the counted price calls of a flavor: once pay as you go, once per prepaid length.

        Args:
            flavor (Dict[str, JsonValue]): The flavor.
            region (str): Its region.

        Yields:
            Request: The POST price calls.
        """
        kind = str(flavor.get(BaiduPriceField.PRODUCT_TYPE))
        lengths = [months for months, _ in self.PREPAY_TERMS] if kind == BaiduProductType.PREPAY else [1]
        for months in lengths:
            self.price_pending += 1
            body: Dict[str, JsonValue] = {
                "bcc": self._instance(flavor, kind),
                "cds": {"diskConfigs": [], "productType": kind},
                "purchaseLength": months,
                "purchaseNum": 1,
                "region": region,
            }
            meta: Dict[str, JsonValue] = {self.REGION_META: region, self.FLAVOR_META: flavor, self.MONTHS_META: months}
            yield self._price_request(self.PRICES_URL, meta, body)

    def _flavor_price(self, result: JsonValue, meta: Dict[str, JsonValue]) -> Optional[ServicePrice]:
        """Read the price of a flavor, the instance part of a price call.

        Args:
            result (JsonValue): The result of the call.
            meta (Dict[str, JsonValue]): The request meta (the region, flavor and prepaid months).

        Returns:
            Optional[ServicePrice]: Its price per minute (pay as you go) or for its prepaid months, None without
                price.
        """
        paid = result.get(BaiduPriceField.PAY_PRICE) if isinstance(result, dict) else None
        flavor, region, months = meta.get(self.FLAVOR_META), meta.get(self.REGION_META), meta.get(self.MONTHS_META)
        amount = paid.get(BaiduPriceField.PRICE) if isinstance(paid, dict) else None
        if not isinstance(paid, dict) or not isinstance(flavor, dict) or not isinstance(amount, (int, float)):
            return None
        price = Decimal(str(amount))
        listed = paid.get(BaiduPriceField.CATALOG_PRICE)
        kind = flavor.get(BaiduPriceField.PRODUCT_TYPE)
        prepaid = kind == BaiduProductType.PREPAY and isinstance(months, int)
        attributes: Dict[str, JsonValue] = {
            field.value: flavor.get(field)
            for field in (
                BaiduPriceField.SPEC_FAMILY,
                BaiduPriceField.CPU_MODEL,
                BaiduPriceField.GPU_CARD_TYPE,
                BaiduPriceField.GPU_CARD_COUNT,
                BaiduPriceField.STATUS,
            )
            if flavor.get(field)
        }
        if isinstance(listed, (int, float)) and Decimal(str(listed)) != price:
            attributes[BaiduPriceField.CATALOG_PRICE.value] = listed
        cpu, memory = flavor.get(BaiduPriceField.CPU_COUNT), flavor.get(BaiduPriceField.MEMORY)
        term = next((term for length, term in self.PREPAY_TERMS if length == months), PriceTerm.NONE)
        fields: Dict[str, RawValue] = {
            "sku_key": f"{region}/{flavor.get(BaiduPriceField.SPEC)}/{kind}/{months if prepaid else 0}",
            "service": self.GPU_SERVICE
            if flavor.get(BaiduPriceField.PRODUCT_CATEGORY) == self.GPU_CATEGORY
            else self.BCC_SERVICE,
            "family": flavor.get(BaiduPriceField.INSTANCE_FAMILY) or None,
            "region": region,
            "instance_type": flavor.get(BaiduPriceField.SPEC),
            "vcpu": cpu if isinstance(cpu, int) and cpu > 0 else None,
            "memory_gib": memory if isinstance(memory, (int, float)) and memory > 0 else None,
            "attributes": attributes,
            "unit": PriceUnit.MONTH if prepaid else PriceUnit.MINUTE,
            "unit_raw": f"{months} months" if prepaid else PriceUnit.MINUTE.value,
            "unit_factor": Decimal(months) if prepaid and isinstance(months, int) else Decimal(1),
            "price": price,
            "currency": paid.get(BaiduPriceField.CURRENCY) or "CNY",
            "model": PriceModel.FREE if price == 0 else PriceModel.COMMITMENT if prepaid else PriceModel.ON_DEMAND,
            "term": term if prepaid else PriceTerm.NONE,
            "source_url": self.PRICES_URL,
            "source_kind": PriceSourceKind.CALCULATOR,
        }
        return self._price_fact(fields)

    def _price_pages(self, response: Response) -> Iterator[Request]:
        """Request the product price pages listed by the price navigation.

        Args:
            response (Response): The price navigation.

        Yields:
            Request: One request per product price page, named after its navigation entry.

        Raises:
            CatalogueFormatError: If the navigation is not a list of categories.
        """
        data = self._json_body(response)
        if not isinstance(data, list):
            self.logger.error("The %s price navigation %s is not a list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the price navigation is not a list")
        pages: Dict[str, str] = {}
        for category in data:
            products = category.get("products") if isinstance(category, dict) else None
            for product in products if isinstance(products, list) else []:
                name = product.get("name") if isinstance(product, dict) else None
                link = product.get("link") if isinstance(product, dict) else None
                if isinstance(name, str) and isinstance(link, str) and self.PRICE_PAGE_PATH in link:
                    pages.setdefault(link.split("?")[0], name.strip())
        self.logger.info("%d %s product price pages to read.", len(pages), self.name)
        for url, name in pages.items():
            yield self._price_request(url, {self.PRODUCT_PAGE_META: name})

    def _price_settled(self) -> None:
        """Count a call as answered, and record the API once every call is answered."""
        self.price_pending -= 1
        if self.price_pending == 0 and not self.price_failures:
            self._record_price_source(self.PRICES_URL, self.price_rows)
            self.logger.info("The %s BCC prices are read whole: %d prices.", self.name, self.price_rows)

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the price navigation, then the BCC flavors of each region priced.

        Yields:
            Request: The navigation request, then the flavors calls.
        """
        self.price_rows = 0
        self.price_pending = len(self.PRICE_REGIONS)
        self.logger.info("Reading the %s product price pages listed by %s.", self.name, self.PRICE_NAV_URL)
        yield self._price_request(self.PRICE_NAV_URL, {self.NAV_META: True})
        for region in self.PRICE_REGIONS:
            self.logger.info("Reading the %s BCC flavors of %s from %s.", self.name, region, self.FLAVORS_URL)
            yield self._price_request(
                self.FLAVORS_URL,
                {self.REGION_META: region},
                {"region": region, "ignoreReservedInstanceProductType": False},
            )

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read a flavors call, or a price call.

        Args:
            response (Response): The answer of the call.

        Yields:
            PriceFact: The product price pages of the navigation, the price calls of each flavor of a region, or
                the price of a flavor.

        Raises:
            CatalogueFormatError: If the answer is not a JSON object, a region lists no flavor, or the navigation
                is not a list.
        """
        meta: Dict[str, JsonValue] = dict(response.meta)
        if meta.get(self.NAV_META):
            for request in self._price_pages(response):
                yield request
            return
        region = str(meta.get(self.REGION_META))
        try:
            result = self._api_result(response)
            if self.FLAVOR_META not in meta:
                flavors = self._flavors(result)
                if not flavors:
                    self.logger.error("The %s price calculator lists no BCC flavor in %s.", self.name, region)
                    raise CatalogueFormatError(self.name, response.url, f"no BCC flavor listed in {region}")
                self.logger.info("Pricing %d %s BCC flavors of %s.", len(flavors), self.name, region)
                for flavor in flavors:
                    for request in self._price_calls(flavor, region):
                        yield request
            elif (fact := self._flavor_price(result, meta)) is not None:
                self.price_rows += 1
                yield fact
            else:
                refused = meta.get(self.FLAVOR_META)
                spec = refused.get(BaiduPriceField.SPEC) if isinstance(refused, dict) else None
                self.logger.warning("The %s price calculator refused to price %s in %s.", self.name, spec, region)
        except CatalogueFormatError:
            self.price_failures.add(response.url)
            raise
        finally:
            self._price_settled()

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
        self.logger.debug("Requesting the %s product pages of the sub-categories of %s.", self.name, response.url)
        for request in self._page_requests(response):
            yield request
