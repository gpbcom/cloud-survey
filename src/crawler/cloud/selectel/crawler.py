from __future__ import annotations

# Standard Library Imports.
import re
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.selectel.enums import (
    SelectelMenu,
    SelectelMenuGroup,
    SelectelPriceFamily,
    SelectelPriceField,
    SelectelPriceUnit,
)
from crawler.enums import HtmlAttribute
from models.cloud.enums import PriceModel, PriceSourceKind, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.products.product import CloudProduct


class SelectelCrawler(BaseCloudCrawler):
    """Selectel catalogue crawler.

    Attributes:
        MENU (ClassVar[str]): The top entries of the header menu, each one with its title and its dropdown.
        MENU_TITLE (ClassVar[str]): The title button of a top entry of the header menu, e.g. `Продукты`.
        GROUP (ClassVar[str]): The groups of a dropdown, each one with its title and its links.
        GROUP_TITLE (ClassVar[str]): The title of a dropdown group, e.g. `Базы данных`.
        LINK (ClassVar[str]): The product links of a dropdown group.
        LINK_ANCHOR (ClassVar[str]): The anchor of a product link, holding the product page.
        NAME (ClassVar[str]): The product name of a product link, without its status badge (`New`, `Free`).
        DESCRIPTION (ClassVar[str]): The product description of a product link.
        MENUS (ClassVar[Tuple[SelectelMenu, ...]]): The titles of the top entries of the header menu listing offers.
        SKIPPED_GROUPS (ClassVar[Tuple[SelectelMenuGroup, ...]]): The titles of the dropdown groups which are not
            catalogue categories.
        PRICES_URL (ClassVar[str]): A family of the cloud price API (no key), in rubles.
        SERVERS_URL (ClassVar[str]): The dedicated server API, with their prices by location.
        BILLING_URL (ClassVar[str]): The billing items API (colocation, network, licences...).
        PRICE_FAMILY (ClassVar[str]): The request meta holding the family (or kind) of a source.
        PRICE_CURRENCY (ClassVar[str]): The currency read.
        KOPECKS (ClassVar[Decimal]): The kopecks in a ruble (the cloud and billing prices are in kopecks).
        CORES (ClassVar[re.Pattern[str]]): A resource priced per core.
        TRAFFIC (ClassVar[re.Pattern[str]]): A resource priced per GB or MB transferred (not per hour).
        FAMILY_SERVICES (ClassVar[Dict[str, str]]): The service of a family of the cloud price API.
        SERVER_PERIODS (ClassVar[Tuple[Tuple[SelectelPriceField, PriceUnit, Decimal], ...]]): The periods of a server
            price: their field, unit and normalized units in one (a day is 24 hours).
        SERVERS_KEY (ClassVar[str]): The kind of the dedicated server source.
        BILLING_KEY (ClassVar[str]): The kind of the billing items source.
        SERVERS_SERVICE (ClassVar[str]): The service of the dedicated servers.
        ONCE_UNIT (ClassVar[str]): The unit written for a one-time billing item.
        GLOBAL_REGION (ClassVar[str]): The region of a price without region.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): The catalogue product pages are read too, for their prices.
        PAGE_TEXT_PRICES (ClassVar[bool]): A product page without price table is read for the prices in its text.

    Notes:
        The https://selectel.ru/services/ page (rendered on the server by Nuxt, read over HTTP) carries the full
        header menu of the website. Its `Продукты` (products) and `Услуги` (services) entries open a dropdown of
        groups, each group listing links with a product name, a description and the product page. A product is
        filed under the title of the top entry, then the title of its group (e.g. `Продукты`, `Базы данных`), and
        under those of every group listing it. The `Популярные` group is a selection of products listed in the other
        groups, the `Бизнес-задачи` group lists use-case pages and the `Отрасли` group lists industries: they are not
        read. The English website has no product menu, the Russian names are kept as written. The page sitemap
        dates some product pages (`lastmod`).
        In price mode it reads the price APIs of the website, in rubles: each family of the cloud prices (kopecks
        per hour per unit, a traffic resource per GB or MB transferred), the dedicated servers (monthly and daily
        per location) and the billing items (monthly, or once). Each is a source.
    """

    MENU: ClassVar[str] = "li.main-nav__list-item"
    MENU_TITLE: ClassVar[str] = "button.main-nav__list-btn"
    GROUP: ClassVar[str] = ".nav-dropdown__body-inner"
    GROUP_TITLE: ClassVar[str] = ".nav-dropdown__return-btn--subcategory"
    LINK: ClassVar[str] = ".menu-link"
    LINK_ANCHOR: ClassVar[str] = "a.menu-link__title"
    NAME: ClassVar[str] = ".menu-link__title-text"
    DESCRIPTION: ClassVar[str] = ".menu-link__description"
    MENUS: ClassVar[Tuple[SelectelMenu, ...]] = (SelectelMenu.PRODUCTS, SelectelMenu.SERVICES)
    SKIPPED_GROUPS: ClassVar[Tuple[SelectelMenuGroup, ...]] = (
        SelectelMenuGroup.POPULAR,
        SelectelMenuGroup.BUSINESS_TASKS,
        SelectelMenuGroup.INDUSTRIES,
    )

    PRODUCT_PAGE_PRICES: ClassVar[bool] = True
    PAGE_TEXT_PRICES: ClassVar[bool] = True
    name = "selectel"
    catalogue_url: ClassVar[str] = "https://selectel.ru/services/"
    dates_sitemaps: ClassVar[Tuple[str, ...]] = ("https://selectel.ru/sitemap-pages.xml",)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Selectel ",)
    PRICES_URL: ClassVar[str] = "https://api.selectel.ru/prices/{family}?currency=rub"
    SERVERS_URL: ClassVar[str] = "https://api.selectel.ru/servers/v2/pub/service/lite/server?is_hidden=false"
    BILLING_URL: ClassVar[str] = "https://api.selectel.ru/v2/billing/prices"
    PRICE_FAMILY: ClassVar[str] = "price_family"
    PRICE_CURRENCY: ClassVar[str] = "RUB"
    KOPECKS: ClassVar[Decimal] = Decimal(100)
    CORES: ClassVar[re.Pattern[str]] = re.compile(r"cores")
    TRAFFIC: ClassVar[re.Pattern[str]] = re.compile(r"traffic|_tx\b|_rx\b|transfer")
    FAMILY_SERVICES: ClassVar[Dict[str, str]] = {
        SelectelPriceFamily.VPC: "Cloud Servers",
        SelectelPriceFamily.DBAAS: "Managed Databases",
        SelectelPriceFamily.MKS: "Managed Kubernetes",
        SelectelPriceFamily.NETDISK: "Network Disks",
        SelectelPriceFamily.ONES: "1C Cloud",
        SelectelPriceFamily.STORAGE: "Object Storage",
        SelectelPriceFamily.VMWARE: "VMware Cloud",
        SelectelPriceFamily.CRAAS: "Container Registry",
    }
    SERVER_PERIODS: ClassVar[Tuple[Tuple[SelectelPriceField, PriceUnit, Decimal], ...]] = (
        (SelectelPriceField.MONTH, PriceUnit.MONTH, Decimal(1)),
        (SelectelPriceField.DAY, PriceUnit.HOUR, Decimal(24)),
    )
    SERVERS_KEY: ClassVar[str] = "servers"
    BILLING_KEY: ClassVar[str] = "billing"
    SERVERS_SERVICE: ClassVar[str] = "Dedicated Servers"
    ONCE_UNIT: ClassVar[str] = "once"
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

    def _url_key(self, url: str) -> str:
        """Normalize a product URL to compare it, keeping its query.

        Args:
            url (str): The absolute product URL.

        Returns:
            str: The comparison key, e.g. `selectel.ru/services/additional/firewall?section=virtualfirewall`.

        Notes:
            The menu links distinct products to sections of one page (`?section=`, `?tab=`), e.g. the hardware and
            the virtual firewalls: the query tells them apart.
        """
        query = urlparse(url.casefold()).query
        key = super()._url_key(url)
        return f"{key}?{query}" if query else key

    def _text(self, element: Selector, selector: str) -> Optional[str]:
        """Read the text of the first element matching a selector.

        Args:
            element (Selector): The element searched.
            selector (str): The CSS selector of the element read.

        Returns:
            Optional[str]: The element text, whitespaces collapsed, `None` when there is no such element.
        """
        found = element.css(selector).first
        return self._clean_text(found.get_all_text(separator=" ", strip=True)) if found is not None else None

    def _link_product(self, link: Selector, page_url: str, categories: List[str]) -> Optional[CloudProduct]:
        """Build the product of a menu link.

        Args:
            link (Selector): The menu link.
            page_url (str): The URL of the page, against which the relative links are resolved.
            categories (List[str]): The titles of the menu entry and of the group listing the link.

        Returns:
            Optional[CloudProduct]: The product, `None` (logged) when the link is invalid.
        """
        anchor = link.css(self.LINK_ANCHOR).first
        href = anchor.attrib.get(HtmlAttribute.HREF) if anchor is not None else None
        return self._build_product(
            self._text(link, self.NAME),
            self._text(link, self.DESCRIPTION),
            urljoin(page_url, href) if href else None,
            categories=categories,
        )

    def _group_products(self, menu: Selector, menu_title: str, page_url: str) -> Iterator[CloudProduct]:
        """Build the products of the groups of a menu entry, filed under the entry and group titles.

        Args:
            menu (Selector): The top entry of the header menu.
            menu_title (str): Its title, e.g. `Продукты`.
            page_url (str): The URL of the page, against which the relative links are resolved.

        Yields:
            Iterator[CloudProduct]: The valid product of each link of the read groups, an occurrence per group.
        """
        for group in menu.css(self.GROUP):
            title = self._text(group, self.GROUP_TITLE)
            if title in self.SKIPPED_GROUPS:
                self.logger.debug("Skipping the menu group %r of %r, not a catalogue category.", title, menu_title)
                continue
            links = group.css(self.LINK)
            self.logger.debug("%d links in the menu group %r of %r.", len(links), title, menu_title)
            for link in links:
                if product := self._link_product(link, page_url, [menu_title, title or ""]):
                    yield product

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Build the products of the read entries of the header menu, an occurrence per group listing them.

        Args:
            response (Response): The services page.

        Yields:
            Iterator[CloudProduct]: Each valid product occurrence, by order of appearance.
        """
        for menu in response.css(self.MENU):
            title = self._text(menu, self.MENU_TITLE)
            if title not in self.MENUS:
                self.logger.debug("Skipping the menu entry %r, it lists no offer.", title)
                continue
            yield from self._group_products(menu, title, response.url)

    def _field(self, value: JsonValue, *path: str) -> JsonValue:
        """Follow a path of object fields in a price API answer.

        Args:
            value (JsonValue): The answer.
            *path (str): The fields, outermost first.

        Returns:
            JsonValue: The value at the end of the path, `None` when a field is missing.
        """
        for field in path:
            value = value.get(field) if isinstance(value, dict) else None
        return value

    def _resource_unit(self, resource: str, unit: str) -> Tuple[PriceUnit, Decimal]:
        """Normalize the unit of a cloud price, per hour unless the resource is transferred.

        Args:
            resource (str): The priced resource, e.g. `dbaas_compute_cores`, `craas_registry_traffic_tx`.
            unit (str): Its unit, e.g. `item`, `MB`.

        Returns:
            Tuple[PriceUnit, Decimal]: The unit (a vCPU-hour for cores, a GiB-hour for memory and storage, a GiB for
                traffic, a unit-hour for an item) and the normalized units in one (a MB is 1/1024 GiB).
        """
        try:
            written = SelectelPriceUnit(unit)
        except ValueError:
            self.logger.debug("The Selectel unit %r of %s has no known unit: kept as other.", unit, resource)
            return PriceUnit.OTHER, Decimal(1)
        if written is SelectelPriceUnit.ITEM:
            return (PriceUnit.VCPU_HOUR if self.CORES.search(resource) else PriceUnit.UNIT_HOUR), Decimal(1)
        factor = (
            Decimal(1) / Decimal(1024) if written in (SelectelPriceUnit.MB, SelectelPriceUnit.MB_HOUR) else Decimal(1)
        )
        transferred = written in (SelectelPriceUnit.GB, SelectelPriceUnit.MB) and self.TRAFFIC.search(resource)
        return (PriceUnit.GIB if transferred else PriceUnit.GIB_HOUR), factor

    def _family_prices(self, family: str, items: JsonValue, source: str) -> Iterator[ServicePrice]:
        """Read the prices of a family of the cloud price API.

        Args:
            family (str): The family, e.g. `vpc`.
            items (JsonValue): Its prices.
            source (str): The family listing (its source).

        Yields:
            ServicePrice: One price per resource and region, in rubles (from kopecks).
        """
        for item in items if isinstance(items, list) else []:
            resource = self._field(item, SelectelPriceField.RESOURCE)
            value = self._field(item, SelectelPriceField.VALUE)
            if not isinstance(resource, str) or not isinstance(value, (int, float)):
                continue
            unit_text = str(self._field(item, SelectelPriceField.UNIT) or "")
            unit, factor = self._resource_unit(resource, unit_text)
            region = self._field(item, SelectelPriceField.GROUP)
            price = Decimal(str(value)) / self.KOPECKS
            fact = self._price_fact(
                {
                    "sku_key": f"{family}/{region}/{resource}",
                    "service": self.FAMILY_SERVICES.get(family, family),
                    "family": family,
                    "region": region if isinstance(region, str) and region else self.GLOBAL_REGION,
                    "attributes": {SelectelPriceField.RESOURCE.value: resource},
                    "unit": unit,
                    "unit_raw": unit_text,
                    "unit_factor": factor,
                    "price": price,
                    "currency": self.PRICE_CURRENCY,
                    "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
                    "source_url": source,
                    "source_kind": PriceSourceKind.API,
                }
            )
            if fact is not None:
                yield fact

    def _total_size(self, parts: JsonValue) -> int:
        """Add up the sizes of the memory modules or the disks of a server.

        Args:
            parts (JsonValue): The modules or disks, each with its size (GB) and count.

        Returns:
            int: Their total size, in GB.
        """
        total = 0
        for part in parts if isinstance(parts, list) else []:
            size, count = self._field(part, SelectelPriceField.SIZE), self._field(part, SelectelPriceField.COUNT)
            if isinstance(size, int):
                total += size * (count if isinstance(count, int) and count > 0 else 1)
        return total

    def _server_prices(self, servers: JsonValue) -> Iterator[ServicePrice]:
        """Read the prices of the dedicated servers, per location: monthly and daily, in rubles.

        Args:
            servers (JsonValue): The servers of the server API.

        Yields:
            ServicePrice: A monthly and a daily price per server and location.
        """
        for server in servers if isinstance(servers, list) else []:
            cpu = self._field(server, SelectelPriceField.CPU)
            count, cores = (
                self._field(cpu, SelectelPriceField.COUNT),
                self._field(cpu, SelectelPriceField.CORES_PER_CPU),
            )
            ram, disks = self._field(server, SelectelPriceField.RAM), self._field(server, SelectelPriceField.DISK)
            memory = self._total_size(ram)
            storage = self._total_size(disks)
            name = self._field(server, SelectelPriceField.NAME)
            identifier = self._field(server, SelectelPriceField.UUID)
            locations = self._field(server, SelectelPriceField.LOCATION_PRICE_COLLECTION)
            for location, currencies in (locations if isinstance(locations, dict) else {}).items():
                for period, unit, factor in self.SERVER_PERIODS:
                    value = self._field(currencies, SelectelPriceField.RUB, period)
                    if not isinstance(value, (int, float)):
                        continue
                    fact = self._price_fact(
                        {
                            "sku_key": f"{self.SERVERS_KEY}/{identifier}/{location}/{period.value}",
                            "service": self.SERVERS_SERVICE,
                            "family": self._field(server, SelectelPriceField.TARIFF_LINE) or None,
                            "region": location,
                            "instance_type": name if isinstance(name, str) else None,
                            "vcpu": count * cores
                            if isinstance(count, int) and isinstance(cores, int) and count * cores > 0
                            else None,
                            "memory_gib": memory or None,
                            "storage_gib": storage or None,
                            "attributes": {
                                SelectelPriceField.CONFIG_NAME.value: self._field(
                                    server, SelectelPriceField.CONFIG_NAME
                                )
                            },
                            "unit": unit,
                            "unit_raw": period.value,
                            "unit_factor": factor,
                            "price": Decimal(str(value)),
                            "currency": self.PRICE_CURRENCY,
                            "model": PriceModel.FREE if value == 0 else PriceModel.ON_DEMAND,
                            "source_url": self.SERVERS_URL,
                            "source_kind": PriceSourceKind.API,
                        }
                    )
                    if fact is not None:
                        yield fact

    def _billing_prices(self, items: JsonValue) -> Iterator[ServicePrice]:
        """Read the prices of the billing items (colocation, network, licences...), in rubles (from kopecks).

        Args:
            items (JsonValue): The billing items.

        Yields:
            ServicePrice: A monthly price per recurring item, a one-time price per other item.
        """
        for item in items if isinstance(items, list) else []:
            value = self._field(item, SelectelPriceField.PRICES, SelectelPriceField.RUB_PRICE)
            if not isinstance(value, (int, float)):
                continue
            monthly = self._field(item, SelectelPriceField.REPEAT) == 1
            price = Decimal(str(value)) / self.KOPECKS
            fact = self._price_fact(
                {
                    "sku_key": f"{self.BILLING_KEY}/{self._field(item, SelectelPriceField.ID)}",
                    "service": self._field(item, SelectelPriceField.NAME_EN)
                    or self._field(item, SelectelPriceField.NAME),
                    "family": f"{self.BILLING_KEY}-{self._field(item, SelectelPriceField.GROUP_ID)}",
                    "attributes": {SelectelPriceField.NAME.value: self._field(item, SelectelPriceField.NAME)},
                    "unit": PriceUnit.MONTH if monthly else PriceUnit.ONE_TIME,
                    "unit_raw": SelectelPriceField.MONTH.value if monthly else self.ONCE_UNIT,
                    "price": price,
                    "currency": self.PRICE_CURRENCY,
                    "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
                    "source_url": self.BILLING_URL,
                    "source_kind": PriceSourceKind.API,
                }
            )
            if fact is not None:
                yield fact

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request each family of the cloud price API, the dedicated servers and the billing items.

        Yields:
            Request: The request of each source.
        """
        for family in SelectelPriceFamily:
            yield self._price_request(self.PRICES_URL.format(family=family.value), {self.PRICE_FAMILY: family.value})
        yield self._price_request(self.SERVERS_URL, {self.PRICE_FAMILY: self.SERVERS_KEY})
        yield self._price_request(self.BILLING_URL, {self.PRICE_FAMILY: self.BILLING_KEY})
        self.logger.info("Reading the Selectel prices from %d sources.", len(SelectelPriceFamily) + 2)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read a source: a family of the cloud prices, the dedicated servers or the billing items.

        Args:
            response (Response): The source.

        Yields:
            PriceFact: Its prices.

        Raises:
            CatalogueFormatError: If it is not JSON.
        """
        data = self._json_body(response)
        family = str(response.meta.get(self.PRICE_FAMILY) or "")
        if family == self.SERVERS_KEY:
            source, facts = self.SERVERS_URL, self._server_prices(self._field(data, SelectelPriceField.RESULT))
        elif family == self.BILLING_KEY:
            source, facts = self.BILLING_URL, self._billing_prices(data)
        else:
            source = self.PRICES_URL.format(family=family)
            facts = self._family_prices(family, data, source)
        found = 0
        for fact in facts:
            found += 1
            yield fact
        if not found:
            self.logger.warning("The Selectel source %s gave no price.", source)
        self._record_price_source(source, found)
        self.logger.info("The Selectel source %s is read: %d prices.", source, found)

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the header menu, each one once with the categories of all its groups.

        Args:
            response (Response): The services page.

        Returns:
            Iterator[CloudProduct]: The valid products of the menu.
        """
        products = self._merge_categories(self._menu_products(response))
        self.logger.debug("%d products in the %s header menu of %s.", len(products), self.name, response.url)
        return iter(products)
