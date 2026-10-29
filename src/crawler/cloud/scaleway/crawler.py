from __future__ import annotations

# Standard Library Imports.
import re
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import (
    AsyncGenerator,
    ClassVar,
    Dict,
    FrozenSet,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.scaleway.enums import (
    ScalewayBlockField,
    ScalewayCatalogField,
    ScalewayChangelogTag,
    ScalewayCmsComponent,
    ScalewayEntryField,
    ScalewayHardwareField,
    ScalewayLinkField,
    ScalewayLocality,
    ScalewayMenuGroup,
    ScalewayNextDataField,
    ScalewayPageField,
    ScalewayPriceUnit,
    ScalewayStatus,
)
from crawler.exception import CatalogueFormatError
from models.cloud.enums import DateCaveat, FreeTierKind, PriceModel, PriceSourceKind, PriceUnit
from models.cloud.prices.facts.free_tier import FreeTier
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class ScalewayCrawler(BaseCloudCrawler):
    """Scaleway catalogue crawler.

    Attributes:
        PRODUCTS_BLOCK (ClassVar[ScalewayCmsComponent]): The page block type listing the products of a category.
        SITE_URL (ClassVar[str]): The website root, the menu links being relative to it.
        MENU_GROUPS (ClassVar[FrozenSet[ScalewayMenuGroup]]): The header menu groups listing products.
        NOT_PRODUCT (ClassVar[re.Pattern[str]]): The header menu entries which are not products.
        DATE_CAVEATS (ClassVar[Tuple[DateCaveat, DateCaveat]]): The caveats of the added and updated dates.
        CHANGELOG_URL (ClassVar[str]): The changelog RSS feed dating the products.
        TITLE_SEPARATOR (ClassVar[str]): The separator of the product label and the change in a changelog title.
        CDATA (ClassVar[re.Pattern[str]]): A text wrapped in a CDATA section, as the feed titles are.
        WORD_SEPARATOR (ClassVar[re.Pattern[str]]): The separators of the words of a name or a label.
        IGNORED_WORDS (ClassVar[FrozenSet[str]]): The words ignored to match a product and a changelog label (the
            brands, the conjunctions).
        PLURAL_MIN_LENGTH (ClassVar[int]): The length above which a word ending with `s` is read as a plural.
        PRICES_URL (ClassVar[str]): The public product catalog API, with the prices of every SKU.
        PRICES_PAGE_SIZE (ClassVar[int]): The products asked per page of the catalog (its maximum).
        PRICE_PAGE (ClassVar[str]): The request meta holding the page of the catalog.
        PRICE_UNITS (ClassVar[Dict[ScalewayPriceUnit, Tuple[PriceUnit, int]]]): The normalized unit of each catalog
            unit, and the normalized units in one (24 hours in a day).
        TRANSFER_SKU (ClassVar[re.Pattern[str]]): The SKUs whose gigabyte is transferred or ingested, not stored.
        FEE_SKU (ClassVar[re.Pattern[str]]): The SKUs of a one-time fee (the setup of a server).
        MINUTE_SKU (ClassVar[re.Pattern[str]]): The SKUs priced per minute whatever their unit says.
        WITHDRAWN (ClassVar[FrozenSet[str]]): The statuses of a product no longer sold (its prices are closed).
        FREE_TIER (ClassVar[re.Pattern[str]]): The name of a free offer.
        NO_UNIT (ClassVar[str]): The unit written for a product without price.
        NO_PRICE_REASON (ClassVar[str]): Why a product without price has none.
        NANOS (ClassVar[Decimal]): The billionths in a unit of the currency.
        BYTES_PER_GIB (ClassVar[Decimal]): The bytes in a gibibyte.
        GIB_PRECISION (ClassVar[Decimal]): The precision of a memory or a storage, in GiB.
        changelog (Optional[Dict[str, datetime]]): The earliest changelog entry of each product label, read once per
            crawl, `None` until read.
        price_pages (Set[int]): The pages of the catalog not read yet, in price mode.
        price_rows (int): The prices read from the catalog, in price mode.

    Notes:
        It reads the Next.js data of the https://www.scaleway.com/en/all-products/ page, as the class names of the
        rendered page are generated: the product columns of the page first, then the products of the header menu
        missing from them (same page, no extra request). A product is dated by its website page record: its creation
        (`link.page.createdAt`, often the date of the CMS migration rather than of the launch) and its last update
        (`link.page.updatedAt`), both with a caveat. A link to a URL without website page (`page: null`) gives no
        date. A product of the columns is filed under the column title (e.g. `Containers`), a product of the menu
        under its groups (e.g. `AI` then `Clusters`).
        The website record date is replaced by the launch read from the changelog RSS feed (`dates_launches`) when
        the feed names the product: the earliest entry (`pubDate`) of the product label heading its titles (e.g.
        `Secret-manager | ...`). The feed is read once per crawl. A product matches a label whose words are a run
        of the words of its name or of its page slug (e.g. `Redistm` for `managed-database-for-redistm`), or whose
        letters are those of its name (`Webhosting` for `Web Hosting`), plurals, brands (`Scaleway`, `Apache`) and
        conjunctions ignored. The longest matching label wins, so several products share a label date (all the
        `... Instances` share the `Instances` one, the GPU ones the `Gpu-instances` one). A renamed product is looked
        up under its alias first. The feed starts in January 2022: an earlier launch is dated `FEED_START`. Without
        a matching label the record date is kept.
        In price mode it reads the public product catalog API (`PRICES_URL`, 1,000 SKUs a page): one price per SKU
        and zone, region or datacenter, as `units + nanos / 10⁹` of the currency per `size` units. The catalog bills
        storage by the gigabyte-hour (the `gigabyte` of a volume, a bucket, a snapshot) but transfers by the
        gigabyte (`TRANSFER_SKU`). A withdrawn product is skipped, so its stored prices are closed. A product
        without price is stored as not public, except the free offers. The catalog is one source: it is recorded
        as read whole only once all its pages are read.
    """

    PRODUCTS_BLOCK: ClassVar[ScalewayCmsComponent] = ScalewayCmsComponent.GENERIC_COLUMNS
    DATE_CAVEATS: ClassVar[Tuple[DateCaveat, DateCaveat]] = (DateCaveat.WEBSITE_RECORD, DateCaveat.PAGE_MODIFIED)
    SITE_URL: ClassVar[str] = "https://www.scaleway.com/en/"
    MENU_GROUPS: ClassVar[FrozenSet[ScalewayMenuGroup]] = frozenset(
        {ScalewayMenuGroup.AI, ScalewayMenuGroup.CLOUD, ScalewayMenuGroup.BARE_METAL}
    )
    NOT_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(r"^Compare our|Program$", re.IGNORECASE)
    CHANGELOG_URL: ClassVar[str] = "https://www.scaleway.com/en/docs/changelog/rss.xml"
    TITLE_SEPARATOR: ClassVar[str] = " | "
    CDATA: ClassVar[re.Pattern[str]] = re.compile(r"^\s*<!\[CDATA\[(.*?)\]\]>\s*$", re.DOTALL)
    WORD_SEPARATOR: ClassVar[re.Pattern[str]] = re.compile(r"[\W_]+")
    IGNORED_WORDS: ClassVar[FrozenSet[str]] = frozenset({"scaleway", "apache", "and", "for", "the"})
    PLURAL_MIN_LENGTH: ClassVar[int] = 4
    PRICES_URL: ClassVar[str] = "https://api.scaleway.com/product-catalog/v2alpha1/public-catalog/products"
    PRICES_PAGE_SIZE: ClassVar[int] = 1000
    PRICE_PAGE: ClassVar[str] = "price_page"
    PRICE_UNITS: ClassVar[Dict[ScalewayPriceUnit, Tuple[PriceUnit, int]]] = {
        ScalewayPriceUnit.HOUR: (PriceUnit.HOUR, 1),
        ScalewayPriceUnit.MINUTE: (PriceUnit.MINUTE, 1),
        ScalewayPriceUnit.SECOND: (PriceUnit.SECOND, 1),
        ScalewayPriceUnit.MONTH: (PriceUnit.MONTH, 1),
        ScalewayPriceUnit.YEAR: (PriceUnit.YEAR, 1),
        ScalewayPriceUnit.SETUP: (PriceUnit.ONE_TIME, 1),
        ScalewayPriceUnit.PLAN: (PriceUnit.MONTH, 1),
        ScalewayPriceUnit.GIGABYTE: (PriceUnit.GIB_HOUR, 1),
        ScalewayPriceUnit.GIGABYTE_DAY: (PriceUnit.GIB_HOUR, 24),
        ScalewayPriceUnit.IOPS_GIGABYTE: (PriceUnit.OTHER, 1),
        ScalewayPriceUnit.GB_S: (PriceUnit.GIB_SECOND, 1),
        ScalewayPriceUnit.VCPU_S: (PriceUnit.VCPU_SECOND, 1),
        ScalewayPriceUnit.MVCPU: (PriceUnit.OTHER, 1),
        ScalewayPriceUnit.TOKEN: (PriceUnit.TOKEN, 1),
        ScalewayPriceUnit.REQUEST: (PriceUnit.REQUEST, 1),
        ScalewayPriceUnit.CHUNK: (PriceUnit.REQUEST, 1),
        ScalewayPriceUnit.EMAIL: (PriceUnit.UNIT, 1),
        ScalewayPriceUnit.DOMAIN: (PriceUnit.UNIT, 1),
        ScalewayPriceUnit.IP: (PriceUnit.UNIT_HOUR, 1),
        ScalewayPriceUnit.NODE: (PriceUnit.HOUR, 1),
        ScalewayPriceUnit.CORE: (PriceUnit.UNIT_MONTH, 1),
        ScalewayPriceUnit.DEVICE: (PriceUnit.UNIT_HOUR, 1),
        ScalewayPriceUnit.VERSION: (PriceUnit.UNIT_HOUR, 1),
        ScalewayPriceUnit.KEY: (PriceUnit.UNIT_HOUR, 1),
        ScalewayPriceUnit.SAMPLE_DAY: (PriceUnit.OTHER, 1),
    }
    TRANSFER_SKU: ClassVar[re.Pattern[str]] = re.compile(
        r"bandwidth|/restore/|/messaging/\w+/volume/|/edge-services/cache/|/cockpit/ext-(?:log|trace)/"
    )
    FEE_SKU: ClassVar[re.Pattern[str]] = re.compile(r"/(?:setup|fees?)(?:/|$)")
    MINUTE_SKU: ClassVar[re.Pattern[str]] = re.compile(r"^/ai/inference_dedicated/deployment/")
    WITHDRAWN: ClassVar[FrozenSet[str]] = frozenset({ScalewayStatus.END_OF_LIFE, ScalewayStatus.RETIRED})
    FREE_TIER: ClassVar[re.Pattern[str]] = re.compile(r"\bfree tier\b", re.IGNORECASE)
    NO_UNIT: ClassVar[str] = "none"
    NO_PRICE_REASON: ClassVar[str] = "The Scaleway public catalog lists the product without a price."
    NANOS: ClassVar[Decimal] = Decimal(1_000_000_000)
    BYTES_PER_GIB: ClassVar[Decimal] = Decimal(2**30)
    GIB_PRECISION: ClassVar[Decimal] = Decimal("0.001")

    name = "scaleway"
    catalogue_url: ClassVar[str] = "https://www.scaleway.com/en/all-products/"
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Scaleway ",)
    dates_launches: ClassVar[bool] = True
    launch_feed_start: ClassVar[Optional[datetime]] = datetime(2022, 2, 1, tzinfo=UTC)

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.changelog: Optional[Dict[str, datetime]] = None
        self.price_pages: Set[int] = set()
        self.price_rows = 0

    ############################
    # Internal Helpers Methods #
    ############################

    def _label_words(self, text: str) -> Tuple[str, ...]:
        """Split a product name, page slug or changelog label into the words compared to match them.

        Args:
            text (str): The name, slug or label, e.g. `Secret-manager`.

        Returns:
            Tuple[str, ...]: The case-folded words, ignored words dropped and plurals made singular.
        """
        words: List[str] = []
        for word in self.WORD_SEPARATOR.split(self._clean_text(text).casefold()):
            if not word or word in self.IGNORED_WORDS:
                continue
            plural = len(word) > self.PLURAL_MIN_LENGTH and word.endswith("s") and not word.endswith("ss")
            words.append(word[:-1] if plural else word)
        return tuple(words)

    def _changelog_entry(self, item: Selector) -> Optional[Tuple[str, datetime]]:
        """Read the product label and the date of a changelog entry.

        Args:
            item (Selector): The `<item>` of the feed.

        Returns:
            Optional[Tuple[str, datetime]]: The label (e.g. `Secret-manager`) and the date in UTC, `None` when the
                title names no product or the date is unreadable or implausible.
        """
        raw = item.css(f"{ScalewayChangelogTag.TITLE}::text").get() or ""
        wrapped = self.CDATA.match(raw)
        title = self._clean_text(wrapped.group(1) if wrapped else raw)
        label, separator, _ = title.partition(self.TITLE_SEPARATOR)
        if not separator or not label.strip():
            self.logger.debug("Skipping the changelog entry %r, it names no product.", title)
            return None
        published = (item.css(f"{ScalewayChangelogTag.PUB_DATE}::text").get() or "").strip()
        try:
            date = parsedate_to_datetime(published)
        except TypeError, ValueError:
            self.logger.debug("Ignoring the unreadable date %r of the changelog entry %r.", published, title)
            return None
        date = (date if date.tzinfo else date.replace(tzinfo=UTC)).astimezone(UTC)
        if not self.EARLIEST_DATE <= date <= datetime.now(UTC):
            self.logger.debug("Ignoring the implausible date %s of the changelog entry %r.", date.isoformat(), title)
            return None
        return label.strip(), date

    def _changelog_launches(self, response: Response) -> Dict[str, datetime]:
        """Read the earliest entry of each product label of the changelog feed.

        Args:
            response (Response): The changelog RSS feed.

        Returns:
            Dict[str, datetime]: The earliest entry date of each label, empty when the page lists no dated entry.

        Notes:
            The feed is not sorted by date. A page without entries (a moved feed served as an HTML page) dates
            nothing.
        """
        launches: Dict[str, datetime] = {}
        items = response.css(str(ScalewayChangelogTag.ITEM))
        for item in items:
            entry = self._changelog_entry(item)
            if entry is not None:
                label, date = entry
                launches[label] = min(date, launches.get(label, date))
        if launches:
            self.logger.info(
                "%d product labels read from %d %s changelog entries.", len(launches), len(items), self.name
            )
        else:
            self.logger.warning("The %s changelog %s lists no dated product entry.", self.name, response.url)
        return launches

    async def _changelog(self) -> Dict[str, datetime]:
        """Get the earliest changelog entry of each product label, the feed being fetched once per crawl.

        Returns:
            Dict[str, datetime]: The earliest entry date of each label, empty when the feed cannot be read.
        """
        if self.changelog is None:
            response = await self._fetch_launch_page(self.CHANGELOG_URL)
            if response is None:
                self.logger.warning(
                    "The %s changelog %s cannot be read, no launch read.", self.name, self.CHANGELOG_URL
                )
            self.changelog = self._changelog_launches(response) if response is not None else {}
        return self.changelog

    def _names_label(self, words: Tuple[str, ...], label: Tuple[str, ...]) -> bool:
        """Tell whether the words of a product name or slug name a changelog label.

        Args:
            words (Tuple[str, ...]): The words of the product name or slug.
            label (Tuple[str, ...]): The words of the label.

        Returns:
            bool: Whether the label words are a run of the product words, or have the same letters.
        """
        if not words or not label:
            return False
        if "".join(words) == "".join(label):
            return True
        size = len(label)
        return any(words[start : start + size] == label for start in range(len(words) - size + 1))

    def _product_names(self, product: CloudProduct) -> List[Tuple[str, ...]]:
        """Get the words of the names a product may have in the changelog: its name and its page slug.

        Args:
            product (CloudProduct): The product.

        Returns:
            List[Tuple[str, ...]]: The words of its name, then of the last segment of its page path, if any.
        """
        names = [self._label_words(product.name)]
        slug = urlparse(product.url).path.rstrip("/").rpartition("/")[2] if product.url else ""
        if slug:
            names.append(self._label_words(slug))
        return names

    def _changelog_label(self, names: List[Tuple[str, ...]], labels: Iterable[str]) -> Optional[str]:
        """Find the changelog label naming a product, the longest one when several do.

        Args:
            names (List[Tuple[str, ...]]): The words of the names of the product.
            labels (Iterable[str]): The changelog labels.

        Returns:
            Optional[str]: The label, `None` when none names the product.
        """
        matches: List[Tuple[int, int, str]] = []
        for label in labels:
            words = self._label_words(label)
            if any(self._names_label(name, words) for name in names):
                matches.append((len(words), len("".join(words)), label))
        return max(matches)[2] if matches else None

    async def _launch_source(self, product: CloudProduct) -> Optional[Tuple[datetime, DateCaveat]]:
        """Read the launch of a product from the earliest changelog entry of its label.

        Args:
            product (CloudProduct): The product, dated by its website record or undated.

        Returns:
            Optional[Tuple[datetime, DateCaveat]]: The launch and its caveat, `None` when no changelog label names
                the product.
        """
        launches = await self._changelog()
        alias = self.launch_aliases.get(self._name_key(product.name))
        label = self._changelog_label([self._label_words(alias)], launches) if alias else None
        label = label or self._changelog_label(self._product_names(product), launches)
        if label is None:
            self.logger.debug("No %s changelog label names %r.", self.name, product.name)
            return None
        self.logger.debug("%r is the %s changelog label %r.", product.name, self.name, label)
        return self._announced(launches[label])

    def _link_url(self, link: JsonValue) -> Optional[str]:
        """Get the absolute URL of a page link, which holds either a URL or a website page path.

        Args:
            link (JsonValue): The link data.

        Returns:
            Optional[str]: The absolute URL, `None` without link.
        """
        fields = self._as_object(link)
        page = self._as_object(fields.get(ScalewayLinkField.PAGE))
        url = self._as_text(fields.get(ScalewayLinkField.URL)) or self._as_text(page.get(ScalewayPageField.PATH))
        return urljoin(self.SITE_URL, url.lstrip("/")) if url else None

    def _link_dates(self, link: JsonValue, name: Optional[str]) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Get the creation and the last update of the website page of a link.

        Args:
            link (JsonValue): The link data.
            name (Optional[str]): The product of the link, for the logs.

        Returns:
            Tuple[Optional[datetime], Optional[datetime]]: The page `createdAt` and `updatedAt`, `None` without
                website page or when unreadable.

        Notes:
            Both are dates of the website's page record (`WEBSITE_RECORD` and `PAGE_MODIFIED` caveats): many records
            were created by a migration of the website, long after the product launch.
        """
        page = self._as_object(self._as_object(link).get(ScalewayLinkField.PAGE))
        created = self._parse_date(page.get(ScalewayPageField.CREATED_AT), name)
        return created, self._parse_date(page.get(ScalewayPageField.UPDATED_AT), name)

    def _categories(self, labels: Sequence[Optional[str]], name: Optional[str]) -> List[str]:
        """Clean the categories of a product: blank, repeated (case-insensitive) labels and its own name dropped.

        Args:
            labels (Sequence[Optional[str]]): The category labels, top level first.
            name (Optional[str]): The product name, e.g. `Serverless Jobs` for the menu group of the same name.

        Returns:
            List[str]: The category labels, in order.
        """
        categories: List[str] = []
        known = {self._clean_text(name).casefold()}
        for label in labels:
            text = self._clean_text(label)
            if text and text.casefold() not in known:
                categories.append(text)
                known.add(text.casefold())
        return categories

    def _merge_entries(
        self, entries: Iterable[Tuple[Optional[str], Optional[str], JsonValue, List[str]]]
    ) -> List[Tuple[Optional[str], Optional[str], JsonValue, List[str]]]:
        """Merge the entries of a product listed several times, gathering all its categories.

        Args:
            entries (Iterable[Tuple[Optional[str], Optional[str], JsonValue, List[str]]]): The name, description,
                link and categories of each entry, in order.

        Returns:
            List[Tuple[Optional[str], Optional[str], JsonValue, List[str]]]: The first entry of each product, with
                the categories of all its entries.

        Notes:
            The entries of a product are matched by name or by URL, as the streamed products are.
        """
        merged: List[Tuple[Optional[str], Optional[str], JsonValue, List[str]]] = []
        positions: Dict[str, int] = {}
        for name, description, link, categories in entries:
            url = self._link_url(link)
            keys = [f"name:{self._name_key(name or '')}"] + ([f"url:{self._url_key(url)}"] if url else [])
            position = next((positions[key] for key in keys if key in positions), None)
            if position is None:
                position = len(merged)
                merged.append((name, description, link, self._categories(categories, name)))
            else:
                first = merged[position]
                self.logger.debug("Product %r listed again, under %s.", name, categories)
                merged[position] = (*first[:3], self._categories([*first[3], *categories], first[0]))
            positions.update(dict.fromkeys(keys, position))
        return merged

    def _product(
        self, name: Optional[str], description: Optional[str], link: JsonValue, categories: List[str]
    ) -> Optional[CloudProduct]:
        """Build the product of a catalogue entry, dated by its website page record.

        Args:
            name (Optional[str]): The product name.
            description (Optional[str]): The product description.
            link (JsonValue): The link data.
            categories (List[str]): The categories of the product.

        Returns:
            Optional[CloudProduct]: The product, `None` (logged) when the entry is invalid.
        """
        added_at, updated_at = self._link_dates(link, name)
        url, (added_caveat, updated_caveat) = self._link_url(link), self.DATE_CAVEATS
        return self._build_product(
            name, description, url, added_at, updated_at, added_caveat, updated_caveat, categories=categories
        )

    def _columns_entries(self, data: JsonValue) -> Iterator[Tuple[Optional[str], Optional[str], JsonValue, List[str]]]:
        """Read the entries of the page columns, filed under the title of their column.

        Args:
            data (JsonValue): The page data.

        Yields:
            Tuple[Optional[str], Optional[str], JsonValue, List[str]]: The name, description, link and category of
                each entry of the columns.
        """
        for block in self._walk_objects(data):
            if block.get(ScalewayBlockField.COMPONENT) != self.PRODUCTS_BLOCK:
                continue
            items = block.get(ScalewayBlockField.ITEMS)
            if not isinstance(items, list):
                self.logger.warning(
                    "Skipping the %r products block without items list.", block.get(ScalewayBlockField.TITLE)
                )
                continue
            title = self._as_text(block.get(ScalewayBlockField.TITLE))
            self.logger.debug("Products block %r: %d items.", title, len(items))
            for item in items:
                fields = self._as_object(item)
                name = self._as_text(fields.get(ScalewayEntryField.TITLE))
                description = self._as_text(fields.get(ScalewayEntryField.DESCRIPTION))
                yield name, description, fields.get(ScalewayEntryField.LINK), [title] if title else []

    def _menu_leaves(self, value: JsonValue, path: Tuple[str, ...] = ()) -> Iterator[Tuple[JsonValue, Tuple[str, ...]]]:
        """Walk the header menu entries without children, with the names of their groups.

        Args:
            value (JsonValue): A header menu entry.
            path (Tuple[str, ...]): The names of the groups above the entry, top level first.

        Yields:
            Tuple[JsonValue, Tuple[str, ...]]: Each entry without children and the names of its groups.
        """
        children = self._as_object(value).get(ScalewayEntryField.CHILDREN)
        if isinstance(children, list) and children:
            group = self._clean_text(self._as_text(self._as_object(value).get(ScalewayEntryField.GROUP_NAME)))
            for child in children:
                yield from self._menu_leaves(child, (*path, group))
        else:
            yield value, path

    def _menu_entries(self, data: JsonValue) -> Iterator[Tuple[Optional[str], Optional[str], JsonValue, List[str]]]:
        """Read the product entries of the header menu product groups, filed under their groups.

        Args:
            data (JsonValue): The page data.

        Yields:
            Tuple[Optional[str], Optional[str], JsonValue, List[str]]: The name, description, link and categories
                (top level group first) of each product entry of the menu.
        """
        props = self._as_object(self._as_object(data).get(ScalewayNextDataField.PROPS))
        header = self._as_object(props.get(ScalewayNextDataField.PAGE_PROPS)).get(ScalewayNextDataField.HEADER)
        groups = self._as_object(header).get(ScalewayNextDataField.MAIN_NAVIGATION_ITEMS)
        for group in groups if isinstance(groups, list) else []:
            if self._as_text(self._as_object(group).get(ScalewayEntryField.GROUP_NAME)) not in self.MENU_GROUPS:
                continue
            for leaf, path in self._menu_leaves(group):
                fields = self._as_object(leaf)
                name = self._as_text(fields.get(ScalewayEntryField.GROUP_NAME))
                description = self._as_text(fields.get(ScalewayEntryField.DESCRIPTION))
                if not (description or "").strip() or self.NOT_PRODUCT.search(name or ""):
                    self.logger.debug("Skipping the header menu entry %r, not a product.", name)
                    continue
                yield name, description, fields.get(ScalewayEntryField.LINK), list(path)

    def _price_unit(self, sku: str, measure: JsonValue) -> Tuple[PriceUnit, str, Decimal]:
        """Normalize the unit a catalog price is per.

        Args:
            sku (str): The SKU of the product (it tells a stored gigabyte from a transferred one).
            measure (JsonValue): Its `unit_of_measure`, `null` for a product without price.

        Returns:
            Tuple[PriceUnit, str, Decimal]: The normalized unit, the unit as written (with its size, e.g.
                `1000 token`), and the normalized units in one written unit.
        """
        if not isinstance(measure, dict) or not isinstance(measure.get(ScalewayCatalogField.UNIT), str):
            return PriceUnit.OTHER, self.NO_UNIT, Decimal(1)
        raw = str(measure[ScalewayCatalogField.UNIT])
        size = measure.get(ScalewayCatalogField.SIZE)
        count = Decimal(size) if isinstance(size, int) and size > 0 else Decimal(1)
        written = raw if count == 1 else f"{count} {raw}"
        try:
            unit, factor = self.PRICE_UNITS[ScalewayPriceUnit(raw)]
        except ValueError:
            self.logger.warning("Unknown Scaleway price unit %r (%s): kept as other.", raw, sku)
            return PriceUnit.OTHER, written, count
        if unit is PriceUnit.GIB_HOUR and self.TRANSFER_SKU.search(sku):
            unit = PriceUnit.GIB
        elif self.FEE_SKU.search(sku):
            unit = PriceUnit.ONE_TIME
        elif self.MINUTE_SKU.search(sku):
            unit = PriceUnit.MINUTE
        return unit, written, count * factor

    def _price_region(self, locality: JsonValue) -> str:
        """Read where a catalog product is sold.

        Args:
            locality (JsonValue): Its `locality`, one of a zone, a region, a datacenter or `global`.

        Returns:
            str: The zone, region or datacenter, `global` when it is sold everywhere.
        """
        if isinstance(locality, dict):
            for place in (ScalewayLocality.ZONE, ScalewayLocality.REGION, ScalewayLocality.DATACENTER):
                value = locality.get(place)
                if isinstance(value, str) and value:
                    return value
        return ScalewayLocality.GLOBAL.value

    def _price_hardware(self, properties: JsonValue) -> Dict[str, Optional[Decimal]]:
        """Read the virtual CPUs, memory and storage of a server of the catalog.

        Args:
            properties (JsonValue): Its `properties`.

        Returns:
            Dict[str, Optional[Decimal]]: Its `vcpu`, `memory_gib` and `storage_gib`, `None` when not stated.
        """
        hardware = properties.get(ScalewayHardwareField.HARDWARE) if isinstance(properties, dict) else None
        found: Dict[str, Optional[Decimal]] = {"vcpu": None, "memory_gib": None, "storage_gib": None}
        if not isinstance(hardware, dict):
            return found
        cpu = hardware.get(ScalewayHardwareField.CPU)
        if isinstance(cpu, dict):
            virtual = cpu.get(ScalewayHardwareField.VIRTUAL)
            count = virtual.get(ScalewayHardwareField.COUNT) if isinstance(virtual, dict) else None
            count = count if isinstance(count, int) else cpu.get(ScalewayHardwareField.THREADS)
            found["vcpu"] = Decimal(count) if isinstance(count, int) and count > 0 else None
        for field, name, key in (
            ("memory_gib", ScalewayHardwareField.RAM, ScalewayHardwareField.SIZE),
            ("storage_gib", ScalewayHardwareField.STORAGE, ScalewayHardwareField.TOTAL),
        ):
            part = hardware.get(name)
            size = part.get(key) if isinstance(part, dict) else None
            if isinstance(size, int) and size > 0:
                found[field] = (Decimal(size) / self.BYTES_PER_GIB).quantize(self.GIB_PRECISION)
        return found

    def _price_attributes(self, item: Dict[str, JsonValue]) -> Dict[str, JsonValue]:
        """Keep the attributes of a catalog product that tell its prices apart.

        Args:
            item (Dict[str, JsonValue]): The product.

        Returns:
            Dict[str, JsonValue]: Its name, variant and status, and the plain values of its service properties
                (e.g. the token type of a language model), the hardware left out.
        """
        attributes: Dict[str, JsonValue] = {
            str(field): item[field]
            for field in (ScalewayCatalogField.PRODUCT, ScalewayCatalogField.VARIANT, ScalewayCatalogField.STATUS)
            if isinstance(item.get(field), str)
        }
        properties = item.get(ScalewayCatalogField.PROPERTIES)
        if not isinstance(properties, dict):
            return attributes
        for group, values in properties.items():
            if group == ScalewayHardwareField.HARDWARE or not isinstance(values, dict):
                continue
            for name, value in values.items():
                if isinstance(value, (str, int, float, bool)):
                    attributes[name] = value
        return attributes

    def _catalog_price(self, item: Dict[str, JsonValue]) -> Optional[Union[ServicePrice, FreeTier]]:
        """Read the price of a product of the catalog.

        Args:
            item (Dict[str, JsonValue]): The product.

        Returns:
            Optional[Union[ServicePrice, FreeTier]]: Its price (a price of 0 as free, no price as not public), its
                free offer when it is one, `None` when it is withdrawn or malformed.
        """
        sku = item.get(ScalewayCatalogField.SKU)
        service = item.get(ScalewayCatalogField.PRODUCT_CATEGORY)
        if not isinstance(sku, str) or not isinstance(service, str):
            self.logger.warning("A Scaleway catalog product has no SKU or service: skipped.")
            return None
        status = item.get(ScalewayCatalogField.STATUS)
        if isinstance(status, str) and status in self.WITHDRAWN:
            self.logger.debug("The Scaleway product %s is withdrawn (%s): skipped.", sku, status)
            return None
        product = str(item.get(ScalewayCatalogField.PRODUCT) or "")
        region = self._price_region(item.get(ScalewayCatalogField.LOCALITY))
        retail = item.get(ScalewayCatalogField.PRICE)
        retail = retail.get(ScalewayCatalogField.RETAIL_PRICE) if isinstance(retail, dict) else None
        if not isinstance(retail, dict) and self.FREE_TIER.search(product):
            self.logger.debug("The Scaleway product %s is a free offer.", sku)
            return self._free_fact(
                {
                    "free_key": sku,
                    "service": service,
                    "kind": FreeTierKind.ALWAYS_FREE,
                    "region_scope": region,
                    "conditions": item.get(ScalewayCatalogField.DESCRIPTION),
                    "source_url": self.PRICES_URL,
                    "source_kind": PriceSourceKind.API,
                }
            )
        unit, written, factor = self._price_unit(sku, item.get(ScalewayCatalogField.UNIT_OF_MEASURE))
        fields: Dict[str, RawValue] = {
            "sku_key": sku,
            "service": service,
            "family": item.get(ScalewayCatalogField.SERVICE_CATEGORY),
            "region": region,
            "attributes": self._price_attributes(item),
            "unit": unit,
            "unit_raw": written,
            "unit_factor": factor,
            "source_url": self.PRICES_URL,
            "source_kind": PriceSourceKind.API,
        }
        hardware = self._price_hardware(item.get(ScalewayCatalogField.PROPERTIES))
        if hardware["vcpu"] is not None:
            fields.update({"instance_type": product, **hardware})
        if not isinstance(retail, dict):
            self.logger.debug("The Scaleway product %s states no price.", sku)
            return self._price_fact({**fields, "model": PriceModel.NOT_PUBLIC, "reason": self.NO_PRICE_REASON})
        units, nanos = retail.get(ScalewayCatalogField.UNITS), retail.get(ScalewayCatalogField.NANOS)
        price = Decimal(units if isinstance(units, int) else 0) + Decimal(nanos if isinstance(nanos, int) else 0) / (
            self.NANOS
        )
        fields.update(
            {
                "price": price,
                "currency": retail.get(ScalewayCatalogField.CURRENCY_CODE),
                "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
            }
        )
        return self._price_fact(fields)

    def _catalog_page_url(self, page: int) -> str:
        """Build the URL of a page of the public product catalog.

        Args:
            page (int): The page, from 1.

        Returns:
            str: Its URL.
        """
        return f"{self.PRICES_URL}?page_size={self.PRICES_PAGE_SIZE}&page={page}"

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the first page of the public product catalog, which tells how many pages follow.

        Yields:
            Request: The request of the first page.
        """
        self.price_pages = set()
        self.price_rows = 0
        self.logger.info("Reading the Scaleway prices from %s.", self.PRICES_URL)
        yield self._price_request(self._catalog_page_url(1), {self.PRICE_PAGE: 1})

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read a page of the public product catalog: the following pages first (from the first one), then prices.

        Args:
            response (Response): The page.

        Yields:
            PriceFact: The requests of the following pages, then the prices and free offers of the page.

        Raises:
            CatalogueFormatError: If the page is not a JSON object listing products.
        """
        data = self._json_body(response)
        products = data.get(ScalewayCatalogField.PRODUCTS) if isinstance(data, dict) else None
        if not isinstance(data, dict) or not isinstance(products, list):
            self.logger.error("The Scaleway catalog page %s lists no products.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the catalog page lists no products")
        page = response.meta.get(self.PRICE_PAGE)
        page = page if isinstance(page, int) else 1
        if page == 1:
            total = data.get(ScalewayCatalogField.TOTAL_COUNT)
            pages = -(-total // self.PRICES_PAGE_SIZE) if isinstance(total, int) else 1
            self.price_pages = set(range(2, pages + 1))
            self.logger.info("The Scaleway catalog lists %s products in %d pages.", total, pages)
            for following in sorted(self.price_pages):
                yield self._price_request(self._catalog_page_url(following), {self.PRICE_PAGE: following})
        read = 0
        for item in products:
            fact = self._catalog_price(item) if isinstance(item, dict) else None
            if fact is not None:
                read += 1
                yield fact
        self.price_rows += read
        self.price_pages.discard(page)
        self.logger.debug("Scaleway catalog page %d: %d prices, %d pages left.", page, read, len(self.price_pages))
        if not self.price_pages:
            self._record_price_source(self.PRICES_URL, self.price_rows)
            self.logger.info("The Scaleway catalog is read whole: %d prices.", self.price_rows)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def on_start(self, resuming: bool = False) -> None:
        """Forget the changelog of a previous crawl, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if resuming:
            self.logger.debug("%s crawl resumed: the changelog read before is kept.", self.name)
            return
        self.logger.debug("%s crawl started: the changelog is read again when needed.", self.name)
        self.changelog = None

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the page columns, then of the header menu, with their categories.

        Args:
            response (Response): The catalogue page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the page.

        Notes:
            A product listed in several columns is filed under all their titles, and a product listed in several
            menu groups under all of them. A product of the columns keeps their categories: its menu entries are
            then duplicates, skipped when streamed.
        """
        self.logger.debug("Reading the %s products menu of %s.", self.name, response.url)
        data = self._next_data(response)
        count = 0
        for entries in (self._columns_entries(data), self._menu_entries(data)):
            for name, description, link, categories in self._merge_entries(entries):
                if product := self._product(name, description, link, categories):
                    count += 1
                    yield product
        if count:
            self.logger.info("%d %s products read from the menu of %s.", count, self.name, response.url)
        else:
            self.logger.warning("No %s product in the menu of %s.", self.name, response.url)
