from __future__ import annotations

# Standard Library Imports.
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import urlencode, urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.azure.enums import (
    AzureCssClass,
    AzureHtmlTag,
    AzureLearnLabel,
    AzurePriceField,
    AzurePriceType,
    AzureTerm,
    AzureUnitSuffix,
    AzureUpdateField,
    AzureUpdatesParameter,
)
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from models.cloud.enums import DateCaveat, PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class AzureCrawler(BaseCloudCrawler):
    """Microsoft Azure catalogue crawler.

    Attributes:
        LEARN_URL (ClassVar[str]): The Microsoft Learn directory of every Azure product documentation.
        LEARN_SECTION_CLASS (ClassVar[AzureCssClass]): The class of the Microsoft Learn directory sections listing the
            products of a category under its `h3` heading.
        UPDATES_URL (ClassVar[str]): The Azure Updates API (OData, no key), dating the launch of the products.
        FIRST_UPDATES (ClassVar[int]): How many of the earliest updates naming a product are read.
        UPDATE_EARLIEST_DATE (ClassVar[datetime]): The earliest plausible date of an update.
        MONTH_FORMAT (ClassVar[str]): The format of the availability months of an update.
        CREATED_FORMAT (ClassVar[str]): The format of the publication date of an update, to the second.
        BRAND_PREFIXES (ClassVar[Tuple[str, ...]]): The brand prefixes the feed may add to, or drop from, a name.
        PRICES_URL (ClassVar[str]): The Retail Prices API (no key), every meter price in dollars, 1,000 a page.
        MEASURE (ClassVar[re.Pattern[str]]): A unit of measure: its number, its multiplier (`K`, `M`) and its suffix.
        MULTIPLIERS (ClassVar[Dict[str, Decimal]]): The value of a multiplier.
        MEASURE_UNITS (ClassVar[Dict[AzureUnitSuffix, Tuple[PriceUnit, Decimal]]]): The normalized unit of a suffix,
            and the normalized units in one.
        TERMS (ClassVar[Dict[str, PriceTerm]]): The term of a reservation or of a savings plan.
        TERM_YEARS (ClassVar[Dict[str, int]]): The years of a term (a reservation is priced for its whole term).
        GLOBAL_REGION (ClassVar[str]): The region of a price without region.
        COMPUTE_FAMILY (ClassVar[str]): The service family whose resource SKU is an instance type.
        VM_SERVICE (ClassVar[str]): The service of the virtual machines (their operating system read).
        WINDOWS_PRODUCT (ClassVar[re.Pattern[str]]): A Windows virtual machine product.
        WINDOWS (ClassVar[str]): The operating system of a Windows virtual machine.
        LINUX (ClassVar[str]): The operating system of another virtual machine.
        PRICE_FILTERS (ClassVar[Tuple[str, ...]]): The OData filters splitting the API into listings of fewer than a
            million items (it refuses to skip more), each a source: the compute pay-as-you-go prices, the other
            compute prices, then every other family.
        FILTER_PARAMETER (ClassVar[str]): The filter parameter of the API.
        PRICE_SOURCE (ClassVar[str]): The request meta holding the listing of a page.
        price_rows (Dict[str, int]): The prices read from each listing, in price mode.

    Notes:
        The main source is the product cards of the https://azure.microsoft.com/en-us/products/ page (generally
        available products). The Microsoft Learn directory completes it with the products missing from the page.
        Both pages list a product in each of its categories: the products page under the `h2` heading of each
        category, the Microsoft Learn directory in a section per category (besides its flat grid of cards).
        The categories of a product are gathered over the whole page before it is streamed.
        Neither page dates the products: each product is dated by the earliest Azure update naming it
        (`dates_launches`), the earliest of the availability months and publication dates of the earliest updates
        naming it (its first preview or general availability). The feed names a product exactly: a catalogue name is
        looked up as given, without its brand prefix, with each brand prefix, then under the name the launch dates
        catalogue's aliases give it. The feed starts on 2013-11-21: a product first named before June 2014 is likely
        older (`FEED_START`).
        In price mode it reads the Retail Prices API (`PRICES_URL`), page by page (`NextPageLink`): a price per
        meter, region, kind and tier (`tierMinimumUnits`), in dollars, and one more per savings plan term. A
        reservation is priced for its whole term, so it is per year, its factor being the years of its term. The
        API refuses to skip a million items: it is read as filtered listings (`PRICE_FILTERS`), each a source
        recorded once its last page is read.
    """

    LEARN_URL: ClassVar[str] = "https://learn.microsoft.com/en-us/azure/?product=all"
    LEARN_SECTION_CLASS: ClassVar[AzureCssClass] = AzureCssClass.BOX

    name = "azure"
    catalogue_url: ClassVar[str] = "https://azure.microsoft.com/en-us/products/"
    complement_urls: ClassVar[Tuple[str, ...]] = (LEARN_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Microsoft Azure ", "Azure AI ", "Microsoft ", "Azure ")
    dates_launches: ClassVar[bool] = True
    launch_feed_start: ClassVar[Optional[datetime]] = datetime(2014, 6, 1, tzinfo=UTC)
    UPDATES_URL: ClassVar[str] = "https://www.microsoft.com/releasecommunications/api/v2/azure"
    FIRST_UPDATES: ClassVar[int] = 10
    UPDATE_EARLIEST_DATE: ClassVar[datetime] = datetime(2008, 1, 1, tzinfo=UTC)
    MONTH_FORMAT: ClassVar[str] = "%Y-%m"
    CREATED_FORMAT: ClassVar[str] = "%Y-%m-%dT%H:%M:%S"
    BRAND_PREFIXES: ClassVar[Tuple[str, ...]] = ("Azure ", "Microsoft ", "Azure AI ")
    PRICES_URL: ClassVar[str] = "https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview"
    MEASURE: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<count>\d+(?:\.\d+)?)\s*(?P<multiplier>[KM](?=\s|/|$))?\s*(?P<suffix>.*)$"
    )
    MULTIPLIERS: ClassVar[Dict[str, Decimal]] = {"K": Decimal(1000), "M": Decimal(1_000_000)}
    MEASURE_UNITS: ClassVar[Dict[AzureUnitSuffix, Tuple[PriceUnit, Decimal]]] = {
        AzureUnitSuffix.COUNT: (PriceUnit.REQUEST, Decimal(1)),
        AzureUnitSuffix.HOUR: (PriceUnit.HOUR, Decimal(1)),
        AzureUnitSuffix.HOURS: (PriceUnit.HOUR, Decimal(1)),
        AzureUnitSuffix.PER_HOUR: (PriceUnit.UNIT_HOUR, Decimal(1)),
        AzureUnitSuffix.PER_DAY: (PriceUnit.UNIT_HOUR, Decimal(24)),
        AzureUnitSuffix.PER_MONTH: (PriceUnit.UNIT_MONTH, Decimal(1)),
        AzureUnitSuffix.PER_YEAR: (PriceUnit.YEAR, Decimal(1)),
        AzureUnitSuffix.PER_SECOND: (PriceUnit.OTHER, Decimal(1)),
        AzureUnitSuffix.GB: (PriceUnit.GIB, Decimal(1)),
        AzureUnitSuffix.GIB: (PriceUnit.GIB, Decimal(1)),
        AzureUnitSuffix.MB: (PriceUnit.GIB, Decimal(1) / Decimal(1024)),
        AzureUnitSuffix.TB: (PriceUnit.GIB, Decimal(1024)),
        AzureUnitSuffix.GB_MONTH: (PriceUnit.GIB_MONTH, Decimal(1)),
        AzureUnitSuffix.GIB_MONTH: (PriceUnit.GIB_MONTH, Decimal(1)),
        AzureUnitSuffix.TB_MONTH: (PriceUnit.GIB_MONTH, Decimal(1024)),
        AzureUnitSuffix.GB_HOUR: (PriceUnit.GIB_HOUR, Decimal(1)),
        AzureUnitSuffix.GIB_HOUR: (PriceUnit.GIB_HOUR, Decimal(1)),
        AzureUnitSuffix.GB_DAY: (PriceUnit.OTHER, Decimal(1)),
        AzureUnitSuffix.SECOND: (PriceUnit.SECOND, Decimal(1)),
        AzureUnitSuffix.SECONDS: (PriceUnit.SECOND, Decimal(1)),
        AzureUnitSuffix.MINUTE: (PriceUnit.MINUTE, Decimal(1)),
        AzureUnitSuffix.MINUTES: (PriceUnit.MINUTE, Decimal(1)),
        AzureUnitSuffix.DAY: (PriceUnit.HOUR, Decimal(24)),
        AzureUnitSuffix.DAYS: (PriceUnit.HOUR, Decimal(24)),
    }
    TERMS: ClassVar[Dict[str, PriceTerm]] = {
        AzureTerm.ONE_YEAR: PriceTerm.ONE_YEAR,
        AzureTerm.THREE_YEARS: PriceTerm.THREE_YEARS,
        AzureTerm.FIVE_YEARS: PriceTerm.FIVE_YEARS,
        AzureTerm.TEN_YEARS: PriceTerm.TEN_YEARS,
    }
    TERM_YEARS: ClassVar[Dict[str, int]] = {
        AzureTerm.ONE_YEAR: 1,
        AzureTerm.THREE_YEARS: 3,
        AzureTerm.FIVE_YEARS: 5,
        AzureTerm.TEN_YEARS: 10,
    }
    GLOBAL_REGION: ClassVar[str] = "global"
    COMPUTE_FAMILY: ClassVar[str] = "Compute"
    VM_SERVICE: ClassVar[str] = "Virtual Machines"
    WINDOWS_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(r"\bWindows\b")
    WINDOWS: ClassVar[str] = "windows"
    LINUX: ClassVar[str] = "linux"
    PRICE_FILTERS: ClassVar[Tuple[str, ...]] = (
        "serviceFamily eq 'Compute' and priceType eq 'Consumption'",
        "serviceFamily eq 'Compute' and priceType ne 'Consumption'",
        "serviceFamily ne 'Compute'",
    )
    FILTER_PARAMETER: ClassVar[str] = "$filter"
    PRICE_SOURCE: ClassVar[str] = "price_source"

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.price_rows: Dict[str, int] = {}

    ############################
    # Internal Helpers Methods #
    ############################

    def _update_names(self, name: str, alias: Optional[str]) -> List[str]:
        """Get the names the Azure Updates feed may give a catalogue product.

        Args:
            name (str): The catalogue name.
            alias (Optional[str]): The name the launch dates catalogue's aliases give it, if any.

        Returns:
            List[str]: The names, each once, the catalogue name first.
        """
        base = next((name.removeprefix(prefix) for prefix in self.name_prefixes if name.startswith(prefix)), name)
        names = [name, base, *(f"{prefix}{base}" for prefix in self.BRAND_PREFIXES)]
        return list(dict.fromkeys([*names, alias] if alias else names))

    def _literal(self, text: str) -> str:
        """Quote a text as an OData string literal.

        Args:
            text (str): The text.

        Returns:
            str: The literal, its quotes doubled.
        """
        return "'" + text.replace("'", "''") + "'"

    def _updates_query(self, name: str, alias: Optional[str] = None) -> Dict[str, str]:
        """Build the query of the earliest Azure updates naming a product.

        Args:
            name (str): The catalogue name.
            alias (Optional[str]): The name the launch dates catalogue's aliases give it, if any.

        Returns:
            Dict[str, str]: The OData query parameters.
        """
        candidates = self._update_names(name, alias)
        self.logger.debug("Querying the Azure updates naming %r under %d name(s).", name, len(candidates))
        names = " or ".join(f"p eq {self._literal(candidate)}" for candidate in candidates)
        fields = (
            AzureUpdateField.PRODUCTS,
            AzureUpdateField.GENERAL_AVAILABILITY,
            AzureUpdateField.PREVIEW,
            AzureUpdateField.CREATED,
        )
        return {
            AzureUpdatesParameter.FILTER: f"{AzureUpdateField.PRODUCTS}/any(p: {names})",
            AzureUpdatesParameter.ORDER_BY: f"{AzureUpdateField.CREATED} asc",
            AzureUpdatesParameter.TOP: str(self.FIRST_UPDATES),
            AzureUpdatesParameter.SELECT: ",".join(fields),
        }

    def _update_date(self, value: JsonValue, date_format: str, length: int) -> Optional[datetime]:
        """Parse a date of an Azure update.

        Args:
            value (JsonValue): The raw date.
            date_format (str): Its format.
            length (int): How many leading characters the format reads.

        Returns:
            Optional[datetime]: The date in UTC, `None` when missing, unreadable or implausible.
        """
        if not isinstance(value, str) or len(value) < length:
            return None
        try:
            parsed = datetime.strptime(value[:length], date_format).replace(tzinfo=UTC)
        except ValueError:
            self.logger.debug("Ignoring the unreadable update date %r.", value)
            return None
        if not self.UPDATE_EARLIEST_DATE <= parsed <= datetime.now(UTC):
            self.logger.debug("Ignoring the implausible update date %r.", value)
            return None
        return parsed

    def _update_dates(self, update: Dict[str, JsonValue]) -> List[datetime]:
        """Get the dates of an Azure update: its availability months and its publication.

        Args:
            update (Dict[str, JsonValue]): The update.

        Returns:
            List[datetime]: The readable dates.
        """
        months = [update.get(AzureUpdateField.PREVIEW), update.get(AzureUpdateField.GENERAL_AVAILABILITY)]
        dates = [self._update_date(month, self.MONTH_FORMAT, 7) for month in months]
        dates.append(self._update_date(update.get(AzureUpdateField.CREATED), self.CREATED_FORMAT, 19))
        return [date for date in dates if date is not None]

    def _first_update(self, payload: JsonValue, name: str) -> Optional[Tuple[datetime, DateCaveat]]:
        """Read the launch of a product from the earliest Azure updates naming it.

        Args:
            payload (JsonValue): The API response.
            name (str): The catalogue name, for the logs.

        Returns:
            Optional[Tuple[datetime, DateCaveat]]: The launch and its caveat (`FEED_START` in the first months of the
                feed, else `FIRST_ANNOUNCEMENT`), `None` when no update names the product.
        """
        updates = payload.get(AzureUpdateField.VALUE) if isinstance(payload, dict) else None
        if not isinstance(updates, list):
            self.logger.warning("The Azure Updates response for %r holds no update list.", name)
            return None
        dates = [date for update in updates if isinstance(update, dict) for date in self._update_dates(update)]
        if not dates:
            self.logger.debug("No Azure update names %r.", name)
            return None
        self.logger.debug("%r first named by Azure Updates on %s.", name, min(dates).date().isoformat())
        return self._announced(min(dates))

    async def _launch_source(self, product: CloudProduct) -> Optional[Tuple[datetime, DateCaveat]]:
        """Read the launch of a product from the earliest Azure updates naming it.

        Args:
            product (CloudProduct): The product, undated.

        Returns:
            Optional[Tuple[datetime, DateCaveat]]: The launch and its caveat, `None` when no update names it or the
                API cannot be read.

        Raises:
            CatalogueFormatError: If the API response is not JSON.
        """
        alias = self.launch_aliases.get(self._name_key(product.name))
        response = await self._fetch_launch_page(self.UPDATES_URL, self._updates_query(product.name, alias))
        if response is None:
            self.logger.debug("No Azure Updates answer for %r, it stays undated.", product.name)
            return None
        return self._first_update(self._json_body(response), product.name)

    def _products_page_cards(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the product cards of the products page, each with the category heading it is listed under.

        Args:
            response (Response): The products page.

        Yields:
            Iterator[CloudProduct]: Each valid product card, a product being listed in each of its categories.
        """
        elements = response.css("h2, div.content-card-list div.card")
        self.logger.debug("%d headings and product cards in %s.", len(elements), response.url)
        category: Optional[str] = None
        for element in elements:
            if element.tag == AzureHtmlTag.H2:
                category = element.get_all_text(separator=" ", strip=True)
                continue
            heading = element.css(".card-body h3").first
            description = element.css(".card-body [data-oc-token-text] p").first
            if heading is None or description is None:
                self.logger.debug("Skipping a product card without name or description.")
                continue
            link = element.css('a[data-bi-cn="Product"]').first or element.css("a[href]").first
            url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, "")) if link is not None else None
            name = heading.get_all_text(separator=" ", strip=True)
            text = description.get_all_text(separator=" ", strip=True)
            if product := self._build_product(name, text, url, categories=[category]):
                yield product

    def _products_page_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products page, skipping the empty cards.

        Args:
            response (Response): The products page.

        Yields:
            Iterator[CloudProduct]: Each valid product, with the categories of all its cards.
        """
        yield from self._merge_categories(self._products_page_cards(response))

    def _learn_category(self, card: Selector) -> Optional[str]:
        """Get the category of a Microsoft Learn directory card: the heading of the section holding it.

        Args:
            card (Selector): The documentation card.

        Returns:
            Optional[str]: The category, `None` when the card is not in a category section (flat grid).
        """
        for ancestor in card.iterancestors():
            classes = ancestor.attrib.get(HtmlAttribute.CLASS, "").split()
            if ancestor.tag == AzureHtmlTag.DIV and self.LEARN_SECTION_CLASS in classes:
                heading = ancestor.css("h3").first
                return heading.get_all_text(separator=" ", strip=True) if heading is not None else None
        return None

    def _learn_cards(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the cards of the Microsoft Learn directory, skipping the "All ... services" cards.

        Args:
            response (Response): The Microsoft Learn directory.

        Yields:
            Iterator[CloudProduct]: Each valid product card, with the category of its section, if any.
        """
        cards = response.css('div[data-bi-name="product-card"]')
        self.logger.debug("%d documentation cards in %s.", len(cards), response.url)
        for card in cards:
            title = card.css("a.card-title").first
            description = card.css(".card-content-description").first
            if title is None or description is None:
                continue
            name = self._clean_text(title.get_all_text(separator=" ", strip=True))
            if name.casefold().startswith(AzureLearnLabel.ALL_PREFIX):
                self.logger.debug("Skipping the documentation card %r, not a product.", name)
                continue
            url = urljoin(response.url, title.attrib.get(HtmlAttribute.HREF, ""))
            text = description.get_all_text(separator=" ", strip=True)
            if product := self._build_product(name, text, url, categories=[self._learn_category(card)]):
                yield product

    def _learn_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the Microsoft Learn directory.

        Args:
            response (Response): The Microsoft Learn directory.

        Yields:
            Iterator[CloudProduct]: Each valid product, with the categories of all its cards.
        """
        yield from self._merge_categories(self._learn_cards(response))

    def _measure_unit(self, measure: str) -> Tuple[PriceUnit, Decimal]:
        """Normalize an Azure unit of measure.

        Args:
            measure (str): The unit of measure, e.g. `1 Hour`, `10K`, `1 GB/Month`.

        Returns:
            Tuple[PriceUnit, Decimal]: The normalized unit and the normalized units in one: its number (`10K` is
                10,000) times the suffix's factor (a day is 24 hours), other when the suffix is unknown.
        """
        match = self.MEASURE.match(measure.strip())
        if match is None:
            self.logger.debug("The Azure unit of measure %r is unreadable: kept as other.", measure)
            return PriceUnit.OTHER, Decimal(1)
        count = Decimal(match["count"]) * self.MULTIPLIERS.get(match["multiplier"] or "", Decimal(1))
        try:
            unit, factor = self.MEASURE_UNITS[AzureUnitSuffix(match["suffix"].strip())]
        except ValueError:
            self.logger.debug("The Azure unit of measure %r has no known unit: kept as other.", measure)
            return PriceUnit.OTHER, count
        if unit is PriceUnit.REQUEST and count == 1:
            return PriceUnit.UNIT, Decimal(1)
        return unit, count * factor

    def _meter_prices(self, item: Dict[str, JsonValue], source: str) -> Iterator[ServicePrice]:
        """Read the prices of a meter of the Retail Prices API.

        Args:
            item (Dict[str, JsonValue]): The meter price.
            source (str): The filtered listing it was read from (the source of its prices).

        Yields:
            ServicePrice: Its price (pay as you go, or a reservation for its whole term, per year), then its
                savings plan prices.
        """
        kind = str(item.get(AzurePriceField.TYPE) or "")
        term = item.get(AzurePriceField.RESERVATION_TERM)
        measure = str(item.get(AzurePriceField.UNIT_OF_MEASURE) or "")
        unit, factor = self._measure_unit(measure)
        model = PriceModel.ON_DEMAND
        price_term = PriceTerm.NONE
        if kind == AzurePriceType.RESERVATION and isinstance(term, str):
            years = self.TERM_YEARS.get(term)
            unit, factor, model = PriceUnit.YEAR, Decimal(years or 1), PriceModel.RESERVED
            price_term = self.TERMS.get(term, PriceTerm.NONE)
        retail = item.get(AzurePriceField.RETAIL_PRICE)
        if not isinstance(retail, (int, float)):
            self.logger.debug("The Azure meter %s has no price: skipped.", item.get(AzurePriceField.METER_ID))
            return
        price = Decimal(str(retail))
        service = item.get(AzurePriceField.SERVICE_NAME)
        product = str(item.get(AzurePriceField.PRODUCT_NAME) or "")
        region = item.get(AzurePriceField.ARM_REGION_NAME)
        start = item.get(AzurePriceField.EFFECTIVE_START_DATE)
        tier = item.get(AzurePriceField.TIER_MINIMUM_UNITS)
        key = "/".join(
            str(part)
            for part in (
                item.get(AzurePriceField.SKU_ID),
                item.get(AzurePriceField.METER_ID),
                kind,
                term or "",
                tier if isinstance(tier, (int, float)) else 0,
            )
        )
        fields: Dict[str, RawValue] = {
            "sku_key": key,
            "service": service,
            "family": item.get(AzurePriceField.SERVICE_FAMILY),
            "region": region if isinstance(region, str) and region else self.GLOBAL_REGION,
            "attributes": {
                field.value: item.get(field)
                for field in (
                    AzurePriceField.PRODUCT_NAME,
                    AzurePriceField.SKU_NAME,
                    AzurePriceField.METER_NAME,
                    AzurePriceField.LOCATION,
                    AzurePriceField.TYPE,
                    AzurePriceField.IS_PRIMARY_METER_REGION,
                )
                if item.get(field) not in (None, "")
            },
            "unit": unit,
            "unit_raw": measure if kind != AzurePriceType.RESERVATION else str(term),
            "unit_factor": factor,
            "price": price,
            "currency": item.get(AzurePriceField.CURRENCY_CODE),
            "model": PriceModel.FREE if price == 0 else model,
            "term": price_term,
            "tier_start": Decimal(str(tier)) if isinstance(tier, (int, float)) else Decimal(0),
            "effective_from": start[:10] if isinstance(start, str) and len(start) >= 10 else None,
            "source_url": source,
            "source_kind": PriceSourceKind.API,
        }
        if item.get(AzurePriceField.SERVICE_FAMILY) == self.COMPUTE_FAMILY:
            fields["instance_type"] = item.get(AzurePriceField.ARM_SKU_NAME) or None
        if service == self.VM_SERVICE:
            fields["os"] = self.WINDOWS if self.WINDOWS_PRODUCT.search(product) else self.LINUX
        fact = self._price_fact(fields)
        if fact is not None:
            yield fact
        plans = item.get(AzurePriceField.SAVINGS_PLAN)
        for plan in plans if isinstance(plans, list) else []:
            plan_price = plan.get(AzurePriceField.RETAIL_PRICE) if isinstance(plan, dict) else None
            plan_term = plan.get(AzurePriceField.TERM) if isinstance(plan, dict) else None
            if not isinstance(plan_price, (int, float)) or not isinstance(plan_term, str):
                continue
            saving = self._price_fact(
                {
                    **fields,
                    "sku_key": f"{key}/savings-plan/{plan_term}",
                    "price": Decimal(str(plan_price)),
                    "model": PriceModel.SAVINGS_PLAN,
                    "term": self.TERMS.get(plan_term, PriceTerm.NONE),
                }
            )
            if saving is not None:
                yield saving

    def _source_url(self, query: str) -> str:
        """Build the URL of a filtered listing of the Retail Prices API.

        Args:
            query (str): The OData filter.

        Returns:
            str: The URL of its first page (the source of its prices).
        """
        return f"{self.PRICES_URL}&{urlencode({self.FILTER_PARAMETER: query})}"

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the first page of each filtered listing of the Retail Prices API.

        Yields:
            Request: The request of the first page of each listing.
        """
        self.price_rows = {}
        for query in self.PRICE_FILTERS:
            source = self._source_url(query)
            self.price_rows[source] = 0
            self.logger.info("Reading the Azure prices of the listing %s.", query)
            yield self._price_request(source, {self.PRICE_SOURCE: source})

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read a page of a filtered listing: the next page first, then its prices.

        Args:
            response (Response): The page.

        Yields:
            PriceFact: The request of the next page, then the prices of the page.

        Raises:
            CatalogueFormatError: If the page lists no prices.
        """
        data = self._json_body(response)
        items = data.get(AzurePriceField.ITEMS) if isinstance(data, dict) else None
        if not isinstance(data, dict) or not isinstance(items, list):
            self.logger.error("The Azure prices page %s lists no prices.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the prices page lists no prices")
        source = str(response.meta.get(self.PRICE_SOURCE) or self.PRICES_URL)
        following = data.get(AzurePriceField.NEXT_PAGE_LINK)
        if isinstance(following, str) and following:
            yield self._price_request(following, {self.PRICE_SOURCE: source})
        found = 0
        for item in items:
            for fact in self._meter_prices(item, source) if isinstance(item, dict) else iter(()):
                found += 1
                yield fact
        self.price_rows[source] = self.price_rows.get(source, 0) + found
        if not (isinstance(following, str) and following):
            self._record_price_source(source, self.price_rows[source])
            self.logger.info("The Azure listing %s is read whole: %d prices.", source, self.price_rows[source])

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products page or of the Microsoft Learn directory.

        Args:
            response (Response): The catalogue page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.
        """
        if urlparse(response.url).netloc == urlparse(self.LEARN_URL).netloc:
            self.logger.debug(
                "Extracting the %s products of the Microsoft Learn directory %s.", self.name, response.url
            )
            return self._learn_products(response)
        self.logger.debug("Extracting the %s products of the products page %s.", self.name, response.url)
        return self._products_page_products(response)
