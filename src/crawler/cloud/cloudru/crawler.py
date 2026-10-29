from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.cloudru.enums import (
    CloudRuCatalogueTab,
    CloudRuProductField,
    CloudRuTariffColumn,
    CloudRuTariffField,
    CloudRuTariffPeriod,
    CloudRuTariffUnit,
)
from crawler.cloud.next_flight_data import NextFlightData
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class CloudRuCrawler(BaseCloudCrawler):
    """Cloud.ru (formerly SberCloud) catalogue crawler.

    Attributes:
        SITE_URL (ClassVar[str]): The website root, the product links being relative to it.
        PRODUCT_PATH (ClassVar[str]): The path of a product page, filled with the product slug.
        MARKETING_CATEGORIES (ClassVar[FrozenSet[CloudRuCatalogueTab]]): The slugs of the catalogue tabs which are
            selections, not categories (`Популярное`).
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The services catalogue page.
        TARIFFS_URL (ClassVar[str]): The tariffs home page, whose navigation lists every tariff document.
        DOCUMENTS_URL (ClassVar[str]): The root of the tariff document paths.
        SKIPPED_PATHS (ClassVar[re.Pattern[str]]): The navigation entries which are not tariff documents (indexes,
            archive, contents).
        SERVICE_TITLE (ClassVar[re.Pattern[str]]): The service named by a document title, between guillemets.
        EFFECTIVE (ClassVar[re.Pattern[str]]): The date a document takes effect, e.g. `14 октября 2026`.
        MONTHS (ClassVar[Dict[str, int]]): The months of the year, by their genitive name.
        INSTANCE (ClassVar[re.Pattern[str]]): The vCPUs and memory of an instance, e.g. `12vCPU/24GB RAM`.
        FLAVOR (ClassVar[re.Pattern[str]]): The flavor code ending an instance name, e.g. `(p2s.8xlarge.8.linux)`.
        NAME_LIMIT (ClassVar[int]): The longest instance type kept, a longer name being replaced by its flavor code.
        UNITS (ClassVar[Dict[Tuple[CloudRuTariffUnit, CloudRuTariffPeriod], Tuple[PriceUnit, Decimal]]]): The unit
            of a price by its unit and billing period, and the normalized units in one.
        PRICE_CURRENCY (ClassVar[str]): The currency of the prices.
        REGION (ClassVar[str]): The region of the prices (Russia).
        SERVICE_META (ClassVar[str]): The request meta holding the service of a document.
        VAT_ATTRIBUTE (ClassVar[str]): The attribute telling whether the price includes the VAT.
        VAT_EXCLUDED (ClassVar[str]): The prices kept exclude it.
        flight (NextFlightData): The reader of the Next.js flight data of the pages.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): The catalogue product pages are read too, for their prices.
        PAGE_TEXT_PRICES (ClassVar[bool]): A product page without price table is read for the prices in its text.

    Notes:
        The https://cloud.ru/products page is rendered by the Next.js App Router (no `__NEXT_DATA__` script): its
        product grid is drawn in the browser from the flight data of the page (see `NextFlightData`), which
        holds the whole catalogue in an object with a `categories` list (the catalogue tabs) and a `products` list.
        Each product gives its name (`title`), its description, its page (`customLink`, else
        `/products/<slug>`) and its tabs (`categories`, e.g. `Инфраструктура`), kept as written (in Russian). The
        `Популярное` tab is a selection of products, not a category: it is left out. The catalogue taxonomy is flat
        (no sub-category). The cloud platform of each product (`productPlatforms`: Evolution, Advanced,
        Облако VMware) is another filter of the page, already part of most product names: it is not a category. A
        product listed several times gets the categories of all its entries. The products marked unavailable are
        skipped. The page gives no date, and the sitemap dates every page with its generation day: the products are
        not dated.
        In price mode it reads the tariff documents (the appendices of the contract): the navigation of the tariffs
        home page lists them by platform (Evolution, Advanced, VMware, ML Space, CRS), each document being a page
        whose flight data holds its price tables (`columnDefinitions` and `data`). A row gives the service or
        resource priced, its unit and billing period, and its price in rubles with and without VAT. The price
        without VAT is kept (the other being an attribute), with the date the document takes effect. Each
        document is a source.
    """

    SITE_URL: ClassVar[str] = "https://cloud.ru/"
    PRODUCT_PATH: ClassVar[str] = "/products/{slug}"
    MARKETING_CATEGORIES: ClassVar[FrozenSet[CloudRuCatalogueTab]] = frozenset({CloudRuCatalogueTab.POPULAR})
    TARIFFS_URL: ClassVar[str] = "https://cloud.ru/documents/tariffs/index"
    DOCUMENTS_URL: ClassVar[str] = "https://cloud.ru/documents"
    SKIPPED_PATHS: ClassVar[re.Pattern[str]] = re.compile(r"/index$|/archive|/doc-contents")
    SERVICE_TITLE: ClassVar[re.Pattern[str]] = re.compile(r"«(?P<service>.+)»")
    EFFECTIVE: ClassVar[re.Pattern[str]] = re.compile(
        r"Вступление в силу:\s*(?P<day>\d{1,2})\s+(?P<month>\w+)\s+(?P<year>\d{4})"
    )
    MONTHS: ClassVar[Dict[str, int]] = {
        "января": 1,
        "февраля": 2,
        "марта": 3,
        "апреля": 4,
        "мая": 5,
        "июня": 6,
        "июля": 7,
        "августа": 8,
        "сентября": 9,
        "октября": 10,
        "ноября": 11,
        "декабря": 12,
    }
    INSTANCE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?P<cpu>\d+)\s*vCPU\W+(?P<ram>\d+(?:[.,]\d+)?)\s*(?:GB|ГБ)\s*RAM", re.IGNORECASE
    )
    FLAVOR: ClassVar[re.Pattern[str]] = re.compile(r"\((?P<flavor>[\w.-]+)\)\s*$")
    NAME_LIMIT: ClassVar[int] = 120
    UNITS: ClassVar[Dict[Tuple[CloudRuTariffUnit, CloudRuTariffPeriod], Tuple[PriceUnit, Decimal]]] = {
        (CloudRuTariffUnit.PIECE, CloudRuTariffPeriod.HOUR): (PriceUnit.UNIT_HOUR, Decimal(1)),
        (CloudRuTariffUnit.PIECE, CloudRuTariffPeriod.DAY): (PriceUnit.UNIT_HOUR, Decimal(24)),
        (CloudRuTariffUnit.PIECE, CloudRuTariffPeriod.MONTH): (PriceUnit.UNIT_MONTH, Decimal(1)),
        (CloudRuTariffUnit.PIECE, CloudRuTariffPeriod.YEAR): (PriceUnit.UNIT_MONTH, Decimal(12)),
        (CloudRuTariffUnit.PIECE, CloudRuTariffPeriod.ONCE): (PriceUnit.UNIT, Decimal(1)),
        (CloudRuTariffUnit.GB, CloudRuTariffPeriod.HOUR): (PriceUnit.GIB_HOUR, Decimal(1)),
        (CloudRuTariffUnit.GB, CloudRuTariffPeriod.DAY): (PriceUnit.GIB_HOUR, Decimal(24)),
        (CloudRuTariffUnit.GB, CloudRuTariffPeriod.MONTH): (PriceUnit.GIB_MONTH, Decimal(1)),
        (CloudRuTariffUnit.GB, CloudRuTariffPeriod.ONCE): (PriceUnit.GIB, Decimal(1)),
        (CloudRuTariffUnit.TB, CloudRuTariffPeriod.HOUR): (PriceUnit.GIB_HOUR, Decimal(1024)),
        (CloudRuTariffUnit.TB, CloudRuTariffPeriod.MONTH): (PriceUnit.GIB_MONTH, Decimal(1024)),
        (CloudRuTariffUnit.TB, CloudRuTariffPeriod.ONCE): (PriceUnit.GIB, Decimal(1024)),
    }
    PRICE_CURRENCY: ClassVar[str] = "RUB"
    REGION: ClassVar[str] = "ru"
    SERVICE_META: ClassVar[str] = "price_service"
    VAT_ATTRIBUTE: ClassVar[str] = "vat"
    VAT_EXCLUDED: ClassVar[str] = "excluded"

    PRODUCT_PAGE_PRICES: ClassVar[bool] = True
    PAGE_TEXT_PRICES: ClassVar[bool] = True
    name = "cloudru"
    catalogue_url: ClassVar[str] = "https://cloud.ru/products"

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

    def _catalogue(self, response: Response) -> List[JsonValue]:
        """Read the products of the catalogue held by the flight data of the page.

        Args:
            response (Response): The catalogue page.

        Returns:
            List[JsonValue]: The raw products, in the order of the catalogue.

        Raises:
            CatalogueFormatError: If the flight data holds no catalogue.
        """
        catalogue = self.flight.find(
            self.flight.documents(response), CloudRuProductField.PRODUCTS, CloudRuProductField.CATEGORIES
        )
        if catalogue is None:
            self.logger.error("The %s page %s holds no products catalogue.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the flight data holds no products catalogue")
        products = catalogue.get(CloudRuProductField.PRODUCTS)
        listed = products if isinstance(products, list) else []
        self.logger.debug("%d products in the %s catalogue of %s.", len(listed), self.name, response.url)
        return listed

    def _categories(self, product: Dict[str, JsonValue]) -> List[str]:
        """Read the catalogue tabs a product is filed under, without the selections.

        Args:
            product (Dict[str, JsonValue]): The raw product.

        Returns:
            List[str]: The category labels, as written on the website, in order.
        """
        categories = product.get(CloudRuProductField.CATEGORIES)
        labels: List[str] = []
        for category in categories if isinstance(categories, list) else []:
            fields = self._as_object(category)
            if self._as_text(fields.get(CloudRuProductField.SLUG)) in self.MARKETING_CATEGORIES:
                continue
            if label := self._as_text(fields.get(CloudRuProductField.TITLE)):
                labels.append(label)
        return labels

    def _product_url(self, product: Dict[str, JsonValue]) -> Optional[str]:
        """Get the absolute page URL of a product.

        Args:
            product (Dict[str, JsonValue]): The raw product.

        Returns:
            Optional[str]: Its custom link, else its `/products/<slug>` page, `None` without either.
        """
        link = (self._as_text(product.get(CloudRuProductField.CUSTOM_LINK)) or "").strip()
        slug = (self._as_text(product.get(CloudRuProductField.SLUG)) or "").strip()
        if not link and slug:
            link = self.PRODUCT_PATH.format(slug=slug)
        return urljoin(self.SITE_URL, link) if link else None

    def _product(self, value: JsonValue) -> Optional[CloudProduct]:
        """Build the product of a catalogue entry.

        Args:
            value (JsonValue): The raw product.

        Returns:
            Optional[CloudProduct]: The product, `None` for an unavailable or invalid entry (logged).
        """
        product = self._as_object(value)
        name = self._as_text(product.get(CloudRuProductField.TITLE))
        if product.get(CloudRuProductField.AVAILABLE) is False:
            self.logger.debug("Skipping the %s product %r, marked unavailable.", self.name, name)
            return None
        return self._build_product(
            name,
            self._as_text(product.get(CloudRuProductField.DESCRIPTION)),
            self._product_url(product),
            categories=self._categories(product),
        )

    def _documents(self, response: Response) -> Dict[str, str]:
        """Read the tariff documents listed by the navigation of a tariffs page.

        Args:
            response (Response): The tariffs page.

        Returns:
            Dict[str, str]: The service of each document (its title between guillemets), by URL.

        Raises:
            CatalogueFormatError: If the navigation lists no tariff document.
        """
        documents: Dict[str, str] = {}
        for entry in self.flight.objects(self.flight.documents(response)):
            href, title = entry.get(CloudRuTariffField.HREF), entry.get(CloudRuTariffField.TITLE)
            if not isinstance(href, str) or not href.startswith("/tariffs/") or not isinstance(title, str):
                continue
            if self.SKIPPED_PATHS.search(href):
                continue
            named = self.SERVICE_TITLE.search(title)
            documents.setdefault(f"{self.DOCUMENTS_URL}{href}", named.group("service") if named else title)
        if not documents:
            self.logger.error("The %s tariffs page %s lists no tariff document.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the tariffs navigation lists no document")
        return documents

    def _effective(self, response: Response) -> Optional[date]:
        """Read the date a tariff document takes effect.

        Args:
            response (Response): The document page.

        Returns:
            Optional[date]: The date, None when not stated.
        """
        match = self.EFFECTIVE.search(response.body.decode("utf-8", errors="replace"))
        month = self.MONTHS.get(match.group("month")) if match else None
        if match is None or month is None:
            self.logger.debug("The %s tariff document %s states no effective date.", self.name, response.url)
            return None
        return date(int(match.group("year")), month, int(match.group("day")))

    def _decimal(self, value: JsonValue) -> Optional[Decimal]:
        """Read a price written with a decimal comma.

        Args:
            value (JsonValue): The cell.

        Returns:
            Optional[Decimal]: The price, None when not a number.
        """
        text = re.sub(r"\s", "", str(value or "")).replace(",", ".")
        return Decimal(text) if re.fullmatch(r"\d+(?:\.\d+)?", text) else None

    def _row_price(
        self, row: Dict[str, str], service: str, url: str, effective: Optional[date]
    ) -> Optional[ServicePrice]:
        """Read the price of a tariff table row.

        Args:
            row (Dict[str, str]): The row, by column header start (`CloudRuTariffColumn`).
            service (str): The service of its document.
            url (str): Its document.
            effective (Optional[date]): The date the document takes effect.

        Returns:
            Optional[ServicePrice]: The price without VAT, None without price.
        """
        name = row.get(CloudRuTariffColumn.NAME, "")
        price = self._decimal(row.get(CloudRuTariffColumn.PRICE_WITHOUT_VAT))
        with_vat = self._decimal(row.get(CloudRuTariffColumn.PRICE_WITH_VAT))
        if not name or (price is None and with_vat is None):
            return None
        unit_raw, period_raw = row.get(CloudRuTariffColumn.UNIT, ""), row.get(CloudRuTariffColumn.PERIOD, "")
        unit, factor = (
            self.UNITS.get(
                (CloudRuTariffUnit(unit_raw), CloudRuTariffPeriod(period_raw)), (PriceUnit.OTHER, Decimal(1))
            )
            if unit_raw in CloudRuTariffUnit and period_raw in CloudRuTariffPeriod
            else (PriceUnit.OTHER, Decimal(1))
        )
        attributes: Dict[str, JsonValue] = {self.VAT_ATTRIBUTE: self.VAT_EXCLUDED if price is not None else "included"}
        if price is not None and with_vat is not None:
            attributes["price_with_vat"] = str(with_vat)
        amount = price if price is not None else with_vat
        fields: Dict[str, RawValue] = {
            "sku_key": f"{url.removeprefix(self.DOCUMENTS_URL)}/{name}/{unit_raw}/{period_raw}",
            "service": service,
            "family": url.removeprefix(f"{self.DOCUMENTS_URL}/tariffs/").split("/")[0],
            "region": self.REGION,
            "attributes": attributes,
            "unit": unit,
            "unit_raw": f"{unit_raw}/{period_raw}".strip("/") or None,
            "unit_factor": factor,
            "price": amount,
            "currency": self.PRICE_CURRENCY,
            "model": PriceModel.FREE if amount == 0 else PriceModel.ON_DEMAND,
            "term": PriceTerm.NONE,
            "effective_from": effective,
            "source_url": url,
            "source_kind": PriceSourceKind.DOCUMENT,
        }
        instance = self.INSTANCE.search(name)
        if instance is not None and unit == PriceUnit.UNIT_HOUR:
            flavor = self.FLAVOR.search(name)
            fields.update(
                {
                    "unit": PriceUnit.HOUR,
                    "instance_type": flavor.group("flavor")
                    if flavor
                    else name
                    if len(name) <= self.NAME_LIMIT
                    else None,
                    "vcpu": int(instance.group("cpu")),
                    "memory_gib": Decimal(instance.group("ram").replace(",", ".")),
                }
            )
        return self._price_fact(fields)

    def _tables(self, response: Response) -> Iterator[Dict[str, str]]:
        """Read the rows of the price tables of a tariff document.

        Args:
            response (Response): The document page.

        Yields:
            Dict[str, str]: Each row, by column header start (`CloudRuTariffColumn`), the other columns left out.
        """
        for table in self.flight.objects(self.flight.documents(response)):
            definitions, data = table.get(CloudRuTariffField.COLUMN_DEFINITIONS), table.get(CloudRuTariffField.DATA)
            if not isinstance(definitions, list) or not isinstance(data, list):
                continue
            keys: Dict[str, CloudRuTariffColumn] = {}
            for definition in definitions:
                header = definition.get(CloudRuTariffField.HEADER) if isinstance(definition, dict) else None
                key = definition.get(CloudRuTariffField.ACCESSOR_KEY) if isinstance(definition, dict) else None
                column = next((column for column in CloudRuTariffColumn if str(header).startswith(column)), None)
                if column is not None and isinstance(key, str):
                    keys[key] = column
            for row in data:
                if isinstance(row, dict):
                    yield {column.value: self._clean_text(str(row.get(key) or "")) for key, column in keys.items()}

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the tariffs home page, whose navigation lists the tariff documents.

        Yields:
            Request: Its request.
        """
        self.logger.info("Reading the %s tariff documents from %s.", self.name, self.TARIFFS_URL)
        yield self._price_request(self.TARIFFS_URL)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the tariffs home page, or a tariff document.

        Args:
            response (Response): The page.

        Yields:
            PriceFact: The requests of the tariff documents, or the prices of a document.

        Raises:
            CatalogueFormatError: If the page holds no flight data, or the navigation lists no document.
        """
        service = response.meta.get(self.SERVICE_META)
        if not isinstance(service, str):
            documents = self._documents(response)
            self.logger.info("%d %s tariff documents to read.", len(documents), self.name)
            for url, title in documents.items():
                yield self._price_request(url, {self.SERVICE_META: title})
            return
        url = str(response.url).split("?")[0]
        effective = self._effective(response)
        found = 0
        seen: Dict[str, int] = {}
        for row in self._tables(response):
            fact = self._row_price(row, service, url, effective)
            if fact is None:
                continue
            count = seen.get(fact.sku_key, 0)
            seen[fact.sku_key] = count + 1
            found += 1
            yield fact if not count else fact.model_copy(update={"sku_key": f"{fact.sku_key}#{count}"})
        self._record_price_source(url, found)
        self.logger.debug("The %s tariff document %s gave %d prices.", self.name, url, found)

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the catalogue, filed under their catalogue tabs.

        Args:
            response (Response): The catalogue page.

        Yields:
            Iterator[CloudProduct]: Each valid product, once, with the categories of all its entries.
        """
        products = [product for product in map(self._product, self._catalogue(response)) if product]
        yield from self._merge_categories(products)
