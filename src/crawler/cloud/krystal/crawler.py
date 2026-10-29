from __future__ import annotations

# Standard Library Imports.
import re
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.krystal.enums import (
    KrystalFooterColumn,
    KrystalHostingPeriod,
    KrystalPriceField,
    KrystalSitemapSection,
)
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
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
        CLOUD_URL (ClassVar[str]): The cloud pricing page, its Next.js data holding the packages, GPUs and unit
            prices.
        HOSTING_URL (ClassVar[str]): The hosting page, its Next.js data holding the hosting plans.
        PRICE_CURRENCY (ClassVar[str]): The currency read (the website shows pounds, the same numbers in every
            currency).
        RESOURCE_UNITS (ClassVar[Dict[str, PriceUnit]]): The unit of each unit price of a cloud resource, by path.
        HOSTING_PERIODS (ClassVar[Tuple[Tuple[KrystalHostingPeriod, int, PriceTerm], ...]]): The billing periods of
            a hosting plan: their months and term.
        GB (ClassVar[re.Pattern[str]]): A memory, e.g. `2GB`.
        PACKAGES_KEY (ClassVar[str]): The key part of a package price.
        MONTH_UNIT (ClassVar[str]): The unit written for a monthly price.
        CLOUD_SERVICE (ClassVar[str]): The service of the cloud prices.
        GPU_SERVICE (ClassVar[str]): The service of the GPU prices.
        HOSTING_SERVICE (ClassVar[str]): The service of the hosting plans.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): The catalogue product pages are read too, for their price tables.
        PAGE_TEXT_PRICES (ClassVar[bool]): A product page without price table is read for the prices in its text.

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
        In price mode it reads the Next.js data of the cloud pricing page (`CLOUD_URL`: the monthly price of each
        virtual machine package and GPU, then the unit prices of the resources, a package's storage being billed
        at the block storage price, which the page adds to the package price it displays) and of the hosting page
        (`HOSTING_URL`: each plan monthly, yearly and biennially), in pounds. Each page is a source.
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

    PRODUCT_PAGE_PRICES: ClassVar[bool] = True
    PAGE_TEXT_PRICES: ClassVar[bool] = True
    name = "krystal"
    catalogue_url: ClassVar[str] = "https://krystal.io/cloud/products"
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_PAGE_URL, SITEMAP_URL)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Krystal Cloud ", "Krystal ", "Katapult ")
    CLOUD_URL: ClassVar[str] = "https://krystal.io/cloud/pricing"
    HOSTING_URL: ClassVar[str] = "https://krystal.io/hosting"
    PRICE_CURRENCY: ClassVar[str] = "GBP"
    RESOURCE_UNITS: ClassVar[Dict[str, PriceUnit]] = {
        "backups": PriceUnit.GIB_MONTH,
        "blockStorage": PriceUnit.GIB_MONTH,
        "containerRegistry.transfer": PriceUnit.GIB,
        "containerRegistry.usage": PriceUnit.GIB_MONTH,
        "dataTransfer": PriceUnit.GIB,
        "fileStorage": PriceUnit.GIB_MONTH,
        "ipAddress": PriceUnit.UNIT_MONTH,
        "isoStorage": PriceUnit.GIB_MONTH,
        "loadBalancer": PriceUnit.MONTH,
        "objectStorage.base": PriceUnit.MONTH,
        "objectStorage.transfer": PriceUnit.GIB,
        "objectStorage.usage": PriceUnit.GIB_MONTH,
    }
    HOSTING_PERIODS: ClassVar[Tuple[Tuple[KrystalHostingPeriod, int, PriceTerm], ...]] = (
        (KrystalHostingPeriod.MONTHLY, 1, PriceTerm.NONE),
        (KrystalHostingPeriod.ANNUALLY, 12, PriceTerm.ONE_YEAR),
        (KrystalHostingPeriod.BIENNIALLY, 24, PriceTerm.TWO_YEARS),
    )
    GB: ClassVar[re.Pattern[str]] = re.compile(r"^(\d+(?:\.\d+)?)\s*GB$")
    PACKAGES_KEY: ClassVar[str] = "packages"
    MONTH_UNIT: ClassVar[str] = "month"
    CLOUD_SERVICE: ClassVar[str] = "Katapult Cloud"
    GPU_SERVICE: ClassVar[str] = "Katapult GPUs"
    HOSTING_SERVICE: ClassVar[str] = "Website Hosting"

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)

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

    def _currency_price(self, prices: JsonValue) -> Optional[Decimal]:
        """Find the price in pounds of a list of prices by currency.

        Args:
            prices (JsonValue): The prices, e.g. `[{"price": 8.5, "currency": {"iso_code": "GBP"}}]`.

        Returns:
            Optional[Decimal]: The price in pounds, `None` when missing.
        """
        for entry in prices if isinstance(prices, list) else []:
            currency = entry.get(KrystalPriceField.CURRENCY) if isinstance(entry, dict) else None
            code = currency.get(KrystalPriceField.ISO_CODE) if isinstance(currency, dict) else None
            value = entry.get(KrystalPriceField.PRICE) if isinstance(entry, dict) else None
            if code == self.PRICE_CURRENCY and isinstance(value, (int, float)):
                return Decimal(str(value))
        return None

    def _priced(self, fields: Dict[str, RawValue], price: Optional[Decimal]) -> Optional[ServicePrice]:
        """Build a price in pounds.

        Args:
            fields (Dict[str, RawValue]): The fields of the price, its price aside.
            price (Optional[Decimal]): The price, if any.

        Returns:
            Optional[ServicePrice]: The price, `None` without price.
        """
        if price is None:
            self.logger.debug("The Krystal price %s has no price in pounds: skipped.", fields.get("sku_key"))
            return None
        return self._price_fact(
            {
                "currency": self.PRICE_CURRENCY,
                "source_kind": PriceSourceKind.CALCULATOR,
                "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
                **fields,
                "price": price,
            }
        )

    def _cloud_prices(self, props: Dict[str, JsonValue]) -> Iterator[ServicePrice]:
        """Read the cloud prices: the packages, the GPUs and the unit prices of the resources, monthly.

        Args:
            props (Dict[str, JsonValue]): The page properties of the cloud pricing page.

        Yields:
            ServicePrice: A monthly price per package and per GPU (the storage of a package being billed apart),
                then each unit price of a resource.
        """
        packages = props.get(KrystalPriceField.PACKAGES)
        for group, listed in (packages if isinstance(packages, dict) else {}).items():
            for package in listed if isinstance(listed, list) else []:
                if not isinstance(package, dict):
                    continue
                pricing = package.get(KrystalPriceField.PRICING)
                first = pricing[0] if isinstance(pricing, list) and pricing else None
                name = package.get(KrystalPriceField.NAME)
                fact = self._priced(
                    {
                        "sku_key": f"{self.PACKAGES_KEY}/{group}/{name}",
                        "service": self.CLOUD_SERVICE,
                        "family": group,
                        "instance_type": name,
                        "vcpu": package.get(KrystalPriceField.CPU_CORES),
                        "memory_gib": package.get(KrystalPriceField.MEMORY_IN_GB),
                        "storage_gib": package.get(KrystalPriceField.STORAGE_IN_GB),
                        "unit": PriceUnit.MONTH,
                        "unit_raw": self.MONTH_UNIT,
                        "source_url": self.CLOUD_URL,
                    },
                    self._currency_price(first.get(KrystalPriceField.PRICES) if isinstance(first, dict) else None),
                )
                if fact is not None:
                    yield fact
        gpus = props.get(KrystalPriceField.GPUS)
        for gpu in gpus if isinstance(gpus, list) else []:
            if not isinstance(gpu, dict):
                continue
            fact = self._priced(
                {
                    "sku_key": f"{KrystalPriceField.GPUS.value}/{gpu.get(KrystalPriceField.NAME)}",
                    "service": self.GPU_SERVICE,
                    "family": KrystalPriceField.GPUS.value,
                    "instance_type": gpu.get(KrystalPriceField.NAME),
                    "unit": PriceUnit.MONTH,
                    "unit_raw": self.MONTH_UNIT,
                    "source_url": self.CLOUD_URL,
                },
                self._currency_price(gpu.get(KrystalPriceField.PRICES)),
            )
            if fact is not None:
                yield fact
        resources = props.get(KrystalPriceField.PRICE)
        for path, unit in self.RESOURCE_UNITS.items():
            value: JsonValue = resources
            for part in path.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            fact = self._priced(
                {
                    "sku_key": f"{KrystalPriceField.PRICE.value}/{path}",
                    "service": self.CLOUD_SERVICE,
                    "family": path.split(".")[0],
                    "unit": unit,
                    "unit_raw": unit.value,
                    "source_url": self.CLOUD_URL,
                },
                Decimal(str(value)) if isinstance(value, (int, float)) else None,
            )
            if fact is not None:
                yield fact

    def _hosting_prices(self, props: Dict[str, JsonValue]) -> Iterator[ServicePrice]:
        """Read the prices of the hosting plans: monthly, then for a year or two paid at once.

        Args:
            props (Dict[str, JsonValue]): The page properties of the hosting page.

        Yields:
            ServicePrice: A price per plan and period (a longer period a commitment, per month, its factor being
                its months).
        """
        plans = props.get(KrystalPriceField.PLANS)
        for plan in plans if isinstance(plans, list) else []:
            if not isinstance(plan, dict):
                continue
            performance = plan.get(KrystalPriceField.PERFORMANCE)
            cpu = performance.get(KrystalPriceField.CPU) if isinstance(performance, dict) else None
            ram = performance.get(KrystalPriceField.RAM) if isinstance(performance, dict) else None
            memory = self.GB.match(ram) if isinstance(ram, str) else None
            prices = plan.get(KrystalPriceField.PRICES)
            identifier = plan.get(KrystalPriceField.IDENTIFIER)
            for period, months, term in self.HOSTING_PERIODS:
                value = prices.get(period) if isinstance(prices, dict) else None
                fact = self._priced(
                    {
                        "sku_key": f"{KrystalPriceField.PLANS.value}/{identifier}/{period.value}",
                        "service": self.HOSTING_SERVICE,
                        "family": KrystalPriceField.PLANS.value,
                        "instance_type": plan.get(KrystalPriceField.NAME),
                        "vcpu": cpu if isinstance(cpu, int) else None,
                        "memory_gib": memory[1] if memory else None,
                        "unit": PriceUnit.MONTH,
                        "unit_raw": period.value,
                        "unit_factor": Decimal(months),
                        "term": term,
                        "model": PriceModel.COMMITMENT if months > 1 else PriceModel.ON_DEMAND,
                        "source_url": self.HOSTING_URL,
                    },
                    Decimal(str(value)) if isinstance(value, (int, float)) else None,
                )
                if fact is not None:
                    yield fact

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the cloud pricing page and the hosting page.

        Yields:
            Request: The request of each page.
        """
        for url in (self.CLOUD_URL, self.HOSTING_URL):
            self.logger.info("Reading the Krystal prices of %s.", url)
            yield self._price_request(url)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the prices of the Next.js data of a pricing page.

        Args:
            response (Response): The cloud pricing page or the hosting page.

        Yields:
            PriceFact: Its prices.

        Raises:
            CatalogueFormatError: If the page has no Next.js data.
        """
        data = self._next_data(response)
        props = data.get(KrystalPriceField.PROPS)
        props = props.get(KrystalPriceField.PAGE_PROPS) if isinstance(props, dict) else None
        if not isinstance(props, dict):
            self.logger.error("The Krystal page %s has no page properties.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the page has no page properties")
        source = self.HOSTING_URL if response.url.rstrip("/") == self.HOSTING_URL else self.CLOUD_URL
        facts = self._hosting_prices(props) if source == self.HOSTING_URL else self._cloud_prices(props)
        found = 0
        for fact in facts:
            found += 1
            yield fact
        self._record_price_source(source, found)
        self.logger.info("The Krystal page %s is read: %d prices.", source, found)

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
            self.logger.debug("Reading the %s products of the HTML sitemap %s.", self.name, response.url)
            return self._sitemap_page_products(response)
        self.logger.debug("Reading the %s product cards of %s.", self.name, response.url)
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
            self.logger.debug("Reading the %s XML sitemap %s.", self.name, response.url)
            for request in self._sitemap_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
        if self.PRODUCT_PAGE not in response.meta and key == self._url_key(self.SITEMAP_PAGE_URL):
            self.logger.debug("Requesting the %s footer product pages of %s.", self.name, response.url)
            for request in self._footer_requests(response):
                yield request
