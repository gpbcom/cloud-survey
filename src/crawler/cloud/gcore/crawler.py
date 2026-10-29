from __future__ import annotations

# Standard Library Imports.
import re
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.gcore.enums import GcoreMachineKind, GcoreMenuTab, GcorePriceField
from crawler.enums import HtmlAttribute, PageMetaName
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class GcoreCrawler(BaseCloudCrawler):
    """Gcore catalogue crawler.

    Attributes:
        SITEMAP_URL (ClassVar[str]): The main sitemap of the website, listing the product pages.
        EXCLUDED_TABS (ClassVar[Tuple[GcoreMenuTab, ...]]): The menu tabs listing use cases, not products
            (case-insensitive).
        PRODUCT_PATHS (ClassVar[Tuple[str, ...]]): The sitemap paths of the product pages missing from the menu.
        TITLE_SUFFIX (ClassVar[re.Pattern[str]]): The tagline or brand suffix of a page heading or title.
        PRICES_URL (ClassVar[str]): The cloud pricing API of the website (no key), every location, in euros.
        PRICE_KIND (ClassVar[str]): The request meta holding the kind of machine of a listing.
        PRICE_CURRENCY (ClassVar[str]): The currency read.
        NUMBER (ClassVar[re.Pattern[str]]): A price written as text, e.g. `2,052.28`.
        COUNT (ClassVar[re.Pattern[str]]): The count a hardware text starts with, e.g. `16` of `16GB RAM`.
        TABLE_SERVICES (ClassVar[Tuple[Tuple[re.Pattern[str], str], ...]]): The service of a price table type.
        HOUR_UNIT (ClassVar[str]): The unit written for an hourly price.
        MONTH_UNIT (ClassVar[str]): The unit written for a monthly price.
        TRAFFIC_UNIT (ClassVar[str]): The unit written for a traffic price.
        GLOBAL_REGION (ClassVar[str]): The region of a row without location.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): The catalogue product pages are read too, for their prices.
        PAGE_TEXT_PRICES (ClassVar[bool]): A product page without price table is read for the prices in its text.
        PRODUCT_PAGE_JS (ClassVar[bool]): The product pages are rendered first (their Angular price widgets).

    Notes:
        The main source is the products menu of the https://gcore.com/ home page: its tabbed menus (Edge Network,
        AI, Cloud, Security) list the products with a name and a short description, each product being filed
        under its tabs. The "By industry" and "By need" tabs (use cases) are skipped. The main sitemap completes it
        with an allowlist of product pages (compute, hosting, security and services pages missing from the menu),
        read for their heading and meta description (without categories).
        The `robots.txt` of the website declares `Content-Signal: ai-train=no, search=yes, ai-input=no` and is
        obeyed by the catalogue crawl.
        In price mode it reads the cloud pricing API the pricing page loads (`PRICES_URL`), once for the virtual
        machines and once for the bare metal servers, each a source: an hourly and a monthly price per flavor and
        location (load balancers included), and the traffic price of the bare metal locations.
    """

    SITEMAP_URL: ClassVar[str] = "https://gcore.com/sitemap-main.xml"
    EXCLUDED_TABS: ClassVar[Tuple[GcoreMenuTab, ...]] = (GcoreMenuTab.BY_INDUSTRY, GcoreMenuTab.BY_NEED)
    PRODUCT_PATHS: ClassVar[Tuple[str, ...]] = (
        "/cloud/virtual-machines",
        "/cloud/faas",
        "/cloud/file-shares",
        "/cloud/load-balancers",
        "/cloud/managed-kubernetes",
        "/cloud/managed-logging",
        "/cloud/marketplace",
        "/cloud/recovery",
        "/container-registry",
        "/hosting/dedicated",
        "/hosting/vds",
        "/hosting/dedicated/gpu",
        "/security/waap",
        "/public-dns",
        "/streaming-platform/video-hosting",
        "/cdn/video-cdn",
        "/ddos-protection/servers",
        "/gcore-fastnetmon-ddos-protection",
        "/pentest",
        "/support-as-a-service",
        "/whitelabel",
        "/internet-peering",
        "/it-infrastructure-management",
        "/development",
    )
    TITLE_SUFFIX: ClassVar[re.Pattern[str]] = re.compile(r"\s+[|\u2013-]\s+.*$|:\s.*$")

    PRODUCT_PAGE_PRICES: ClassVar[bool] = True
    PAGE_TEXT_PRICES: ClassVar[bool] = True
    PRODUCT_PAGE_JS: ClassVar[bool] = True
    name = "gcore"
    catalogue_url: ClassVar[str] = "https://gcore.com/"
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Gcore ",)
    PRICES_URL: ClassVar[str] = "https://bff.gcore.pro/cloud/pricing-cloud?location=all&currency=EUR&vmType={kind}"
    PRICE_KIND: ClassVar[str] = "price_kind"
    PRICE_CURRENCY: ClassVar[str] = "EUR"
    NUMBER: ClassVar[re.Pattern[str]] = re.compile(r"^\d[\d,]*(?:\.\d+)?$")
    COUNT: ClassVar[re.Pattern[str]] = re.compile(r"^\s*(\d+)")
    TABLE_SERVICES: ClassVar[Tuple[Tuple[re.Pattern[str], str], ...]] = (
        (re.compile(r"^bm"), "Bare Metal"),
        (re.compile(r"^lb"), "Load Balancers"),
        (re.compile(r"^egress"), "Egress traffic"),
        (re.compile(r"^gpu"), "GPU Virtual Machines"),
        (re.compile(r"^(?:cpu|standard|memory|shared|highfreq|net)_"), "Virtual Machines"),
    )
    HOUR_UNIT: ClassVar[str] = "hour"
    MONTH_UNIT: ClassVar[str] = "month"
    TRAFFIC_UNIT: ClassVar[str] = "GB"
    GLOBAL_REGION: ClassVar[str] = "global"

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

    def _page_title(self, title: str) -> str:
        """Clean the product name read from a product page, removing its tagline or `| Gcore` suffix.

        Args:
            title (str): The page heading or title, e.g. `VDS Hosting - Buy virtual dedicated servers`.

        Returns:
            str: The product name, e.g. `VDS Hosting`.
        """
        return self.TITLE_SUFFIX.sub("", self._clean_text(title))

    def _page_name(self, response: Response) -> Optional[str]:
        """Read the product name of a product page: its first heading, else its Open Graph title.

        The Open Graph titles of the website are marketing sentences, the headings name the products.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The product name, `None` when the page has none.
        """
        heading = response.css("h1").first
        title = self._clean_text(heading.get_all_text(separator=" ", strip=True)) if heading is not None else None
        title = title or self._meta_content(response, PageMetaName.OG_TITLE)
        return self._page_title(title) if title else None

    def _menu_entries(self, response: Response) -> List[Tuple[str, str, str, List[str]]]:
        """Gather the product links of the tabbed menus with all their tabs, skipping the use case tabs.

        Args:
            response (Response): The home page.

        Returns:
            List[Tuple[str, str, str, List[str]]]: The name, description and URL of the first link of each product,
                by order of appearance, and the tabs of all its links.

        Notes:
            Each menu lists its tab labels (`.gc-tabbed-menu__rail-label`) and, in the same order, one grid of links
            per tab (`.gc-tabbed-menu__grid`). The links of a product are matched by name or by URL, as the
            streamed products are.
        """
        menus = response.css(".gc-tabbed-menu")
        self.logger.debug("%d tabbed menus in %s.", len(menus), response.url)
        entries: List[Tuple[str, str, str, List[str]]] = []
        positions: Dict[str, int] = {}
        for menu in menus:
            tabs = [
                self._clean_text(tab.get_all_text(separator=" ", strip=True))
                for tab in menu.css(".gc-tabbed-menu__rail-label")
            ]
            for index, grid in enumerate(menu.css(".gc-tabbed-menu__grid")):
                tab = tabs[index] if index < len(tabs) else ""
                if tab.casefold() in self.EXCLUDED_TABS:
                    self.logger.debug("Skipping the menu tab %r, use cases not products.", tab)
                    continue
                for link in grid.css("a.gc-menu-link-item"):
                    label = link.css(".gc-menu-link-item__label").first
                    description = link.css(".gc-menu-link-item__description").first
                    if label is None or description is None:
                        self.logger.debug("Skipping a menu link without name or description in the tab %r.", tab)
                        continue
                    url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, ""))
                    name = label.get_all_text(separator=" ", strip=True)
                    keys = [f"name:{self._name_key(name)}", f"url:{self._url_key(url)}"]
                    position = next((positions[key] for key in keys if key in positions), None)
                    if position is None:
                        position = len(entries)
                        entries.append((name, description.get_all_text(separator=" ", strip=True), url, []))
                    else:
                        self.logger.debug("Menu product %r listed again, in the tab %r.", name, tab)
                    if tab:
                        entries[position][3].append(tab)
                    positions.update(dict.fromkeys(keys, position))
        return entries

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the tabbed menus, filed under their tabs, skipping the use case tabs.

        Args:
            response (Response): The home page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menus, once.
        """
        for name, description, url, tabs in self._menu_entries(response):
            if product := self._build_product(name, description, url, categories=tabs):
                yield product

    def _sitemap_requests(self, response: Response) -> List[Request]:
        """Request the allowlisted product pages of the sitemap which were not found in the menu.

        Args:
            response (Response): The sitemap.

        Returns:
            List[Request]: The product page requests.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        urls = self._sitemap_urls(response)
        requests: List[Request] = []
        for url in urls:
            if urlparse(url).path.rstrip("/") not in self.PRODUCT_PATHS:
                self.logger.debug("Skipping the sitemap page %s, not an allowlisted product page.", url)
                continue
            if (request := self._product_page_request(url)) is not None:
                requests.append(request)
        self.logger.info("%d %s product pages to check in the sitemap (%d pages).", len(requests), self.name, len(urls))
        return requests

    def _price_number(self, text: JsonValue) -> Optional[Decimal]:
        """Read a price written as text, e.g. `2,052.28`.

        Args:
            text (JsonValue): The written price.

        Returns:
            Optional[Decimal]: The price, `None` when unreadable.
        """
        match = self.NUMBER.match(text.strip()) if isinstance(text, str) else None
        return Decimal(match[0].replace(",", "")) if match else None

    def _table_service(self, table: str) -> str:
        """Name the service of a price table, e.g. `Bare Metal` for `bm2w`.

        Args:
            table (str): The table type.

        Returns:
            str: The service of the first matching `TABLE_SERVICES` rule, the table type otherwise.
        """
        return next((service for pattern, service in self.TABLE_SERVICES if pattern.match(table)), table)

    def _row_prices(self, row: Dict[str, JsonValue], kind: str, source: str) -> Iterator[ServicePrice]:
        """Read the prices of a row of the pricing API: hourly and monthly, or per GB of traffic.

        Args:
            row (Dict[str, JsonValue]): The row.
            kind (str): The kind of machine of its listing (`vm`, `bm`).
            source (str): The listing it was read from (its source).

        Yields:
            ServicePrice: Its hourly then monthly prices, or its traffic price.
        """
        name = str(row.get(GcorePriceField.NAME) or "").strip()
        table = str(row.get(GcorePriceField.TABLE_TYPE) or "")
        location = str(row.get(GcorePriceField.LOCATION) or self.GLOBAL_REGION)
        vcpus = self.COUNT.match(str(row.get(GcorePriceField.VCPUS) or ""))
        ram = self.COUNT.match(str(row.get(GcorePriceField.RAM) or ""))
        base: Dict[str, RawValue] = {
            "service": self._table_service(table),
            "family": table or None,
            "region": location,
            "instance_type": name or None,
            "vcpu": int(vcpus[1]) if vcpus and int(vcpus[1]) > 0 else None,
            "memory_gib": int(ram[1]) if ram and int(ram[1]) > 0 else None,
            "attributes": {
                field.value: str(value).strip()
                for field in (GcorePriceField.GPU, GcorePriceField.CPU, GcorePriceField.DISKS, GcorePriceField.NETWORK)
                if (value := row.get(field))
            },
            "currency": self.PRICE_CURRENCY,
            "source_url": source,
            "source_kind": PriceSourceKind.API,
        }
        priced = (
            (GcorePriceField.PRICE_PER_HOUR, PriceUnit.HOUR, self.HOUR_UNIT),
            (GcorePriceField.PRICE_PER_MONTH, PriceUnit.MONTH, self.MONTH_UNIT),
            (GcorePriceField.PRICE_PER_TRAFFIC, PriceUnit.GIB, self.TRAFFIC_UNIT),
        )
        for field, unit, written in priced:
            price = self._price_number(row.get(field))
            if price is None:
                continue
            fact = self._price_fact(
                {
                    **base,
                    "sku_key": f"{kind}/{location}/{table}/{name}/{written}",
                    "unit": unit,
                    "unit_raw": written,
                    "price": price,
                    "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
                }
            )
            if fact is not None:
                yield fact

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the pricing of the virtual machines and of the bare metal servers.

        Yields:
            Request: The request of each listing.
        """
        for kind in GcoreMachineKind:
            source = self.PRICES_URL.format(kind=kind.value)
            self.logger.info("Reading the Gcore %s prices from %s.", kind.value, source)
            yield self._price_request(source, {self.PRICE_KIND: kind.value})

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read a listing of the pricing API.

        Args:
            response (Response): The listing.

        Yields:
            PriceFact: The prices of its rows.

        Raises:
            CatalogueFormatError: If it has no price tables.
        """
        data = self._json_body(response)
        tables = data.get(GcorePriceField.BODY) if isinstance(data, dict) else None
        if not isinstance(tables, list):
            self.logger.error("The Gcore pricing %s has no price tables.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the pricing has no price tables")
        kind = str(response.meta.get(self.PRICE_KIND) or GcoreMachineKind.VIRTUAL.value)
        source = self.PRICES_URL.format(kind=kind)
        found = 0
        for table in tables:
            for row in table if isinstance(table, list) else []:
                for fact in self._row_prices(row, kind, source) if isinstance(row, dict) else iter(()):
                    found += 1
                    yield fact
        self._record_price_source(source, found)
        self.logger.info("The Gcore %s pricing is read: %d prices of %d tables.", kind, found, len(tables))

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the home page menus.

        Args:
            response (Response): The home page.

        Returns:
            Iterator[CloudProduct]: The valid products of the menus.
        """
        return self._menu_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the menu products, request the sitemap product pages, or stream a sitemap product page.

        The product pages are read by the base crawler.

        Args:
            response (Response): The home page, the sitemap or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, or the product page requests.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
            EmptyCatalogueError: If the home page menus hold no product.
        """
        if response.url == self.SITEMAP_URL:
            for request in self._sitemap_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
