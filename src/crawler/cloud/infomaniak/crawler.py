from __future__ import annotations

# Standard Library Imports.
import re
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class InfomaniakCrawler(BaseCloudCrawler):
    """Infomaniak catalogue crawler.

    Attributes:
        PRODUCT_LINK (ClassVar[str]): The products menu links (generated CSS module class names, matched by prefix).
        NAME_ELEMENT (ClassVar[str]): The product name element of a menu link.
        DESCRIPTION_ELEMENT (ClassVar[str]): The product description element of a menu link.
        PRODUCTS_NAV (ClassVar[str]): The products menu, listing its groups and, in the same order, their panels.
        GROUP_TITLE (ClassVar[str]): The title of a products menu group.
        GROUP_PANELS (ClassVar[str]): The container of the panels of the products menu groups, one child per group.
        PRICES_URL (ClassVar[str]): The page data of the Public Cloud prices page, naming its static queries.
        QUERY_URL (ClassVar[str]): A static query of the website (its hash changes at every build).
        PRICE_QUERY (ClassVar[str]): The request meta holding the hash of a static query.
        PRICE_CURRENCY (ClassVar[str]): The currency read (the euro rates, VAT excluded).
        STATIC_QUERY_HASHES (ClassVar[str]): The field of the page data naming its static queries.
        CLOUD_QUERY (ClassVar[str]): The field of the Public Cloud prices in a static query.
        DBAAS_QUERY (ClassVar[str]): The field of the database plans in a static query.
        KAAS_QUERY (ClassVar[str]): The field of the Kubernetes plans in a static query.
        DATA (ClassVar[str]): The data of a query or of a node.
        NODES (ClassVar[str]): The nodes of a query.
        INSTANCES (ClassVar[str]): The instance flavors of the Public Cloud prices.
        DETAILS (ClassVar[str]): The hardware of a flavor.
        CORES (ClassVar[str]): Its cores.
        MEMORY (ClassVar[str]): Its memory, in GB.
        DISK (ClassVar[str]): Its disk, in GB.
        GPU (ClassVar[str]): Whether it has a GPU.
        RATES (ClassVar[str]): The rates of a flavor, a resource or a plan.
        EUR_RATE (ClassVar[str]): The euro rate, VAT excluded, of a flavor or a resource.
        UNIT (ClassVar[str]): The unit of a resource.
        EUR (ClassVar[str]): The euro rates of a plan.
        HOUR_EXCLUDING_TAX (ClassVar[str]): The hourly rate of a plan, VAT excluded.
        PRICE_PER_HOUR (ClassVar[str]): The hourly prices of a Kubernetes plan.
        NAME (ClassVar[str]): The name of a plan.
        TYPE (ClassVar[str]): The engine of a database plan.
        CPU (ClassVar[str]): The cores of a plan.
        RAM (ClassVar[str]): Its memory.
        STORAGE (ClassVar[str]): Its storage.
        VARIANT (ClassVar[str]): The attribute naming the rate variant of a resource (e.g. a volume class).
        TRAFFIC (ClassVar[re.Pattern[str]]): The resources priced per GiB transferred (not per GiB-hour).
        GIB_UNIT (ClassVar[str]): The unit of a resource priced per GiB (case-folded).
        HOUR_UNIT (ClassVar[str]): The unit written for an hourly price.
        UNIT_UNIT (ClassVar[str]): The unit written for a resource without unit.
        CLOUD_SERVICE (ClassVar[str]): The service of the Public Cloud prices.
        DBAAS_SERVICE (ClassVar[str]): The service of the database plans.
        KAAS_SERVICE (ClassVar[str]): The service of the Kubernetes plans.
        price_queries (Set[str]): The static queries not read yet, in price mode.
        price_rows (int): The prices read, in price mode.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): The catalogue product pages are read too, for their prices.
        PAGE_TEXT_PRICES (ClassVar[bool]): A product page without price table is read for the prices in its text.

    Notes:
        Infomaniak has no catalogue page. The source is the products menu embedded in the
        https://www.infomaniak.com/en home page: every group (collaboration, websites and domains, cloud computing,
        events and marketing, streaming) is read, each link giving a product name, a description and its page. A
        product is filed under the title of its group (e.g. `Cloud Computing`), and under those of every group
        listing it.
        In price mode it reads the Public Cloud prices page through its page data: the static queries it names
        (their hashes change at every build) hold the prices of the instance flavors and resources, of the database
        plans and of the Kubernetes plans, all hourly, in euros VAT excluded. The page and its queries are one
        source, recorded once every query is read.
    """

    PRODUCT_LINK: ClassVar[str] = '[class*="DisplayProductsLink-module--productsLink--"]'
    NAME_ELEMENT: ClassVar[str] = '[class*="DisplayProductsLink-module--productsLinkContentTitle--"]'
    DESCRIPTION_ELEMENT: ClassVar[str] = '[class*="DisplayProductsLink-module--productsLinkContentDesc--"]'
    PRODUCTS_NAV: ClassVar[str] = '[class*="DisplayProductsNav-module--productsNav--"]'
    GROUP_TITLE: ClassVar[str] = '[class*="DisplayProductsNav-module--productsNavLeftItemTitle--"]'
    GROUP_PANELS: ClassVar[str] = '[class*="DisplayProductsNav-module--productsNavRight--"]'

    PRODUCT_PAGE_PRICES: ClassVar[bool] = True
    PAGE_TEXT_PRICES: ClassVar[bool] = True
    name = "infomaniak"
    catalogue_url: ClassVar[str] = "https://www.infomaniak.com/en"
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Infomaniak ",)
    PRICES_URL: ClassVar[str] = "https://www.infomaniak.com/g/page-data/en/hosting/public-cloud/prices/page-data.json"
    QUERY_URL: ClassVar[str] = "https://www.infomaniak.com/g/page-data/sq/d/{hash}.json"
    PRICE_QUERY: ClassVar[str] = "price_query"
    PRICE_CURRENCY: ClassVar[str] = "EUR"
    STATIC_QUERY_HASHES: ClassVar[str] = "staticQueryHashes"
    CLOUD_QUERY: ClassVar[str] = "apiPublicCloudPrices"
    DBAAS_QUERY: ClassVar[str] = "allApiDbaasPrices"
    KAAS_QUERY: ClassVar[str] = "allApiKaasPrices"
    DATA: ClassVar[str] = "data"
    NODES: ClassVar[str] = "nodes"
    INSTANCES: ClassVar[str] = "instances"
    DETAILS: ClassVar[str] = "details"
    CORES: ClassVar[str] = "cores"
    MEMORY: ClassVar[str] = "memory"
    DISK: ClassVar[str] = "disk"
    GPU: ClassVar[str] = "gpu"
    RATES: ClassVar[str] = "rates"
    EUR_RATE: ClassVar[str] = "EUR_excl_tax"
    UNIT: ClassVar[str] = "unit"
    EUR: ClassVar[str] = "EUR"
    HOUR_EXCLUDING_TAX: ClassVar[str] = "hour_excl_tax"
    PRICE_PER_HOUR: ClassVar[str] = "price_per_hour"
    NAME: ClassVar[str] = "name"
    TYPE: ClassVar[str] = "type"
    CPU: ClassVar[str] = "cpu"
    RAM: ClassVar[str] = "ram"
    STORAGE: ClassVar[str] = "storage"
    VARIANT: ClassVar[str] = "variant"
    TRAFFIC: ClassVar[re.Pattern[str]] = re.compile(r"outgoing")
    GIB_UNIT: ClassVar[str] = "gib"
    HOUR_UNIT: ClassVar[str] = "hour"
    UNIT_UNIT: ClassVar[str] = "unit"
    CLOUD_SERVICE: ClassVar[str] = "Public Cloud"
    DBAAS_SERVICE: ClassVar[str] = "Database as a Service"
    KAAS_SERVICE: ClassVar[str] = "Kubernetes Service"

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.price_queries: Set[str] = set()
        self.price_rows = 0

    ############################
    # Internal Helpers Methods #
    ############################

    def _text(self, link: Selector, selector: str) -> Optional[str]:
        """Read the text of the first element of a menu link matching a selector.

        Args:
            link (Selector): The menu link.
            selector (str): The CSS selector of the element.

        Returns:
            Optional[str]: The element text, `None` when the link has no such element.
        """
        element = link.css(selector).first
        return element.get_all_text(separator=" ", strip=True) if element is not None else None

    def _grouped_links(self, response: Response) -> List[Tuple[Selector, Optional[str]]]:
        """List the products menu links with the title of their group.

        Args:
            response (Response): The home page.

        Returns:
            List[Tuple[Selector, Optional[str]]]: Each menu link and its group, `None` when the menu has no groups.

        Notes:
            The menu lists its group titles (left) and, in the same order, one panel of links per group (the
            children of the right side).
        """
        links: List[Tuple[Selector, Optional[str]]] = []
        for nav in response.css(self.PRODUCTS_NAV):
            titles = [
                self._clean_text(title.get_all_text(separator=" ", strip=True)) for title in nav.css(self.GROUP_TITLE)
            ]
            right = nav.css(self.GROUP_PANELS).first
            for index, panel in enumerate(right.children if right is not None else []):
                title = titles[index] if index < len(titles) else None
                links.extend((link, title) for link in panel.css(self.PRODUCT_LINK))
        if not links:
            self.logger.debug("No products menu groups on %s, its products are not categorized.", response.url)
            links = [(link, None) for link in response.css(self.PRODUCT_LINK)]
        return links

    def _menu_entries(self, response: Response) -> List[Tuple[Optional[str], Optional[str], Optional[str], List[str]]]:
        """Gather the products of the menu links with all their groups, a product being listed in several groups.

        Args:
            response (Response): The home page.

        Returns:
            List[Tuple[Optional[str], Optional[str], Optional[str], List[str]]]: The name, description and URL of the
                first link of each product, by order of appearance, and the groups of all its links.

        Notes:
            The links of a product are matched by name or by URL, as the streamed products are.
        """
        links = self._grouped_links(response)
        self.logger.debug("%d products menu links found on %s.", len(links), response.url)
        entries: List[Tuple[Optional[str], Optional[str], Optional[str], List[str]]] = []
        positions: Dict[str, int] = {}
        for link, group in links:
            href = link.attrib.get(HtmlAttribute.HREF)
            url = urljoin(response.url, href) if href else None
            name, description = self._text(link, self.NAME_ELEMENT), self._text(link, self.DESCRIPTION_ELEMENT)
            keys = ([f"name:{self._name_key(name)}"] if name else []) + ([f"url:{self._url_key(url)}"] if url else [])
            position = next((positions[key] for key in keys if key in positions), None)
            if position is None:
                position = len(entries)
                entries.append((name, description, url, []))
            else:
                self.logger.debug("Menu product %r listed again, in the group %r.", name, group)
            if group:
                entries[position][3].append(group)
            positions.update(dict.fromkeys(keys, position))
        return entries

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products menu, filed under their groups.

        Args:
            response (Response): The home page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menu, once.
        """
        count = 0
        for name, description, url, groups in self._menu_entries(response):
            if product := self._build_product(name, description, url, categories=groups):
                count += 1
                yield product
        if count:
            self.logger.info("%d %s products read from the menu of %s.", count, self.name, response.url)
        else:
            self.logger.warning("No %s product in the menu of %s.", self.name, response.url)

    def _field(self, value: JsonValue, *path: str) -> JsonValue:
        """Follow a path of object fields in a static query.

        Args:
            value (JsonValue): The document.
            *path (str): The fields, outermost first.

        Returns:
            JsonValue: The value at the end of the path, `None` when a field is missing.
        """
        for field in path:
            value = value.get(field) if isinstance(value, dict) else None
        return value

    def _hourly(self, fields: Dict[str, RawValue], rate: JsonValue) -> Optional[ServicePrice]:
        """Build an hourly price in euros, VAT excluded.

        Args:
            fields (Dict[str, RawValue]): The fields of the price, its price and currency aside.
            rate (JsonValue): The rate, in euros VAT excluded, if any.

        Returns:
            Optional[ServicePrice]: The price, `None` without rate.
        """
        if not isinstance(rate, (int, float)):
            self.logger.debug("The Infomaniak price %s has no euro rate: skipped.", fields.get("sku_key"))
            return None
        price = Decimal(str(rate))
        return self._price_fact(
            {
                "currency": self.PRICE_CURRENCY,
                "source_url": self.PRICES_URL,
                "source_kind": PriceSourceKind.CALCULATOR,
                **fields,
                "price": price,
                "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
            }
        )

    def _cloud_prices(self, data: JsonValue) -> Iterator[ServicePrice]:
        """Read the Public Cloud prices: the instances, then the resources (volumes, addresses, traffic...).

        Args:
            data (JsonValue): The Public Cloud prices of the static query.

        Yields:
            ServicePrice: An hourly price per instance flavor, and one per resource rate (per hour, per GiB-hour,
                or per GiB of traffic).
        """
        instances = self._field(data, self.INSTANCES)
        for flavor, instance in (instances if isinstance(instances, dict) else {}).items():
            details = self._field(instance, self.DETAILS)
            fact = self._hourly(
                {
                    "sku_key": f"{self.INSTANCES}/{flavor}",
                    "service": self.CLOUD_SERVICE,
                    "family": self.INSTANCES,
                    "instance_type": flavor,
                    "vcpu": self._field(details, self.CORES) or None,
                    "memory_gib": self._field(details, self.MEMORY) or None,
                    "storage_gib": self._field(details, self.DISK) or None,
                    "attributes": {self.GPU: self._field(details, self.GPU) is True},
                    "unit": PriceUnit.HOUR,
                    "unit_raw": self.HOUR_UNIT,
                },
                self._field(instance, self.RATES, self.EUR_RATE),
            )
            if fact is not None:
                yield fact
        for resource, entry in (data if isinstance(data, dict) else {}).items():
            if resource == self.INSTANCES:
                continue
            written = str(self._field(entry, self.UNIT) or "")
            unit = (
                PriceUnit.GIB
                if self.TRAFFIC.search(resource)
                else PriceUnit.GIB_HOUR
                if written.casefold() == self.GIB_UNIT
                else PriceUnit.UNIT_HOUR
            )
            rates = self._field(entry, self.RATES)
            for variant, rate in (rates if isinstance(rates, dict) else {}).items():
                fact = self._hourly(
                    {
                        "sku_key": f"{resource}/{variant}",
                        "service": self.CLOUD_SERVICE,
                        "family": resource,
                        "attributes": {self.VARIANT: variant},
                        "unit": unit,
                        "unit_raw": f"{written or self.UNIT_UNIT}/{self.HOUR_UNIT}"
                        if unit is not PriceUnit.GIB
                        else written,
                    },
                    self._field(rate, self.EUR_RATE),
                )
                if fact is not None:
                    yield fact

    def _node_prices(self, nodes: JsonValue, service: str) -> Iterator[ServicePrice]:
        """Read the hourly prices of the plans of a managed service (databases, Kubernetes).

        Args:
            nodes (JsonValue): The nodes of the static query.
            service (str): The service.

        Yields:
            ServicePrice: An hourly price per plan.
        """
        for node in nodes if isinstance(nodes, list) else []:
            plans = self._field(node, self.DATA)
            for plan in plans if isinstance(plans, list) else []:
                name = self._field(plan, self.NAME)
                rate = self._field(plan, self.RATES, self.EUR, self.HOUR_EXCLUDING_TAX)
                rate = rate if rate is not None else self._field(plan, self.PRICE_PER_HOUR, self.EUR)
                kind = self._field(plan, self.TYPE)
                fact = self._hourly(
                    {
                        "sku_key": f"{service}/{kind or ''}/{name}",
                        "service": service,
                        "family": kind if isinstance(kind, str) else None,
                        "instance_type": name if isinstance(name, str) else None,
                        "vcpu": self._field(plan, self.CPU) or None,
                        "memory_gib": self._field(plan, self.RAM) or None,
                        "storage_gib": self._field(plan, self.STORAGE) or None,
                        "unit": PriceUnit.HOUR,
                        "unit_raw": self.HOUR_UNIT,
                    },
                    rate,
                )
                if fact is not None:
                    yield fact

    def _query_prices(self, data: JsonValue) -> Iterator[ServicePrice]:
        """Read the prices of a static query of the prices page, by what it holds.

        Args:
            data (JsonValue): The `data` of the static query.

        Yields:
            ServicePrice: Its Public Cloud, database or Kubernetes prices, nothing for another query.
        """
        cloud = self._field(data, self.CLOUD_QUERY, self.DATA)
        if cloud is not None:
            yield from self._cloud_prices(cloud)
        databases = self._field(data, self.DBAAS_QUERY, self.NODES)
        if databases is not None:
            yield from self._node_prices(databases, self.DBAAS_SERVICE)
        kubernetes = self._field(data, self.KAAS_QUERY, self.NODES)
        if kubernetes is not None:
            yield from self._node_prices(kubernetes, self.KAAS_SERVICE)

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the page data of the prices page, which names its static queries.

        Yields:
            Request: The request of the page data.
        """
        self.price_queries = set()
        self.price_rows = 0
        self.logger.info("Reading the Infomaniak prices from %s.", self.PRICES_URL)
        yield self._price_request(self.PRICES_URL)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the page data (requesting its static queries), or a static query (reading its prices).

        Args:
            response (Response): The page data or a static query.

        Yields:
            PriceFact: The static query requests, or the prices of a static query.

        Raises:
            CatalogueFormatError: If the page data names no static query or a query is not an object.
        """
        data = self._json_body(response)
        query = response.meta.get(self.PRICE_QUERY)
        if not isinstance(query, str):
            hashes = self._field(data, self.STATIC_QUERY_HASHES)
            if not isinstance(hashes, list) or not hashes:
                self.logger.error("The Infomaniak page data %s names no static query.", response.url)
                raise CatalogueFormatError(self.name, response.url, "the page data names no static query")
            self.price_queries = {str(value) for value in hashes}
            for value in sorted(self.price_queries):
                yield self._price_request(self.QUERY_URL.format(hash=value), {self.PRICE_QUERY: value})
            self.logger.info("The Infomaniak prices page has %d static queries.", len(self.price_queries))
            return
        if not isinstance(data, dict):
            self.logger.error("The Infomaniak static query %s is not an object.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the static query is not an object")
        found = 0
        for fact in self._query_prices(self._field(data, self.DATA)):
            found += 1
            yield fact
        self.price_rows += found
        self.price_queries.discard(query)
        self.logger.debug("Infomaniak static query %s: %d prices.", query, found)
        if not self.price_queries:
            self._record_price_source(self.PRICES_URL, self.price_rows)
            self.logger.info("The Infomaniak prices are read whole: %d prices.", self.price_rows)

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products menu.

        Args:
            response (Response): The home page.

        Returns:
            Iterator[CloudProduct]: The valid products of the menu.
        """
        self.logger.debug("Reading the %s products menu of %s.", self.name, response.url)
        return self._menu_products(response)
