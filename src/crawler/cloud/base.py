from __future__ import annotations

# Standard Library Imports.
import asyncio
import html
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import (
    AsyncGenerator,
    ClassVar,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)
from urllib.parse import urlparse

# Third Party Imports.
import httpx
from pydantic import JsonValue, ValidationError
from scrapling.fetchers import AsyncDynamicSession, AsyncFetcher, AsyncStealthySession, FetcherSession
from scrapling.parser import Selector
from scrapling.spiders import Request, Response, Spider
from scrapling.spiders.session import SessionManager

# First Party Imports.
from crawler.enums import HtmlAttribute, PageMetaName, RequestMeta, TextEncoding
from crawler.exception import (
    CatalogueFormatError,
    CrawlerError,
    EmptyCatalogueError,
    LaunchCatalogError,
    ParseNotImplementedError,
    PriceDownloadError,
)
from crawler.tls.ca_bundle import CaBundle
from curated.bundle.bundle_catalogs import BundleCatalogs
from curated.exception import CuratedError
from models.cloud.dated_item import DatedItem
from models.cloud.enums import (
    CloudProvider,
    DateCaveat,
    LaunchPrecision,
    PriceFactKind,
    PriceModel,
    PriceSourceKind,
    PriceSourceStatus,
    PriceTerm,
    PriceUnit,
    UrlScheme,
)
from models.cloud.launch.curated_launch import CuratedLaunch
from models.cloud.launch.launch_catalog import LaunchCatalog
from models.cloud.prices.facts.free_tier import FreeTier
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.prices.stored.price_source import PriceSource
from models.cloud.products.product import CloudProduct

type PriceFact = Union[ServicePrice, FreeTier, Request]
type PriceItem = Dict[str, Union[str, ServicePrice, FreeTier]]
type PriceFields = Dict[str, RawValue]


class BaseCloudCrawler(Spider):
    """Base class for cloud provider catalogue crawlers.

    Attributes:
        PRIMARY_PRIORITY (ClassVar[int]): The priority of the main catalogue requests, crawled before the complements.
        PRICE_KIND_KEY (ClassVar[str]): The item key naming the kind of a price fact (a price, a free offer): `fact`,
            since a free offer has a `kind` field of its own.
        PRICE_MODEL_KEY (ClassVar[str]): The item key holding the validated price or free offer.
        DATES_PRIORITY (ClassVar[int]): The priority of the sitemaps read for their dates, crawled first.
        PAGE_DATES (ClassVar[str]): The meta key marking a sitemap request read for the last modification of its
            pages.
        PRODUCT_PAGE (ClassVar[str]): The meta key marking a product page request, holding the requested URL.
        PRODUCT_NAME (ClassVar[str]): The meta key holding the product name given by a listing, if any.
        PRODUCT_UPDATED (ClassVar[str]): The meta key holding the last modification of a product page given by a
            sitemap, if any.
        PRODUCT_CATEGORIES (ClassVar[str]): The meta key holding the catalogue categories of a product page given by
            a listing, if any.
        ADDED_META (ClassVar[Tuple[PageMetaName, ...]]): The `meta` tags giving the publication date of a page.
        UPDATED_META (ClassVar[Tuple[PageMetaName, ...]]): The `meta` tags giving the last modification of a page.
        EARLIEST_DATE (ClassVar[datetime]): The earliest plausible date of a product: an earlier one is an error of
            the website.
        SAME_DAY_LIMIT (ClassVar[int]): From how many pages a sitemap dating them all the same day is ignored: its
            dates are then the generation date of the sitemap.
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The URL the catalogue crawl starts from: the main product listing.
        complement_urls (ClassVar[Tuple[str, ...]]): Secondary sources, crawled after the main listing, which only
            add the products not found yet.
        dates_sitemaps (ClassVar[Tuple[str, ...]]): The sitemaps giving the last modification of the product pages,
            read before anything else so that every product with a listed page is dated.
        name_prefixes (ClassVar[Tuple[str, ...]]): Brand prefixes ignored when comparing product names, e.g. `AWS `.
        robots_txt_obey (bool): Whether the `robots.txt` rules of the provider are respected.
        solve_cloudflare (ClassVar[bool]): Whether the browser solves the Cloudflare challenges. Off by default: no
            provider shows one, and the check waits for each page to be idle and logs an error when there is none.
        lazy_browser (ClassVar[bool]): Whether the stealth browser is only started when a request uses it.
        fetch_retries (ClassVar[int]): How many times a failed page fetch is attempted.
        PRICE_TIMEOUT_S (ClassVar[int]): How long a price source may take to download, in seconds (each read of a
            streamed price file).
        PRICE_CONNECT_TIMEOUT_S (ClassVar[int]): How long the connection to a streamed price file may take.
        PRICE_HEADERS (ClassVar[Dict[str, str]]): The headers of the price session, none by default (a provider
            answering browsers with a captcha has the crawler named instead).
        POST_METHOD (ClassVar[str]): The method of a price request with a JSON body.
        GET_METHOD (ClassVar[str]): The method of a price request without body.
        TABLE_HEADING (ClassVar[str]): The XPath of the nearest heading before a price table.
        UNPRICED_REASON (ClassVar[Optional[str]]): Why the provider has no public price, for a provider publishing
            none: its products are then stated unpriced (`None`, the default, for a provider with price sources).
        UNPRICED_MODEL (ClassVar[PriceModel]): How the products of such a provider are priced (on request, or not
            published).
        UNPRICED_URL (ClassVar[Optional[str]]): The page read as the evidence of its unpriced products (its
            catalogue page when `None`).
        UNPRICED_META (ClassVar[str]): The request meta marking the evidence page request.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): Whether the live catalogue product pages are read too, for their price
            tables (for a provider whose product pages show prices its other sources miss).
        PRODUCT_PAGE_META (ClassVar[str]): The request meta holding the product of a product page request.
        CURATED_PAGE_META (ClassVar[str]): The request meta marking a curated price page (its text read when it has
            no price table).
        PAGE_TEXT_PRICES (ClassVar[bool]): Whether a product page without price table is read for the prices written
            in its text (cards, lists), for a provider whose pages show prices that way.
        PRODUCT_PAGE_JS (ClassVar[bool]): Whether the product pages are rendered by a plain headless browser (not the
            stealth one) before being read, for a provider whose prices load client-side.
        RENDER_WAIT_MS (ClassVar[int]): The wait after a rendered page is idle, for its late price widgets.
        RENDER_TIMEOUT_MS (ClassVar[int]): The longest wait for a rendered page.
        TEXT_LINE_LIMIT (ClassVar[int]): The longest text line read for a price (longer ones are prose).
        STARTING (ClassVar[re.Pattern[str]]): The words of a starting price, e.g. `from` or `от`.
        MONEY (ClassVar[re.Pattern[str]]): An amount of money with its currency sign or code, before or after it.
        CURRENCY_SIGNS (ClassVar[Dict[str, str]]): The ISO currency of each sign or code (case ignored).
        PERIOD_WORDS (ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit, PriceUnit], ...]]): The words of a billing
            period, its unit, and its unit for a size (per GB).
        COUNT_WORDS (ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit, Decimal], ...]]): The words of a price per
            count of tokens or requests, its unit and the units in one.
        ZERO_WIDTH (ClassVar[re.Pattern[str]]): The zero-width marks removed from scraped texts.
        TABLE_CONTEXT (ClassVar[str]): The XPath of the texts just before a table (its unit, often).
        BARE_NUMBER (ClassVar[re.Pattern[str]]): A cell written as a bare number.
        CONTEXT_CURRENCIES (ClassVar[Tuple[Tuple[re.Pattern[str], str], ...]]): The words stating the currency of
            a table, and its ISO code.
        SIZE_WORD (ClassVar[re.Pattern[str]]): The words of a price per GB.
        retry_delay (ClassVar[float]): The delay between two attempts of a failed fetch, in seconds.
        DESCRIPTION_LIMIT (ClassVar[int]): The longest description kept, longer ones are shortened.
        LAUNCH_TIMEOUT (ClassVar[int]): How long a page of a dated source is waited for, in seconds.
        REPLACEABLE_CAVEATS (ClassVar[Tuple[DateCaveat, ...]]): The caveats of a catalogue date which is not a
            launch (a page or record date): the dated source is still asked for the launch of such a product.
        dates_launches (ClassVar[bool]): Whether the crawler reads the launch of each product from the provider's
            dated source (`_launch_source`).
        launch_feed_start (ClassVar[Optional[datetime]]): Until when the dated source is in its first months: an
            earlier first entry may postdate the launch (`FEED_START`), `None` when the source covers every launch.
        concurrent_requests (int): The maximum number of requests in flight.
        download_delay (float): The delay between two requests, in seconds.
        seen_products (Set[str]): The normalized names (and aliases) of the products already streamed by the crawl.
        seen_urls (Set[str]): The normalized URLs of the products already streamed by the crawl.
        page_dates (Dict[str, str]): The last modification (raw) of each page listed by the `dates_sitemaps`, by
            normalized URL.
        curated (Dict[str, CuratedLaunch]): The curated launches of the crawler's products, by normalized name.
        launch_aliases (Dict[str, str]): The name the dated source gives each renamed product, by normalized name.
        undated (Set[str]): The products the crawl left without launch, known gaps excepted.
        prices_mode (bool): Whether the crawler reads its price sources instead of its catalogue (`use_prices`).
        price_provider (CloudProvider): The provider of the prices read, given by `use_prices`.
        price_sources (Dict[str, PriceSource]): The price sources as last read, by source.
        price_reads (Dict[str, PriceSource]): The price sources read in this crawl, by source (read whole or
            unchanged): only the rows of those read whole are closed when a crawl no longer finds them.
        price_failures (Set[str]): The price sources which failed in this crawl.
        price_count (int): The prices and free offers streamed in this crawl.
        price_products (Dict[str, Optional[str]]): The page of each live catalogue product of the provider, by
            name, in price mode.
        price_pages (Dict[str, List[str]]): The curated extra price pages of each product, by name, in price mode
            (read as product pages whatever `PRODUCT_PAGE_PRICES`, their text read when they have no price table).
        price_stream_lock (asyncio.Lock): Held while a price file is streamed: one at a time (the crawl engine runs
            the callbacks of several responses at once).

    Notes:
        A product is streamed once: it is skipped when its normalized name or URL was already seen.
        The `allowed_domains` attribute, inherited from `Spider`, is set to the domains of the catalogue URLs.
        The scrapling spider logger (`scrapling.spiders.<name>`), also used by the crawl engine, is routed to the
        application logging configuration.
        When a listing only gives the product names or links, each product page is requested (`PRODUCT_PAGE` meta)
        and its product is read from its title and meta description, filed under the categories the listing gave
        (`PRODUCT_CATEGORIES` meta).
        A listing filing a product under several categories lists it once per category: `_merge_categories` gathers
        these occurrences into one product holding all their categories.
        A product is dated before it is streamed, the first source giving a launch winning:
            1. its curated launch in the launch dates catalogue (`data/curated/launches.json`), any crawler,
            2. the date the catalogue page gives, if any,
            3. for a `dates_launches` crawler, the provider's dated source (`_launch_source`), under the product's
               name or under the name the catalogue's aliases give it.
        A dated source that cannot be read leaves the product undated, never drops it. The products left undated
        (a new product the launch dates catalogue does not list yet) are reported at the end of the crawl.
    """

    PRIMARY_PRIORITY: ClassVar[int] = 10
    PRICE_KIND_KEY: ClassVar[str] = "fact"
    PRICE_MODEL_KEY: ClassVar[str] = "model"
    DATES_PRIORITY: ClassVar[int] = 20
    PAGE_DATES: ClassVar[str] = RequestMeta.PAGE_DATES
    SAME_DAY_LIMIT: ClassVar[int] = 10
    EARLIEST_DATE: ClassVar[datetime] = datetime(1990, 1, 1, tzinfo=UTC)
    PRODUCT_PAGE: ClassVar[str] = RequestMeta.PRODUCT_PAGE
    PRODUCT_NAME: ClassVar[str] = RequestMeta.PRODUCT_NAME
    PRODUCT_UPDATED: ClassVar[str] = RequestMeta.PRODUCT_UPDATED
    PRODUCT_CATEGORIES: ClassVar[str] = RequestMeta.PRODUCT_CATEGORIES
    ADDED_META: ClassVar[Tuple[PageMetaName, ...]] = (PageMetaName.ARTICLE_PUBLISHED_TIME, PageMetaName.DATE_PUBLISHED)
    UPDATED_META: ClassVar[Tuple[PageMetaName, ...]] = (
        PageMetaName.ARTICLE_MODIFIED_TIME,
        PageMetaName.OG_UPDATED_TIME,
        PageMetaName.DATE_MODIFIED,
        PageMetaName.CPP_LAST_MODIFIED_TIME,
    )
    DESCRIPTION_LIMIT: ClassVar[int] = 1000
    LAUNCH_TIMEOUT: ClassVar[int] = 60
    REPLACEABLE_CAVEATS: ClassVar[Tuple[DateCaveat, ...]] = (
        DateCaveat.WEBSITE_RECORD,
        DateCaveat.PAGE_MODIFIED,
        DateCaveat.PAGE_PUBLISHED,
    )
    PRICE_TIMEOUT_S: ClassVar[int] = 300
    PRICE_CONNECT_TIMEOUT_S: ClassVar[int] = 30
    PRICE_HEADERS: ClassVar[Dict[str, str]] = {}
    POST_METHOD: ClassVar[str] = "POST"
    GET_METHOD: ClassVar[str] = "GET"
    TABLE_HEADING: ClassVar[str] = "preceding::*[self::h1 or self::h2 or self::h3 or self::h4][1]"
    UNPRICED_REASON: ClassVar[Optional[str]] = None
    UNPRICED_MODEL: ClassVar[PriceModel] = PriceModel.NOT_PUBLIC
    UNPRICED_URL: ClassVar[Optional[str]] = None
    UNPRICED_META: ClassVar[str] = "price_unpriced"
    PRODUCT_PAGE_PRICES: ClassVar[bool] = False
    PRODUCT_PAGE_META: ClassVar[str] = "price_product_page"
    CURATED_PAGE_META: ClassVar[str] = "curated_price_page"
    PAGE_TEXT_PRICES: ClassVar[bool] = False
    PRODUCT_PAGE_JS: ClassVar[bool] = False
    RENDER_WAIT_MS: ClassVar[int] = 1500
    RENDER_TIMEOUT_MS: ClassVar[int] = 60000
    TEXT_LINE_LIMIT: ClassVar[int] = 160
    STARTING: ClassVar[re.Pattern[str]] = re.compile(r"^(from|starting|à partir|ab|от|起)\b|\bfrom\b", re.I)
    MONEY: ClassVar[re.Pattern[str]] = re.compile(
        r"(?P<before>US\$|€|\$|£|₽|¥|CHF|EUR|USD|GBP|RUB|CNY)\s?(?P<first>\d(?:[\d\s\u00a0\u202f.,']*\d)?)"
        r"|(?P<second>\d(?:[\d\s\u00a0\u202f.,']*\d)?)\s?(?P<after>€|\$|£|₽|\u0440\u0443\u0431\.?|¥|元|CHF|EUR|USD|GBP|RUB|CNY)",
        re.IGNORECASE,
    )
    CURRENCY_SIGNS: ClassVar[Dict[str, str]] = {
        "us$": "USD",
        "$": "USD",
        "usd": "USD",
        "€": "EUR",
        "eur": "EUR",
        "£": "GBP",
        "gbp": "GBP",
        "₽": "RUB",
        "\u0440\u0443\u0431": "RUB",
        "rub": "RUB",
        "¥": "CNY",
        "元": "CNY",
        "cny": "CNY",
        "chf": "CHF",
    }
    PERIOD_WORDS: ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit, PriceUnit], ...]] = (
        (
            re.compile(r"/\s*h(?:ou)?r?\b|per hour|hourly|\bhour\b|/\s*час|в час|小时", re.I),
            PriceUnit.HOUR,
            PriceUnit.GIB_HOUR,
        ),
        (
            re.compile(r"/\s*mo(?:nth)?\b|per month|monthly|\bmonth\b|/\s*мес|в месяц|30 дней|每月|/月", re.I),
            PriceUnit.MONTH,
            PriceUnit.GIB_MONTH,
        ),
        (
            re.compile(r"/\s*y(?:ea)?r\b|per year|yearly|annual|\byear\b|/\s*год|每年|/年", re.I),
            PriceUnit.YEAR,
            PriceUnit.YEAR,
        ),
        (re.compile(r"/\s*min\b|per minute|минут", re.I), PriceUnit.MINUTE, PriceUnit.MINUTE),
        (
            re.compile(r"/\s*sec(?:ond)?\b|per second|/\s*сек|/秒|每秒", re.I),
            PriceUnit.SECOND,
            PriceUnit.GIB_SECOND,
        ),
    )
    COUNT_WORDS: ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit, Decimal], ...]] = (
        (
            re.compile(r"(?:1M|1 ?million|million|百万|1,000,000)\s*(?:input |output )?tokens?", re.I),
            PriceUnit.TOKEN,
            Decimal(1_000_000),
        ),
        (
            re.compile(r"(?:1K|1 ?thousand|thousand|千|1,000)\s*(?:input |output )?tokens?", re.I),
            PriceUnit.TOKEN,
            Decimal(1000),
        ),
        (re.compile(r"\btokens?\b", re.I), PriceUnit.TOKEN, Decimal(1)),
        (
            re.compile(r"(?:1M|million|百万)\s*(?:requests|calls|次)|百万次", re.I),
            PriceUnit.REQUEST,
            Decimal(1_000_000),
        ),
        (
            re.compile(r"(?:10,000|10k|10 ?thousand)\s*(?:requests|calls)|万次", re.I),
            PriceUnit.REQUEST,
            Decimal(10_000),
        ),
    )
    ZERO_WIDTH: ClassVar[re.Pattern[str]] = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
    TABLE_CONTEXT: ClassVar[str] = "preceding::text()[normalize-space()][position() <= 2]"
    BARE_NUMBER: ClassVar[re.Pattern[str]] = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?")
    CONTEXT_CURRENCIES: ClassVar[Tuple[Tuple[re.Pattern[str], str], ...]] = (
        (re.compile(r"元|人民币|\bCNY\b|\bRMB\b"), "CNY"),
        (re.compile(r"美元|\bUSD\b|US\$", re.I), "USD"),
        (re.compile(r"€|\bEUR\b|\beuros?\b", re.I), "EUR"),
        (re.compile(r"₽|\bRUB\b|\u0440\u0443\u0431", re.I), "RUB"),
        (re.compile(r"£|\bGBP\b", re.I), "GBP"),
    )
    SIZE_WORD: ClassVar[re.Pattern[str]] = re.compile(r"\bper (?:1 ?)?GB\b|/\s*(?:1 ?)?GB\b|\bGB/|за ГБ|/GiB", re.I)

    name: str = "default-crawler"
    catalogue_url: ClassVar[str] = ""
    complement_urls: ClassVar[Tuple[str, ...]] = ()
    dates_sitemaps: ClassVar[Tuple[str, ...]] = ()
    name_prefixes: ClassVar[Tuple[str, ...]] = ()
    robots_txt_obey: bool = True
    solve_cloudflare: ClassVar[bool] = False
    lazy_browser: ClassVar[bool] = False
    fetch_retries: ClassVar[int] = 3
    retry_delay: ClassVar[float] = 1.0
    dates_launches: ClassVar[bool] = False
    launch_feed_start: ClassVar[Optional[datetime]] = None
    concurrent_requests: int = 1
    download_delay: float = 1.0

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        urls = [url for url in (self.catalogue_url, *self.complement_urls) if url]
        self.allowed_domains = {urlparse(url).netloc for url in urls}
        self.seen_products: Set[str] = set()
        self.seen_urls: Set[str] = set()
        self.page_dates: Dict[str, str] = {}
        self.curated: Dict[str, CuratedLaunch] = {}
        self.launch_aliases: Dict[str, str] = {}
        self.use_launches(self._bundled_launches())
        self.undated: Set[str] = set()
        self.prices_mode = False
        self.price_provider = CloudProvider.AWS
        self.price_sources: Dict[str, PriceSource] = {}
        self.price_reads: Dict[str, PriceSource] = {}
        self.price_failures: Set[str] = set()
        self.price_count = 0
        self.price_stream_lock = asyncio.Lock()
        self.logger.debug(
            "%s crawler ready: catalogue %s, allowed domains %s.", self.name, self.catalogue_url, self.allowed_domains
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _bundled_launches(self) -> LaunchCatalog:
        """Read the curated launches of the bundle (`data/curated/launches.json`), the default of a crawler.

        Returns:
            LaunchCatalog: The launch dates catalogue.

        Raises:
            LaunchCatalogError: If the bundle cannot be read or is invalid.
        """
        try:
            return BundleCatalogs(logger=self.logger).launches()
        except CuratedError as e:
            self.logger.error("The curated launches of the bundle cannot be read: %s", e)
            raise LaunchCatalogError("data/curated/launches.json", str(e)) from e

    def _use_application_logging(self) -> None:
        """Hand the spider logger over to the application logging configuration.

        Notes:
            Scrapling isolates the spider logger with its own console handler:
            it is removed (the log counter used by the
            crawl stats, and the log file if any, are kept)
            and the records are propagated to the application handlers.
        """
        for handler in list(self.logger.handlers):
            if type(handler) is logging.StreamHandler:
                self.logger.removeHandler(handler)
        self.logger.propagate = True

    def _clean_text(self, text: Optional[str]) -> str:
        """Collapse the whitespaces (including non-breaking spaces) of a scraped text, zero-width marks removed.

        Args:
            text (Optional[str]): The scraped text.

        Returns:
            str: The text with single spaces, empty when missing.
        """
        return " ".join(self.ZERO_WIDTH.sub("", text or "").split())

    def _as_object(self, value: JsonValue) -> Dict[str, JsonValue]:
        """Read a JSON value expected to be an object.

        Args:
            value (JsonValue): The JSON value.

        Returns:
            Dict[str, JsonValue]: The object, empty when the value is not an object.
        """
        return value if isinstance(value, dict) else {}

    def _as_text(self, value: JsonValue) -> Optional[str]:
        """Read a JSON value expected to be a string.

        Args:
            value (JsonValue): The JSON value.

        Returns:
            Optional[str]: The string, `None` when the value is not a string.
        """
        return value if isinstance(value, str) else None

    def _walk_objects(self, value: JsonValue) -> Iterator[Dict[str, JsonValue]]:
        """Walk every JSON object of a JSON document, depth first.

        Args:
            value (JsonValue): The JSON document.

        Yields:
            Dict[str, JsonValue]: Each object, parents before their children.
        """
        children: List[JsonValue] = []
        if isinstance(value, dict):
            yield value
            children = list(value.values())
        elif isinstance(value, list):
            children = value
        for child in children:
            yield from self._walk_objects(child)

    def _name_key(self, name: str) -> str:
        """Normalize a product name to compare it: brand prefix, parenthesized notes and punctuation are ignored.

        Args:
            name (str): The product name.

        Returns:
            str: The comparison key, e.g. `apprunner` for `AWS App Runner`, `云服务器bcc` for `云服务器 BCC`.
        """
        text = re.sub(r"[(\uff08][^)\uff09]*[)\uff09]", " ", self._clean_text(name).casefold())
        for prefix in sorted(self.name_prefixes, key=len, reverse=True):
            if text.startswith(prefix.casefold()):
                text = text[len(prefix) :]
                break
        return re.sub(r"[\W_]+", "", text) or self._clean_text(name).casefold()

    def _url_key(self, url: str) -> str:
        """Normalize a product URL to compare it: scheme, `www.`, query, fragment and trailing slash are ignored.

        Args:
            url (str): The absolute product URL.

        Returns:
            str: The comparison key, e.g. `azure.microsoft.com/en-us/products/functions`.
        """
        link = urlparse(url.casefold())
        return f"{link.netloc.removeprefix('www.')}{link.path.rstrip('/')}"

    def _remember(self, names: Iterable[str]) -> None:
        """Mark product names (e.g. the former names of a product) as already streamed.

        Args:
            names (Iterable[str]): The product names.
        """
        self.seen_products.update(self._name_key(name) for name in names if self._clean_text(name))

    def _seen(self, product: CloudProduct) -> bool:
        """Tell whether a product was already streamed, without marking it.

        Args:
            product (CloudProduct): The product.

        Returns:
            bool: Whether its normalized name or its normalized URL was seen before.
        """
        url_key = self._url_key(product.url) if product.url else None
        return self._name_key(product.name) in self.seen_products or (url_key is not None and url_key in self.seen_urls)

    def _is_new(self, product: CloudProduct) -> bool:
        """Tell whether a product was not streamed yet, and mark it as streamed.

        Args:
            product (CloudProduct): The product.

        Returns:
            bool: Whether neither its normalized name nor its normalized URL was seen before.
        """
        if self._seen(product):
            return False
        name_key = self._name_key(product.name)
        url_key = self._url_key(product.url) if product.url else None
        self.seen_products.add(name_key)
        if url_key is not None:
            self.seen_urls.add(url_key)
        return True

    def _browser_session_id(self) -> str:
        """Get the identifier of the stealth browser session.

        Returns:
            str: The session identifier, e.g. `aws-session`.
        """
        return f"{self.name}-session"

    def _price_session_id(self) -> str:
        """Get the identifier of the HTTP session of the price sources.

        Returns:
            str: The session identifier, e.g. `aws-prices`.
        """
        return f"{self.name}-prices"

    def _rendered_session_id(self) -> str:
        """Get the identifier of the plain headless browser session rendering the product pages (`PRODUCT_PAGE_JS`).

        Returns:
            str: The session identifier, e.g. `arsys-prices-js`.
        """
        return f"{self.name}-prices-js"

    def _catalogue_request(self) -> Request:
        """Build the request of the main catalogue page, crawled first (primary priority).

        Returns:
            Request: The request, with the default session options.
        """
        return Request(self.catalogue_url, priority=self.PRIMARY_PRIORITY)

    def _complement_request(self, url: str) -> Request:
        """Build the request of a complementary catalogue page, after the main listing (lower priority).

        Args:
            url (str): The complementary catalogue page.

        Returns:
            Request: The request, with the default session options.
        """
        return Request(url)

    async def _catalogue_requests(self) -> AsyncGenerator[Request]:
        """Request the catalogue: the dates sitemaps, the main catalogue page, then the complementary pages.

        Yields:
            AsyncGenerator[Request]: The `dates_sitemaps` requests (first), the main catalogue page request, then the
                complementary pages ones (lower priority, a sitemap already read for its dates is requested again, not
                filtered out as a duplicate).
        """
        for url in self.dates_sitemaps:
            self.logger.debug("Requesting the %s sitemap %s for the dates of the product pages.", self.name, url)
            yield Request(url, priority=self.DATES_PRIORITY, dont_filter=True, meta={self.PAGE_DATES: url})
        self.logger.debug("Requesting the %s catalogue page %s.", self.name, self.catalogue_url)
        yield self._catalogue_request()
        for url in self.complement_urls:
            self.logger.debug("Requesting the %s complementary catalogue page %s.", self.name, url)
            request = self._complement_request(url)
            if url in self.dates_sitemaps:
                request.dont_filter = True
            yield request

    def _price_item(self, fact: Union[ServicePrice, FreeTier]) -> PriceItem:
        """Write a price or a free offer as a streamed item, with its kind.

        Args:
            fact (Union[ServicePrice, FreeTier]): The price or the free offer, validated.

        Returns:
            PriceItem: Its kind under `fact`, and the validated model itself under `model` (the stream is in the
                process: the collector uses the model as it is, never validating it twice).
        """
        kind = PriceFactKind.PRICE if isinstance(fact, ServicePrice) else PriceFactKind.FREE_TIER
        return {self.PRICE_KIND_KEY: kind.value, self.PRICE_MODEL_KEY: fact}

    def _price_fact(self, fields: PriceFields) -> Optional[ServicePrice]:
        """Validate a price read from a price source, the provider of the crawl filled in.

        Args:
            fields (PriceFields): The raw fields of the price, the provider left out.

        Returns:
            Optional[ServicePrice]: The price, `None` when a field is malformed (logged, the price skipped).
        """
        try:
            return ServicePrice.model_validate({"provider": self.price_provider, **fields})
        except ValidationError as e:
            self.logger.warning(
                "The %s price %s is skipped: %s", self.name, fields.get("sku_key"), e.errors()[0]["msg"]
            )
            return None

    def _free_fact(self, fields: PriceFields) -> Optional[FreeTier]:
        """Validate a free offer read from a price source, the provider of the crawl filled in.

        Args:
            fields (PriceFields): The raw fields of the offer, the provider left out.

        Returns:
            Optional[FreeTier]: The offer, `None` when a field is malformed (logged, the offer skipped).
        """
        try:
            return FreeTier.model_validate({"provider": self.price_provider, **fields})
        except ValidationError as e:
            self.logger.warning(
                "The %s free offer %s is skipped: %s", self.name, fields.get("free_key"), e.errors()[0]["msg"]
            )
            return None

    def _record_price_source(
        self,
        url: str,
        rows: int,
        version: Optional[str] = None,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        status: PriceSourceStatus = PriceSourceStatus.FETCHED,
    ) -> None:
        """Record what a price source stated of its version, once read (the next crawl compares it).

        Args:
            url (str): The source, the `source_url` of its prices.
            rows (int): The prices it gave.
            version (Optional[str]): The version it states, if any.
            etag (Optional[str]): Its `ETag`, if any.
            last_modified (Optional[str]): Its `Last-Modified`, if any.
            status (PriceSourceStatus): The outcome of the read.
        """
        try:
            self.price_reads[url] = PriceSource(
                provider=self.price_provider,
                source_key=url,
                version=version,
                etag=etag,
                last_modified=last_modified,
                rows=rows,
                status=status,
            )
        except ValidationError as e:
            self.logger.error("The %s price source %s cannot be recorded: %s", self.name, url, e.errors()[0]["msg"])
            return
        self.logger.debug("%s price source %s recorded: %s, %d prices.", self.name, url, status.value, rows)

    def _unpriced_facts(self, url: str) -> Iterator[ServicePrice]:
        """State each live catalogue product of a provider publishing no price as unpriced.

        Args:
            url (str): The page read as the evidence (the source of the facts).

        Yields:
            Iterator[ServicePrice]: One fact per product, priced on request or not published (`UNPRICED_MODEL`), with
                the reason (`UNPRICED_REASON`).
        """
        if not self.price_products:
            self.logger.warning("The %s crawler knows no catalogue product to state unpriced.", self.name)
        for name in self.price_products:
            fact = self._price_fact(
                {
                    "sku_key": f"unpriced/{name}",
                    "service": name,
                    "region": "global",
                    "unit": PriceUnit.OTHER,
                    "unit_raw": self.UNPRICED_MODEL.value,
                    "model": self.UNPRICED_MODEL,
                    "term": PriceTerm.NONE,
                    "reason": self.UNPRICED_REASON,
                    "source_url": url,
                    "source_kind": PriceSourceKind.PAGE,
                }
            )
            if fact is not None:
                yield fact
        self.logger.info(
            "%d %s products stated unpriced (%s).", len(self.price_products), self.name, self.UNPRICED_MODEL.value
        )

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Extract the prices, the free offers and the follow-up requests of a price source (a provider's hook).

        Args:
            response (Response): The price source.

        Yields:
            AsyncGenerator[PriceFact]: The prices and free offers it states, and the requests of the sources it leads
                to. For a provider publishing no price (`UNPRICED_REASON`), its evidence page states each catalogue
                product unpriced.
        """
        if self.UNPRICED_REASON is not None and response.meta.get(self.UNPRICED_META):
            facts = list(self._unpriced_facts(str(response.url)))
            for fact in facts:
                yield fact
            self._record_price_source(str(response.url), len(facts))
            return
        self.logger.warning("The %s crawler does not read its price source %s yet.", self.name, response.url)

    async def _price_fallback(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Answer a price source that failed, when the provider knows another way (a provider's hook).

        Args:
            response (Response): The failed price source (HTTP 400 or more).

        Yields:
            AsyncGenerator[PriceFact]: The requests of the sources to read instead, or the facts stating the source has
                no price. Nothing (the default) when the failure stands.
        """
        self.logger.debug("The %s crawler has no fallback for %s.", self.name, response.url)
        facts: List[PriceFact] = []
        for fact in facts:
            yield fact

    def _span(self, cell: Selector, attribute: str) -> int:
        """Read the span of a table cell (`rowspan` or `colspan`).

        Args:
            cell (Selector): The cell.
            attribute (str): The span attribute, either case.

        Returns:
            int: The span, 1 when missing or malformed, 0 for a placeholder cell (`colspan="0"`).
        """
        raw = cell.attrib.get(attribute) or cell.attrib.get(attribute.casefold()) or "1"
        return int(raw) if raw.strip().isdigit() else 1

    def _table_rows(self, table: Selector) -> List[List[str]]:
        """Read the rows of a table as cell texts, the spanned cells repeated on every row and column they cover.

        Args:
            table (Selector): The table.

        Returns:
            List[List[str]]: Its rows, the empty ones left out, the placeholder cells (`colspan="0"`) skipped.
        """
        rows: List[List[str]] = []
        carried: Dict[int, Tuple[str, int]] = {}
        for row in table.css("tr"):
            cells: List[str] = []
            for cell in row.css("th, td"):
                while len(cells) in carried:
                    cells.append(carried[len(cells)][0])
                width = self._span(cell, "colSpan")
                if width == 0:
                    continue
                height = self._span(cell, "rowSpan") or 1
                text = self._clean_text(cell.get_all_text(separator=" ", strip=True))
                for _ in range(width):
                    if height > 1:
                        carried[len(cells)] = (text, height)
                    cells.append(text)
            while len(cells) in carried:
                cells.append(carried[len(cells)][0])
            carried = {column: (text, left - 1) for column, (text, left) in carried.items() if left > 1}
            if any(cells):
                rows.append(cells)
        return rows

    def _price_tables(self, response: Response, selector: str = "table") -> List[Tuple[str, List[List[str]]]]:
        """Read the tables of a pricing page as rows of cell texts, each under its heading.

        Args:
            response (Response): The pricing page.
            selector (str): The CSS selector of its price tables.

        Returns:
            List[Tuple[str, List[List[str]]]]: The text of the nearest heading before each table (empty when none),
                and its rows, header rows included, of the texts of their cells (spaces collapsed, spanned cells
                repeated).
        """
        tables: List[Tuple[str, List[List[str]]]] = []
        for table in response.css(selector):
            heading = table.xpath(self.TABLE_HEADING).first
            title = self._clean_text(heading.get_all_text(separator=" ", strip=True)) if heading is not None else ""
            tables.append((title, self._table_rows(table)))
        self.logger.debug("%d price tables read from the %s page %s.", len(tables), self.name, response.url)
        return tables

    def _money(self, text: str) -> Optional[Tuple[Decimal, str]]:
        """Read the first amount of money written in a text, with its currency.

        Args:
            text (str): The text, e.g. `€ 1,234.50`, `1 297,50 ₽` or `19.99 € + VAT`.

        Returns:
            Optional[Tuple[Decimal, str]]: The amount and its ISO currency, `None` without amount.
        """
        match = self.MONEY.search(text)
        if match is None:
            return None
        sign = match.group("before") or match.group("after") or ""
        digits = re.sub(r"[\s\u00a0\u202f']", "", match.group("first") or match.group("second") or "")
        if "," in digits and "." in digits:
            decimal = "," if digits.rfind(",") > digits.rfind(".") else "."
            digits = digits.replace("." if decimal == "," else ",", "").replace(",", ".")
        elif "," in digits:
            digits = digits.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", digits) else digits.replace(",", ".")
        elif digits.count(".") > 1:
            digits = digits.replace(".", "")
        try:
            return Decimal(digits), self.CURRENCY_SIGNS[sign.casefold().rstrip(".")]
        except ArithmeticError, KeyError:
            self.logger.debug("The amount %r of %r is unreadable.", digits, text)
            return None

    def _page_unit(self, *texts: str) -> Tuple[PriceUnit, Decimal, str]:
        """Find the unit of a price from the texts around it (its cell, its column header, its row label).

        Args:
            *texts (str): The texts, the closest first.

        Returns:
            Tuple[PriceUnit, Decimal, str]: The unit, the normalized units in one (e.g. a million for a price per
                million tokens), and the words that gave it (`other` when none did).
        """
        for text in texts:
            for pattern, unit, factor in self.COUNT_WORDS:
                found = pattern.search(text)
                if found is not None:
                    return unit, factor, found.group(0)
            sized = bool(self.SIZE_WORD.search(text))
            for pattern, unit, sized_unit in self.PERIOD_WORDS:
                found = pattern.search(text)
                if found is not None:
                    return (sized_unit if sized else unit), Decimal(1), found.group(0)
            if sized:
                return PriceUnit.GIB, Decimal(1), self.SIZE_WORD.pattern
        return PriceUnit.OTHER, Decimal(1), PriceUnit.OTHER.value

    def _table_contexts(self, response: Response, selector: str = "table") -> List[str]:
        """Read the short texts just before each table of a page (often its unit and currency).

        Args:
            response (Response): The page.
            selector (str): The CSS selector of its tables.

        Returns:
            List[str]: The context of each table, in the order of `_price_tables`.
        """
        contexts: List[str] = []
        for table in response.css(selector):
            texts = [self._clean_text(str(text)) for text in table.xpath(self.TABLE_CONTEXT)]
            contexts.append(" ".join(reversed([text for text in texts if text]))[:300])
        return contexts

    def _context_currency(self, *texts: str) -> Optional[str]:
        """Find the currency a table states around it, for its cells written as bare numbers.

        Args:
            *texts (str): The texts around the table (its heading, context, column header).

        Returns:
            Optional[str]: The ISO currency, `None` when none is stated.
        """
        for text in texts:
            for pattern, currency in self.CONTEXT_CURRENCIES:
                if pattern.search(text):
                    return currency
        return None

    def _cell_money(self, cell: str, currency: Optional[str]) -> Optional[Tuple[Decimal, str]]:
        """Read the amount of a table cell: written with its currency, or a bare number in a table stating it.

        Args:
            cell (str): The cell.
            currency (Optional[str]): The currency the table states, if any.

        Returns:
            Optional[Tuple[Decimal, str]]: The amount and its currency, `None` when the cell holds none.
        """
        money = self._money(cell)
        if money is not None or currency is None or not self.BARE_NUMBER.fullmatch(cell):
            return money
        return Decimal(cell.replace(",", "")), currency

    def _product_page_prices(self, response: Response) -> Iterator[ServicePrice]:
        """Read the price tables of a catalogue product page: one price per cell holding an amount.

        Args:
            response (Response): The product page.

        Yields:
            ServicePrice: The prices of its tables, named after the product, their unit found in the cell, its
                column header, its row label or the text around the table.

        Notes:
            The rows before the first priced one are the header rows, joined per column (a matrix of regions by
            types has two). A cell written as a bare number is an amount when the table states its currency
            (e.g. a unit in yuan per GiB and month written before it).
        """
        product = str(response.meta.get(self.PRODUCT_PAGE_META) or "")
        url = str(response.url).split("#")[0]
        path = urlparse(url).path.strip("/") or urlparse(url).netloc
        contexts = self._table_contexts(response)
        seen: Dict[str, int] = {}
        for number, (heading, rows) in enumerate(self._price_tables(response)):
            context = contexts[number] if number < len(contexts) else ""
            currency = self._context_currency(context, heading, *(rows[0] if rows else []))
            priced = [any(self._cell_money(cell, currency) for cell in row[1:]) for row in rows]
            first = priced.index(True) if True in priced else len(rows)
            width = max((len(row) for row in rows), default=0)
            header = [
                " ".join(row[index] for row in rows[:first] if index < len(row) and row[index]).strip()
                for index in range(width)
            ]
            for row in rows[first:]:
                label = next((cell for cell in row if cell and self._cell_money(cell, currency) is None), "")
                for index, cell in enumerate(row):
                    money = self._cell_money(cell, currency)
                    if money is None:
                        continue
                    column = header[index] if index < len(header) else ""
                    unit, factor, written = self._page_unit(cell, column, label, f"{heading} {context}")
                    key = f"page/{path}/{number}/{label}/{column or index}"[:900]
                    count = seen.get(key, 0)
                    seen[key] = count + 1
                    fact = self._price_fact(
                        {
                            "sku_key": key if not count else f"{key}#{count}",
                            "service": product,
                            "family": heading[:120] or None,
                            "region": "global",
                            "attributes": {
                                "table": heading[:200],
                                "context": context[:200],
                                "row": label[:200],
                                "column": column[:200],
                            },
                            "unit": unit,
                            "unit_raw": f"{cell} ({written})"[:200],
                            "unit_factor": factor,
                            "price": money[0],
                            "currency": money[1],
                            "model": PriceModel.FREE if money[0] == 0 else PriceModel.ON_DEMAND,
                            "term": PriceTerm.NONE,
                            "source_url": url,
                            "source_kind": PriceSourceKind.PAGE,
                        }
                    )
                    if fact is not None:
                        yield fact

    def _page_text_prices(self, response: Response) -> Iterator[ServicePrice]:
        """Read the prices written in the text of a product page without price table (cards, lists).

        Args:
            response (Response): The product page.

        Yields:
            ServicePrice: One price per text line holding an amount (a starting price when written `from`),
                labelled by the nearest line before it without amount, its unit found in the line, the next line or
                that label.

        Notes:
            An amount without unit or period written around it is prose (e.g. a cost quoted in a sentence), not
            a price: it is skipped. The page title is read first, as some pages state their starting price only
            there (e.g. `VPS Lite from € 2,70 / month`).
        """
        body = response.css("body").first
        if body is None:
            return
        product = str(response.meta.get(self.PRODUCT_PAGE_META) or "")
        url = str(response.url).split("#")[0]
        path = urlparse(url).path.strip("/") or urlparse(url).netloc
        lines = [
            line
            for line in (
                self._clean_text(text)
                for text in [
                    *(str(title) for title in response.css("title::text")),
                    *body.get_all_text(separator="\n", strip=True).split("\n"),
                ]
            )
            if 0 < len(line) <= self.TEXT_LINE_LIMIT and "{" not in line
        ]
        label = ""
        seen: Dict[str, int] = {}
        for index, line in enumerate(lines):
            money = self._money(line)
            if money is None:
                label = line
                continue
            after = lines[index + 1] if index + 1 < len(lines) else ""
            unit, factor, written = self._page_unit(line, after, label)
            if unit is PriceUnit.OTHER:
                self.logger.debug("Amount without unit or period skipped on %s: %r.", url, line)
                continue
            key = f"text/{path}/{label}"[:900]
            count = seen.get(key, 0)
            seen[key] = count + 1
            fact = self._price_fact(
                {
                    "sku_key": key if not count else f"{key}#{count}",
                    "service": product,
                    "region": "global",
                    "attributes": {"label": label[:200], "text": line, "starting": bool(self.STARTING.search(line))},
                    "unit": unit,
                    "unit_raw": f"{line} ({written})"[:200],
                    "unit_factor": factor,
                    "price": money[0],
                    "currency": money[1],
                    "model": PriceModel.FREE if money[0] == 0 else PriceModel.ON_DEMAND,
                    "term": PriceTerm.NONE,
                    "source_url": url,
                    "source_kind": PriceSourceKind.PAGE,
                }
            )
            if fact is not None:
                yield fact

    def _price_request(
        self,
        url: str,
        meta: Optional[Dict[str, JsonValue]] = None,
        body: Optional[Dict[str, JsonValue]] = None,
        headers: Optional[Dict[str, str]] = None,
        rendered: bool = False,
    ) -> Request:
        """Build the request of a price source, parsed by `_parse_prices`.

        Args:
            url (str): The price source.
            meta (Optional[Dict[str, JsonValue]]): The request meta, given back with the response.
            body (Optional[Dict[str, JsonValue]]): The JSON body of a price API answering POST requests only.
            headers (Optional[Dict[str, str]]): The headers of the request, beyond those of the price session.
            rendered (bool): Whether the page is rendered by the headless browser session (`PRODUCT_PAGE_JS`).

        Returns:
            Request: The request (a POST of its JSON body when it has one), never filtered as a duplicate.
        """
        if body is None and not headers:
            self.logger.debug("Requesting the %s price source %s%s.", self.name, url, " (rendered)" if rendered else "")
            return Request(
                url,
                sid=self._rendered_session_id() if rendered else self._price_session_id(),
                callback=self._parse_prices,
                priority=self.PRIMARY_PRIORITY,
                meta=meta or {},
                dont_filter=True,
            )
        method = self.POST_METHOD if body is not None else self.GET_METHOD
        self.logger.debug("Requesting the %s price source %s (%s).", self.name, url, method)
        return Request(
            url,
            sid=self._price_session_id(),
            callback=self._parse_prices,
            priority=self.PRIMARY_PRIORITY,
            meta=meta or {},
            dont_filter=True,
            method=method,
            json=body,
            headers=dict(headers or {}),
        )

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the price sources of the provider (a provider's hook).

        Yields:
            AsyncGenerator[Request]: The requests of its price sources, built by `_price_request`, or the request of the
                evidence page of a provider publishing no price (`UNPRICED_REASON`).
        """
        if self.UNPRICED_REASON is not None:
            url = self.UNPRICED_URL or self.catalogue_url
            self.logger.info("The %s provider publishes no price: %s is read as the evidence.", self.name, url)
            yield self._price_request(url, {self.UNPRICED_META: True})
            return
        self.logger.warning("The %s crawler has no price source yet.", self.name)

    async def _stream_lines(self, url: str) -> AsyncGenerator[str]:
        """Stream the lines of a large price file, never holding it whole (a price list of hundreds of MB).

        Args:
            url (str): The price file.

        Yields:
            str: Each line, as it is downloaded.

        Raises:
            PriceDownloadError: If the file cannot be downloaded (an HTTP error, a broken connection).

        Notes:
            It is read outside the crawl engine (which holds whole bodies), so it waits the delay between requests
            first itself. The timeout applies to each read, not to the whole download.
        """
        lines = 0
        timeout = httpx.Timeout(self.PRICE_TIMEOUT_S, connect=self.PRICE_CONNECT_TIMEOUT_S)
        try:
            async with (
                self.price_stream_lock,
                httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client,
            ):
                await asyncio.sleep(self.download_delay)
                self.logger.info("Streaming the %s price file %s.", self.name, url)
                async with client.stream("GET", url) as response:
                    if response.status_code >= 400:
                        self.logger.error(
                            "The %s price file %s answered HTTP %d.", self.name, url, response.status_code
                        )
                        raise PriceDownloadError(self.name, url, f"HTTP {response.status_code}")
                    async for line in response.aiter_lines():
                        lines += 1
                        yield line
        except httpx.HTTPError as e:
            self.logger.error("The %s price file %s broke after %d lines: %s", self.name, url, lines, e)
            raise PriceDownloadError(self.name, url, str(e)) from e
        if not lines:
            self.logger.warning("The %s price file %s is empty.", self.name, url)
        self.logger.info("%d lines streamed from the %s price file %s.", lines, self.name, url)

    def _product_page_requests(self) -> Iterator[Request]:
        """Request the live catalogue product pages (`PRODUCT_PAGE_PRICES`) and the curated price pages.

        Yields:
            Request: One request per product page, once per page.
        """
        pages: Dict[str, str] = {}
        for name, url in self.price_products.items() if self.PRODUCT_PAGE_PRICES else ():
            if url and url.startswith(("http://", "https://")):
                pages.setdefault(url.split("#")[0], name)
        curated: Set[str] = set()
        for name, urls in self.price_pages.items():
            for url in urls:
                curated.add(url.split("#")[0])
                pages.setdefault(url.split("#")[0], name)
        self.logger.info(
            "%d %s product pages to read for their price tables (%d curated).", len(pages), self.name, len(curated)
        )
        for url, name in pages.items():
            meta: Dict[str, JsonValue] = {self.PRODUCT_PAGE_META: name, self.CURATED_PAGE_META: url in curated}
            yield self._price_request(url, meta, rendered=self.PRODUCT_PAGE_JS)

    async def _parse_prices(self, response: Response) -> AsyncGenerator[Union[PriceItem, Request]]:
        """Stream the prices and free offers of a price source, then the requests it leads to.

        Args:
            response (Response): The price source.

        Yields:
            AsyncGenerator[Union[PriceItem, Request]]: Each price and free offer, as an item naming its kind, and each
                follow-up request.

        Notes:
            A source answered with an error (HTTP 400 or more) is handed to `_price_fallback`: it fails (its
            prices are then kept as they are) unless the provider answers it otherwise.
        """
        found = 0
        if response.status >= 400:
            handled = False
            async for fact in self._price_fallback(response):
                handled = True
                if isinstance(fact, Request):
                    yield fact
                else:
                    found += 1
                    yield self._price_item(fact)
            self.price_count += found
            if handled:
                self.logger.info(
                    "The %s price source %s is missing (HTTP %s): answered otherwise (%d prices).",
                    self.name,
                    response.url,
                    response.status,
                    found,
                )
                return
            self.logger.error("The %s price source %s failed (HTTP %s).", self.name, response.url, response.status)
            self.price_failures.add(response.url)
            return
        if response.meta.get(self.PRODUCT_PAGE_META):
            facts = list(self._product_page_prices(response))
            if not facts and (self.PAGE_TEXT_PRICES or response.meta.get(self.CURATED_PAGE_META)):
                facts = list(self._page_text_prices(response))
            for fact in facts:
                yield self._price_item(fact)
            self.price_count += len(facts)
            self._record_price_source(str(response.url).split("#")[0], len(facts))
            self.logger.info("%s product page %s read: %d prices.", self.name, response.url, len(facts))
            return
        try:
            async for fact in self._extract_prices(response):
                if isinstance(fact, Request):
                    yield fact
                    continue
                found += 1
                yield self._price_item(fact)
        except CrawlerError as e:
            self.logger.error("The %s price source %s is malformed: %s", self.name, response.url, e)
            self.price_failures.add(response.url)
        self.price_count += found
        if not found:
            self.logger.debug(
                "The %s price source %s gave no price (a source may only lead to others).", self.name, response.url
            )
        self.logger.info("%s price source %s read: %d prices.", self.name, response.url, found)

    def _price_unchanged(
        self, url: str, version: Optional[str] = None, etag: Optional[str] = None, last_modified: Optional[str] = None
    ) -> bool:
        """Tell whether a price source is unchanged since its last read (then recorded as such, not read again).

        Args:
            url (str): The source.
            version (Optional[str]): The version it states now, if any.
            etag (Optional[str]): Its `ETag` now, if any.
            last_modified (Optional[str]): Its `Last-Modified` now, if any.

        Returns:
            bool: Whether a stated version, `ETag` or `Last-Modified` equals that of the last successful read.
        """
        known = self.price_sources.get(url)
        if known is None or known.status is PriceSourceStatus.FAILED:
            self.logger.debug("The %s price source %s was never read whole: it is read.", self.name, url)
            return False
        same = any(
            now is not None and now == before
            for now, before in ((version, known.version), (etag, known.etag), (last_modified, known.last_modified))
        )
        if same:
            self._record_price_source(url, known.rows, version, etag, last_modified, PriceSourceStatus.UNCHANGED)
            self.logger.info("The %s price source %s is unchanged: not read again.", self.name, url)
        return same

    def _stream(self, product: CloudProduct) -> Optional[Dict[str, JsonValue]]:
        """Get the item of a product not streamed yet, and log it.

        Args:
            product (CloudProduct): The extracted product.

        Returns:
            Optional[Dict[str, JsonValue]]: The product as a dictionary, `None` when it was already streamed.
        """
        if not self._is_new(product):
            self.logger.debug("Skipping the duplicated product %r.", product.name)
            return None
        self.logger.info("Product extracted from %s: %s - %s", self.name, product.name, product.description)
        return product.item_dump()

    def _shorten(self, text: str) -> str:
        """Shorten a text over the description limit: at its last sentence end, else at a word, with an ellipsis.

        Args:
            text (str): The text, whitespaces collapsed.

        Returns:
            str: The text, unchanged when it is within the limit.
        """
        if len(text) <= self.DESCRIPTION_LIMIT:
            return text
        head = text[: self.DESCRIPTION_LIMIT]
        ends = [match.end() for match in re.finditer(r"[.!?](?=\s|$)|[\u3002\uff01\uff1f]", head)]
        if ends and ends[-1] >= self.DESCRIPTION_LIMIT // 2:
            shortened = head[: ends[-1]]
        else:
            shortened = head[: self.DESCRIPTION_LIMIT - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "\u2026"
        self.logger.debug("Description shortened from %d to %d characters.", len(text), len(shortened))
        return shortened

    def _valid_url(self, url: Optional[str], name: Optional[str]) -> Optional[str]:
        """Get a scraped page URL, if it is an absolute http(s) link.

        Args:
            url (Optional[str]): The scraped URL.
            name (Optional[str]): The name of the catalogue entry, for the logs.

        Returns:
            Optional[str]: The trimmed URL, `None` (logged) when it is missing or invalid.
        """
        if not url or not url.strip():
            return None
        link = urlparse(url.strip())
        if link.scheme not in tuple(UrlScheme) or not link.netloc:
            self.logger.debug("Ignoring the invalid URL %r of the catalogue entry %r.", url, name)
            return None
        return url.strip()

    def _parse_date(self, value: JsonValue, name: Optional[str] = None) -> Optional[datetime]:
        """Parse a date published by a website, leniently: an unreadable date is dropped, not its item.

        Args:
            value (JsonValue): The raw date: an ISO 8601 text, or a Unix timestamp in seconds or milliseconds.
            name (Optional[str]): The item the date belongs to, for the logs.

        Returns:
            Optional[datetime]: The timezone-aware date, `None` when missing, unreadable or implausible (before 1990
                or in the future, logged).
        """
        try:
            date = DatedItem.model_validate({"added_at": value}).added_at
        except ValidationError:
            self.logger.debug("Ignoring the unreadable date %r of the entry %r.", value, name)
            return None
        if date is not None and not self.EARLIEST_DATE <= date <= datetime.now(UTC) + timedelta(days=1):
            self.logger.debug("Ignoring the implausible date %s of the entry %r.", date.isoformat(), name)
            return None
        return date

    def _build_product(
        self,
        name: Optional[str],
        description: Optional[str],
        url: Optional[str] = None,
        added_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        added_caveat: Optional[DateCaveat] = None,
        updated_caveat: Optional[DateCaveat] = None,
        categories: Optional[Sequence[Optional[str]]] = None,
    ) -> Optional[CloudProduct]:
        """Build a product from scraped texts, with collapsed whitespaces and a description within the limit.

        Args:
            name (Optional[str]): The scraped product name.
            description (Optional[str]): The scraped product description.
            url (Optional[str]): The product page, dropped (not the product) when it is not an absolute http(s) link.
            added_at (Optional[datetime]): When the website says the product was added, if it does.
            updated_at (Optional[datetime]): When the website says the product was last updated, if it does. Else,
                the last modification of its page given by a `dates_sitemaps` sitemap, if any.
            added_caveat (Optional[DateCaveat]): Why `added_at` may not be the launch, if it may not.
            updated_caveat (Optional[DateCaveat]): Why `updated_at` may not be a change of the product, if it may not.
            categories (Optional[Sequence[Optional[str]]]): The categories the catalogue files the product under, as
                labelled there (blank ones dropped), `None` when it gives none.

        Returns:
            Optional[CloudProduct]: The product, or `None` (logged) when the scraped texts are invalid.
        """
        url = self._valid_url(url, name)
        if updated_at is None and url and self._url_key(url) in self.page_dates:
            updated_at = self._parse_date(self.page_dates[self._url_key(url)], name)
            updated_caveat = DateCaveat.PAGE_MODIFIED
        try:
            return CloudProduct.model_validate(
                {
                    "name": self._clean_text(name),
                    "description": self._shorten(self._clean_text(description)),
                    "url": url,
                    "catalogue_categories": [self._clean_text(category) for category in categories or []],
                    "added_at": added_at,
                    "added_caveat": added_caveat if added_at else None,
                    "updated_at": updated_at,
                    "updated_caveat": updated_caveat if updated_at else None,
                }
            )
        except ValidationError as e:
            reasons = "; ".join(f"{'.'.join(map(str, error['loc']))}: {error['msg']}" for error in e.errors())
            self.logger.warning("Skipping the invalid catalogue entry %r (%s).", name, reasons)
            return None

    def _merge_categories(self, products: Iterable[CloudProduct]) -> List[CloudProduct]:
        """Merge the occurrences of the same product (same normalized name or URL) of a listing.

        Args:
            products (Iterable[CloudProduct]): The products of the listing, an occurrence per category.

        Returns:
            List[CloudProduct]: Each product once, as first listed, with the categories of all its occurrences in
                their first-occurrence order.

        Notes:
            An occurrence matches a product kept before when its normalized name or URL is one of those of the
            first occurrence, as `_is_new` compares the streamed products.
            The merged product is validated again, so that its categories are cleaned like those of a built product.
            Should it be invalid, the first occurrence is kept unchanged (logged).
        """
        merged: List[CloudProduct] = []
        positions: Dict[str, int] = {}
        count = 0
        for product in products:
            count += 1
            keys = [self._name_key(product.name)] + ([self._url_key(product.url)] if product.url else [])
            position = next((positions[key] for key in keys if key in positions), None)
            if position is None:
                positions.update(dict.fromkeys(keys, len(merged)))
                merged.append(product)
                continue
            first = merged[position]
            categories = [*first.catalogue_categories, *product.catalogue_categories]
            try:
                merged[position] = type(first).model_validate(
                    {**first.model_dump(), "catalogue_categories": categories}
                )
            except ValidationError as e:
                self.logger.warning("Keeping the categories of the first %r listing (%s).", first.name, e)
        self.logger.debug("%d distinct products out of %d listed entries.", len(merged), count)
        return merged

    def _next_data(self, response: Response) -> Dict[str, JsonValue]:
        """Read the Next.js data embedded in a page (`__NEXT_DATA__` script).

        Args:
            response (Response): The page.

        Returns:
            Dict[str, JsonValue]: The page data.

        Raises:
            CatalogueFormatError: If the script is missing or does not hold a JSON object.
        """
        self.logger.debug("Reading the Next.js data of %s.", response.url)
        raw = response.css("script#__NEXT_DATA__::text").get()
        if raw is None:
            self.logger.error("The %s page %s has no `__NEXT_DATA__` script.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the `__NEXT_DATA__` script is missing")
        try:
            data: JsonValue = json.loads(raw)
        except json.JSONDecodeError as e:
            self.logger.error("The %s page %s `__NEXT_DATA__` is not JSON: %s", self.name, response.url, e)
            raise CatalogueFormatError(self.name, response.url, "the `__NEXT_DATA__` script is not JSON") from e
        if not isinstance(data, dict):
            self.logger.error("The `__NEXT_DATA__` script of the %s page %s is not an object.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the `__NEXT_DATA__` script is not a JSON object")
        self.logger.debug("Next.js data of %s read (%d characters).", response.url, len(raw))
        return data

    def _json_body(self, response: Response) -> JsonValue:
        """Read a JSON response (the raw body, not a rendered page).

        Args:
            response (Response): The JSON response.

        Returns:
            JsonValue: The JSON document.

        Raises:
            CatalogueFormatError: If the response is not JSON.
        """
        try:
            data: JsonValue = json.loads(response.body.decode(TextEncoding.UTF_8, errors=TextEncoding.REPLACE))
        except json.JSONDecodeError as e:
            self.logger.error("The %s page %s is not JSON: %s", self.name, response.url, e)
            raise CatalogueFormatError(self.name, response.url, "the page is not JSON") from e
        return data

    def _sitemap_entries(self, response: Response) -> Dict[str, Optional[str]]:
        """Read the pages listed by a sitemap with their last modification, in order and without duplicates.

        Args:
            response (Response): The sitemap.

        Returns:
            Dict[str, Optional[str]]: The last modification (`lastmod`, raw) of each page URL, `None` when not given.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        body = response.body.decode(TextEncoding.UTF_8, errors=TextEncoding.REPLACE)
        blocks = re.findall(r"<(?:url|sitemap)>(.*?)</(?:url|sitemap)>", body, re.DOTALL) or [body]
        entries: Dict[str, Optional[str]] = {}
        for block in blocks:
            lastmod = re.search(r"<lastmod>\s*([^<\s]+)", block)
            for url in re.findall(r"<loc>\s*(?:<!\[CDATA\[)?\s*([^<\s\]]+)", block):
                entries.setdefault(html.unescape(url), lastmod.group(1) if lastmod else None)
        if not entries:
            self.logger.error("The %s sitemap %s lists no page.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the sitemap lists no page")
        self.logger.debug("%d pages listed by the %s sitemap %s.", len(entries), self.name, response.url)
        return entries

    def _sitemap_urls(self, response: Response) -> List[str]:
        """Read the pages listed by a sitemap, in order and without duplicates.

        Args:
            response (Response): The sitemap.

        Returns:
            List[str]: The page URLs.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        return list(self._sitemap_entries(response))

    def _meta_content(self, response: Response, *names: str) -> Optional[str]:
        """Read the first non-empty `meta` tag content of a page among some names, case-insensitively.

        Args:
            response (Response): The page.
            *names (str): The `name` or `property` values, by order of preference, e.g. `description`.

        Returns:
            Optional[str]: The content, `None` when no tag holds one.
        """
        contents: Dict[str, str] = {}
        for tag in response.css("meta[content]"):
            key = (tag.attrib.get(HtmlAttribute.NAME) or tag.attrib.get(HtmlAttribute.PROPERTY) or "").casefold()
            content = self._clean_text(tag.attrib.get(HtmlAttribute.CONTENT))
            if key and content and key not in contents:
                contents[key] = content
        return next((contents[name.casefold()] for name in names if name.casefold() in contents), None)

    def _page_title(self, title: str) -> str:
        """Clean the product name read from a product page title, e.g. to remove a brand suffix.

        Args:
            title (str): The page title.

        Returns:
            str: The product name.
        """
        return self._clean_text(title)

    def _page_name(self, response: Response) -> Optional[str]:
        """Read the product name of a product page: its Open Graph title, else its first heading.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The product name, `None` when the page has none.
        """
        title = self._meta_content(response, PageMetaName.OG_TITLE)
        if title is None and (heading := response.css("h1").first) is not None:
            title = heading.get_all_text(separator=" ", strip=True)
        return self._page_title(title) if title else None

    def _page_description(self, response: Response) -> Optional[str]:
        """Read the product description of a product page: its meta description, else its Open Graph one.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The description, `None` when the page has none.
        """
        return self._meta_content(response, PageMetaName.DESCRIPTION, PageMetaName.OG_DESCRIPTION)

    def _product_page_request(
        self,
        url: str,
        name: Optional[str] = None,
        updated: Optional[str] = None,
        categories: Optional[Sequence[str]] = None,
    ) -> Optional[Request]:
        """Build the request of a product page, whose product is read from the page (`PRODUCT_PAGE` meta).

        Args:
            url (str): The absolute product page URL.
            name (Optional[str]): The product name given by the listing,
                preferred to the page title.
            updated (Optional[str]): The last modification of the page given by a sitemap, preferred to the page
                `meta` tags.
            categories (Optional[Sequence[str]]): The categories the listing files the product under, carried by the
                request (`PRODUCT_CATEGORIES` meta) when there are some.

        Returns:
            Optional[Request]: The request, `None` when a product
                of this page was already streamed.
        """
        if self._url_key(url) in self.seen_urls:
            self.logger.debug("Not requesting the product page %s, its product is already streamed.", url)
            return None
        meta: Dict[str, Union[str, List[str]]] = {self.PRODUCT_PAGE: url}
        if name and self._clean_text(name):
            meta[self.PRODUCT_NAME] = self._clean_text(name)
        if updated:
            meta[self.PRODUCT_UPDATED] = updated
        if categories:
            meta[self.PRODUCT_CATEGORIES] = list(categories)
        return Request(url, meta=meta)

    def _page_categories(self, response: Response) -> List[str]:
        """Read the catalogue categories a request carries, e.g. a product page request.

        Args:
            response (Response): The page, requested with the `PRODUCT_CATEGORIES` meta, if any.

        Returns:
            List[str]: The categories (`PRODUCT_CATEGORIES` meta), empty when the request carries none.
        """
        categories = response.meta.get(self.PRODUCT_CATEGORIES)
        if not isinstance(categories, list):
            return []
        return [str(category) for category in categories if category]

    def _page_product(self, response: Response) -> Optional[CloudProduct]:
        """Extract the product of a product page: its name and description, filed under the request categories.

        Args:
            response (Response): The product page, requested with the `PRODUCT_PAGE` meta.

        Returns:
            Optional[CloudProduct]: The product, `None` for a missing page (HTTP error),
                a redirected (retired) page or an article page.

        Notes:
            A redirected page is a retired product, unless
            the product is named by a listing and its page moved
            within the same website (not to its home page):
            the product is then kept with its new page.
        """
        requested = str(response.meta.get(self.PRODUCT_PAGE, response.url))
        if response.status >= 400:
            self.logger.debug("Skipping %s, the page is missing (HTTP %s).", requested, response.status)
            return None
        listed = response.meta.get(self.PRODUCT_NAME)
        if self._url_key(response.url) != self._url_key(requested):
            final, origin = urlparse(response.url), urlparse(requested)
            if not listed or final.netloc != origin.netloc or not final.path.strip("/"):
                self.logger.debug("Skipping %s, redirected to %s (retired product).", requested, response.url)
                return None
            self.logger.debug("The product page %s moved to %s.", requested, response.url)
        name = str(listed) if listed else self._page_name(response)
        if not name or (not listed and (":" in name or "?" in name)):
            self.logger.debug("Skipping %s, not a product page (title %r).", response.url, name)
            return None
        added = self._meta_content(response, *self.ADDED_META)
        updated = response.meta.get(self.PRODUCT_UPDATED) or self._meta_content(response, *self.UPDATED_META)
        return self._build_product(
            name,
            self._page_description(response),
            response.url,
            self._parse_date(added, name) if added else None,
            self._parse_date(str(updated), name) if updated else None,
            DateCaveat.PAGE_PUBLISHED,
            DateCaveat.PAGE_MODIFIED,
            categories=self._page_categories(response),
        )

    def _record_page_dates(self, response: Response) -> None:
        """Remember the last modification of the pages listed by a sitemap, unless they are all of the same day.

        Args:
            response (Response): A `dates_sitemaps` sitemap.

        Notes:
            Some websites date every page of their sitemap
            with the generation date of the sitemap: such dates tell
            nothing about the pages and are ignored.
        """
        dates = {url: lastmod for url, lastmod in self._sitemap_entries(response).items() if lastmod}
        days = {lastmod[:10] for lastmod in dates.values()}
        if len(dates) >= self.SAME_DAY_LIMIT and len(days) == 1:
            self.logger.info(
                "The %s sitemap %s dates its %d pages %s, its generation date: its dates are ignored.",
                self.name,
                response.url,
                len(dates),
                days.pop(),
            )
            return
        self.page_dates.update({self._url_key(url): lastmod for url, lastmod in dates.items()})
        self.logger.info("%d page dates read from the %s sitemap %s.", len(dates), self.name, response.url)

    async def _fetch_launch_page(self, url: str, params: Optional[Dict[str, str]] = None) -> Optional[Response]:
        """Fetch a page of the provider's dated source, outside the crawl queue.

        Args:
            url (str): The page.
            params (Optional[Dict[str, str]]): Its query parameters, if any.

        Returns:
            Optional[Response]: The page, `None` when it is missing (HTTP error) or cannot be fetched (logged).

        Notes:
            The dated source is read while the catalogue page listing the product is parsed, so that the product is
            streamed dated. A failed fetch is not retried by the crawl engine: it leaves the product undated, and the
            product is still streamed.
        """
        self.logger.debug("Fetching the %s dated source %s %s.", self.name, url, params or "")
        try:
            response = await AsyncFetcher.get(
                url,
                params=params or {},
                timeout=self.LAUNCH_TIMEOUT,
                retries=self.fetch_retries,
                stealthy_headers=False,
            )
        except OSError as e:  # The HTTP client errors (`CurlError`), timeouts included, once the retries are spent.
            self.logger.warning("The %s dated source %s cannot be fetched: %r", self.name, url, e)
            return None
        if response.status >= 400:
            self.logger.debug("The %s dated source %s is missing (HTTP %s).", self.name, url, response.status)
            return None
        return response

    async def _launch_source(self, product: CloudProduct) -> Optional[Tuple[datetime, DateCaveat]]:
        """Read the launch of a product from the provider's dated source (for a `dates_launches` crawler).

        Args:
            product (CloudProduct): The product, undated.

        Returns:
            Optional[Tuple[datetime, DateCaveat]]: The launch and why it may differ from the actual launch, `None`
                when the source does not date the product (no dated source by default).
        """
        self.logger.debug("The %s crawler has no dated source for %r.", self.name, product.name)
        return None

    def _announced(self, launched: datetime) -> Tuple[datetime, DateCaveat]:
        """Qualify the first entry of the dated source naming a product.

        Args:
            launched (datetime): The date of that entry.

        Returns:
            Tuple[datetime, DateCaveat]: The launch, `FEED_START` when it is in the first months of the source
                (`launch_feed_start`), else `FIRST_ANNOUNCEMENT`.
        """
        start = self.launch_feed_start
        return launched, DateCaveat.FEED_START if start and launched < start else DateCaveat.FIRST_ANNOUNCEMENT

    def _with_launch(self, product: CloudProduct, launched: datetime, caveat: DateCaveat) -> CloudProduct:
        """Give a product its launch.

        Args:
            product (CloudProduct): The product.
            launched (datetime): Its launch.
            caveat (DateCaveat): Why the launch may differ from the actual launch.

        Returns:
            CloudProduct: The product with its launch as its added date.
        """
        self.logger.debug("%s launched on %s (%s).", product.name, launched.date().isoformat(), caveat)
        return product.model_copy(update={"added_at": launched, "added_caveat": caveat})

    def _curated_launch(self, name: str) -> Optional[Tuple[datetime, DateCaveat]]:
        """Get the curated launch of a product from the launch dates catalogue.

        Args:
            name (str): The product name, as the catalogue gives it.

        Returns:
            Optional[Tuple[datetime, DateCaveat]]: The launch and its caveat (`YEAR_ONLY` when only its year is
                known, else `CURATED`), `None` when the catalogue has no launch for the product (or lists it as a
                known gap).
        """
        curated = self.curated.get(self._name_key(name))
        launched = curated.launch_date() if curated is not None else None
        if curated is None or launched is None:
            return None
        return launched, DateCaveat.YEAR_ONLY if curated.precision() is LaunchPrecision.YEAR else DateCaveat.CURATED

    async def _sourced(self, product: CloudProduct) -> Optional[Tuple[datetime, DateCaveat]]:
        """Read the launch of a product from the dated source, for a `dates_launches` crawler.

        Args:
            product (CloudProduct): The product.

        Returns:
            Optional[Tuple[datetime, DateCaveat]]: The launch and its caveat, `None` without dated source, when the
                source does not date the product or cannot be read (logged).
        """
        if not self.dates_launches:
            return None
        try:
            return await self._launch_source(product)
        except CrawlerError as e:
            self.logger.warning("The %s dated source of %r cannot be read: %s", self.name, product.name, e)
            return None

    async def _dated(self, product: CloudProduct) -> CloudProduct:
        """Date the launch of a product: its curated launch, else the catalogue's date, else the dated source.

        Args:
            product (CloudProduct): The product, as the catalogue gives it.

        Returns:
            CloudProduct: The product, with its launch when a source gives it.

        Notes:
            - A catalogue date with a `REPLACEABLE_CAVEATS` caveat (a page or record date) is kept only when the
              dated source has no launch for the product.
            - A launch known only by its year (`YEAR_ONLY`, curated or from the catalogue) takes the day of the
              dated source when the source dates the product in that same year, outside the first months of the
              source (`FEED_START`, often sparse): a later announcement never replaces an earlier launch.
        """
        curated = self.curated.get(self._name_key(product.name))
        if curated is not None:
            launch = self._curated_launch(product.name)
            if launch is None:
                self.logger.debug("%s has no known launch: %s", product.name, curated.reason)
                return product
            product = self._with_launch(product, *launch)
        elif product.added_at is None or product.added_caveat in self.REPLACEABLE_CAVEATS:
            found = await self._sourced(product)
            if found is None:
                self.logger.info("No launch found for the %s product %r.", self.name, product.name)
                if product.added_at is None:
                    self.undated.add(product.name)
                return product
            return self._with_launch(product, *found)
        if product.added_at is None or product.added_caveat is not DateCaveat.YEAR_ONLY:
            return product
        found = await self._sourced(product)
        if found is None or found[1] is DateCaveat.FEED_START or found[0].year != product.added_at.year:
            return product
        self.logger.debug("The %s launch year of %r refined by its dated source.", self.name, product.name)
        return self._with_launch(product, *found)

    ############################
    # Publicly Exposed Methods #
    ############################

    def use_launches(self, catalog: LaunchCatalog) -> None:
        """Use the curated launches of a catalogue (the runs give the database's, where the edits are).

        Args:
            catalog (LaunchCatalog): The launch dates catalogue.
        """
        self.curated = {self._name_key(launch.name): launch for launch in catalog.launches_of(self.name)}
        self.launch_aliases = {
            self._name_key(name): feed_name for name, feed_name in catalog.aliases_of(self.name).items()
        }
        self.logger.debug("%s uses %d curated launches.", self.name, len(self.curated))

    def use_prices(
        self,
        provider: CloudProvider,
        sources: Mapping[str, PriceSource],
        delay_s: float = 2.0,
        products: Optional[Mapping[str, Optional[str]]] = None,
        pages: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> None:
        """Turn the crawler to its price sources (instead of its catalogue), knowing how they were last read.

        Args:
            provider (CloudProvider): The provider the crawler reads (the provider of its prices).
            sources (Mapping[str, PriceSource]): The price sources of the provider as last read, by source: an
                unchanged one is not read again.
            delay_s (float): The wait between two price requests, in seconds.
            products (Optional[Mapping[str, Optional[str]]]): The page of each live catalogue product of the
                provider, by name (stated unpriced by a provider publishing no price, read by one reading its
                product pages).
            pages (Optional[Mapping[str, Sequence[str]]]): The curated extra price pages of each product, by name
                (`conf/prices/coverage/<provider>.yaml`), read as product pages.

        Notes:
            The price sources are read politely rather than by their `robots.txt` (the user's choice: several
            providers disallow their public price APIs to every robot): one request at a time, `delay_s` apart. The
            catalogue crawl keeps obeying `robots.txt`.
            They are read over plain HTTP: the sessions of the catalogue, the stealth browser included, are
            replaced by the price session (none of them is started), and no domain restriction applies (a price API
            is often on another host than the website). A crawler rendering its product pages (`PRODUCT_PAGE_JS`,
            the user's choice for prices loaded client-side) also gets a plain headless browser session, started
            only when its first product page is requested, images, fonts and stylesheets blocked.
        """
        if delay_s <= 0:
            self.logger.warning("The %s price crawl asked no delay: it keeps %.1f s.", self.name, self.download_delay)
        else:
            self.download_delay = delay_s
        self.robots_txt_obey = False
        self.concurrent_requests = 1
        self.allowed_domains = set()
        for session_id in self._session_manager.session_ids:
            self._session_manager.remove(session_id)
            self.logger.debug("The %s session %s is not used to read prices: removed.", self.name, session_id)
        self._session_manager.add(
            self._price_session_id(),
            FetcherSession(
                impersonate="chrome",
                stealthy_headers=False,
                headers=dict(self.PRICE_HEADERS) or None,
                timeout=self.PRICE_TIMEOUT_S,
                retries=self.fetch_retries,
                retry_delay=round(self.retry_delay),
            ),
            default=True,
        )
        self.logger.debug("The %s prices are read by the HTTP session %s.", self.name, self._price_session_id())
        if self.PRODUCT_PAGE_JS:
            self._session_manager.add(
                self._rendered_session_id(),
                AsyncDynamicSession(
                    headless=True,
                    disable_resources=True,
                    block_ads=True,
                    network_idle=True,
                    load_dom=True,
                    timeout=self.RENDER_TIMEOUT_MS,
                    wait=self.RENDER_WAIT_MS,
                    retries=self.fetch_retries,
                    retry_delay=round(self.retry_delay),
                ),
                lazy=True,
            )
            self.logger.info(
                "The %s product pages are rendered by the plain headless browser session %s.",
                self.name,
                self._rendered_session_id(),
            )
        self.prices_mode = True
        self.price_provider = provider
        self.price_sources = dict(sources)
        self.price_reads = {}
        self.price_failures = set()
        self.price_count = 0
        self.price_products = dict(products or {})
        self.price_pages = {name: list(urls) for name, urls in (pages or {}).items() if urls}
        self.logger.info(
            "%s crawler in price mode: %d sources known, %.1f s between requests.",
            self.name,
            len(self.price_sources),
            self.download_delay,
        )

    def curated_launch(self, name: str) -> Optional[Tuple[datetime, DateCaveat]]:
        """Get the curated launch of a product, to date the stored products without crawling.

        Args:
            name (str): The product name, as stored.

        Returns:
            Optional[Tuple[datetime, DateCaveat]]: The launch and its caveat, `None` when the launch dates catalogue
                has none for the product.
        """
        launch = self._curated_launch(name)
        self.logger.debug("Curated launch of the %s product %r: %s.", self.name, name, launch)
        return launch

    def configure_sessions(self, manager: SessionManager) -> None:
        """Configure stealth crawler session.

        Args:
            manager (SessionManager): Consistent scrapling session mechanism.

        Notes:
            It is the first hook scrapling calls once the spider
            logger is created: the logger is handed over to the
            application logging configuration here, so that even
            the spider initialization is logged through it.
            The merged certificate bundle (`CaBundle`) is installed
            for the fetches outside the browser, e.g. the dated
            sources read by `_fetch_launch_page`.
        """
        self._use_application_logging()
        CaBundle(logger=self.logger).install()
        self.logger.debug("Configuring the stealth browser session %s.", self._browser_session_id())
        manager.add(
            self._browser_session_id(),
            AsyncStealthySession(
                timeout=120000,
                wait=2000,
                headless=False,
                load_dom=True,
                solve_cloudflare=self.solve_cloudflare,
                retries=self.fetch_retries,
                retry_delay=self.retry_delay,
            ),
            lazy=self.lazy_browser,
        )

    async def on_start(self, resuming: bool = False) -> None:
        """Forget the products of a previous crawl, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if resuming:
            self.logger.info(
                "Resuming the %s catalogue crawl (%d products already streamed).", self.name, len(self.seen_products)
            )
        elif self.prices_mode:
            self.price_count = 0
            self.logger.info("Starting the %s price crawl, %.1f s between requests.", self.name, self.download_delay)
        else:
            self.seen_products.clear()
            self.seen_urls.clear()
            self.page_dates.clear()
            self.undated.clear()
            self.logger.info("Starting the %s catalogue crawl from %s.", self.name, self.catalogue_url)

    async def on_error(self, request: Request, error: Exception) -> None:
        """Log the failed requests.

        Args:
            request (Request): The failed request.
            error (Exception): The error.

        Notes:
            The crawl engine already logs the errors raised
            while parsing a page (the crawler errors), not the fetch
            errors (network, browser, ...).
        """
        await super().on_error(request, error)
        if isinstance(error, CrawlerError):
            self.logger.debug("The %s catalogue page %s was not processed: %s", self.name, request.url, error)
        else:
            self.logger.error("Fetching the %s catalogue page %s failed: %r", self.name, request.url, error)

    async def on_close(self) -> None:
        """Log the crawl summary."""
        await super().on_close()
        if self.prices_mode:
            if self.price_failures:
                self.logger.warning(
                    "The %s price crawl is over: %d prices, %d sources failed.",
                    self.name,
                    self.price_count,
                    len(self.price_failures),
                )
            elif not self.price_count and self.price_reads:
                self.logger.info("The %s price crawl is over: its sources are unchanged.", self.name)
            elif not self.price_count:
                self.logger.warning("The %s price crawl is over without any price.", self.name)
            else:
                self.logger.info("The %s price crawl is over: %d prices.", self.name, self.price_count)
            return
        self.logger.info("The %s catalogue crawl is over: %d products streamed.", self.name, len(self.seen_products))
        if self.undated:
            self.logger.warning(
                "%d %s products have no launch date (neither the catalogue, "
                "its dated source nor the launch dates "
                "catalogue gives one): %s",
                len(self.undated),
                self.name,
                ", ".join(sorted(self.undated)),
            )
        else:
            self.logger.info("Every %s product has a launch date, known gaps excepted.", self.name)

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Start the crawl: the catalogue, or the price sources of the provider in price mode (`use_prices`).

        Yields:
            Request: The catalogue requests (`_catalogue_requests`), or the price requests (`_price_requests`, then
                the product pages of a crawler reading them, `PRODUCT_PAGE_PRICES`, and the curated price pages).
        """
        if self.prices_mode:
            self.logger.info("Starting the %s price crawl (%d sources known).", self.name, len(self.price_sources))
            async for request in self._price_requests():
                yield request
            if self.PRODUCT_PAGE_PRICES or self.price_pages:
                for request in self._product_page_requests():
                    yield request
            return
        self.logger.debug("Starting the %s catalogue crawl.", self.name)
        async for request in self._catalogue_requests():
            yield request

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of a catalogue page.

        Args:
            response (Response): The catalogue page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page, duplicates included.

        Raises:
            ParseNotImplementedError: If the crawler does not implement the extraction.
        """
        self.logger.error("The %s crawler does not implement the catalogue extraction.", type(self).__name__)
        raise ParseNotImplementedError(type(self).__name__)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the products of a catalogue page, or the product of a product page.

        Args:
            response (Response): The catalogue page, or a product page (`PRODUCT_PAGE` meta).

        Yields:
            Dict[str, JsonValue]: Each product not streamed yet, as a dictionary.

        Raises:
            EmptyCatalogueError: If a catalogue page holds no valid product at all.
        """
        self.logger.debug("Parsing the %s catalogue page %s (HTTP %s).", self.name, response.url, response.status)
        if self.PAGE_DATES in response.meta:
            if response.status < 400:
                self._record_page_dates(response)
            else:
                self.logger.warning(
                    "The %s sitemap %s is unavailable (HTTP %s).", self.name, response.url, response.status
                )
            return
        if self.PRODUCT_PAGE in response.meta:
            product = self._page_product(response)
            if product is not None and not self._seen(product):
                product = await self._dated(product)
            if product is not None and (page_item := self._stream(product)) is not None:
                yield page_item
            return
        found = duplicates = 0
        for product in self.extract_products(response):
            found += 1
            item = self._stream(product if self._seen(product) else await self._dated(product))
            if item is None:
                duplicates += 1
                continue
            yield item
        if not found:
            self.logger.error("The %s catalogue page %s holds no product.", self.name, response.url)
            raise EmptyCatalogueError(self.name, response.url)
        self.logger.info(
            "%s catalogue page %s parsed: %d new products, %d duplicates skipped.",
            self.name,
            response.url,
            found - duplicates,
            duplicates,
        )
