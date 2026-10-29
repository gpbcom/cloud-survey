from __future__ import annotations

# Standard Library Imports.
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.exoscale.enums import (
    ExoscaleChangelogMarkup,
    ExoscaleChangelogTag,
    ExoscaleLaunchKeyword,
    ExoscaleMenuMarkup,
    ExoscalePriceColumn,
    ExoscalePriceLiteral,
)
from crawler.enums import HtmlAttribute, PageMetaName
from crawler.exception import CatalogueFormatError
from models.cloud.enums import DateCaveat, PriceModel, PriceSourceKind, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class ExoscaleCrawler(BaseCloudCrawler):
    """Exoscale catalogue crawler.

    Attributes:
        SITEMAP_URL (ClassVar[str]): The sitemap of the website, listing the product pages.
        NOT_PRODUCT_NAME (ClassVar[re.Pattern[str]]): The menu entries which are overviews, not products.
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The menu links to compliance pages, not products.
        SITEMAP_PRODUCT_PAGE (ClassVar[re.Pattern[str]]): The top level pages of the website, capturing their slug:
            the product pages are top level pages, unlike the blog, the GPU models or the product features.
        SITEMAP_NOT_PRODUCT (ClassVar[re.Pattern[str]]): The top level pages which are not product pages.
        TITLE_BRAND (ClassVar[re.Pattern[str]]): The brand prefix or suffix of the page titles.
        CHANGELOG_URL (ClassVar[str]): The changelog, a single page listing every entry, read for the launches.
        CHANGELOG_DATE_FORMAT (ClassVar[str]): The format of the changelog dates, e.g. `Jan 28, 2022`.
        CHANGELOG_TAG (ClassVar[re.Pattern[str]]): The link of a changelog tag, capturing its slug, e.g. `dbaas`.
        LAUNCH_TITLE (ClassVar[re.Pattern[str]]): The words of a changelog title announcing a launch, e.g.
            `now available` or `Preview` (`ExoscaleLaunchKeyword`).
        LAUNCH_TAG (ClassVar[ExoscaleChangelogTag]): The changelog tag announcing something new.
        OFF_CATALOGUE_TAGS (ClassVar[Tuple[ExoscaleChangelogTag, ...]]): The changelog tags of the entries about
            partner products or courses, which date no product.
        not_product_urls (Set[str]): The URL keys of the menu entries filtered out, whose pages are not products.
        PRICING_URL (ClassVar[str]): The pricing page, every service priced in its tables.
        PRICES_API_URL (ClassVar[str]): An endpoint of the price API the pricing page reads its prices from.
        PRICE_ENDPOINT (ClassVar[str]): The request meta holding the endpoint of the price API.
        API_CURRENCY (ClassVar[str]): The currency of the price API read (its currencies state the same numbers).
        PRICE_CURRENCY (ClassVar[str]): That currency, as stored.
        COMPUTE_ENDPOINT (ClassVar[str]): The endpoint of the instances.
        DNS_ENDPOINT (ClassVar[str]): The endpoint of the DNS plans.
        STANDARD_FAMILY (ClassVar[str]): The family of the instances named without family in the API.
        INSTANCE_PREFIX (ClassVar[str]): The prefix of the instance keys of the API.
        PRICE_EXPRESSION (ClassVar[re.Pattern[str]]): The page template of a price cell, capturing its path, its
            multiplier (`* 10` zones) and its monthly conversion (`monthly_price(...)`).
        PATH_PART (ClassVar[re.Pattern[str]]): A part of a template path, dotted or quoted.
        HOURS_PER_MONTH (ClassVar[Decimal]): The hours of the monthly price of the page.
        PRICE_HEADER (ClassVar[re.Pattern[str]]): The header of a price column.
        TOKENS_HEADER (ClassVar[re.Pattern[str]]): The header of a price per million tokens.
        CURRENCY_LABEL (ClassVar[re.Pattern[str]]): The currency template of a header.
        HEADER_UNITS (ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit, int], ...]]): The unit of a price column,
            with the normalized units in one.
        DETAIL_UNITS (ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit], ...]]): The unit of a price whose column
            has none, from the name and details of its row.
        SECTION_UNITS (ClassVar[Dict[str, PriceUnit]]): The unit of a price whose row has none, by section.
        SPEC_FIELDS (ClassVar[Dict[str, str]]): The hardware field of a column.
        SIZE (ClassVar[re.Pattern[str]]): A memory or storage size, capturing its number and unit.
        GIB_PER (ClassVar[Dict[str, Decimal]]): The GiB in a size unit.
        COUNT (ClassVar[re.Pattern[str]]): A count of cores.
        VOLUME_TIER (ClassVar[re.Pattern[str]]): A volume tier, in TB (`next 25 to 100 TB Volume`).
        GB_PER_TB (ClassVar[Decimal]): The GB in a TB.
        PRICE_NUMBER (ClassVar[re.Pattern[str]]): A price written out, e.g. `2,500.00`.
        NUMBER_SEPARATORS (ClassVar[re.Pattern[str]]): The thousands separators of a price written out.
        INCLUDED_REASON (ClassVar[str]): Why an included service has no price.
        SECTION_ATTRIBUTE (ClassVar[str]): The attribute of a price naming its section.
        COLUMN_ATTRIBUTE (ClassVar[str]): The attribute of a price naming its column.
        changelog (Optional[List[Tuple[datetime, str, Tuple[str, ...]]]]): The changelog entries (date, title, tag
            keys), read once per crawl, `None` until read.
        price_api (Dict[str, Dict[str, str]]): The prices of each endpoint of the price API read, in price mode.
        price_endpoints (Set[str]): The endpoints the pricing page shows not read yet, in price mode.
        price_table (List[Tuple[str, List[str], List[str]]]): The rows of the pricing page, in price mode.

    Notes:
        Exoscale has no catalogue page. The main source is the products mega menu embedded in every page
        (`#dropdown-products a.mega__item`, read from https://www.exoscale.com/products/): each entry gives a name
        (`b`), a description (`span`) and a product page, once the overviews and compliance entries are filtered
        out. Some entries link the documentation website. A product is filed under its menu tab (`.mega__rail`) and
        its group (`.mega__group__title`), e.g. `Concrete AI` then `Inference`, and under those of every entry
        listing it. The sitemap completes it: its top level product pages missing from the menu are requested and
        read from their title and meta description (without categories).
        The catalogue dates no product: each product is dated (`dates_launches`) by the earliest entry of the
        changelog (https://changelog.exoscale.com/, every entry on a single page fetched once per crawl) which names
        it and announces a launch. An entry names a product when its title holds the product name, its alias or
        the slug of its page (whole words, case and punctuation ignored), or when one of its tags is the product
        name, alias or page slug, e.g. the `kms` tag for the `.../security/kms/` page. It announces a launch when it
        is tagged `new` or its title holds a launch keyword (`ExoscaleLaunchKeyword`), e.g. `now available`. A
        mere update dates nothing, nor do the marketplace, partner and academy entries. The changelog starts in
        2018: a launch dated before `launch_feed_start` may postdate the actual launch (`FEED_START`). A changelog
        page without entries (a soft 404) dates nothing.
        In price mode it reads the pricing page (`PRICING_URL`), whose tables name every service, its hardware and
        what its price is per, then the endpoints of the price API (`PRICES_API_URL`) its price cells read, the
        page keying them as its own script structures them (`_api_price`). A price written in the page is read
        from it (`FREE`, `INCLUDED`, a number, else a formula stored as not public). The page and its endpoints
        are one source, recorded once all are read. The prices are the same in every zone (`global`).
    """

    SITEMAP_URL: ClassVar[str] = "https://www.exoscale.com/sitemap.xml"
    NOT_PRODUCT_NAME: ClassVar[re.Pattern[str]] = re.compile(r"\boverview\b", re.IGNORECASE)
    NOT_PRODUCT_LINK: ClassVar[re.Pattern[str]] = re.compile(r"/compliance/", re.IGNORECASE)
    SITEMAP_PRODUCT_PAGE: ClassVar[re.Pattern[str]] = re.compile(
        r"^https://www\.exoscale\.com/([\w-]+)/?$", re.IGNORECASE
    )
    SITEMAP_NOT_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?:about-us|abuse|academy|backup|blog|calculator|changelog|compare|compliance|contact|data-portability|"
        r"datacenters|docker-in-the-cloud|dpa|end-user-certificate-gpu|eusa|eyeson|faq|integration|jobs|"
        r"liquidcooling|lp|marketplace|newsletter|ocre|partner-programs|pricing|privacy|products|security|signup|sla|"
        r"support|sustainability|syslog|technology-providers|templates|terms|wp)$",
        re.IGNORECASE,
    )
    TITLE_BRAND: ClassVar[re.Pattern[str]] = re.compile(r"^Exoscale\s+|\s*\|\s*Exoscale\s*$", re.IGNORECASE)

    name = "exoscale"
    catalogue_url: ClassVar[str] = "https://www.exoscale.com/products/"
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Exoscale ",)
    dates_launches: ClassVar[bool] = True
    launch_feed_start: ClassVar[Optional[datetime]] = datetime(2018, 6, 1, tzinfo=UTC)
    CHANGELOG_URL: ClassVar[str] = "https://changelog.exoscale.com/"
    CHANGELOG_DATE_FORMAT: ClassVar[str] = "%b %d, %Y"
    CHANGELOG_TAG: ClassVar[re.Pattern[str]] = re.compile(r"/tags/([^/]+)/?$")
    LAUNCH_TITLE: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(?:" + "|".join(map(re.escape, ExoscaleLaunchKeyword)) + r")\b", re.IGNORECASE
    )
    LAUNCH_TAG: ClassVar[ExoscaleChangelogTag] = ExoscaleChangelogTag.NEW
    OFF_CATALOGUE_TAGS: ClassVar[Tuple[ExoscaleChangelogTag, ...]] = (
        ExoscaleChangelogTag.MARKETPLACE,
        ExoscaleChangelogTag.PARTNERS,
        ExoscaleChangelogTag.ACADEMY,
    )
    PRICING_URL: ClassVar[str] = "https://www.exoscale.com/pricing/"
    PRICES_API_URL: ClassVar[str] = "https://portal.exoscale.com/api/pricing/{endpoint}"
    PRICE_ENDPOINT: ClassVar[str] = "price_endpoint"
    API_CURRENCY: ClassVar[str] = "eur"
    PRICE_CURRENCY: ClassVar[str] = "EUR"
    COMPUTE_ENDPOINT: ClassVar[str] = "opencompute"
    DNS_ENDPOINT: ClassVar[str] = "dns"
    STANDARD_FAMILY: ClassVar[str] = "standard"
    INSTANCE_PREFIX: ClassVar[str] = "running"
    PRICE_EXPRESSION: ClassVar[re.Pattern[str]] = re.compile(
        r"\{\{\s*(?P<monthly>monthly_price\()?\s*prices(?P<path>(?:\.[\w-]+|\['[\w.-]+'\])+)\[currency\]\s*\)?"
        r"\s*(?:\*\s*(?P<times>\d+))?\s*\|"
    )
    PATH_PART: ClassVar[re.Pattern[str]] = re.compile(r"\.([\w-]+)|\['([\w.-]+)'\]")
    HOURS_PER_MONTH: ClassVar[Decimal] = Decimal(720)
    PRICE_HEADER: ClassVar[re.Pattern[str]] = re.compile(r"^Price\b|per 1M tokens", re.IGNORECASE)
    TOKENS_HEADER: ClassVar[re.Pattern[str]] = re.compile(r"per 1M tokens", re.IGNORECASE)
    CURRENCY_LABEL: ClassVar[re.Pattern[str]] = re.compile(r"\s*\(\{\{.*?\}\}\)")
    HEADER_UNITS: ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit, int], ...]] = (
        (re.compile(r"Price / Hour", re.IGNORECASE), PriceUnit.HOUR, 1),
        (re.compile(r"Price / Month", re.IGNORECASE), PriceUnit.MONTH, 1),
        (re.compile(r"per 1M tokens", re.IGNORECASE), PriceUnit.TOKEN, 1_000_000),
    )
    DETAIL_UNITS: ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit], ...]] = (
        (re.compile(r"GiB\.hour", re.IGNORECASE), PriceUnit.GIB_HOUR),
        (re.compile(r"one-off|setup", re.IGNORECASE), PriceUnit.ONE_TIME),
        (re.compile(r"per month", re.IGNORECASE), PriceUnit.MONTH),
        (re.compile(r"per hour", re.IGNORECASE), PriceUnit.HOUR),
        (re.compile(r"per GiB|traffic|networking|TB Volume", re.IGNORECASE), PriceUnit.GIB),
    )
    SECTION_UNITS: ClassVar[Dict[str, PriceUnit]] = {
        "Network": PriceUnit.UNIT_HOUR,
        "Licenses": PriceUnit.HOUR,
        "SKS": PriceUnit.HOUR,
        "DNS": PriceUnit.MONTH,
        "Support": PriceUnit.MONTH,
    }
    SPEC_FIELDS: ClassVar[Dict[str, str]] = {
        ExoscalePriceColumn.RAM: "memory_gib",
        ExoscalePriceColumn.MEMORY: "memory_gib",
        ExoscalePriceColumn.CPU_CORES: "vcpu",
        ExoscalePriceColumn.CPU: "vcpu",
        ExoscalePriceColumn.MIN_LOCAL_STORAGE: "storage_gib",
        ExoscalePriceColumn.VOLUME_SIZE: "storage_gib",
        ExoscalePriceColumn.ALLOCATED_DISK: "storage_gib",
    }
    SIZE: ClassVar[re.Pattern[str]] = re.compile(r"([\d.]+)\s*(MB|GB|GiB|TB|TiB)\b", re.IGNORECASE)
    GIB_PER: ClassVar[Dict[str, Decimal]] = {
        "mb": Decimal(1) / Decimal(1024),
        "gb": Decimal(1),
        "gib": Decimal(1),
        "tb": Decimal(1024),
        "tib": Decimal(1024),
    }
    COUNT: ClassVar[re.Pattern[str]] = re.compile(r"\d+")
    VOLUME_TIER: ClassVar[re.Pattern[str]] = re.compile(r"(\d+) to (\d+) TB", re.IGNORECASE)
    GB_PER_TB: ClassVar[Decimal] = Decimal(1000)
    PRICE_NUMBER: ClassVar[re.Pattern[str]] = re.compile(r"^\d[\d,']*(?:\.\d+)?$")
    NUMBER_SEPARATORS: ClassVar[re.Pattern[str]] = re.compile(r"[,']")
    INCLUDED_REASON: ClassVar[str] = "Included for every Exoscale customer."
    SECTION_ATTRIBUTE: ClassVar[str] = "section"
    COLUMN_ATTRIBUTE: ClassVar[str] = "column"

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.not_product_urls: Set[str] = set()
        self.changelog: Optional[List[Tuple[datetime, str, Tuple[str, ...]]]] = None
        self.price_api: Dict[str, Dict[str, str]] = {}
        self.price_endpoints: Set[str] = set()
        self.price_table: List[Tuple[str, List[str], List[str]]] = []

    ############################
    # Internal Helpers Methods #
    ############################

    def _page_title(self, title: str) -> str:
        """Clean the product name read from a product page title: the brand prefix or suffix is removed.

        Args:
            title (str): The page title, e.g. `Exoscale Scion Network`.

        Returns:
            str: The product name, e.g. `Scion Network`.
        """
        return self._clean_text(self.TITLE_BRAND.sub("", self._clean_text(title)))

    def _page_description(self, response: Response) -> Optional[str]:
        """Read the product description of a product page: its meta description, else its header texts.

        Some pages only repeat their title in their meta description: their header subtitle and text are read then.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The description, `None` when the page has none.
        """
        description = super()._page_description(response)
        title = self._meta_content(response, PageMetaName.OG_TITLE) or ""
        if description and description.casefold() != title.casefold():
            return description
        header = [
            element.get_all_text(separator="") for element in response.css(".page-header__subtitle, .page-header__text")
        ]
        return self._clean_text(" ".join(header)) or description

    def _text(self, entry: Selector, selector: str) -> Optional[str]:
        """Read the text of the first element of a menu entry matching a selector.

        Args:
            entry (Selector): The menu entry.
            selector (str): The CSS selector of the element.

        Returns:
            Optional[str]: The element text, `None` when the entry has no such element.
        """
        element = entry.css(selector).first
        return element.get_all_text(separator=" ", strip=True) if element is not None else None

    def _entry_categories(self, entry: Selector, tab: Optional[str]) -> List[str]:
        """Get the categories of a products menu entry: its menu tab, then its group.

        Args:
            entry (Selector): The menu entry (`a.mega__item`).
            tab (Optional[str]): The label of the menu tab listing it, if any.

        Returns:
            List[str]: The category labels, e.g. `["Concrete AI", "Inference"]`.
        """
        categories = [tab] if tab else []
        group = entry.parent
        if group is not None and group.has_class(ExoscaleMenuMarkup.GROUP):
            title = group.css(".mega__group__title").first
            if title is not None and (label := self._clean_text(title.get_all_text(separator=" ", strip=True))):
                categories.append(label)
        return categories

    def _menu_entries(self, response: Response) -> List[Tuple[Selector, List[str]]]:
        """Gather the products menu entries with all their categories, a product being listed in several tabs.

        Args:
            response (Response): A page of the website.

        Returns:
            List[Tuple[Selector, List[str]]]: The first entry of each product, by order of appearance, and the
                categories of all its entries.

        Notes:
            Each menu tab (`.mega__rail label b`) has a grid of entries (`.mega__grid`), in the same order. A menu
            without grids lists its entries without categories. The entries of a product are matched by name or
            by link, as the streamed products are.
        """
        tabs = [
            self._clean_text(label.get_all_text(separator=" ", strip=True))
            for label in response.css("#dropdown-products .mega__rail label b")
        ]
        grids = response.css("#dropdown-products .mega__grid")
        listed: List[Tuple[Optional[str], Selector]] = [
            (tabs[index] if index < len(tabs) else None, entry)
            for index, grid in enumerate(grids)
            for entry in grid.css("a.mega__item")
        ] or [(None, entry) for entry in response.css("#dropdown-products a.mega__item")]
        self.logger.debug("%d products menu entries found on %s, in %d tabs.", len(listed), response.url, len(tabs))
        entries: List[Tuple[Selector, List[str]]] = []
        positions: Dict[str, int] = {}
        for tab, entry in listed:
            name = self._clean_text(self._text(entry, "b"))
            href = entry.attrib.get(HtmlAttribute.HREF)
            keys = ([f"name:{self._name_key(name)}"] if name else []) + (
                [f"url:{self._url_key(urljoin(response.url, href))}"] if href else []
            )
            position = next((positions[key] for key in keys if key in positions), None)
            if position is None:
                position = len(entries)
                entries.append((entry, []))
            else:
                self.logger.debug("Menu entry %r listed again, under %r.", name, tab)
            entries[position][1].extend(self._entry_categories(entry, tab))
            positions.update(dict.fromkeys(keys, position))
        return entries

    def _menu_product(self, entry: Selector, page_url: str, categories: List[str]) -> Optional[CloudProduct]:
        """Extract the product of a products menu entry.

        Args:
            entry (Selector): The menu entry (`a.mega__item`).
            page_url (str): The page URL, the menu links being relative to it.
            categories (List[str]): The categories of all the entries of the product.

        Returns:
            Optional[CloudProduct]: The product, `None` for an overview, a compliance page or an invalid entry.

        Notes:
            A group named after the product (e.g. the `Object Storage` group of `Object Storage`) is not one of its
            categories.
        """
        name = self._text(entry, "b")
        href = entry.attrib.get(HtmlAttribute.HREF)
        link = urljoin(page_url, href) if href else None
        reasons = {
            "overview": bool(self.NOT_PRODUCT_NAME.search(name or "")),
            "compliance page": bool(self.NOT_PRODUCT_LINK.search(link or "")),
        }
        if failed := [reason for reason, matched in reasons.items() if matched]:
            self.logger.debug("Skipping the menu entry %r (%s).", name, ", ".join(failed))
            if link:
                self.not_product_urls.add(self._url_key(link))
            return None
        own = self._clean_text(name).casefold()
        categories = [category for category in categories if category.casefold() != own]
        return self._build_product(name, self._text(entry, "span"), link, categories=categories)

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products menu, with their categories.

        Args:
            response (Response): A page of the website.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menu, once.
        """
        for entry, categories in self._menu_entries(response):
            if product := self._menu_product(entry, response.url, categories):
                yield product

    def _is_product_page(self, url: str) -> bool:
        """Tell whether a sitemap page is a product page not filtered out of the menu.

        Args:
            url (str): The sitemap page URL.

        Returns:
            bool: Whether the page is a top level page which is not a company,
                legal, learning or menu overview page.
        """
        page = self.SITEMAP_PRODUCT_PAGE.match(url)
        if page is None:
            return False
        if self.SITEMAP_NOT_PRODUCT.match(page.group(1)) or self._url_key(url) in self.not_product_urls:
            self.logger.debug("Skipping the sitemap page %s, not a product.", url)
            return False
        return True

    def _sitemap_requests(self, response: Response) -> List[Request]:
        """Request the product pages of the sitemap which were not found in the products menu.

        Args:
            response (Response): The sitemap.

        Returns:
            List[Request]: The product page requests.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        urls = self._sitemap_urls(response)
        pages = [url for url in urls if self._is_product_page(url)]
        requests = [request for url in pages if (request := self._product_page_request(url)) is not None]
        self.logger.info(
            "%d %s product pages to check in the sitemap (%d product pages, %d pages).",
            len(requests),
            self.name,
            len(pages),
            len(urls),
        )
        return requests

    def _words(self, text: str) -> str:
        """Normalize a text to compare its words: case and punctuation are ignored.

        Args:
            text (str): The text, e.g. `Managed OpenSearch now available`.

        Returns:
            str: Its words separated and surrounded by single spaces, e.g. ` managed opensearch now available `.
        """
        words = re.sub(r"[\W_]+", " ", self._clean_text(text).casefold()).strip()
        return f" {words} " if words else ""

    def _page_slug(self, url: Optional[str]) -> Optional[str]:
        """Get the slug of a product page: the last segment of its path.

        Args:
            url (Optional[str]): The product page, if any.

        Returns:
            Optional[str]: The slug, e.g. `kms` for `https://community.exoscale.com/product/security/kms/`, `None`
                for a home page or no page.
        """
        segments = [segment for segment in urlparse(url or "").path.split("/") if segment]
        return segments[-1] if segments else None

    def _changelog_date(self, text: Optional[str]) -> Optional[datetime]:
        """Parse the date of a changelog entry.

        Args:
            text (Optional[str]): The entry date, e.g. `Jan 28, 2022`.

        Returns:
            Optional[datetime]: The date in UTC, `None` when missing, unreadable or implausible.
        """
        try:
            parsed = datetime.strptime(self._clean_text(text), self.CHANGELOG_DATE_FORMAT).replace(tzinfo=UTC)
        except ValueError:
            self.logger.debug("Unreadable %s changelog date %r.", self.name, text)
            return None
        return parsed if self.EARLIEST_DATE <= parsed <= datetime.now(UTC) else None

    def _changelog_entries(self, response: Response) -> List[Tuple[datetime, str, Tuple[str, ...]]]:
        """Read the dated entries of the changelog.

        Args:
            response (Response): The changelog page.

        Returns:
            List[Tuple[datetime, str, Tuple[str, ...]]]: The date, title and tag keys (e.g. `dbaas`) of each dated
                entry, by order of appearance.
        """
        entries: List[Tuple[datetime, str, Tuple[str, ...]]] = []
        for card in response.css(ExoscaleChangelogMarkup.CARD):
            date = self._changelog_date(card.css(ExoscaleChangelogMarkup.DATE).get())
            title = card.css(ExoscaleChangelogMarkup.TITLE).first
            if date is None or title is None:
                continue
            links = [link.attrib.get(HtmlAttribute.HREF, "") for link in card.css(ExoscaleChangelogMarkup.TAG)]
            tags = tuple(self._name_key(match.group(1)) for link in links if (match := self.CHANGELOG_TAG.search(link)))
            entries.append((date, self._clean_text(title.get_all_text(separator=" ", strip=True)), tags))
        return entries

    async def _changelog(self) -> List[Tuple[datetime, str, Tuple[str, ...]]]:
        """Get the changelog entries, the changelog being fetched once per crawl.

        Returns:
            List[Tuple[datetime, str, Tuple[str, ...]]]: The dated entries, none when the changelog cannot be
                fetched or lists no entry (a soft 404).
        """
        if self.changelog is not None:
            return self.changelog
        response = await self._fetch_launch_page(self.CHANGELOG_URL)
        self.changelog = self._changelog_entries(response) if response is not None else []
        if self.changelog:
            self.logger.info("%d dated entries read from the %s changelog.", len(self.changelog), self.name)
        else:
            self.logger.warning("The %s changelog %s gives no dated entry.", self.name, self.CHANGELOG_URL)
        return self.changelog

    def _product_terms(self, product: CloudProduct) -> Tuple[List[str], Set[str]]:
        """Get the terms a changelog entry names a product with: its name, its alias and its page slug.

        Args:
            product (CloudProduct): The product.

        Returns:
            Tuple[List[str], Set[str]]: The terms as words (`_words`), looked up in the titles, and as name keys,
                compared with the tags.
        """
        alias = self.launch_aliases.get(self._name_key(product.name))
        slug = self._page_slug(product.url)
        terms = [self._page_title(term) for term in (product.name, alias, slug) if term]
        words = [words for words in (self._words(term) for term in terms) if words]
        return words, {self._name_key(term) for term in terms}

    def _is_launch(self, title: str, tags: Tuple[str, ...]) -> bool:
        """Tell whether a changelog entry announces a launch.

        Args:
            title (str): The entry title.
            tags (Tuple[str, ...]): The entry tag keys.

        Returns:
            bool: Whether the entry is tagged `new` or its title holds a launch keyword.
        """
        return self.LAUNCH_TAG in tags or self.LAUNCH_TITLE.search(title) is not None

    def _first_launch(
        self, entries: List[Tuple[datetime, str, Tuple[str, ...]]], product: CloudProduct
    ) -> Optional[datetime]:
        """Find the earliest changelog entry naming a product and announcing a launch.

        Args:
            entries (List[Tuple[datetime, str, Tuple[str, ...]]]): The changelog entries.
            product (CloudProduct): The product.

        Returns:
            Optional[datetime]: The date of that entry, `None` when no launch-like entry names the product.
        """
        words, keys = self._product_terms(product)
        launches: List[Tuple[datetime, str]] = []
        for date, title, tags in entries:
            if any(tag in self.OFF_CATALOGUE_TAGS for tag in tags) or not self._is_launch(title, tags):
                continue
            title_words = self._words(title)
            if any(term in title_words for term in words) or not keys.isdisjoint(tags):
                launches.append((date, title))
        if not launches:
            self.logger.debug("No %s changelog launch names %r.", self.name, product.name)
            return None
        launched, title = min(launches)
        self.logger.debug("%r launched on %s: %r.", product.name, launched.date().isoformat(), title)
        return launched

    async def _launch_source(self, product: CloudProduct) -> Optional[Tuple[datetime, DateCaveat]]:
        """Read the launch of a product from the earliest changelog entry naming it and announcing a launch.

        Args:
            product (CloudProduct): The product, undated.

        Returns:
            Optional[Tuple[datetime, DateCaveat]]: The launch and its caveat, `None` when no launch-like entry names
                the product or the changelog cannot be read.
        """
        launched = self._first_launch(await self._changelog(), product)
        return self._announced(launched) if launched is not None else None

    def _pricing_rows(self, response: Response) -> List[Tuple[str, List[str], List[str]]]:
        """Read the rows of the tables of the pricing page, as text.

        Args:
            response (Response): The pricing page.

        Returns:
            List[Tuple[str, List[str], List[str]]]: For each row, the title of its section (e.g. `Managed
                PostgreSQL`), the headers of its table and its cells (a price cell holds its page template, e.g.
                `{{ prices['dbaas-pg']['business-4'][currency] | number:8 }}`).
        """
        rows: List[Tuple[str, List[str], List[str]]] = []
        for table in response.css("table"):
            headers = [self._clean_text(" ".join(cell.css("::text").getall())) for cell in table.css("thead th")]
            section = self._clean_text(table.xpath("preceding::h2[1]//text()").get() or "")
            for row in table.css("tbody tr"):
                cells = [self._clean_text(" ".join(cell.css("::text").getall())) for cell in row.css("td")]
                if len(cells) != len(headers) or not cells or not cells[0]:
                    self.logger.debug("A row of the %s pricing table %r is skipped: %s", self.name, section, cells)
                    continue
                rows.append((section, headers, cells))
        self.logger.debug("%d rows in the %s pricing tables.", len(rows), self.name)
        return rows

    def _expression_path(self, cell: str) -> Optional[List[str]]:
        """Read the price a cell of the pricing page shows, as the path of the structured price API data.

        Args:
            cell (str): The cell, e.g. `{{ prices.opencompute.standard.micro[currency] | number:8 }}`.

        Returns:
            Optional[List[str]]: The path, e.g. `['opencompute', 'standard', 'micro']`, `None` when the cell
                states its price itself.
        """
        match = self.PRICE_EXPRESSION.search(cell)
        if match is None:
            return None
        return [dotted or quoted for dotted, quoted in self.PATH_PART.findall(match["path"])]

    def _api_price(self, path: List[str]) -> Optional[Decimal]:
        """Find the price of a path in the price API data, structured as the pricing page structures it.

        Args:
            path (List[str]): The path, its endpoint first.

        Returns:
            Optional[Decimal]: The price, `None` when the endpoint does not state it.

        Notes:
            The page keys the instances by family and size (`opencompute.cpu.huge` is `running_cpu_huge`, the
            standard family unnamed: `running_huge`), and the DNS plans by size (`dns.small` is `dns-small-1`).
        """
        endpoint, rest = path[0], path[1:]
        prices = self.price_api.get(endpoint, {})
        if endpoint == self.COMPUTE_ENDPOINT and len(rest) == 2:
            family = [] if rest[0] == self.STANDARD_FAMILY else [rest[0]]
            key = "_".join([self.INSTANCE_PREFIX, *family, rest[1]])
        elif endpoint == self.DNS_ENDPOINT and len(rest) == 1:
            key = next((name for name in prices if name.split("-")[1:2] == rest), rest[0])
        elif len(rest) == 1:
            key = rest[0]
        else:
            self.logger.warning("The %s price path %s has no known structure.", self.name, ".".join(path))
            return None
        if key not in prices:
            self.logger.warning("The %s price API states no %s.%s.", self.name, endpoint, key)
            return None
        return Decimal(prices[key])

    def _cell_price(self, cell: str) -> Optional[Tuple[Optional[Decimal], PriceModel, Optional[str]]]:
        """Read the price a cell of the pricing page shows.

        Args:
            cell (str): The cell: a page template, a number or a word.

        Returns:
            Optional[Tuple[Optional[Decimal], PriceModel, Optional[str]]]: The price, how it is charged and why
                there is none, `None` when the cell prices nothing (`-`, `Not applicable`) or its API price is
                missing.
        """
        path = self._expression_path(cell)
        if path is not None:
            price = self._api_price(path)
            if price is None:
                return None
            match = self.PRICE_EXPRESSION.search(cell)
            if match is not None and match["times"]:
                price *= Decimal(match["times"])
            if match is not None and match["monthly"]:
                price *= self.HOURS_PER_MONTH
            return price, PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND, None
        folded = cell.casefold()
        if not folded or folded in (ExoscalePriceLiteral.NOT_APPLICABLE, ExoscalePriceLiteral.NONE):
            return None
        if folded == ExoscalePriceLiteral.FREE:
            return Decimal(0), PriceModel.FREE, None
        if folded == ExoscalePriceLiteral.INCLUDED:
            return None, PriceModel.INCLUDED, self.INCLUDED_REASON
        if self.PRICE_NUMBER.match(cell):
            price = Decimal(self.NUMBER_SEPARATORS.sub("", cell))
            return price, PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND, None
        self.logger.debug("The %s price %r is not a number: stored as not public.", self.name, cell)
        return None, PriceModel.NOT_PUBLIC, cell

    def _row_unit(self, section: str, header: str, text: str) -> Tuple[PriceUnit, Decimal]:
        """Normalize the unit of a price of the pricing page.

        Args:
            section (str): The section of its table.
            header (str): The header of its column (`Price / Hour`, `Input per 1M tokens`).
            text (str): The name and the details of its row (`per GiB.hour`, `One-Off Setup Cost`).

        Returns:
            Tuple[PriceUnit, Decimal]: The unit, from the column header, else the row, else the section, and the
                normalized units in one (a million tokens).
        """
        for pattern, unit, factor in self.HEADER_UNITS:
            if pattern.search(header):
                return unit, Decimal(factor)
        for pattern, unit in self.DETAIL_UNITS:
            if pattern.search(text):
                return unit, Decimal(1)
        unit = self.SECTION_UNITS.get(section, PriceUnit.OTHER)
        if unit is PriceUnit.OTHER:
            self.logger.debug("The unit of the %s price %r (%s) is unknown.", self.name, text, section)
        return unit, Decimal(1)

    def _row_specs(self, headers: List[str], cells: List[str]) -> Tuple[Dict[str, Decimal], Dict[str, JsonValue]]:
        """Read the hardware and the other attributes of a row of the pricing page.

        Args:
            headers (List[str]): The headers of its table.
            cells (List[str]): Its cells.

        Returns:
            Tuple[Dict[str, Decimal], Dict[str, JsonValue]]: Its `vcpu`, `memory_gib` and `storage_gib` (those
                stated), and its other cells by header (the prices and the links left out).
        """
        specs: Dict[str, Decimal] = {}
        attributes: Dict[str, JsonValue] = {}
        for header, cell in zip(headers[1:], cells[1:], strict=True):
            if not cell or cell == ExoscalePriceLiteral.NONE or header == ExoscalePriceColumn.INFORMATION:
                continue
            if self.PRICE_HEADER.search(header):
                continue
            field = self.SPEC_FIELDS.get(header)
            size = self.SIZE.search(cell)
            count = self.COUNT.search(cell)
            if field is not None and field != "vcpu" and size is not None:
                specs[field] = Decimal(size[1]) * self.GIB_PER[size[2].casefold()]
            elif field == "vcpu" and count is not None:
                specs[field] = Decimal(count[0])
            else:
                attributes[header] = cell
        return specs, attributes

    def _row_prices(self, section: str, headers: List[str], cells: List[str]) -> Iterator[ServicePrice]:
        """Read the prices of a row of the pricing page.

        Args:
            section (str): The section of its table, e.g. `Managed PostgreSQL`.
            headers (List[str]): The headers of its table.
            cells (List[str]): Its cells, its name first.

        Yields:
            ServicePrice: One price per price column (three for a language model: input, output and cache read).
        """
        name = cells[0]
        details = next(
            (
                cell
                for header, cell in zip(headers, cells, strict=True)
                if header == ExoscalePriceColumn.PRODUCT_DETAILS
            ),
            "",
        )
        details = "" if details == ExoscalePriceLiteral.NONE else details
        specs, attributes = self._row_specs(headers, cells)
        attributes[self.SECTION_ATTRIBUTE] = section
        for header, cell in zip(headers, cells, strict=True):
            if not self.PRICE_HEADER.search(header):
                continue
            priced = self._cell_price(cell)
            if priced is None:
                continue
            price, model, reason = priced
            column = self.CURRENCY_LABEL.sub("", header).strip()
            path = self._expression_path(cell)
            key = "/".join(path) if path else "/".join(part for part in (section, name, details) if part)
            if self.TOKENS_HEADER.search(header):
                key = f"{key}/{column}"
            unit, factor = self._row_unit(section, header, f"{name} {details}")
            tier = self.VOLUME_TIER.search(details)
            fields: Dict[str, RawValue] = {
                "sku_key": key,
                "service": section or name,
                "family": section or None,
                "attributes": {**attributes, self.COLUMN_ATTRIBUTE: column},
                "unit": unit,
                "unit_raw": details or column,
                "unit_factor": factor,
                "price": price,
                "currency": self.PRICE_CURRENCY if price is not None else None,
                "model": model,
                "reason": reason,
                "source_url": self.PRICING_URL,
                "source_kind": PriceSourceKind.API if path else PriceSourceKind.PAGE,
            }
            if "vcpu" in specs:
                fields["instance_type"] = name
            if tier is not None:
                fields["tier_start"] = Decimal(tier[1]) * self.GB_PER_TB
                fields["tier_end"] = Decimal(tier[2]) * self.GB_PER_TB
            fact = self._price_fact({**fields, **specs})
            if fact is not None:
                yield fact

    def _read_price_api(self, endpoint: str, response: Response) -> None:
        """Keep the prices of an endpoint of the price API, in the currency read.

        Args:
            endpoint (str): The endpoint, e.g. `dbaas-pg`.
            response (Response): Its response, `{currency: {key: price}}`.

        Raises:
            CatalogueFormatError: If it states no prices in the currency read.
        """
        data = self._json_body(response)
        prices = data.get(self.API_CURRENCY) if isinstance(data, dict) else None
        if not isinstance(prices, dict):
            self.logger.error("The %s price API %s states no %s prices.", self.name, endpoint, self.API_CURRENCY)
            raise CatalogueFormatError(self.name, response.url, f"no {self.API_CURRENCY} prices")
        self.price_api[endpoint] = {key: value for key, value in prices.items() if isinstance(value, str)}
        self.logger.debug("%s price API %s read: %d prices.", self.name, endpoint, len(self.price_api[endpoint]))

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the pricing page, which tells which endpoints of the price API it shows.

        Yields:
            Request: The request of the pricing page.
        """
        self.price_api = {}
        self.price_endpoints = set()
        self.price_table = []
        self.logger.info("Reading the %s prices from %s.", self.name, self.PRICING_URL)
        yield self._price_request(self.PRICING_URL)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the pricing page, then the endpoints of the price API it shows, then give the prices of the page.

        Args:
            response (Response): The pricing page or an endpoint of the price API.

        Yields:
            PriceFact: The requests of the endpoints (from the page), then, once the last endpoint is read, every
                price of the page.

        Raises:
            CatalogueFormatError: If the page has no pricing table or an endpoint states no prices.
        """
        endpoint = response.meta.get(self.PRICE_ENDPOINT)
        if isinstance(endpoint, str):
            self._read_price_api(endpoint, response)
            self.price_endpoints.discard(endpoint)
        else:
            self.price_table = self._pricing_rows(response)
            if not self.price_table:
                self.logger.error("The %s pricing page %s has no pricing table.", self.name, response.url)
                raise CatalogueFormatError(self.name, response.url, "the pricing page has no pricing table")
            paths = (self._expression_path(cell) for _, _, cells in self.price_table for cell in cells)
            self.price_endpoints = {path[0] for path in paths if path}
            self.logger.info("The %s pricing page shows %d API endpoints.", self.name, len(self.price_endpoints))
            for name in sorted(self.price_endpoints):
                yield self._price_request(self.PRICES_API_URL.format(endpoint=name), {self.PRICE_ENDPOINT: name})
        if self.price_endpoints:
            self.logger.debug("%d %s price API endpoints left to read.", len(self.price_endpoints), self.name)
            return
        found = 0
        for section, headers, cells in self.price_table:
            for fact in self._row_prices(section, headers, cells):
                found += 1
                yield fact
        self._record_price_source(self.PRICING_URL, found)
        self.logger.info("The %s pricing page is read whole: %d prices.", self.name, found)

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products menu.

        Args:
            response (Response): A page of the website.

        Returns:
            Iterator[CloudProduct]: The valid products of the menu, duplicates included.
        """
        return self._menu_products(response)

    async def on_start(self, resuming: bool = False) -> None:
        """Forget the changelog of a previous crawl, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if not resuming:
            self.changelog = None
            self.logger.debug("The %s changelog will be read again.", self.name)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the menu products, request the sitemap product pages, or stream a sitemap product page.

        The product pages are read by the base crawler.

        Args:
            response (Response): The products page, the sitemap or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, or the product page requests.

        Raises:
            EmptyCatalogueError: If the products page holds no valid product.
            CatalogueFormatError: If the sitemap lists no page.
        """
        if response.url == self.SITEMAP_URL:
            for request in self._sitemap_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
