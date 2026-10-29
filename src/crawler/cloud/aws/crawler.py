from __future__ import annotations

import csv
import json
import re

# Standard Library Imports.
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

# Third Party Imports.
from patchright.async_api import Page, Route
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

from crawler.cloud.aws.enums import (
    AwsBadgeField,
    AwsCapacityStatus,
    AwsCardField,
    AwsDirectoryField,
    AwsDirectoryParameter,
    AwsDirectoryParameterValue,
    AwsDocsLink,
    AwsDocsSection,
    AwsHtmlTag,
    AwsLeaseLength,
    AwsOfferField,
    AwsPriceColumn,
    AwsSavingsColumn,
    AwsTagField,
    AwsTagNamespace,
    AwsTermType,
    AwsWhatsNewField,
)
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError, PriceDownloadError

# First Party Imports.
from models.cloud.enums import DateCaveat, PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class AWSCrawler(BaseCloudCrawler):
    """Amazon Web Services catalogue crawler.

    Attributes:
        API_URL (ClassVar[str]): The directory search API.
        PAGE_SIZE (ClassVar[int]): The products read per page.
        QUERY (ClassVar[Dict[str, str]]): The directory search parameters, page number excluded.
        YEAR_TAG (ClassVar[AwsTagNamespace]): The tag namespace of the launch year of a directory entry.
        CATEGORY_TAG (ClassVar[AwsTagNamespace]): The tag namespace of the technology categories of a directory entry.
        DOCS_URL (ClassVar[str]): The documentation home page, listing every service documentation.
        DOCS_EXCLUDED_SECTIONS (ClassVar[FrozenSet[AwsDocsSection]]): The documentation sections which are not services.
        DOCS_NOT_SERVICE (ClassVar[re.Pattern[str]]): The documentation entries which are not services.
        DOCS_HOST (ClassVar[str]): The documentation host, whose first path segment is the service slug.
        DOCS_APP_SCRIPT (ClassVar[str]): The script replacing the server-rendered documentation list in a browser.
        DOCS_SECTION_TAG (ClassVar[AwsHtmlTag]): The element of a documentation home page section, holding its title.
        WHATS_NEW_PAGE_SIZE (ClassVar[int]): The announcements read per page of the dated source.
        WHATS_NEW_MAX_PAGES (ClassVar[int]): The most pages of a year of the dated source read (a bound, not a cut).
        WHATS_NEW_YEAR_TAG (ClassVar[str]): The tag of the announcements of a year, formatted with the year.
        WHATS_NEW_QUERY (ClassVar[Dict[str, str]]): The What's New search parameters, page number excluded.
        WHATS_NEW_START (ClassVar[datetime]): The first announcement of What's New: an earlier date is an error.
        TAGGED_SINCE (ClassVar[datetime]): Since when the announcements are tagged with their products: an earlier
            tagged one may follow untagged ones about the same product, so the headlines date it.
        SLUG_SEPARATOR (ClassVar[re.Pattern[str]]): What separates the words of a product tag.
        whats_new (Optional[Dict[str, datetime]]): The first announcement of each product tag, read once per crawl.
        PRICE_HOST (ClassVar[str]): The host of the Price List bulk API (no key).
        OFFER_INDEX_URL (ClassVar[str]): Its offer index, listing the offers (services) and their region indexes.
        PRICE_FILE_URL (ClassVar[str]): The stable URL of the price file of an offer in a region (its source).
        PRICE_OFFER (ClassVar[str]): The request meta holding the offer (or the savings plan) of a region index.
        PRICE_SAVINGS (ClassVar[str]): The request meta marking a savings plan region index.
        SAVINGS_FILE_URL (ClassVar[str]): The stable URL of the savings plan file of a region (its source).
        SAVINGS_FAMILY (ClassVar[re.Pattern[str]]): The savings plan in the path of its region index.
        EC2_OFFER (ClassVar[str]): The offer of EC2, whose savings plan rates are filtered.
        SAVINGS_KEPT_OPERATION (ClassVar[str]): The EC2 operation whose savings plan rates are kept (Linux).
        SAVINGS_KEPT_USAGE (ClassVar[str]): The EC2 usage whose savings plan rates are kept (shared tenancy).
        SAVINGS_TERMS (ClassVar[Dict[Tuple[str, str], PriceTerm]]): The term of a savings plan.
        VERSION (ClassVar[re.Pattern[str]]): The version in the path of a price file.
        JSON_FILE (ClassVar[str]): The name of the JSON price file of a region.
        CSV_FILE (ClassVar[str]): The name of its CSV twin, streamed row by row.
        PRICE_UNITS (ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit], ...]]): The rules normalizing a unit.
        UNIT_COUNT (ClassVar[re.Pattern[str]]): The count a unit starts with (`1K tokens`, `Per 1000 requests`).
        MULTIPLIERS (ClassVar[Dict[str, int]]): The value of a count multiplier.
        COUNTABLE_UNITS (ClassVar[FrozenSet[PriceUnit]]): The units a count multiplies.
        LEASE_TERMS (ClassVar[Dict[str, PriceTerm]]): The term of a reservation.
        UPFRONT (ClassVar[re.Pattern[str]]): The description of the upfront fee of a reservation.
        GIB (ClassVar[re.Pattern[str]]): A memory size, in GiB.
        NUMBER (ClassVar[re.Pattern[str]]): A tier bound written as a number (not `Inf`).
        NOT_APPLICABLE (ClassVar[str]): The value of a column which does not apply.
        NO_UNIT (ClassVar[str]): The unit written for a row without unit.
        ATTRIBUTE_LENGTH (ClassVar[int]): The longest attribute value kept.
        KEPT_COLUMNS (ClassVar[Tuple[AwsPriceColumn, ...]]): The columns kept as attributes.
        headlines (List[Tuple[str, datetime]]): The headlines of the announcements, lower-case, oldest first.

    Notes:
        The main source is the JSON directory API behind the https://aws.amazon.com/products/ page, read page after
        page. A directory entry gives the launch year of the product (its `GLOBAL#local-tags-year` tag, `YEAR_ONLY`
        caveat), else the publication of its card (`additionalFields.publishedDate`, mostly 2020 when the directory
        was rebuilt, `CATALOGUE_ENTRY` caveat), and the last update of its card (`dateUpdated`, `CATALOGUE_ENTRY`
        caveat). `dateCreated` is the same migration date for every entry. The documentation home
        page completes it with the services missing from the directory, undated. A service
        documentation (`docs.aws.amazon.com/ec2/...`) matches the product page of the same slug (`/ec2/`).
        In a browser, a script replaces the full server-rendered documentation list by collapsed panels: it is not
        loaded, so that the list stays complete.
        The categories of a directory entry are its technology category tags (`CATEGORY_TAG`), else the category
        badge of its card (`additionalFields.badge`). Those of a documentation entry are the titles of the sections
        listing it, gathered over the whole page before it is streamed.
        The dated source is What's New (the `whats-new-v2` directory of the same API, about 23,000 announcements
        since October 2004, read once per crawl, year by year since the search reads at most 10,000 entries): a
        product is dated by its first announcement tagged with it (the product tags are kept since 2015), else by the
        first headline naming it. It dates the products the directory gives no year, and the day of a launch year in
        that same year only (`_dated`).
        In price mode it reads the Price List bulk API: the offer index, the region index of each offer, then the
        CSV price file of each offer in each region, streamed row by row (EC2 is hundreds of MB a region), one price
        per rate code. Each file is a source versioned by the date in its path: an unchanged file is not
        downloaded again. The EC2 lines of reservation accounting (`CapacityStatus` other than `Used`) repeat the
        price of the running instance: they are skipped. A reservation is priced per hour, its upfront fee being
        a one-time price of its own.
        The savings plans (compute, database, machine learning) are read the same way, from the savings plan
        index each offer names (each plan once): one rate per discounted usage. For EC2, only the rates of a Linux
        instance of shared tenancy are kept (`SAVINGS_KEPT_OPERATION`, `SAVINGS_KEPT_USAGE`): the other operating
        systems, tenancies and reservation accounting lines repeat the discount, 40 times the rows (about 45
        million).
    """

    API_URL: ClassVar[str] = "https://aws.amazon.com/api/dirs/items/search"
    YEAR_TAG: ClassVar[AwsTagNamespace] = AwsTagNamespace.YEAR
    CATEGORY_TAG: ClassVar[AwsTagNamespace] = AwsTagNamespace.TECHNOLOGY_CATEGORY
    PAGE_SIZE: ClassVar[int] = 500
    QUERY: ClassVar[Dict[str, str]] = {
        AwsDirectoryParameter.DIRECTORY_ID: AwsDirectoryParameterValue.PRODUCTS_DIRECTORY,
        AwsDirectoryParameter.LOCALE: AwsDirectoryParameterValue.ENGLISH,
        AwsDirectoryParameter.SORT_BY: AwsDirectoryParameterValue.TITLE_FIELD,
        AwsDirectoryParameter.SORT_ORDER: AwsDirectoryParameterValue.ASCENDING,
        AwsDirectoryParameter.SIZE: str(PAGE_SIZE),
    }
    DOCS_URL: ClassVar[str] = "https://docs.aws.amazon.com/"
    DOCS_EXCLUDED_SECTIONS: ClassVar[FrozenSet[AwsDocsSection]] = frozenset(
        {
            AwsDocsSection.DECISION_GUIDES,
            AwsDocsSection.SDK_TOOLKITS,
            AwsDocsSection.GENERAL_REFERENCE,
            AwsDocsSection.ADDITIONAL_RESOURCES,
            AwsDocsSection.FEATURED_SERVICES,
            AwsDocsSection.CONSOLE,
            AwsDocsSection.CUSTOMER_ENABLEMENT,
        }
    )
    DOCS_NOT_SERVICE: ClassVar[re.Pattern[str]] = re.compile(
        r"^Choosing|\?$|SDK for|Toolkit for|Tools for|Guide$|Reference", re.IGNORECASE
    )
    DOCS_HOST: ClassVar[str] = "docs.aws.amazon.com"
    DOCS_APP_SCRIPT: ClassVar[str] = "**/awsdocs-main-landing-page*.js"
    DOCS_SECTION_TAG: ClassVar[AwsHtmlTag] = AwsHtmlTag.ARTICLE
    WHATS_NEW_PAGE_SIZE: ClassVar[int] = 2000
    WHATS_NEW_MAX_PAGES: ClassVar[int] = 5
    WHATS_NEW_YEAR_TAG: ClassVar[str] = "whats-new-v2#year#{year}"
    WHATS_NEW_QUERY: ClassVar[Dict[str, str]] = {
        AwsDirectoryParameter.DIRECTORY_ID: AwsDirectoryParameterValue.WHATS_NEW_DIRECTORY,
        AwsDirectoryParameter.LOCALE: AwsDirectoryParameterValue.ENGLISH,
        AwsDirectoryParameter.SORT_BY: AwsDirectoryParameterValue.POST_DATE_FIELD,
        AwsDirectoryParameter.SORT_ORDER: AwsDirectoryParameterValue.ASCENDING,
        AwsDirectoryParameter.SIZE: str(WHATS_NEW_PAGE_SIZE),
    }
    WHATS_NEW_START: ClassVar[datetime] = datetime(2004, 10, 1, tzinfo=UTC)
    TAGGED_SINCE: ClassVar[datetime] = datetime(2015, 1, 1, tzinfo=UTC)
    SLUG_SEPARATOR: ClassVar[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")
    PRICE_HOST: ClassVar[str] = "https://pricing.us-east-1.amazonaws.com"
    OFFER_INDEX_URL: ClassVar[str] = f"{PRICE_HOST}/offers/v1.0/aws/index.json"
    PRICE_FILE_URL: ClassVar[str] = PRICE_HOST + "/offers/v1.0/aws/{offer}/current/{region}/index.csv"
    PRICE_OFFER: ClassVar[str] = "price_offer"
    PRICE_SAVINGS: ClassVar[str] = "price_savings"
    SAVINGS_FILE_URL: ClassVar[str] = PRICE_HOST + "/savingsPlan/v1.0/aws/{offer}/current/{region}/index.csv"
    SAVINGS_FAMILY: ClassVar[re.Pattern[str]] = re.compile(r"/savingsPlan/v1\.0/aws/([^/]+)/")
    EC2_OFFER: ClassVar[str] = "AmazonEC2"
    SAVINGS_KEPT_OPERATION: ClassVar[str] = "RunInstances"
    SAVINGS_KEPT_USAGE: ClassVar[str] = "BoxUsage"
    SAVINGS_TERMS: ClassVar[Dict[Tuple[str, str], PriceTerm]] = {
        ("1", "year"): PriceTerm.ONE_YEAR,
        ("3", "year"): PriceTerm.THREE_YEARS,
    }
    VERSION: ClassVar[re.Pattern[str]] = re.compile(r"/(\d{14})/")
    JSON_FILE: ClassVar[str] = "index.json"
    CSV_FILE: ClassVar[str] = "index.csv"
    PRICE_UNITS: ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit], ...]] = (
        (re.compile(r"\btokens?\b", re.IGNORECASE), PriceUnit.TOKEN),
        (re.compile(r"vCPU[- ]?(?:Hours?|hour|Hrs?)\b", re.IGNORECASE), PriceUnit.VCPU_HOUR),
        (re.compile(r"vCPU[- ]?Seconds?\b", re.IGNORECASE), PriceUnit.VCPU_SECOND),
        (re.compile(r"GB[- ]?Seconds?\b", re.IGNORECASE), PriceUnit.GIB_SECOND),
        (re.compile(r"GB[- ]?Hours?\b", re.IGNORECASE), PriceUnit.GIB_HOUR),
        (re.compile(r"^(?:GB[- ]?Mo(?:nth)?|GigaBytesMonth)$", re.IGNORECASE), PriceUnit.GIB_MONTH),
        (re.compile(r"^(?:GB|GigaBytes|Gigabytes|Processed-Gigabytes)$", re.IGNORECASE), PriceUnit.GIB),
        (re.compile(r"^(?:Hrs?|Hours?|Hourly)$", re.IGNORECASE), PriceUnit.HOUR),
        (re.compile(r"[- ](?:Hrs?|Hours?|hour)$|^TrainingHour$", re.IGNORECASE), PriceUnit.UNIT_HOUR),
        (re.compile(r"^seconds?$", re.IGNORECASE), PriceUnit.SECOND),
        (re.compile(r"^minutes?$", re.IGNORECASE), PriceUnit.MINUTE),
        (re.compile(r"-Mo$|-month$", re.IGNORECASE), PriceUnit.UNIT_MONTH),
        (re.compile(r"^Images?\b", re.IGNORECASE), PriceUnit.IMAGE),
        (re.compile(r"Characters?\b", re.IGNORECASE), PriceUnit.CHARACTER),
        (
            re.compile(
                r"Requests?|RequestUnits|Notifications|Messages|IOs|Objects|Updates|Connections|Operations|Analyses|"
                r"Jobs|Keys|Events|Invocations|Queries",
                re.IGNORECASE,
            ),
            PriceUnit.REQUEST,
        ),
        (re.compile(r"^Quantity$", re.IGNORECASE), PriceUnit.UNIT),
    )
    UNIT_COUNT: ClassVar[re.Pattern[str]] = re.compile(r"^(?:Per\s+)?(\d[\d,]*)\s*([KM])?\b", re.IGNORECASE)
    MULTIPLIERS: ClassVar[Dict[str, int]] = {"K": 1000, "k": 1000, "M": 1_000_000, "m": 1_000_000}
    COUNTABLE_UNITS: ClassVar[FrozenSet[PriceUnit]] = frozenset(
        {PriceUnit.TOKEN, PriceUnit.REQUEST, PriceUnit.IMAGE, PriceUnit.CHARACTER}
    )
    LEASE_TERMS: ClassVar[Dict[str, PriceTerm]] = {
        AwsLeaseLength.ONE_YEAR: PriceTerm.ONE_YEAR,
        AwsLeaseLength.THREE_YEARS: PriceTerm.THREE_YEARS,
    }
    UPFRONT: ClassVar[re.Pattern[str]] = re.compile(r"\bUpfront Fee\b", re.IGNORECASE)
    GIB: ClassVar[re.Pattern[str]] = re.compile(r"^([\d.,]+)\s*GiB\b")
    NUMBER: ClassVar[re.Pattern[str]] = re.compile(r"^\d+(?:\.\d+)?$")
    NOT_APPLICABLE: ClassVar[str] = "NA"
    NO_UNIT: ClassVar[str] = "none"
    ATTRIBUTE_LENGTH: ClassVar[int] = 300
    KEPT_COLUMNS: ClassVar[Tuple[AwsPriceColumn, ...]] = (
        AwsPriceColumn.PRICE_DESCRIPTION,
        AwsPriceColumn.LOCATION,
        AwsPriceColumn.TENANCY,
        AwsPriceColumn.LICENSE_MODEL,
        AwsPriceColumn.PRE_INSTALLED_SW,
        AwsPriceColumn.PURCHASE_OPTION,
        AwsPriceColumn.OFFERING_CLASS,
        AwsPriceColumn.USAGE_TYPE,
        AwsPriceColumn.OPERATION,
    )

    name = "aws"
    catalogue_url: ClassVar[str] = f"{API_URL}?{urlencode({**QUERY, AwsDirectoryParameter.PAGE: 0})}"
    complement_urls: ClassVar[Tuple[str, ...]] = (DOCS_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Amazon ", "AWS ")
    dates_launches: ClassVar[bool] = True
    launch_feed_start: ClassVar[Optional[datetime]] = datetime(2007, 1, 1, tzinfo=UTC)

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.whats_new: Optional[Dict[str, datetime]] = None
        self.headlines: List[Tuple[str, datetime]] = []

    ############################
    # Internal Helpers Methods #
    ############################

    def _slug(self, text: str) -> str:
        """Write a product name or page slug as a What's New product tag.

        Args:
            text (str): The name or slug, e.g. `AWS Backup`.

        Returns:
            str: The tag, e.g. `aws-backup`.
        """
        return self.SLUG_SEPARATOR.sub("-", text.casefold()).strip("-")

    def _announcement(self, entry: Dict[str, JsonValue]) -> Optional[Tuple[List[str], str, datetime]]:
        """Read the product tags, the headline and the date of a What's New announcement.

        Args:
            entry (Dict[str, JsonValue]): The directory entry (its item and its tags).

        Returns:
            Optional[Tuple[List[str], str, datetime]]: Its product tags, its headline (lower-case) and its date in
                UTC, `None` when the date is unreadable or implausible.
        """
        fields = self._as_object(
            self._as_object(entry.get(AwsDirectoryField.ITEM)).get(AwsDirectoryField.ADDITIONAL_FIELDS)
        )
        raw = self._as_text(fields.get(AwsWhatsNewField.POST_DATE_TIME)) or ""
        try:
            date = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            self.logger.debug("Ignoring the unreadable What's New date %r.", raw)
            return None
        if not self.WHATS_NEW_START <= date <= datetime.now(UTC) + timedelta(days=1):
            self.logger.debug("Ignoring the implausible What's New date %s.", date.isoformat())
            return None
        tags = entry.get(AwsDirectoryField.TAGS)
        products = [
            str(tag.get(AwsTagField.NAME))
            for tag in (tags if isinstance(tags, list) else [])
            if isinstance(tag, dict) and tag.get(AwsTagField.TAG_NAMESPACE_ID) == AwsTagNamespace.WHATS_NEW_PRODUCT
        ]
        headline = self._clean_text(self._as_text(fields.get(AwsWhatsNewField.HEADLINE))).casefold()
        return products, headline, date

    async def _read_whats_new(self) -> Dict[str, datetime]:
        """Read What's New year after year, page after page: the first announcement of each product tag.

        Returns:
            Dict[str, datetime]: The first announcement of each product tag (the headlines are kept apart), empty
                when the source cannot be read.
        """
        launches: Dict[str, datetime] = {}
        read = 0
        for year in range(self.WHATS_NEW_START.year, datetime.now(UTC).year + 1):
            for page in range(self.WHATS_NEW_MAX_PAGES):
                query = {
                    **self.WHATS_NEW_QUERY,
                    AwsDirectoryParameter.TAG_ID: self.WHATS_NEW_YEAR_TAG.format(year=year),
                    AwsDirectoryParameter.PAGE: str(page),
                }
                response = await self._fetch_launch_page(self.API_URL, query)
                if response is None:
                    self.logger.warning(
                        "The What's New page %d of %d cannot be read: that year stops there.", page, year
                    )
                    break
                entries = self._as_object(self._json_body(response)).get(AwsDirectoryField.ITEMS)
                entries = entries if isinstance(entries, list) else []
                for entry in entries:
                    announcement = self._announcement(self._as_object(entry))
                    if announcement is None:
                        continue
                    products, headline, date = announcement
                    for tag in products:
                        launches[tag] = min(date, launches.get(tag, date))
                    self.headlines.append((headline, date))
                read += len(entries)
                if len(entries) < self.WHATS_NEW_PAGE_SIZE:
                    break
        self.headlines.sort(key=lambda pair: pair[1])
        self.logger.info("%d What's New announcements read: %d product tags.", read, len(launches))
        return launches

    def _product_tags(self, product: CloudProduct, alias: Optional[str]) -> Set[str]:
        """Get the What's New product tags a product may have.

        Args:
            product (CloudProduct): The product.
            alias (Optional[str]): The name What's New gives it, when the launch dates catalogue gives one.

        Returns:
            Set[str]: The tags of its names (`aws-backup`, without the abbreviation in parentheses too) and of its
                page slug (`backup`, `aws-backup`, `amazon-backup`).
        """
        names = [product.name, *([alias] if alias else [])]
        tags = {self._slug(name) for name in names} | {self._slug(name.split("(")[0]) for name in names}
        slug = urlparse(product.url).path.strip("/").split("/")[0] if product.url else ""
        if slug:
            tags |= {slug, f"aws-{slug}", f"amazon-{slug}"}
        return {tag for tag in tags if tag}

    async def _launch_source(self, product: CloudProduct) -> Optional[Tuple[datetime, DateCaveat]]:
        """Read the launch of a product from its first What's New announcement.

        Args:
            product (CloudProduct): The product, undated or dated by its year only.

        Returns:
            Optional[Tuple[datetime, DateCaveat]]: The launch and its caveat, `None` when no announcement is tagged
                with the product nor names it in its headline. The earlier of the first tagged announcement and the
                first headline naming it wins (a product first tagged before `TAGGED_SINCE` by the headlines only).
        """
        if self.whats_new is None:
            self.whats_new = await self._read_whats_new()
        alias = self.launch_aliases.get(self._name_key(product.name))
        tagged = [self.whats_new[tag] for tag in self._product_tags(product, alias) if tag in self.whats_new]
        dates = (
            [date for date in tagged if date >= self.TAGGED_SINCE]
            if len(tagged) and min(tagged) >= self.TAGGED_SINCE
            else []
        )
        names = [name.casefold() for name in (product.name.split("(")[0].strip(), alias) if name]
        patterns = [re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])") for name in names]
        named = next((date for headline, date in self.headlines if any(p.search(headline) for p in patterns)), None)
        found = min([*dates, *([named] if named is not None else [])], default=None)
        if found is None:
            self.logger.debug("No What's New announcement names %r.", product.name)
            return None
        return self._announced(found)

    def _url_key(self, url: str) -> str:
        """Compare a service documentation with the product page of the same slug.

        Args:
            url (str): The absolute product URL.

        Returns:
            str: The product page key of the service slug for the documentation pages (`docs.aws.amazon.com/ec2/...`
                is compared as `aws.amazon.com/ec2`), the generic URL key otherwise.
        """
        link = urlparse(url.casefold())
        slug = link.path.strip("/").split("/")[0]
        if link.netloc == self.DOCS_HOST and slug:
            return f"aws.amazon.com/{slug}"
        return super()._url_key(url)

    async def _abort(self, route: Route) -> None:
        """Abort a browser request.

        Args:
            route (Route): The intercepted browser request.
        """
        await route.abort()

    async def _keep_server_rendered_list(self, page: Page) -> None:
        """Block the documentation page script, before navigation, so that its full list is kept.

        Args:
            page (Page): The browser page.
        """
        await page.route(self.DOCS_APP_SCRIPT, self._abort)

    def _complement_request(self, url: str) -> Request:
        """Build the documentation home page request, without the script hiding its full list.

        Args:
            url (str): The documentation home page.

        Returns:
            Request: The request, blocking the documentation page script.
        """
        return Request(url, page_setup=self._keep_server_rendered_list)

    def _html_to_text(self, fragment: Optional[str]) -> Optional[str]:
        """Get the text of an HTML fragment, as some descriptions are HTML paragraphs.

        Args:
            fragment (Optional[str]): The HTML fragment.

        Returns:
            Optional[str]: The fragment text, `None` when missing.
        """
        if fragment is None:
            return None
        return Selector(f"<div>{fragment}</div>").get_all_text(separator=" ", strip=True)

    def _product_link(self, link: Optional[str]) -> Optional[str]:
        """Get the absolute URL of a product page, ignoring the links without a product slug (e.g. `#`).

        Args:
            link (Optional[str]): The raw product link.

        Returns:
            Optional[str]: The absolute product URL, `None` without a product slug.
        """
        url = urljoin("https://aws.amazon.com/", link or "")
        if not urlparse(url).path.strip("/"):
            self.logger.debug("Ignoring the %s link %r without a product slug.", self.name, link)
            return None
        return url

    def _catalogue_page(self, response: Response) -> Dict[str, JsonValue]:
        """Read a catalogue page.

        Args:
            response (Response): The catalogue page.

        Returns:
            Dict[str, JsonValue]: The page data.

        Raises:
            CatalogueFormatError: If the page is not a JSON object.
        """
        try:
            data: JsonValue = response.json()
        except ValueError as e:
            self.logger.error("The %s catalogue page %s is not JSON: %s", self.name, response.url, e)
            raise CatalogueFormatError(self.name, response.url, "the page is not JSON") from e
        if not isinstance(data, dict):
            self.logger.error("The %s catalogue page %s is not a JSON object.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the page is not a JSON object")
        return data

    def _next_page_url(self, response: Response) -> Optional[str]:
        """Get the URL of the next catalogue page.

        Args:
            response (Response): The current catalogue page.

        Returns:
            Optional[str]: The next page URL, `None` on the last page.
        """
        total = self._as_object(self._catalogue_page(response).get(AwsDirectoryField.METADATA)).get(
            AwsDirectoryField.TOTAL_HITS
        )
        page = int(
            parse_qs(urlparse(response.url).query).get(
                AwsDirectoryParameter.PAGE, [AwsDirectoryParameterValue.FIRST_PAGE]
            )[0]
        )
        if not isinstance(total, int) or (page + 1) * self.PAGE_SIZE >= total:
            self.logger.debug("Page %d is the last catalogue page (%s products in total).", page, total)
            return None
        return f"{self.API_URL}?{urlencode({**self.QUERY, AwsDirectoryParameter.PAGE: page + 1})}"

    def _launch_year(self, entry: Dict[str, JsonValue], name: Optional[str]) -> Optional[datetime]:
        """Get the launch year of a directory entry, from its year tag.

        Args:
            entry (Dict[str, JsonValue]): The directory entry.
            name (Optional[str]): The product, for the logs.

        Returns:
            Optional[datetime]: The 1st of January of the launch year, `None` without a year tag.
        """
        tags = entry.get(AwsDirectoryField.TAGS)
        for tag in tags if isinstance(tags, list) else []:
            fields = self._as_object(tag)
            year = self._as_text(fields.get(AwsTagField.NAME)) or ""
            if fields.get(AwsTagField.TAG_NAMESPACE_ID) == self.YEAR_TAG and year.isdigit():
                self.logger.debug("Launch year %s of the %s product %r.", year, self.name, name)
                return self._parse_date(f"{year}-01-01", name)
        self.logger.debug("No launch year tag for the %s product %r.", self.name, name)
        return None

    def _badge_categories(self, badge: Optional[str], name: Optional[str]) -> List[str]:
        """Read the category badge of a directory card, a JSON text such as `{"value": ["Compute"]}`.

        Args:
            badge (Optional[str]): The raw badge.
            name (Optional[str]): The product, for the logs.

        Returns:
            List[str]: The badge labels, empty when missing or unreadable.
        """
        if not badge:
            return []
        try:
            value: JsonValue = json.loads(badge)
        except ValueError:
            self.logger.debug("Ignoring the unreadable category badge %r of %r.", badge, name)
            return []
        labels = self._as_object(value).get(AwsBadgeField.VALUE)
        return [label for label in labels if isinstance(label, str)] if isinstance(labels, list) else []

    def _directory_categories(self, entry: Dict[str, JsonValue], name: Optional[str]) -> List[str]:
        """Get the categories of a directory entry: its technology category tags, else its card badge.

        Args:
            entry (Dict[str, JsonValue]): The directory entry.
            name (Optional[str]): The product, for the logs.

        Returns:
            List[str]: The category labels, empty when the entry has none.
        """
        tags = entry.get(AwsDirectoryField.TAGS)
        categories = [
            self._as_text(fields.get(AwsTagField.NAME)) or ""
            for fields in (self._as_object(tag) for tag in (tags if isinstance(tags, list) else []))
            if fields.get(AwsTagField.TAG_NAMESPACE_ID) == self.CATEGORY_TAG
        ]
        if any(categories):
            return categories
        self.logger.debug("No category tag for the %s product %r, reading its card badge.", self.name, name)
        item = self._as_object(entry.get(AwsDirectoryField.ITEM))
        fields = self._as_object(item.get(AwsDirectoryField.ADDITIONAL_FIELDS))
        return self._badge_categories(self._as_text(fields.get(AwsCardField.BADGE)), name)

    def _docs_category(self, card: Selector) -> Optional[str]:
        """Get the category of a documentation entry: the title of the section listing it.

        Args:
            card (Selector): The documentation entry.

        Returns:
            Optional[str]: The section title, `None` when the entry is not in a titled section.
        """
        for ancestor in card.iterancestors():
            if ancestor.tag == self.DOCS_SECTION_TAG:
                title = ancestor.css("h3").first
                return title.get_all_text(separator=" ", strip=True) if title is not None else None
        self.logger.debug("A %s documentation entry is not in a titled section.", self.name)
        return None

    def _directory_entries(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of a directory page.

        Args:
            response (Response): The directory page.

        Yields:
            Iterator[CloudProduct]: Each valid entry of the page.

        Raises:
            CatalogueFormatError: If the page has no `items` list.
        """
        items = self._catalogue_page(response).get(AwsDirectoryField.ITEMS)
        if not isinstance(items, list):
            self.logger.error("The %s catalogue page %s has no `items` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "`items` is not a list")
        self.logger.debug("%d catalogue entries in %s.", len(items), response.url)
        for entry in items:
            data = self._as_object(self._as_object(entry).get(AwsDirectoryField.ITEM))
            fields = self._as_object(data.get(AwsDirectoryField.ADDITIONAL_FIELDS))
            name = self._as_text(fields.get(AwsCardField.TITLE))
            description = self._html_to_text(self._as_text(fields.get(AwsCardField.BODY)))
            url = self._product_link(self._as_text(fields.get(AwsCardField.CTA_LINK)))
            added_at, added_caveat = self._launch_year(self._as_object(entry), name), DateCaveat.YEAR_ONLY
            if added_at is None:
                published = fields.get(AwsCardField.PUBLISHED_DATE)
                added_at, added_caveat = self._parse_date(published, name), DateCaveat.CATALOGUE_ENTRY
            updated_at = self._parse_date(data.get(AwsDirectoryField.DATE_UPDATED), name)
            dates = (added_at, updated_at, added_caveat, DateCaveat.CATALOGUE_ENTRY)
            categories = self._directory_categories(self._as_object(entry), name)
            if product := self._build_product(name, description, url, *dates, categories=categories):
                yield product

    def _directory_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of a directory page.

        Args:
            response (Response): The directory page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the page, with the categories of all its entries.

        Raises:
            CatalogueFormatError: If the page has no `items` list.
        """
        yield from self._merge_categories(self._directory_entries(response))

    def _docs_entries(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the entries of the documentation home page, skipping the guides, SDKs and tools sections.

        Args:
            response (Response): The documentation home page.

        Yields:
            Iterator[CloudProduct]: Each valid service entry, with the title of its section.
        """
        cards = response.css("li.awsdocs-card-list-item")
        self.logger.debug("%d documentation entries in %s.", len(cards), response.url)
        for card in cards:
            link = card.css("a.awsdocs-link").first
            abstract = card.css(".awsdocs-card-list-abstract").first
            if link is None or abstract is None:
                continue
            href = link.attrib.get(HtmlAttribute.HREF, "")
            campaign = parse_qs(urlparse(href).query).get(AwsDocsLink.CAMPAIGN, [""])[0]
            section = campaign.removeprefix(AwsDocsLink.HOMEPAGE_PREFIX)
            name = self._clean_text(link.get_all_text(separator=" ", strip=True))
            if section in self.DOCS_EXCLUDED_SECTIONS or self.DOCS_NOT_SERVICE.search(name):
                self.logger.debug("Skipping the documentation entry %r (%s), not a service.", name, section)
                continue
            description = abstract.get_all_text(separator=" ", strip=True)
            url = urljoin(response.url, href)
            if product := self._build_product(name, description, url, categories=[self._docs_category(card)]):
                yield product

    def _docs_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the services of the documentation home page.

        Args:
            response (Response): The documentation home page.

        Yields:
            Iterator[CloudProduct]: Each valid service of the page, with the titles of all the sections listing it.
        """
        yield from self._merge_categories(self._docs_entries(response))

    def _price_unit(self, unit: str, upfront: bool) -> Tuple[PriceUnit, Decimal]:
        """Normalize what an AWS price is per.

        Args:
            unit (str): The unit of the price file, e.g. `Hrs`, `GB-Mo`, `1K tokens`, `Per 1000 requests`.
            upfront (bool): Whether the price is the upfront fee of a reservation (a one-time charge).

        Returns:
            Tuple[PriceUnit, Decimal]: The unit of the first matching `PRICE_UNITS` rule, other when none matches,
                and the count it starts with for a countable unit (`1K tokens` is 1,000).
        """
        if upfront:
            return PriceUnit.ONE_TIME, Decimal(1)
        for pattern, normalized in self.PRICE_UNITS:
            if not pattern.search(unit):
                continue
            count = self.UNIT_COUNT.match(unit)
            if normalized in self.COUNTABLE_UNITS and count is not None:
                return normalized, Decimal(count[1].replace(",", "")) * self.MULTIPLIERS.get(count[2] or "", 1)
            return normalized, Decimal(1)
        self.logger.debug("The AWS price unit %r has no known unit: kept as other.", unit)
        return PriceUnit.OTHER, Decimal(1)

    def _row_price(self, row: Dict[str, str], offer: str, region: str, source: str) -> Optional[ServicePrice]:
        """Read the price of a row of a price file.

        Args:
            row (Dict[str, str]): The row, by column.
            offer (str): The offer of the file, e.g. `AmazonEC2`.
            region (str): The region of the file.
            source (str): The stable URL of the file (its source).

        Returns:
            Optional[ServicePrice]: Its price, `None` for a reservation accounting line of EC2 or a malformed row.
        """
        status = row.get(AwsPriceColumn.CAPACITY_STATUS)
        if status and status != AwsCapacityStatus.USED and status != self.NOT_APPLICABLE:
            return None
        try:
            price = Decimal(row.get(AwsPriceColumn.PRICE_PER_UNIT) or "")
        except ArithmeticError:
            self.logger.debug("An AWS %s row of %s has no price: skipped.", offer, region)
            return None
        reserved = row.get(AwsPriceColumn.TERM_TYPE) == AwsTermType.RESERVED
        unit_text = row.get(AwsPriceColumn.UNIT) or ""
        upfront = reserved and self.UPFRONT.search(row.get(AwsPriceColumn.PRICE_DESCRIPTION) or "") is not None
        unit, factor = self._price_unit(unit_text, upfront)
        vcpu = row.get(AwsPriceColumn.VCPU) or ""
        memory = self.GIB.search(row.get(AwsPriceColumn.MEMORY) or "")
        ending = row.get(AwsPriceColumn.ENDING_RANGE) or ""
        starting = row.get(AwsPriceColumn.STARTING_RANGE) or "0"
        rate = (
            row.get(AwsPriceColumn.RATE_CODE)
            or f"{row.get(AwsPriceColumn.SKU)}.{row.get(AwsPriceColumn.OFFER_TERM_CODE)}"
        )
        fields: Dict[str, RawValue] = {
            "sku_key": rate,
            "service": row.get(AwsPriceColumn.SERVICE_NAME) or offer,
            "family": row.get(AwsPriceColumn.PRODUCT_FAMILY) or None,
            "region": region,
            "instance_type": row.get(AwsPriceColumn.INSTANCE_TYPE) or None,
            "vcpu": vcpu if vcpu.isdigit() and int(vcpu) > 0 else None,
            "memory_gib": memory[1].replace(",", "") if memory else None,
            "os": row.get(AwsPriceColumn.OPERATING_SYSTEM) or row.get(AwsPriceColumn.DATABASE_ENGINE) or None,
            "attributes": {
                column.value: value[: self.ATTRIBUTE_LENGTH]
                for column in self.KEPT_COLUMNS
                if (value := row.get(column) or "") and value != self.NOT_APPLICABLE
            },
            "unit": unit,
            "unit_raw": unit_text or self.NO_UNIT,
            "unit_factor": factor,
            "price": price,
            "currency": row.get(AwsPriceColumn.CURRENCY) or None,
            "model": PriceModel.FREE if price == 0 else PriceModel.RESERVED if reserved else PriceModel.ON_DEMAND,
            "term": self.LEASE_TERMS.get(row.get(AwsPriceColumn.LEASE_CONTRACT_LENGTH) or "", PriceTerm.NONE),
            "tier_start": starting if self.NUMBER.match(starting) else "0",
            "tier_end": ending if self.NUMBER.match(ending) and Decimal(ending) > Decimal(starting or 0) else None,
            "effective_from": row.get(AwsPriceColumn.EFFECTIVE_DATE) or None,
            "source_url": source,
            "source_kind": PriceSourceKind.API,
        }
        return self._price_fact(fields)

    def _savings_row_price(self, row: Dict[str, str], region: str, source: str) -> Optional[ServicePrice]:
        """Read the rate of a row of a savings plan price file.

        Args:
            row (Dict[str, str]): The row, by column.
            region (str): The region of the file.
            source (str): The stable URL of the file (its source).

        Returns:
            Optional[ServicePrice]: Its rate, `None` for an EC2 usage other than a Linux instance of shared tenancy
                (`SAVINGS_KEPT_OPERATION`, `SAVINGS_KEPT_USAGE`) or a malformed row.
        """
        service = row.get(AwsSavingsColumn.DISCOUNTED_SERVICE_CODE) or ""
        usage = row.get(AwsSavingsColumn.DISCOUNTED_USAGE_TYPE) or ""
        operation = row.get(AwsSavingsColumn.DISCOUNTED_OPERATION) or ""
        if service == self.EC2_OFFER and (
            operation != self.SAVINGS_KEPT_OPERATION or self.SAVINGS_KEPT_USAGE not in usage.split(":", 1)[0]
        ):
            return None
        try:
            price = Decimal(row.get(AwsSavingsColumn.DISCOUNTED_RATE) or "")
        except ArithmeticError:
            self.logger.debug("A savings plan row of %s has no rate: skipped.", region)
            return None
        unit_text = row.get(AwsSavingsColumn.UNIT) or ""
        unit, factor = self._price_unit(unit_text, False)
        length = (
            row.get(AwsSavingsColumn.LEASE_CONTRACT_LENGTH) or "",
            row.get(AwsSavingsColumn.LEASE_CONTRACT_LENGTH_UNIT) or "",
        )
        fields: Dict[str, RawValue] = {
            "sku_key": row.get(AwsSavingsColumn.RATE_CODE),
            "service": service,
            "family": row.get(AwsSavingsColumn.PRODUCT_FAMILY) or None,
            "region": row.get(AwsSavingsColumn.DISCOUNTED_REGION_CODE) or region,
            "instance_type": row.get(AwsSavingsColumn.DISCOUNTED_INSTANCE_TYPE) or None,
            "attributes": {
                column.value: value[: self.ATTRIBUTE_LENGTH]
                for column in (
                    AwsSavingsColumn.PURCHASE_OPTION,
                    AwsSavingsColumn.DESCRIPTION,
                    AwsSavingsColumn.DISCOUNTED_USAGE_TYPE,
                    AwsSavingsColumn.DISCOUNTED_OPERATION,
                )
                if (value := row.get(column) or "")
            },
            "unit": unit,
            "unit_raw": unit_text or self.NO_UNIT,
            "unit_factor": factor,
            "price": price,
            "currency": row.get(AwsSavingsColumn.CURRENCY) or None,
            "model": PriceModel.SAVINGS_PLAN,
            "term": self.SAVINGS_TERMS.get(length, PriceTerm.NONE),
            "effective_from": (row.get(AwsSavingsColumn.EFFECTIVE_DATE) or "")[:10] or None,
            "source_url": source,
            "source_kind": PriceSourceKind.API,
        }
        return self._price_fact(fields)

    async def _file_prices(
        self, url: str, offer: str, region: str, source: str, savings: bool = False
    ) -> AsyncGenerator[ServicePrice]:
        """Stream the prices of a CSV price file, row by row.

        Args:
            url (str): The versioned file.
            offer (str): Its offer.
            region (str): Its region.
            source (str): Its stable URL (the source of its prices).
            savings (bool): Whether it is a savings plan file (rates of discounted usages).

        Yields:
            ServicePrice: The price of each row.

        Raises:
            PriceDownloadError: If the file cannot be downloaded.
        """
        header: Optional[List[str]] = None
        pending = ""
        async for line in self._stream_lines(url):
            pending = f"{pending}\n{line}" if pending else line
            if pending.count('"') % 2:
                continue
            cells = next(csv.reader([pending]), [])
            pending = ""
            if header is None:
                if cells and cells[0] == AwsPriceColumn.SKU:
                    header = cells
                continue
            if len(cells) != len(header):
                continue
            row = dict(zip(header, cells, strict=True))
            fact = (
                self._savings_row_price(row, region, source) if savings else self._row_price(row, offer, region, source)
            )
            if fact is not None:
                yield fact
        if header is None:
            self.logger.warning("The AWS price file %s has no header row.", url)

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the offer index of the Price List bulk API.

        Yields:
            Request: The request of the offer index.
        """
        self.logger.info("Reading the AWS prices from %s.", self.OFFER_INDEX_URL)
        yield self._price_request(self.OFFER_INDEX_URL, {self.PRICE_OFFER: ""})

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the offer index (requesting each region index), or a region index (streaming each changed file).

        Args:
            response (Response): The offer index or the region index of an offer.

        Yields:
            PriceFact: The region index requests (of the offers and of the savings plans), or the prices of the
                region files of an offer or of a savings plan.

        Raises:
            CatalogueFormatError: If an index is not a JSON object.
        """
        data = self._json_body(response)
        if not isinstance(data, dict):
            self.logger.error("The AWS index %s is not an object.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the index is not a JSON object")
        offer = str(response.meta.get(self.PRICE_OFFER) or "")
        if not offer:
            offers = data.get(AwsOfferField.OFFERS)
            plans: Set[str] = set()
            for code, entry in (offers if isinstance(offers, dict) else {}).items():
                index = entry.get(AwsOfferField.CURRENT_REGION_INDEX_URL) if isinstance(entry, dict) else None
                if isinstance(index, str):
                    yield self._price_request(urljoin(self.PRICE_HOST, index), {self.PRICE_OFFER: code})
                plan = entry.get(AwsOfferField.CURRENT_SAVINGS_PLAN_INDEX_URL) if isinstance(entry, dict) else None
                family = self.SAVINGS_FAMILY.search(plan) if isinstance(plan, str) else None
                if isinstance(plan, str) and family is not None and family[1] not in plans:
                    plans.add(family[1])
                    yield self._price_request(
                        urljoin(self.PRICE_HOST, plan), {self.PRICE_OFFER: family[1], self.PRICE_SAVINGS: True}
                    )
            self.logger.info("The AWS offer index lists %d offers.", len(offers) if isinstance(offers, dict) else 0)
            return
        savings = response.meta.get(self.PRICE_SAVINGS) is True
        regions = data.get(AwsOfferField.REGIONS)
        entries: List[Tuple[str, JsonValue]] = (
            list(regions.items())
            if isinstance(regions, dict)
            else [
                (str(entry.get(AwsOfferField.REGION_CODE)), entry)
                for entry in (regions if isinstance(regions, list) else [])
                if isinstance(entry, dict)
            ]
        )
        for region, entry in entries:
            path = (
                entry.get(AwsOfferField.CURRENT_VERSION_URL) or entry.get(AwsOfferField.VERSION_URL)
                if isinstance(entry, dict)
                else None
            )
            version = self.VERSION.search(path) if isinstance(path, str) else None
            if not isinstance(path, str) or version is None:
                self.logger.warning("The AWS %s region %s has no versioned price file.", offer, region)
                continue
            template = self.SAVINGS_FILE_URL if savings else self.PRICE_FILE_URL
            source = template.format(offer=offer, region=region)
            if self._price_unchanged(source, version=version[1]):
                continue
            rows = 0
            try:
                async for fact in self._file_prices(
                    urljoin(self.PRICE_HOST, path.replace(self.JSON_FILE, self.CSV_FILE)),
                    offer,
                    region,
                    source,
                    savings,
                ):
                    rows += 1
                    yield fact
            except PriceDownloadError as e:
                self.logger.error("The AWS %s prices of %s are not read whole: %s", offer, region, e)
                self.price_failures.add(source)
                continue
            self._record_price_source(source, rows, version=version[1])
            self.logger.info("AWS %s prices of %s read: %d (version %s).", offer, region, rows, version[1])

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of a directory page or of the documentation home page.

        Args:
            response (Response): The catalogue page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.

        Raises:
            CatalogueFormatError: If a directory page has no `items` list.
        """
        if urlparse(response.url).netloc == self.DOCS_HOST:
            self.logger.debug("Extracting the %s products of the documentation page %s.", self.name, response.url)
            return self._docs_products(response)
        self.logger.debug("Extracting the %s products of the directory page %s.", self.name, response.url)
        return self._directory_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the products of a catalogue page, then request the next directory page if any.

        Args:
            response (Response): The catalogue page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, then the next page request.
        """
        async for item in super().parse(response):
            yield item
        if urlparse(response.url).netloc == self.DOCS_HOST:
            return
        if next_url := self._next_page_url(response):
            self.logger.info("Requesting the next %s catalogue page %s.", self.name, next_url)
            yield Request(next_url, priority=self.PRIMARY_PRIORITY)
