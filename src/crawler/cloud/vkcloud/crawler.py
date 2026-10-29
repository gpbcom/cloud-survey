from __future__ import annotations

# Standard Library Imports.
import re
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.next_flight_data import NextFlightData
from crawler.cloud.vkcloud.enums import (
    VkCloudCmsComponent,
    VkCloudCmsField,
    VkCloudHost,
    VkCloudPriceColumn,
    VkCloudQuantityUnit,
)
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class VKCloudCrawler(BaseCloudCrawler):
    """VK Cloud (formerly Mail.ru Cloud Solutions) catalogue crawler.

    Attributes:
        MENU_COMPONENT (ClassVar[VkCloudCmsComponent]): The CMS component of the products menu of the page header.
        MENU_LISTS (ClassVar[Tuple[VkCloudCmsField, ...]]): The lists of products of a products menu group.
        LEGACY_HOSTS (ClassVar[FrozenSet[VkCloudHost]]): The former hosts of the website, redirected to the current
            one.
        SITE_HOST (ClassVar[VkCloudHost]): The current host of the website.
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The services catalogue page.
        dates_sitemaps (ClassVar[Tuple[str, ...]]): The sitemap dating the product pages.
        name_prefixes (ClassVar[Tuple[str, ...]]): The brand prefixes ignored when comparing product names.
        PRICELIST_URL (ClassVar[str]): The price list page, the price source.
        PERIODS (ClassVar[Tuple[VkCloudPriceColumn, ...]]): The price columns, the one read first when a row has
            several (the price per minute being the same price).
        COLUMNS (ClassVar[Tuple[VkCloudPriceColumn, ...]]): The columns recognized by their header, the longer
            headers first (`Цена` starting them all).
        UNITS (ClassVar[Dict[Tuple[VkCloudPriceColumn, VkCloudQuantityUnit], Tuple[PriceUnit, Decimal]]]): The unit
            of a price by its column and the unit of its quantity, and the normalized units in one.
        QUANTITY (ClassVar[re.Pattern[str]]): A quantity priced, e.g. `1 шт.` or `1 Гб`.
        INSTANCE (ClassVar[re.Pattern[str]]): An instance flavor, e.g. `GPU-44-256-H200-1 (44 CPU, 256 RAM, ...)`.
        AMOUNT (ClassVar[re.Pattern[str]]): A price in rubles, e.g. `1 297,50 ₽`.
        ON_REQUEST (ClassVar[str]): The text of a price given on request.
        QUOTE_REASON (ClassVar[str]): Why a price given on request is not public.
        PRICE_CURRENCY (ClassVar[str]): The currency of the prices.
        VAT_ATTRIBUTE (ClassVar[str]): The attribute telling whether the price includes the VAT.
        VAT_INCLUDED (ClassVar[str]): The prices include it.
        flight (NextFlightData): The reader of the Next.js flight data of the pages.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): The catalogue product pages are read too, for their prices.
        PAGE_TEXT_PRICES (ClassVar[bool]): A product page without price table is read for the prices in its text.

    Notes:
        The website moved from cloud.vk.com to cloud.vk.ru. Its English version (https://cloud.vk.ru/en/) is a
        single page showing a dozen products, the Russian one is the complete catalogue: the source is the
        https://cloud.vk.ru/cloud-platform/ page, listing all the services and solutions. It is a Next.js application
        whose CMS data is embedded in the page as flight data (`self.__next_f.push` scripts): the catalogue
        (`catalog.items`) lists its groups (e.g. `Вычисления`), each listing its services with their card title,
        description (`service.text`) and page (`service.url.url`). The products menu of the page header
        (`header.header-menu` component) is read too: its groups (e.g. `Data-платформа`) list a few products the
        catalogue does not (e.g. Cloud Streams, Cloud Flink, Registry). A product is filed under every group listing
        it, the catalogue ones first, and gets the name and description of its first listing. The listings of a
        product are matched by name or by page, e.g. the catalogue `Load Balancer` and the menu `Load Balancing`.
        The groups are flat: each listing gives one category. The links to the former host are rewritten to the
        current one, so that the product pages are dated by the sitemap.
        In price mode it reads the tables of the price list page, in rubles with VAT: a table holds the prices of
        the service of its heading, a row a priced item with its quantity (`Значение`) and its price per minute and
        per 30 days (or per day, or per usage). The price per 30 days is kept (per month), the price per minute
        being an attribute. A row may restart the columns of its table. A discounted price gives its former price as
        an attribute. A price given on request is a quote.
    """

    MENU_COMPONENT: ClassVar[VkCloudCmsComponent] = VkCloudCmsComponent.HEADER_MENU
    MENU_LISTS: ClassVar[Tuple[VkCloudCmsField, ...]] = (VkCloudCmsField.DROPDOWN, VkCloudCmsField.DROPDOWN_ITEMS)
    LEGACY_HOSTS: ClassVar[FrozenSet[VkCloudHost]] = frozenset({VkCloudHost.LEGACY, VkCloudHost.LEGACY_WWW})
    SITE_HOST: ClassVar[VkCloudHost] = VkCloudHost.CURRENT
    PRICELIST_URL: ClassVar[str] = "https://cloud.vk.ru/pricelist/"
    PERIODS: ClassVar[Tuple[VkCloudPriceColumn, ...]] = (
        VkCloudPriceColumn.PER_30_DAYS,
        VkCloudPriceColumn.PER_ONE_DAY,
        VkCloudPriceColumn.PER_DAY,
        VkCloudPriceColumn.PRICE,
        VkCloudPriceColumn.PER_MINUTE,
    )
    COLUMNS: ClassVar[Tuple[VkCloudPriceColumn, ...]] = (
        VkCloudPriceColumn.VALUE,
        VkCloudPriceColumn.PER_MINUTE,
        VkCloudPriceColumn.PER_30_DAYS,
        VkCloudPriceColumn.PER_ONE_DAY,
        VkCloudPriceColumn.PER_DAY,
        VkCloudPriceColumn.PRICE,
    )
    UNITS: ClassVar[Dict[Tuple[VkCloudPriceColumn, VkCloudQuantityUnit], Tuple[PriceUnit, Decimal]]] = {
        (VkCloudPriceColumn.PER_30_DAYS, VkCloudQuantityUnit.PIECE): (PriceUnit.UNIT_MONTH, Decimal(1)),
        (VkCloudPriceColumn.PER_30_DAYS, VkCloudQuantityUnit.USER): (PriceUnit.UNIT_MONTH, Decimal(1)),
        (VkCloudPriceColumn.PER_30_DAYS, VkCloudQuantityUnit.GB): (PriceUnit.GIB_MONTH, Decimal(1)),
        (VkCloudPriceColumn.PER_30_DAYS, VkCloudQuantityUnit.GB_UPPER): (PriceUnit.GIB_MONTH, Decimal(1)),
        (VkCloudPriceColumn.PER_30_DAYS, VkCloudQuantityUnit.TB): (PriceUnit.GIB_MONTH, Decimal(1024)),
        (VkCloudPriceColumn.PER_DAY, VkCloudQuantityUnit.PIECE): (PriceUnit.UNIT_HOUR, Decimal(24)),
        (VkCloudPriceColumn.PER_DAY, VkCloudQuantityUnit.USER): (PriceUnit.UNIT_HOUR, Decimal(24)),
        (VkCloudPriceColumn.PER_DAY, VkCloudQuantityUnit.GB): (PriceUnit.GIB_HOUR, Decimal(24)),
        (VkCloudPriceColumn.PER_DAY, VkCloudQuantityUnit.GB_UPPER): (PriceUnit.GIB_HOUR, Decimal(24)),
        (VkCloudPriceColumn.PER_DAY, VkCloudQuantityUnit.TB): (PriceUnit.GIB_HOUR, Decimal(24 * 1024)),
        (VkCloudPriceColumn.PER_ONE_DAY, VkCloudQuantityUnit.PIECE): (PriceUnit.UNIT_HOUR, Decimal(24)),
        (VkCloudPriceColumn.PER_ONE_DAY, VkCloudQuantityUnit.USER): (PriceUnit.UNIT_HOUR, Decimal(24)),
        (VkCloudPriceColumn.PER_ONE_DAY, VkCloudQuantityUnit.GB): (PriceUnit.GIB_HOUR, Decimal(24)),
        (VkCloudPriceColumn.PER_ONE_DAY, VkCloudQuantityUnit.GB_UPPER): (PriceUnit.GIB_HOUR, Decimal(24)),
        (VkCloudPriceColumn.PER_ONE_DAY, VkCloudQuantityUnit.TB): (PriceUnit.GIB_HOUR, Decimal(24 * 1024)),
        (VkCloudPriceColumn.PRICE, VkCloudQuantityUnit.PIECE): (PriceUnit.UNIT, Decimal(1)),
        (VkCloudPriceColumn.PRICE, VkCloudQuantityUnit.USER): (PriceUnit.UNIT, Decimal(1)),
        (VkCloudPriceColumn.PRICE, VkCloudQuantityUnit.GB): (PriceUnit.GIB, Decimal(1)),
        (VkCloudPriceColumn.PRICE, VkCloudQuantityUnit.GB_UPPER): (PriceUnit.GIB, Decimal(1)),
        (VkCloudPriceColumn.PRICE, VkCloudQuantityUnit.TB): (PriceUnit.GIB, Decimal(1024)),
        (VkCloudPriceColumn.PER_MINUTE, VkCloudQuantityUnit.PIECE): (PriceUnit.MINUTE, Decimal(1)),
        (VkCloudPriceColumn.PER_MINUTE, VkCloudQuantityUnit.USER): (PriceUnit.MINUTE, Decimal(1)),
    }
    QUANTITY: ClassVar[re.Pattern[str]] = re.compile(r"^(?P<count>\d+(?:[.,]\d+)?)\s*(?P<unit>[^\s.]+)")
    INSTANCE: ClassVar[re.Pattern[str]] = re.compile(r"^(?P<type>\S+)\s*\((?P<cpu>\d+)\s*CPU,\s*(?P<ram>\d+)\s*RAM")
    AMOUNT: ClassVar[re.Pattern[str]] = re.compile(r"(\d[\d\s]*(?:,\d+)?)\s*₽")
    ON_REQUEST: ClassVar[str] = "по запросу"
    QUOTE_REASON: ClassVar[str] = "The price is computed on request (Расчет стоимости по запросу клиента)."
    PRICE_CURRENCY: ClassVar[str] = "RUB"
    VAT_ATTRIBUTE: ClassVar[str] = "vat"
    VAT_INCLUDED: ClassVar[str] = "included"

    PRODUCT_PAGE_PRICES: ClassVar[bool] = True
    PAGE_TEXT_PRICES: ClassVar[bool] = True
    name = "vkcloud"
    catalogue_url: ClassVar[str] = "https://cloud.vk.ru/cloud-platform/"
    dates_sitemaps: ClassVar[Tuple[str, ...]] = ("https://cloud.vk.ru/sitemap.xml",)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("VK Cloud ", "VK ")

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.flight = NextFlightData(self.name, self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _link(self, value: JsonValue, response: Response) -> Optional[str]:
        """Read the absolute page URL of a CMS link object (`{url: "/cloud-servers/", ...}`).

        Args:
            value (JsonValue): The link object.
            response (Response): The page, against which the relative links are resolved.

        Returns:
            Optional[str]: The URL on the current host of the website, `None` when the link has none.
        """
        href = self._as_text(self._as_object(value).get(VkCloudCmsField.URL))
        if not href or not href.strip():
            return None
        link = urlparse(urljoin(response.url, href.strip()))
        if link.netloc in self.LEGACY_HOSTS:
            self.logger.debug("Moving the %s link %s to the host %s.", self.name, link.geturl(), self.SITE_HOST)
            link = link._replace(netloc=self.SITE_HOST)
        return link.geturl()

    def _items(self, holder: Dict[str, JsonValue]) -> List[Dict[str, JsonValue]]:
        """Read the `items` list of a CMS object, e.g. the groups of the catalogue.

        Args:
            holder (Dict[str, JsonValue]): The CMS object.

        Returns:
            List[Dict[str, JsonValue]]: The items (those which are not objects are empty),
                empty without a list.
        """
        items = holder.get(VkCloudCmsField.ITEMS)
        return [self._as_object(item) for item in items] if isinstance(items, list) else []

    def _catalogue_groups(self, rows: List[JsonValue]) -> List[Dict[str, JsonValue]]:
        """Find the groups of the services catalogue (`catalog.items`) in the flight data.

        Args:
            rows (List[JsonValue]): The flight data rows.

        Returns:
            List[Dict[str, JsonValue]]: The groups of the first catalogue listing some, empty without catalogue.
        """
        for row in rows:
            for candidate in self._walk_objects(row):
                if groups := self._items(self._as_object(candidate.get(VkCloudCmsField.CATALOG))):
                    self.logger.debug("%d %s catalogue groups found.", len(groups), self.name)
                    return groups
        self.logger.warning("No %s catalogue group in the %d page rows.", self.name, len(rows))
        return []

    def _menu_groups(self, rows: List[JsonValue]) -> List[Dict[str, JsonValue]]:
        """Find the groups of the products menu (`header.header-menu` component) in the flight data.

        Args:
            rows (List[JsonValue]): The flight data rows.

        Returns:
            List[Dict[str, JsonValue]]: The groups of the first products menu listing some, empty without menu.

        Notes:
            The page data repeats the header: only its first occurrence is read.
        """
        for row in rows:
            for candidate in self._walk_objects(row):
                if candidate.get(VkCloudCmsField.COMPONENT) == self.MENU_COMPONENT and (
                    groups := self._items(candidate)
                ):
                    self.logger.debug("%d %s menu groups found.", len(groups), self.name)
                    return groups
        self.logger.warning("No %s menu group in the %d page rows.", self.name, len(rows))
        return []

    def _catalogue_products(self, rows: List[JsonValue], response: Response) -> List[CloudProduct]:
        """Extract the services of the catalogue, filed under their group, an occurrence per listing.

        Args:
            rows (List[JsonValue]): The flight data rows of the catalogue page.
            response (Response): The catalogue page.

        Returns:
            List[CloudProduct]: The valid services, in the catalogue order.
        """
        groups = self._catalogue_groups(rows)
        if not groups:
            self.logger.warning("The %s page %s holds no services catalogue.", self.name, response.url)
        products: List[CloudProduct] = []
        for group in groups:
            title = self._as_text(group.get(VkCloudCmsField.TITLE))
            services = group.get(VkCloudCmsField.SERVICES)
            for entry in services if isinstance(services, list) else []:
                card = self._as_object(entry)
                service = self._as_object(card.get(VkCloudCmsField.SERVICE))
                product = self._build_product(
                    self._as_text(card.get(VkCloudCmsField.TITLE)) or self._as_text(service.get(VkCloudCmsField.TITLE)),
                    self._as_text(service.get(VkCloudCmsField.TEXT)),
                    self._link(service.get(VkCloudCmsField.URL), response),
                    categories=[title],
                )
                if product is not None:
                    products.append(product)
        self.logger.info("%d %s catalogue listings in %d groups.", len(products), self.name, len(groups))
        return products

    def _menu_products(self, rows: List[JsonValue], response: Response) -> List[CloudProduct]:
        """Extract the products of the products menu, filed under their group, an occurrence per listing.

        Args:
            rows (List[JsonValue]): The flight data rows of the catalogue page.
            response (Response): The catalogue page.

        Returns:
            List[CloudProduct]: The valid products, in the menu order.
        """
        groups = self._menu_groups(rows)
        if not groups:
            self.logger.warning("The %s page %s has no products menu.", self.name, response.url)
        products: List[CloudProduct] = []
        for group in groups:
            title = self._as_text(group.get(VkCloudCmsField.TITLE))
            for key in self.MENU_LISTS:
                entries = group.get(key)
                for entry in entries if isinstance(entries, list) else []:
                    link = self._as_object(entry)
                    product = self._build_product(
                        self._as_text(link.get(VkCloudCmsField.TITLE)),
                        self._as_text(link.get(VkCloudCmsField.TEXT)),
                        self._link(link.get(VkCloudCmsField.URL), response),
                        categories=[title],
                    )
                    if product is not None:
                        products.append(product)
        self.logger.info("%d %s products menu listings in %d groups.", len(products), self.name, len(groups))
        return products

    def _columns(self, header: List[str]) -> Dict[int, VkCloudPriceColumn]:
        """Read the role of the columns of a header row, the first being the item priced.

        Args:
            header (List[str]): The header row.

        Returns:
            Dict[int, VkCloudPriceColumn]: The quantity and price columns, by index.
        """
        columns: Dict[int, VkCloudPriceColumn] = {}
        for index, text in enumerate(header[1:], start=1):
            role = next((column for column in self.COLUMNS if text.startswith(column.value)), None)
            if role is not None:
                columns[index] = role
        return columns

    def _amounts(self, text: str) -> List[Decimal]:
        """Read the prices written in a cell (a discounted price follows its former price).

        Args:
            text (str): The cell text.

        Returns:
            List[Decimal]: Its prices, in order.
        """
        return [Decimal(re.sub(r"\s", "", amount).replace(",", ".")) for amount in self.AMOUNT.findall(text)]

    def _row_price(
        self, service: str, group: str, row: List[str], columns: Dict[int, VkCloudPriceColumn]
    ) -> Optional[ServicePrice]:
        """Read the price of a row of a price list table.

        Args:
            service (str): The service of its table (the heading).
            group (str): The header of its first column (e.g. the hot or cold data of a storage).
            row (List[str]): The row.
            columns (Dict[int, VkCloudPriceColumn]): The roles of its columns.

        Returns:
            Optional[ServicePrice]: The price per 30 days (or per day, or per usage), a quote when given on request,
                None without price.
        """
        name = row[0]
        cells = {role: row[index] for index, role in columns.items() if index < len(row)}
        quantity = cells.get(VkCloudPriceColumn.VALUE, "")
        prices = {period: self._amounts(cells[period]) for period in self.PERIODS if cells.get(period)}
        period = next((period for period in self.PERIODS if prices.get(period)), None)
        attributes: Dict[str, JsonValue] = {self.VAT_ATTRIBUTE: self.VAT_INCLUDED}
        if group:
            attributes["group"] = group
        fields: Dict[str, RawValue] = {
            "sku_key": f"{service}/{group}/{name}/{quantity}",
            "service": service,
            "region": "ru",
            "source_url": self.PRICELIST_URL,
            "source_kind": PriceSourceKind.PAGE,
            "term": PriceTerm.NONE,
            "attributes": attributes,
        }
        if period is None:
            if not any(self.ON_REQUEST in cell for cell in row[1:]):
                return None
            fields.update(
                {"unit": PriceUnit.OTHER, "unit_raw": "quote", "model": PriceModel.QUOTE, "reason": self.QUOTE_REASON}
            )
            return self._price_fact(fields)
        amounts = prices[period]
        if len(amounts) > 1:
            attributes["list_price"] = str(amounts[0])
        if period != VkCloudPriceColumn.PER_MINUTE and prices.get(VkCloudPriceColumn.PER_MINUTE):
            attributes["per_minute"] = str(prices[VkCloudPriceColumn.PER_MINUTE][-1])
        match = self.QUANTITY.match(quantity)
        count = Decimal(match.group("count").replace(",", ".")) if match else Decimal(1)
        word = match.group("unit") if match else ""
        unit, factor = (
            self.UNITS.get((period, VkCloudQuantityUnit(word)), (PriceUnit.OTHER, Decimal(1)))
            if word in VkCloudQuantityUnit
            else (PriceUnit.OTHER, Decimal(1))
        )
        instance = self.INSTANCE.match(name)
        if instance is not None and unit == PriceUnit.UNIT_MONTH:
            unit = PriceUnit.MONTH
            fields.update(
                {
                    "instance_type": instance.group("type"),
                    "vcpu": int(instance.group("cpu")),
                    "memory_gib": Decimal(instance.group("ram")),
                }
            )
        price = amounts[-1]
        fields.update(
            {
                "unit": unit,
                "unit_raw": f"{quantity or name} / {period.value}",
                "unit_factor": factor * count,
                "price": price,
                "currency": self.PRICE_CURRENCY,
                "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
            }
        )
        return self._price_fact(fields)

    def _table_prices(self, title: str, rows: List[List[str]]) -> Iterator[ServicePrice]:
        """Read the prices of a price list table.

        Args:
            title (str): Its heading, the service.
            rows (List[List[str]]): Its rows, the first being its header.

        Yields:
            ServicePrice: The price of each priced row, a row restarting the columns being a header, and the quote
                of each row priced on request (in a table without price column too).
        """
        service = title.strip(" *") or self.name
        columns: Dict[int, VkCloudPriceColumn] = {}
        group = ""
        seen: Dict[str, int] = {}
        for row in rows:
            restart = self._columns(row)
            if any(role != VkCloudPriceColumn.VALUE for role in restart.values()) or (restart and not columns):
                columns, group = restart, row[0].strip(" *") if row[0] != "Параметр" else ""
                continue
            quote = any(self.ON_REQUEST in cell for cell in row[1:])
            fact = self._row_price(service, group, row, columns) if row[0] and (columns or quote) else None
            if fact is None:
                continue
            count = seen.get(fact.sku_key, 0)
            seen[fact.sku_key] = count + 1
            yield fact if not count else fact.model_copy(update={"sku_key": f"{fact.sku_key}#{count}"})

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the price list page.

        Yields:
            Request: Its request.
        """
        self.logger.info("Reading the %s prices from %s.", self.name, self.PRICELIST_URL)
        yield self._price_request(self.PRICELIST_URL)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the tables of the price list page.

        Args:
            response (Response): The price list page.

        Yields:
            PriceFact: The prices of every table.

        Raises:
            CatalogueFormatError: If the page has no price table.
        """
        tables = self._price_tables(response)
        if not tables:
            self.logger.error("The %s price list %s has no table.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the price list has no table")
        found = 0
        for title, rows in tables:
            for fact in self._table_prices(title, rows):
                found += 1
                yield fact
        self._record_price_source(self.PRICELIST_URL, found)
        self.logger.info("The %s price list is read: %d prices in %d tables.", self.name, found, len(tables))

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the services catalogue and of the products menu.

        Args:
            response (Response): The catalogue page.

        Returns:
            Iterator[CloudProduct]: Each valid product once, with the groups of all its listings.
        """
        rows = self.flight.rows(response)
        self.logger.debug("Reading the %d %s page rows of %s.", len(rows), self.name, response.url)
        listings = [*self._catalogue_products(rows, response), *self._menu_products(rows, response)]
        products = self._merge_categories(listings)
        self.logger.info(
            "%d %s products read from %s (%d listings before merging).",
            len(products),
            self.name,
            response.url,
            len(listings),
        )
        return iter(products)
