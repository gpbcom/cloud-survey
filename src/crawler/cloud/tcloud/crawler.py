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
from crawler.cloud.tcloud.enums import TCloudPriceField, TCloudPriceUnit
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class TCloudPublicCrawler(BaseCloudCrawler):
    """T Cloud Public (formerly Open Telekom Cloud) catalogue crawler.

    Attributes:
        SITEMAP_URL (ClassVar[str]): The sitemap of the website, listing the product pages.
        SITEMAP_PRODUCT_PAGE (ClassVar[re.Pattern[str]]): The sitemap pages of the core services, capturing the slug.
        NOT_PRODUCT_SLUG (ClassVar[re.Pattern[str]]): The core services pages which are not products: dashboards,
            price display, documentation, certifications and professional services.
        TITLE_SUFFIX (ClassVar[re.Pattern[str]]): The brand suffix of the page titles.
        SERVICE_LINK (ClassVar[str]): The CSS selector of the core service link of a table row.
        PRICES_URL (ClassVar[str]): A page of the public price API (no key), in euros.
        PAGE_SIZE (ClassVar[int]): The records of a page.
        PRICE_OFFSET (ClassVar[str]): The request meta holding the offset of a page.
        PRICE_CURRENCY (ClassVar[str]): The currency of the API.
        AMOUNT (ClassVar[re.Pattern[str]]): A price written with its currency, e.g. `6,239.000000 EUR`.
        GIB (ClassVar[re.Pattern[str]]): A memory, e.g. `8 GiB`.
        PRICE_UNITS (ClassVar[Dict[TCloudPriceUnit, Tuple[PriceUnit, Decimal]]]): The normalized unit of a unit, and
            the normalized units in one.
        RESERVATIONS (ClassVar[Tuple[Tuple[TCloudPriceField, PriceTerm, bool], ...]]): The reserved prices of a
            record: their field, term and whether paid upfront.
        RESERVED_UNIT (ClassVar[str]): The unit of a reserved price (a month).
        UNBOUNDED (ClassVar[int]): The upper bound written for a tier without one.
        GLOBAL_REGION (ClassVar[str]): The region of a record without region.
        NO_UNIT (ClassVar[str]): The unit written for a record without unit.
        price_pages (Set[int]): The offsets of the pages not read yet, in price mode.
        price_rows (int): The prices read, in price mode.

    Notes:
        The main source is the https://www.t-cloud-public.com/en/products-services/core-services page: a table
        per category whose rows link a core service page and describe it in a tooltip
        (`scale-tooltip div[slot=content]`). The sitemap completes it: its core services pages missing from the
        tables are requested and read from their first heading (the page titles are marketing taglines) and meta
        description, dated by their sitemap last modification (`lastmod`). The table products are undated. The
        heading row of each table names its category (e.g. `Computing`): a table product gets the category of every
        table it is listed in, a sitemap product none.
        In price mode it reads the public price API of the calculator (`PRICES_URL`, 500 records a page, the
        first page telling how many follow): a price per record (its region in its identifier), a tier of its
        group when tiered, and its monthly reserved prices (12, 24, 36 months, plain or upfront). The API is one
        source, recorded once all its pages are read.
    """

    SITEMAP_URL: ClassVar[str] = "https://www.t-cloud-public.com/en/sitemap.xml"
    SITEMAP_PRODUCT_PAGE: ClassVar[re.Pattern[str]] = re.compile(
        r"^https://www\.t-cloud-public\.com/en/products-services/core-services/([\w-]+)/?$", re.IGNORECASE
    )
    NOT_PRODUCT_SLUG: ClassVar[re.Pattern[str]] = re.compile(
        r"dashboard|price|pricing|documentation|certification|professional-services", re.IGNORECASE
    )
    TITLE_SUFFIX: ClassVar[re.Pattern[str]] = re.compile(r"\s*\|\s*(?:T Cloud Public|Open Telekom Cloud)\s*$")
    SERVICE_LINK: ClassVar[str] = 'a[href*="/core-services/"]'

    name = "tcloud"
    catalogue_url: ClassVar[str] = "https://www.t-cloud-public.com/en/products-services/core-services"
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    dates_sitemaps: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("T Cloud Public ", "Open Telekom Cloud ")
    PRICES_URL: ClassVar[str] = "https://calculator.otc-service.com/en/open-telekom-price-api/?limitFrom={offset}"
    PAGE_SIZE: ClassVar[int] = 500
    PRICE_OFFSET: ClassVar[str] = "price_offset"
    PRICE_CURRENCY: ClassVar[str] = "EUR"
    AMOUNT: ClassVar[re.Pattern[str]] = re.compile(r"^([\d,]+(?:\.\d+)?) [A-Z]{3}$")
    GIB: ClassVar[re.Pattern[str]] = re.compile(r"^([\d.]+)\s*GiB$")
    PRICE_UNITS: ClassVar[Dict[TCloudPriceUnit, Tuple[PriceUnit, Decimal]]] = {
        TCloudPriceUnit.HOUR: (PriceUnit.HOUR, Decimal(1)),
        TCloudPriceUnit.HOUR_PER_MONTH: (PriceUnit.HOUR, Decimal(1)),
        TCloudPriceUnit.MONTH: (PriceUnit.MONTH, Decimal(1)),
        TCloudPriceUnit.GB: (PriceUnit.GIB, Decimal(1)),
        TCloudPriceUnit.GB_MONTH: (PriceUnit.GIB_MONTH, Decimal(1)),
        TCloudPriceUnit.REQUEST: (PriceUnit.REQUEST, Decimal(1)),
        TCloudPriceUnit.RESTORE: (PriceUnit.REQUEST, Decimal(1)),
        TCloudPriceUnit.MILLION_ITEMS_MONTH: (PriceUnit.REQUEST, Decimal(1_000_000)),
        TCloudPriceUnit.ITEM_MONTH: (PriceUnit.UNIT_MONTH, Decimal(1)),
        TCloudPriceUnit.RULES_HOUR: (PriceUnit.UNIT_HOUR, Decimal(1)),
        TCloudPriceUnit.MBIT_HOUR: (PriceUnit.UNIT_HOUR, Decimal(1)),
        TCloudPriceUnit.REQUESTS: (PriceUnit.REQUEST, Decimal(1)),
        TCloudPriceUnit.THOUSAND_REQUESTS: (PriceUnit.REQUEST, Decimal(1000)),
        TCloudPriceUnit.CORES_BROKERS_HOUR: (PriceUnit.VCPU_HOUR, Decimal(1)),
        TCloudPriceUnit.GB_MONTH_CAPITAL: (PriceUnit.GIB_MONTH, Decimal(1)),
        TCloudPriceUnit.LCU_HOUR_ZONE: (PriceUnit.UNIT_HOUR, Decimal(1)),
        TCloudPriceUnit.PIECE: (PriceUnit.UNIT, Decimal(1)),
        TCloudPriceUnit.PIECES: (PriceUnit.UNIT, Decimal(1)),
        TCloudPriceUnit.GB_HOURS: (PriceUnit.GIB_HOUR, Decimal(1)),
        TCloudPriceUnit.ITEM_ONE_TIME: (PriceUnit.ONE_TIME, Decimal(1)),
    }
    RESERVATIONS: ClassVar[Tuple[Tuple[TCloudPriceField, PriceTerm, bool], ...]] = (
        (TCloudPriceField.RESERVED_12, PriceTerm.ONE_YEAR, False),
        (TCloudPriceField.RESERVED_24, PriceTerm.TWO_YEARS, False),
        (TCloudPriceField.RESERVED_36, PriceTerm.THREE_YEARS, False),
        (TCloudPriceField.UPFRONT_12, PriceTerm.ONE_YEAR, True),
        (TCloudPriceField.UPFRONT_24, PriceTerm.TWO_YEARS, True),
        (TCloudPriceField.UPFRONT_36, PriceTerm.THREE_YEARS, True),
    )
    RESERVED_UNIT: ClassVar[str] = "month"
    UNBOUNDED: ClassVar[int] = 999_999_999_999
    GLOBAL_REGION: ClassVar[str] = "global"
    NO_UNIT: ClassVar[str] = "none"

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.price_pages: Set[int] = set()
        self.price_rows = 0

    ############################
    # Internal Helpers Methods #
    ############################

    def _page_title(self, title: str) -> str:
        """Clean the product name read from a product page title: the brand suffix is removed.

        Args:
            title (str): The page title, e.g. `Bare Metal Server | T Cloud Public`.

        Returns:
            str: The product name, e.g. `Bare Metal Server`.
        """
        return self._clean_text(self.TITLE_SUFFIX.sub("", self._clean_text(title)))

    def _page_name(self, response: Response) -> Optional[str]:
        """Read the product name of a product page: its first heading, else its Open Graph title.

        The Open Graph titles are marketing taglines, e.g. `Virtual machines from the cloud`.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The product name, `None` when the page has none.
        """
        heading = response.css("h1").first
        title = heading.get_all_text(separator=" ", strip=True) if heading is not None else None
        if title:
            return self._page_title(title)
        return super()._page_name(response)

    def _table_category(self, table: Selector) -> str:
        """Read the category of a services table: the first cell of its first row without core service link.

        Args:
            table (Selector): The services table.

        Returns:
            str: The category, e.g. `Computing`, empty when the table has no heading row.
        """
        for row in table.css("tr"):
            if row.css(self.SERVICE_LINK).first is None:
                cell = row.css("td, th").first
                return self._clean_text(cell.get_all_text(separator=" ", strip=True)) if cell is not None else ""
        return ""

    def _table_categories(self, response: Response) -> Dict[str, List[str]]:
        """Gather the categories of the services table rows, by core service page (`_url_key`).

        Args:
            response (Response): The core services page.

        Returns:
            Dict[str, List[str]]: The categories of each core service page, in page order.
        """
        categories: Dict[str, List[str]] = {}
        for table in response.css("table"):
            category = self._table_category(table)
            for link in table.css(self.SERVICE_LINK):
                key = self._url_key(urljoin(response.url, str(link.attrib[HtmlAttribute.HREF])))
                categories.setdefault(key, []).append(category)
        self.logger.debug("%d categorized core services on %s.", len(categories), response.url)
        return categories

    def _row_product(self, row: Selector, page_url: str, categories: Dict[str, List[str]]) -> Optional[CloudProduct]:
        """Extract the product of a services table row.

        Args:
            row (Selector): The table row.
            page_url (str): The catalogue page URL, the row links being relative to it.
            categories (Dict[str, List[str]]): The categories of each core service page, by `_url_key`.

        Returns:
            Optional[CloudProduct]: The product, `None` for a row without core service link or an invalid one.
        """
        link = next(iter(row.css(self.SERVICE_LINK)), None)
        if link is None:
            self.logger.debug("Skipping a services table row without core service link.")
            return None
        tooltip = row.css("scale-tooltip div[slot=content]").first
        description = tooltip.get_all_text(separator=" ", strip=True) if tooltip is not None else None
        name = link.get_all_text(separator=" ", strip=True)
        url = urljoin(page_url, str(link.attrib[HtmlAttribute.HREF]))
        return self._build_product(name, description, url, categories=categories.get(self._url_key(url), []))

    def _table_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the services tables.

        Args:
            response (Response): The core services page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the tables.
        """
        rows = response.css("tr")
        self.logger.debug("%d services table rows found on %s.", len(rows), response.url)
        categories = self._table_categories(response)
        for row in rows:
            if product := self._row_product(row, response.url, categories):
                yield product

    def _is_product_page(self, url: str) -> bool:
        """Tell whether a sitemap page is a core service product page.

        Args:
            url (str): The sitemap page URL.

        Returns:
            bool: Whether the page is a core service page which is not a tool, documentation or service page.
        """
        page = self.SITEMAP_PRODUCT_PAGE.match(url)
        if page is None:
            return False
        if self.NOT_PRODUCT_SLUG.search(page.group(1)):
            self.logger.debug("Skipping the sitemap page %s, not a product.", url)
            return False
        return True

    def _sitemap_requests(self, response: Response) -> List[Request]:
        """Request the core service pages of the sitemap missing from the tables, with their last modification.

        Args:
            response (Response): The sitemap.

        Returns:
            List[Request]: The product page requests.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        entries = self._sitemap_entries(response)
        pages = [url for url in entries if self._is_product_page(url)]
        requests = [
            request for url in pages if (request := self._product_page_request(url, updated=entries[url])) is not None
        ]
        self.logger.info(
            "%d %s product pages to check in the sitemap (%d product pages, %d pages).",
            len(requests),
            self.name,
            len(pages),
            len(entries),
        )
        return requests

    def _amount(self, text: JsonValue) -> Optional[Decimal]:
        """Read a price written with its currency, e.g. `6,239.000000 EUR`.

        Args:
            text (JsonValue): The written price.

        Returns:
            Optional[Decimal]: The price, `None` when unreadable.
        """
        match = self.AMOUNT.match(text) if isinstance(text, str) else None
        return Decimal(match[1].replace(",", "")) if match else None

    def _record_prices(self, record: Dict[str, JsonValue], source: str) -> Iterator[ServicePrice]:
        """Read the prices of a record of the price API: pay as you go, then each reservation.

        Args:
            record (Dict[str, JsonValue]): The record.
            source (str): The source of its prices (the first page of the API).

        Yields:
            ServicePrice: Its pay-as-you-go price (a tier of its group, if tiered), then its monthly reserved
                prices (12, 24, 36 months, plain and upfront) that are not 0.
        """
        identifier = record.get(TCloudPriceField.ID)
        price = self._amount(record.get(TCloudPriceField.PRICE_AMOUNT))
        if not isinstance(identifier, str) or price is None:
            self.logger.debug("A T Cloud Public record has no identifier or price: skipped.")
            return
        unit_text = str(record.get(TCloudPriceField.UNIT) or "")
        try:
            unit, factor = self.PRICE_UNITS[TCloudPriceUnit(unit_text)]
        except ValueError:
            self.logger.debug("The T Cloud Public unit %r has no known unit: kept as other.", unit_text)
            unit, factor = PriceUnit.OTHER, Decimal(1)
        vcpu = record.get(TCloudPriceField.VCPU)
        memory = self.GIB.match(str(record.get(TCloudPriceField.RAM) or ""))
        tiered = bool(record.get(TCloudPriceField.ID_GROUP_TIERED))
        start, end = record.get(TCloudPriceField.FROM_ON), record.get(TCloudPriceField.UP_TO)
        fields: Dict[str, RawValue] = {
            "sku_key": identifier,
            "service": record.get(TCloudPriceField.PRODUCT_ID),
            "family": record.get(TCloudPriceField.PRODUCT_FAMILY) or None,
            "region": record.get(TCloudPriceField.REGION) or self.GLOBAL_REGION,
            "instance_type": record.get(TCloudPriceField.OPI_FLAVOUR) or None,
            "vcpu": vcpu if isinstance(vcpu, str) and vcpu.isdigit() and int(vcpu) > 0 else None,
            "memory_gib": memory[1] if memory and Decimal(memory[1]) > 0 else None,
            "os": record.get(TCloudPriceField.OS_UNIT) or None,
            "attributes": {
                field.value: record.get(field)
                for field in (TCloudPriceField.PRODUCT_NAME, TCloudPriceField.PRODUCT_SECTION)
                if record.get(field)
            },
            "unit": unit,
            "unit_raw": unit_text or self.NO_UNIT,
            "unit_factor": factor,
            "price": price,
            "currency": self.PRICE_CURRENCY,
            "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
            "tier_start": start if tiered and isinstance(start, int) else 0,
            "tier_end": end if tiered and isinstance(end, int) and end < self.UNBOUNDED else None,
            "source_url": source,
            "source_kind": PriceSourceKind.API,
        }
        fact = self._price_fact(fields)
        if fact is not None:
            yield fact
        for field, term, upfront in self.RESERVATIONS:
            reserved = self._amount(record.get(field))
            if reserved is None or reserved == 0:
                continue
            fact = self._price_fact(
                {
                    **fields,
                    "sku_key": f"{identifier}/{field.value}",
                    "unit": PriceUnit.MONTH,
                    "unit_raw": self.RESERVED_UNIT,
                    "unit_factor": Decimal(1),
                    "price": reserved,
                    "model": PriceModel.RESERVED,
                    "term": term,
                    "attributes": {
                        **(fields["attributes"] if isinstance(fields["attributes"], dict) else {}),
                        "upfront": upfront,
                    },
                }
            )
            if fact is not None:
                yield fact

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the first page of the price API, which tells how many pages follow.

        Yields:
            Request: The request of the first page.
        """
        self.price_pages = set()
        self.price_rows = 0
        self.logger.info("Reading the T Cloud Public prices from %s.", self.PRICES_URL)
        yield self._price_request(self.PRICES_URL.format(offset=0), {self.PRICE_OFFSET: 0})

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read a page of the price API: the following pages first (from the first one), then its prices.

        Args:
            response (Response): The page.

        Yields:
            PriceFact: The requests of the following pages, then the prices of the page.

        Raises:
            CatalogueFormatError: If the page lists no prices.
        """
        data = self._json_body(response)
        body = data.get(TCloudPriceField.RESPONSE) if isinstance(data, dict) else None
        result = body.get(TCloudPriceField.RESULT) if isinstance(body, dict) else None
        if not isinstance(body, dict) or not isinstance(result, dict):
            self.logger.error("The T Cloud Public price page %s lists no prices.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the price page lists no prices")
        offset = response.meta.get(self.PRICE_OFFSET)
        offset = offset if isinstance(offset, int) else 0
        if offset == 0:
            stats = body.get(TCloudPriceField.STATS)
            pages = stats.get(TCloudPriceField.MAX_PAGES) if isinstance(stats, dict) else None
            following = [page * self.PAGE_SIZE for page in range(1, pages if isinstance(pages, int) else 1)]
            self.price_pages = set(following)
            for start in following:
                yield self._price_request(self.PRICES_URL.format(offset=start), {self.PRICE_OFFSET: start})
            self.logger.info("The T Cloud Public price API has %d pages.", len(following) + 1)
        found = 0
        source = self.PRICES_URL.format(offset=0)
        for records in result.values():
            for record in records if isinstance(records, list) else []:
                for fact in self._record_prices(record, source) if isinstance(record, dict) else iter(()):
                    found += 1
                    yield fact
        self.price_rows += found
        self.price_pages.discard(offset)
        if not self.price_pages:
            self._record_price_source(source, self.price_rows)
            self.logger.info("The T Cloud Public price API is read whole: %d prices.", self.price_rows)

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the services tables.

        Args:
            response (Response): The core services page.

        Returns:
            Iterator[CloudProduct]: The valid products of the tables.
        """
        self.logger.debug("Reading the %s service tables of %s.", self.name, response.url)
        return self._table_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the table products, request the sitemap product pages, or stream a sitemap product page.

        Args:
            response (Response): The core services page, the sitemap or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, or the product page requests.

        Raises:
            EmptyCatalogueError: If the core services page holds no valid product.
            CatalogueFormatError: If the sitemap lists no page.
        """
        if response.url == self.SITEMAP_URL and self.PAGE_DATES not in response.meta:
            self.logger.debug("Reading the %s sitemap %s.", self.name, response.url)
            for request in self._sitemap_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
