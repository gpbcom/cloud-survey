from __future__ import annotations

# Standard Library Imports.
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.stackit.enums import (
    StackitLaunchKeyword,
    StackitNotLaunchMarker,
    StackitReleaseNoteAttribute,
    StackitSkuAttribute,
    StackitSkuField,
    StackitUnitBilling,
)
from crawler.exception import CatalogueFormatError
from models.cloud.enums import DateCaveat, PriceModel, PriceSourceKind, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class STACKITCrawler(BaseCloudCrawler):
    """STACKIT catalogue crawler.

    Attributes:
        SITEMAP_URL (ClassVar[str]): The sitemap of the English website, listing the product pages.
        SITEMAP_PRODUCT_PAGE (ClassVar[re.Pattern[str]]): The sitemap product pages, e.g.
            `/en/products/<category>/stackit-<slug>`, not the category pages nor their sub-pages.
        TITLE_TAGLINE (ClassVar[re.Pattern[str]]): The tagline following the product name in the page titles.
        RELEASE_NOTES_URL (ClassVar[str]): The release notes page, all the products' notes on one page.
        RELEASE_NOTES (ClassVar[str]): The CSS selector of the release notes (`article.release-note`).
        RELEASE_NOTE_TITLE (ClassVar[str]): The CSS selector of the title of a release note.
        RELEASE_NOTE_DATE (ClassVar[str]): The CSS selector of the `time` element dating a release note.
        RELEASE_NOTE_DATETIME (ClassVar[StackitReleaseNoteAttribute]): The attribute of that element holding the
            ISO date.
        LAUNCH_TITLE (ClassVar[re.Pattern[str]]): The words of a release note title announcing a launch
            (`StackitLaunchKeyword`), e.g. `beta`, `now available`, `general availability`.
        NOT_LAUNCH_TITLE (ClassVar[re.Pattern[str]]): The patterns of a release note title which is not a launch
            (`StackitNotLaunchMarker`), e.g. a deprecation or a product made available in a new region.
        PRODUCT_MENTION (ClassVar[str]): The pattern of a product name in a release note title, `{name}` being the
            name pattern: a whole name, not followed by a version number.
        PRICES_URL (ClassVar[str]): The public price list API (PIM SKUs), every SKU with its price.
        PRICE_CURRENCY (ClassVar[str]): The currency of the price list (`€`).
        PRICE_UNITS (ClassVar[Dict[StackitUnitBilling, Tuple[PriceUnit, Decimal]]]): The normalized unit of what a
            price is per, and the normalized units in one.
        SKU_FIELD_ATTRIBUTES (ClassVar[FrozenSet[str]]): The SKU attributes read as price fields (not kept as
            attributes).
        release_notes (Optional[List[Tuple[datetime, str]]]): The date and title of each release note, the earliest
            first, read once per crawl, `None` until read.

    Notes:
        The main source is the https://stackit.com/en/products page: a grid of product tiles
        (`article.digits-base-tile`), each with a name, a short description and a product page link, shown in
        category tabs (e.g. `Compute Engine`, `Data & AI`) which file the products. The English
        sitemap completes it: its product pages missing from the grid (e.g. the products without category) are
        requested and read from their title and meta description, dated by their sitemap last modification
        (`lastmod`). The `www.` host redirects to `stackit.com`.
        The products are dated by their launch note in the release notes (`dates_launches`), one page
        (`https://docs.stackit.cloud/release-notes/`) of all the products' notes since September 2021, read once per
        crawl. Its tags are categories, not products: a note names its product in its title, matched on the product
        name without its `STACKIT` brand (or on its alias). The launch is the earliest note naming the product whose
        title announces a launch (`beta`, `public preview`, `now available`, `GA` ...), the version releases (e.g.
        `STACKIT RabbitMQ 3.10 is now available`), deprecations, documentation releases and extensions (a feature,
        a region, a machine type) excepted. A product without such a note is left undated, as are all the products
        when the page holds no dated note (a soft 404). The notes before December 2021 may postdate the launch
        (`FEED_START`).
        In price mode it reads the public price list API (`PRICES_URL`): one price per SKU and region, in euros,
        its unit normalized from what it is per (`unitBilling`, e.g. `per vCPU/hour`, `mio input token`). The list
        states its version (`lastUpdatedAt`): an unchanged list is not read again. A band price (a license for 1
        to 8 vCPUs) has its band as tier.
    """

    SITEMAP_URL: ClassVar[str] = "https://stackit.com/en/sitemap/default.xml"
    SITEMAP_PRODUCT_PAGE: ClassVar[re.Pattern[str]] = re.compile(
        r"^https://(?:www\.)?stackit\.com/en/products/(?:[\w-]+/)?stackit-[\w-]+/?$", re.IGNORECASE
    )
    TITLE_TAGLINE: ClassVar[re.Pattern[str]] = re.compile(r"\s*(?:\||:\s|\s[-\u2013]\s).*$")
    RELEASE_NOTES_URL: ClassVar[str] = "https://docs.stackit.cloud/release-notes/"
    RELEASE_NOTES: ClassVar[str] = "article.release-note"
    RELEASE_NOTE_TITLE: ClassVar[str] = "h2.release-note__title"
    RELEASE_NOTE_DATE: ClassVar[str] = "time.release-note__date"
    RELEASE_NOTE_DATETIME: ClassVar[StackitReleaseNoteAttribute] = StackitReleaseNoteAttribute.DATETIME
    LAUNCH_TITLE: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(?:" + "|".join(map(re.escape, StackitLaunchKeyword)) + r")\b", re.IGNORECASE
    )
    NOT_LAUNCH_TITLE: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(?:" + "|".join(StackitNotLaunchMarker) + ")", re.IGNORECASE
    )
    PRODUCT_MENTION: ClassVar[str] = r"(?<![\w-]){name}(?![\w-])(?!\s*[-\u2013:]?\s*(?:version\s+)?v?\d)"

    name = "stackit"
    catalogue_url: ClassVar[str] = "https://stackit.com/en/products"
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    dates_sitemaps: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("STACKIT ",)
    dates_launches: ClassVar[bool] = True
    launch_feed_start: ClassVar[Optional[datetime]] = datetime(2021, 12, 1, tzinfo=UTC)
    PRICES_URL: ClassVar[str] = "https://pim.api.stackit.cloud/v1/skus"
    PRICE_CURRENCY: ClassVar[str] = "EUR"
    PRICE_UNITS: ClassVar[Dict[StackitUnitBilling, Tuple[PriceUnit, Decimal]]] = {
        StackitUnitBilling.HOUR: (PriceUnit.HOUR, Decimal(1)),
        StackitUnitBilling.DISK_HOUR: (PriceUnit.UNIT_HOUR, Decimal(1)),
        StackitUnitBilling.GB_HOUR: (PriceUnit.GIB_HOUR, Decimal(1)),
        StackitUnitBilling.MONTH: (PriceUnit.MONTH, Decimal(1)),
        StackitUnitBilling.VCPU_HOUR: (PriceUnit.VCPU_HOUR, Decimal(1)),
        StackitUnitBilling.MB: (PriceUnit.GIB, Decimal(1) / Decimal(1024)),
        StackitUnitBilling.VERSION_HOUR: (PriceUnit.UNIT_HOUR, Decimal(1)),
        StackitUnitBilling.AMOUNT: (PriceUnit.UNIT, Decimal(1)),
        StackitUnitBilling.INPUT_TOKENS: (PriceUnit.TOKEN, Decimal(1_000_000)),
        StackitUnitBilling.OUTPUT_TOKENS: (PriceUnit.TOKEN, Decimal(1_000_000)),
        StackitUnitBilling.SERVER_HOUR: (PriceUnit.HOUR, Decimal(1)),
        StackitUnitBilling.CLUSTER_HOUR: (PriceUnit.HOUR, Decimal(1)),
        StackitUnitBilling.GB_INGEST: (PriceUnit.GIB, Decimal(1)),
        StackitUnitBilling.GB_RETENTION_DAY: (PriceUnit.GIB_HOUR, Decimal(24)),
        StackitUnitBilling.THOUSAND_REQUESTS: (PriceUnit.REQUEST, Decimal(1000)),
        StackitUnitBilling.MB_RAM_HOUR: (PriceUnit.GIB_HOUR, Decimal(1) / Decimal(1024)),
        StackitUnitBilling.GB: (PriceUnit.GIB, Decimal(1)),
        StackitUnitBilling.NODE_HOUR: (PriceUnit.HOUR, Decimal(1)),
        StackitUnitBilling.KB: (PriceUnit.GIB, Decimal(1) / Decimal(1024 * 1024)),
        StackitUnitBilling.SECRET_HOUR: (PriceUnit.UNIT_HOUR, Decimal(1)),
        StackitUnitBilling.RUNTIME_MINUTE: (PriceUnit.MINUTE, Decimal(1)),
        StackitUnitBilling.USER_MONTH: (PriceUnit.UNIT_MONTH, Decimal(1)),
    }
    SKU_FIELD_ATTRIBUTES: ClassVar[FrozenSet[str]] = frozenset(
        {
            StackitSkuAttribute.VCPU,
            StackitSkuAttribute.RAM,
            StackitSkuAttribute.FLAVOR,
            StackitSkuAttribute.OS,
            StackitSkuAttribute.TIER_MIN_VALUE,
            StackitSkuAttribute.TIER_MAX_VALUE,
            StackitSkuAttribute.CF_UNIQUE_IDS,
        }
    )

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.release_notes: Optional[List[Tuple[datetime, str]]] = None

    ############################
    # Internal Helpers Methods #
    ############################

    def _note_date(self, text: str) -> Optional[datetime]:
        """Parse the date of a release note.

        Args:
            text (str): The ISO date, e.g. `2026-01-14T00:00:00.000Z`.

        Returns:
            Optional[datetime]: The date in UTC, `None` when unreadable or implausible.
        """
        try:
            parsed = datetime.fromisoformat(text.strip())
        except ValueError:
            self.logger.debug("Unreadable release note date %r.", text)
            return None
        parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        return parsed if self.EARLIEST_DATE <= parsed <= datetime.now(UTC) else None

    def _release_note_entries(self, response: Response) -> List[Tuple[datetime, str]]:
        """Read the dated release notes of the release notes page.

        Args:
            response (Response): The release notes page.

        Returns:
            List[Tuple[datetime, str]]: The date and title of each dated note, the earliest first, none when the
                page holds no dated note.
        """
        notes: List[Tuple[datetime, str]] = []
        for note in response.css(self.RELEASE_NOTES):
            title = note.css(self.RELEASE_NOTE_TITLE).first
            text = note.css(self.RELEASE_NOTE_DATE).first
            date = self._note_date(text.attrib.get(self.RELEASE_NOTE_DATETIME, "")) if text is not None else None
            if title is None or date is None:
                self.logger.debug("Skipping a release note without title or date in %s.", response.url)
                continue
            notes.append((date, self._clean_text(title.get_all_text(separator=" ", strip=True))))
        if not notes:
            self.logger.warning("The %s release notes page %s holds no dated note.", self.name, response.url)
        return sorted(notes)

    async def _release_notes(self) -> List[Tuple[datetime, str]]:
        """Get the release notes, fetched once per crawl.

        Returns:
            List[Tuple[datetime, str]]: The date and title of each dated note, the earliest first, none when the page
                cannot be read.
        """
        if self.release_notes is None:
            response = await self._fetch_launch_page(self.RELEASE_NOTES_URL)
            self.release_notes = self._release_note_entries(response) if response is not None else []
            self.logger.info("%d %s release notes read.", len(self.release_notes), self.name)
        return self.release_notes

    def _note_names(self, product: CloudProduct) -> List[str]:
        """Get the names a release note title gives a product: its name and its alias, without the brand.

        Args:
            product (CloudProduct): The product.

        Returns:
            List[str]: The names, e.g. `File Storage` for `STACKIT File Storage`.
        """
        alias = self.launch_aliases.get(self._name_key(product.name))
        names: List[str] = []
        for name in [product.name] + ([alias] if alias else []):
            text = self._clean_text(name)
            for prefix in self.name_prefixes:
                if text.casefold().startswith(prefix.casefold()):
                    text = text[len(prefix) :].strip()
            if text and text not in names:
                names.append(text)
        return names

    def _mentions(self, names: List[str]) -> List[re.Pattern[str]]:
        """Build the patterns of the product names in a release note title.

        Args:
            names (List[str]): The product names, without the brand.

        Returns:
            List[re.Pattern[str]]: One pattern per name, its words separated by any spaces, a version number
                following it excluded.
        """
        return [
            re.compile(self.PRODUCT_MENTION.format(name=r"\s+".join(map(re.escape, name.split()))), re.IGNORECASE)
            for name in names
        ]

    def _is_launch(self, title: str, mentions: List[re.Pattern[str]]) -> bool:
        """Tell whether a release note title announces the launch of a product.

        Args:
            title (str): The note title.
            mentions (List[re.Pattern[str]]): The patterns of the product names.

        Returns:
            bool: Whether the title names the product and announces a launch, not a version, a deprecation or an
                extension.
        """
        named = any(mention.search(title) for mention in mentions)
        return named and bool(self.LAUNCH_TITLE.search(title)) and not self.NOT_LAUNCH_TITLE.search(title)

    def _first_launch(self, notes: List[Tuple[datetime, str]], product: CloudProduct) -> Optional[datetime]:
        """Find the date of the earliest release note announcing the launch of a product.

        Args:
            notes (List[Tuple[datetime, str]]): The date and title of each release note, the earliest first.
            product (CloudProduct): The product.

        Returns:
            Optional[datetime]: The date of the launch note, `None` when no note announces the product launch.
        """
        mentions = self._mentions(self._note_names(product))
        for date, title in notes:
            if self._is_launch(title, mentions):
                self.logger.debug("%s launch note: %r (%s).", product.name, title, date.date().isoformat())
                return date
        self.logger.debug("No %s release note announces the launch of %r.", self.name, product.name)
        return None

    async def _launch_source(self, product: CloudProduct) -> Optional[Tuple[datetime, DateCaveat]]:
        """Read the launch of a product from the earliest release note announcing it.

        Args:
            product (CloudProduct): The product, undated.

        Returns:
            Optional[Tuple[datetime, DateCaveat]]: The launch and its caveat, `None` when no release note announces
                the product launch.
        """
        self.logger.debug("Looking for the %s release note announcing %r.", self.name, product.name)
        launched = self._first_launch(await self._release_notes(), product)
        if launched is None:
            self.logger.debug("No %s release note announces %r.", self.name, product.name)
            return None
        return self._announced(launched)

    def _page_title(self, title: str) -> str:
        """Clean the product name read from a product page title: the tagline is removed.

        Args:
            title (str): The page title, e.g. `STACKIT DNS: Highly available and fast domain resolution`.

        Returns:
            str: The product name, e.g. `STACKIT DNS`.
        """
        return self._clean_text(self.TITLE_TAGLINE.sub("", self._clean_text(title)))

    def _tile_fields(self, tile: Selector, page_url: str) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
        """Read the product of a product tile.

        Args:
            tile (Selector): The product tile (`article.digits-base-tile`).
            page_url (str): The catalogue page URL, the tile links being relative to it.

        Returns:
            Optional[Tuple[str, Optional[str], Optional[str]]]: The name, description and URL of the product, `None`
                when the tile has no name.
        """
        name = " ".join(line.get_all_text(separator=" ", strip=True) for line in tile.css(".digits-tile__title-line"))
        if not self._clean_text(name):
            self.logger.debug("Skipping a product tile without name.")
            return None
        details = tile.css("p.digits-tile__details").first
        description = details.get_all_text(separator=" ", strip=True) if details is not None else None
        link = tile.css("a.digits-base-tile__link::attr(href)").get()
        return name, description, urljoin(page_url, link) if link else None

    def _tabbed_tiles(self, response: Response) -> List[Tuple[Selector, Optional[str]]]:
        """List the product tiles with the label of the tab showing them.

        Args:
            response (Response): The products page.

        Returns:
            List[Tuple[Selector, Optional[str]]]: Each product tile and its tab, `None` when the page has no tabs.

        Notes:
            Each tabs container (`.digits-tile-tabs__container`) lists its tab labels (`.digits-tabs__pill`) and, in
            the same order, one panel of tiles per tab (`.digits-tabs__content`).
        """
        tiles: List[Tuple[Selector, Optional[str]]] = []
        for container in response.css(".digits-tile-tabs__container"):
            tabs = [
                self._clean_text(pill.get_all_text(separator=" ", strip=True))
                for pill in container.css(".digits-tabs__pill")
            ]
            for index, panel in enumerate(container.css(".digits-tabs__content")):
                tab = tabs[index] if index < len(tabs) else None
                tiles.extend((tile, tab) for tile in panel.css("article.digits-base-tile"))
        if not tiles:
            self.logger.debug("No product tabs on %s, its tiles are not categorized.", response.url)
            tiles = [(tile, None) for tile in response.css("article.digits-base-tile")]
        return tiles

    def _tile_entries(self, response: Response) -> List[Tuple[str, Optional[str], Optional[str], List[str]]]:
        """Gather the products of the tiles with all their tabs, a product being shown in several tabs.

        Args:
            response (Response): The products page.

        Returns:
            List[Tuple[str, Optional[str], Optional[str], List[str]]]: The name, description and URL of the first
                tile of each product, by order of appearance, and the tabs of all its tiles.

        Notes:
            The tiles of a product are matched by name or by URL, as the streamed products are.
        """
        tiles = self._tabbed_tiles(response)
        self.logger.debug("%d product tiles found on %s.", len(tiles), response.url)
        entries: List[Tuple[str, Optional[str], Optional[str], List[str]]] = []
        positions: Dict[str, int] = {}
        for tile, tab in tiles:
            if (fields := self._tile_fields(tile, response.url)) is None:
                continue
            name, description, url = fields
            keys = [f"name:{self._name_key(name)}"] + ([f"url:{self._url_key(url)}"] if url else [])
            position = next((positions[key] for key in keys if key in positions), None)
            if position is None:
                position = len(entries)
                entries.append((name, description, url, []))
            else:
                self.logger.debug("Product tile %r shown again, in the tab %r.", name, tab)
            if tab:
                entries[position][3].append(tab)
            positions.update(dict.fromkeys(keys, position))
        return entries

    def _tiles_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the product tiles grid, filed under their tabs.

        Args:
            response (Response): The products page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the grid, once.
        """
        count = 0
        for name, description, url, tabs in self._tile_entries(response):
            if product := self._build_product(name, description, url, categories=tabs):
                count += 1
                yield product
        if count:
            self.logger.info("%d %s products read from the tiles of %s.", count, self.name, response.url)
        else:
            self.logger.warning("No %s product in the tiles of %s.", self.name, response.url)

    def _sitemap_requests(self, response: Response) -> List[Request]:
        """Request the product pages of the sitemap missing from the product tiles, with their last modification.

        Args:
            response (Response): The sitemap.

        Returns:
            List[Request]: The product page requests.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        entries = self._sitemap_entries(response)
        pages = [url for url in entries if self.SITEMAP_PRODUCT_PAGE.match(url)]
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

    def _sku_unit(self, billing: JsonValue) -> Tuple[PriceUnit, Decimal]:
        """Normalize what a price of the price list is per.

        Args:
            billing (JsonValue): Its `unitBilling`, e.g. `per vCPU/hour`.

        Returns:
            Tuple[PriceUnit, Decimal]: The normalized unit and the normalized units in one (a million tokens, a
                MB in GiB), other for an unknown one.
        """
        try:
            unit, factor = self.PRICE_UNITS[StackitUnitBilling(str(billing))]
        except ValueError:
            self.logger.warning("Unknown STACKIT price unit %r: kept as other.", billing)
            return PriceUnit.OTHER, Decimal(1)
        return unit, factor

    def _sku_price(self, item: Dict[str, JsonValue]) -> Optional[ServicePrice]:
        """Read the price of a SKU of the price list.

        Args:
            item (Dict[str, JsonValue]): The SKU.

        Returns:
            Optional[ServicePrice]: Its price (a price of 0 as free), `None` when it is malformed.
        """
        attributes = item.get(StackitSkuField.ATTRIBUTES)
        attributes = attributes if isinstance(attributes, dict) else {}
        unit, factor = self._sku_unit(item.get(StackitSkuField.UNIT_BILLING))
        raw_price = item.get(StackitSkuField.PRICE)
        try:
            price = Decimal(str(raw_price))
        except ArithmeticError:
            self.logger.warning(
                "The STACKIT SKU %s has no readable price %r.", item.get(StackitSkuField.SKU), raw_price
            )
            return None
        kept: Dict[str, JsonValue] = {
            key: value
            for key, value in attributes.items()
            if value is not None and key not in self.SKU_FIELD_ATTRIBUTES
        }
        for field in (
            StackitSkuField.NAME,
            StackitSkuField.MATURITY,
            StackitSkuField.DEPRECATED,
            StackitSkuField.PRICE_LIST_VISIBILITY,
        ):
            if isinstance(item.get(field), str):
                kept[field] = item[field]
        vcpu, ram = attributes.get(StackitSkuAttribute.VCPU), attributes.get(StackitSkuAttribute.RAM)
        tier_min = attributes.get(StackitSkuAttribute.TIER_MIN_VALUE)
        tier_max = attributes.get(StackitSkuAttribute.TIER_MAX_VALUE)
        fields: Dict[str, RawValue] = {
            "sku_key": item.get(StackitSkuField.SKU),
            "service": item.get(StackitSkuField.PRODUCT),
            "family": item.get(StackitSkuField.CATEGORY),
            "region": item.get(StackitSkuField.REGION),
            "instance_type": attributes.get(StackitSkuAttribute.FLAVOR),
            "vcpu": vcpu if isinstance(vcpu, int) and vcpu > 0 else None,
            "memory_gib": ram if isinstance(ram, (int, float)) and ram > 0 else None,
            "os": attributes.get(StackitSkuAttribute.OS),
            "attributes": kept,
            "unit": unit,
            "unit_raw": item.get(StackitSkuField.UNIT_BILLING),
            "unit_factor": factor,
            "price": price,
            "currency": self.PRICE_CURRENCY,
            "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
            "tier_start": tier_min if isinstance(tier_min, int) else 0,
            "tier_end": tier_max if isinstance(tier_max, int) else None,
            "source_url": self.PRICES_URL,
            "source_kind": PriceSourceKind.API,
        }
        return self._price_fact(fields)

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the price list.

        Yields:
            Request: The request of the price list.
        """
        self.logger.info("Reading the STACKIT prices from %s.", self.PRICES_URL)
        yield self._price_request(self.PRICES_URL)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the prices of the price list, unless it is unchanged since its last read.

        Args:
            response (Response): The price list.

        Yields:
            PriceFact: The price of each SKU.

        Raises:
            CatalogueFormatError: If the price list lists no SKUs.
        """
        data = self._json_body(response)
        items = data.get(StackitSkuField.SERVICES) if isinstance(data, dict) else None
        if not isinstance(data, dict) or not isinstance(items, list):
            self.logger.error("The STACKIT price list %s lists no SKUs.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the price list lists no SKUs")
        version = data.get(StackitSkuField.LAST_UPDATED_AT)
        version = version if isinstance(version, str) else None
        if self._price_unchanged(self.PRICES_URL, version=version):
            return
        found = 0
        for item in items:
            fact = self._sku_price(item) if isinstance(item, dict) else None
            if fact is not None:
                found += 1
                yield fact
        self._record_price_source(self.PRICES_URL, found, version=version)
        self.logger.info("The STACKIT price list (%s) is read: %d prices of %d SKUs.", version, found, len(items))

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the product tiles grid.

        Args:
            response (Response): The products page.

        Returns:
            Iterator[CloudProduct]: The valid products of the grid.
        """
        self.logger.debug("Reading the %s product tiles of %s.", self.name, response.url)
        return self._tiles_products(response)

    async def on_start(self, resuming: bool = False) -> None:
        """Forget the release notes of a previous crawl, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if not resuming:
            self.release_notes = None
            self.logger.debug("The %s release notes will be read again.", self.name)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the grid products, request the sitemap product pages, or stream a sitemap product page.

        Args:
            response (Response): The products page, the sitemap or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, or the product page requests.

        Raises:
            EmptyCatalogueError: If the products page holds no valid product.
            CatalogueFormatError: If the sitemap lists no page.
        """
        if response.url == self.SITEMAP_URL and self.PAGE_DATES not in response.meta:
            self.logger.debug("Reading the %s sitemap %s.", self.name, response.url)
            for request in self._sitemap_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
