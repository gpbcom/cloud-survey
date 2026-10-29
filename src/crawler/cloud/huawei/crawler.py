from __future__ import annotations

# Standard Library Imports.
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.huawei.enums import (
    HuaweiBillingMode,
    HuaweiDocsCatalogueField,
    HuaweiDocsCategory,
    HuaweiDocsCategoryField,
    HuaweiDocsCode,
    HuaweiDocsEntryField,
    HuaweiPriceField,
    HuaweiProductSection,
    HuaweiReservedAmount,
)
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from models.cloud.enums import DateCaveat, PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class HuaweiCloudCrawler(BaseCloudCrawler):
    """Huawei Cloud (international website, in English) catalogue crawler.

    Attributes:
        DOCS_URL (ClassVar[str]): The documentation catalogue JSON, listing the documented services by category.
        DOCS_HOST (ClassVar[str]): The documentation website, whose pages describe the services without description.
        PRODUCT_CARDS (ClassVar[str]): The CSS selector of the product cards of the products page (desktop copy).
        SECTIONS (ClassVar[str]): The CSS selector of the category sections of the products page.
        SECTION_TITLE (ClassVar[str]): The CSS selector of the category title of a section.
        SUB_SECTIONS (ClassVar[str]): The CSS selector of the sub-category groups of a section (desktop copy).
        SUB_SECTION_TITLE (ClassVar[str]): The CSS selector of the sub-category title of a group, absent from the
            sections without sub-categories.
        CARD (ClassVar[str]): The CSS selector of a product card within a group.
        MARKETING_SECTIONS (ClassVar[FrozenSet[HuaweiProductSection]]): The sections of the products page which are
            not categories.
        DOCS_EXCLUDED_CATEGORIES (ClassVar[FrozenSet[HuaweiDocsCategory]]): The documentation categories which are
            not services.
        DOCS_EXCLUDED_CODES (ClassVar[FrozenSet[HuaweiDocsCode]]): The documentation entries which are guides, not
            services.
        DOCS_NOT_PRODUCT (ClassVar[re.Pattern[str]]): The documentation pages which are not services (decision
            guides).
        WHATS_NEW_URLS (ClassVar[Tuple[str, ...]]): The "What's New" pages of a service, from its documentation
            code: the Chinese website (generally the longer history), then the international one.
        WHATS_NEW_HEADINGS (ClassVar[str]): The CSS selector of the dated headings of a "What's New" page.
        PAGE_TITLE (ClassVar[str]): The CSS selector of the title of a "What's New" page.
        MISSING_PAGE_TITLE (ClassVar[str]): The title of a missing "What's New" page, served with HTTP 200.
        CHINESE_MONTH (ClassVar[re.Pattern[str]]): A month heading of the Chinese website, e.g. `2017年10月`.
        ENGLISH_MONTH_FORMAT (ClassVar[str]): The format of a month heading of the international website, e.g.
            `April 2018`.
        MENU_URL (ClassVar[str]): The menu of the price calculator API (no key): its services and their regions.
        PRODUCT_URL (ClassVar[str]): The prices of a service of the calculator in a region.
        PRICE_CURRENCY (ClassVar[str]): The currency of the international calculator.
        TIME_MEASURES (ClassVar[Dict[int, Tuple[PriceUnit, Decimal]]]): The unit of a time measure identifier.
        SIZED_TIME_UNITS (ClassVar[Dict[PriceUnit, PriceUnit]]): The unit of a time measure for a sized resource.
        MEASURES (ClassVar[Dict[int, Tuple[PriceUnit, Decimal]]]): The unit of another measure identifier, and the
            normalized units in one.
        SIZED (ClassVar[re.Pattern[str]]): The resource types priced by their size (volumes, storages).
        RESERVED_UNITS (ClassVar[Dict[str, PriceUnit]]): The unit of each amount of a reserved instance.
        TERMS (ClassVar[Dict[int, PriceTerm]]): The term of a subscription, by its months.
        MONTHS_PER_YEAR (ClassVar[int]): The months of a yearly subscription period.
        VCPUS (ClassVar[re.Pattern[str]]): The vCPUs of a written specification.
        MEMORY (ClassVar[re.Pattern[str]]): The memory of a written specification.
        MB (ClassVar[str]): The megabyte unit of a memory.
        GIB_PRECISION (ClassVar[Decimal]): The precision of a memory, in GiB.
        DESCRIPTION_LENGTH (ClassVar[int]): The longest specification kept.
        GLOBAL_REGION (ClassVar[str]): The region of a price without region.
        PATH_META (ClassVar[str]): The request meta holding the calculator code of a service.
        REGION_META (ClassVar[str]): The request meta holding the region.
        SERVICE_META (ClassVar[str]): The request meta holding the service name.
        CATEGORY_META (ClassVar[str]): The request meta holding the service category.
        whats_new_codes (Optional[Dict[str, str]]): The documentation code of each documented service, by
            normalized name, read once per crawl, `None` until read.
        price_pending (int): The calculator calls not answered yet, in price mode.
        price_rows (int): The prices read, in price mode.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): The catalogue product pages are read too, for their prices.
        PAGE_TEXT_PRICES (ClassVar[bool]): A product page without price table is read for the prices in its text.

    Notes:
        The main source is the https://www.huaweicloud.com/intl/en-us/product/ page, whose cards give the name,
        description and link of each product. The page holds a desktop and a mobile copy of every card: only the
        desktop copy is read. The documentation catalogue JSON completes it with the documented services missing
        from the products page, its solutions, cloud adoption, ecosystem, user support and miscellaneous
        categories, decision guides, SDK and signing guides excluded. The documentation page of a service without
        description is read for its meta description.
        The products page files its cards under categories (e.g. `Compute`), some split into sub-categories (e.g.
        `Containers & Middleware` > `Containers`): a product gets every category it is listed under, the `Featured`
        section excepted. A documented service gets its documentation category.
        No catalogue page dates the products: each product is dated by the earliest month of its "What's New" page
        (`dates_launches`), at `https://support.huaweicloud.com/wtsnew-<code>/index.html`, `<code>` being the
        documentation code of the service (e.g. `nosql` for GeminiDB), not the slug of its product page. The codes
        come from the documentation catalogue JSON, fetched once per crawl outside the crawl queue since the
        products page is parsed before it: a product is matched by its normalized name, else by the name the launch
        dates catalogue's aliases give it. The page lists the features by month, newest first, the launch being the
        earliest month (its first day). The Chinese website generally keeps the longer history, but some of its pages
        were cut (e.g. ModelArts from 2024): the earliest month of both the Chinese page and the international one
        (`April 2018` headings) is taken. A missing page is served with
        HTTP 200 and a `-` title: it dates nothing. The pages start in 2015 but most services were documented from
        2018: a product first listed before 2018 is likely older (`FEED_START`).
        In price mode it reads the price calculator API of the international website, in dollars: its menu lists
        the services and their regions, then each service is read in each region. Each resource has its plans: on
        demand (its unit from its measure identifier, per GiB for a volume or a storage), monthly and yearly
        subscriptions (per month, their factor being their months) and reserved instances (their effective hourly
        price, and their upfront price when any), a tiered plan expanding into its tiers. The calculator is one
        source, recorded once every call is answered.
    """

    DOCS_URL: ClassVar[str] = (
        "https://portal.huaweicloud.com/rest/cbc/portaldocdataservice/v1/books/items?appId=INTL-EN_US"
    )
    DOCS_HOST: ClassVar[str] = "support.huaweicloud.com"
    PRODUCT_CARDS: ClassVar[str] = "div.second-content.second-pc a.card"
    SECTIONS: ClassVar[str] = "div.first-content"
    SECTION_TITLE: ClassVar[str] = ".first-title"
    SUB_SECTIONS: ClassVar[str] = "div.second-content.second-pc div.second-flex"
    SUB_SECTION_TITLE: ClassVar[str] = ".second-title"
    CARD: ClassVar[str] = "a.card"
    MARKETING_SECTIONS: ClassVar[FrozenSet[HuaweiProductSection]] = frozenset({HuaweiProductSection.FEATURED})
    DOCS_EXCLUDED_CATEGORIES: ClassVar[FrozenSet[HuaweiDocsCategory]] = frozenset(HuaweiDocsCategory)
    DOCS_EXCLUDED_CODES: ClassVar[FrozenSet[HuaweiDocsCode]] = frozenset(HuaweiDocsCode)
    DOCS_NOT_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(r"/how-to-choose-")
    WHATS_NEW_URLS: ClassVar[Tuple[str, ...]] = (
        "https://support.huaweicloud.com/wtsnew-{code}/index.html",
        "https://support.huaweicloud.com/intl/en-us/wtsnew-{code}/index.html",
    )
    WHATS_NEW_HEADINGS: ClassVar[str] = "h4.sectiontitle"
    PAGE_TITLE: ClassVar[str] = "title"
    MISSING_PAGE_TITLE: ClassVar[str] = "-"
    CHINESE_MONTH: ClassVar[re.Pattern[str]] = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月")
    ENGLISH_MONTH_FORMAT: ClassVar[str] = "%B %Y"

    PRODUCT_PAGE_PRICES: ClassVar[bool] = True
    PAGE_TEXT_PRICES: ClassVar[bool] = True
    name = "huawei"
    catalogue_url: ClassVar[str] = "https://www.huaweicloud.com/intl/en-us/product/"
    complement_urls: ClassVar[Tuple[str, ...]] = (DOCS_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Huawei Cloud ", "HUAWEI CLOUD ", "Huawei ")
    dates_launches: ClassVar[bool] = True
    launch_feed_start: ClassVar[Optional[datetime]] = datetime(2018, 1, 1, tzinfo=UTC)
    MENU_URL: ClassVar[str] = (
        "https://portal-intl.huaweicloud.com/api/calculator/rest/cbc/portalcalculatornodeservice/v4/api/menuInfo"
        "?sign=common&language=en-us"
    )
    PRODUCT_URL: ClassVar[str] = (
        "https://portal-intl.huaweicloud.com/api/calculator/rest/cbc/portalcalculatornodeservice/v4/api/productInfo"
        "?urlPath={path}&tag=general.online.portal&region={region}&tab=calc&sign=common"
    )
    PRICE_CURRENCY: ClassVar[str] = "USD"
    TIME_MEASURES: ClassVar[Dict[int, Tuple[PriceUnit, Decimal]]] = {
        0: (PriceUnit.HOUR, Decimal(24)),
        4: (PriceUnit.HOUR, Decimal(1)),
        5: (PriceUnit.MINUTE, Decimal(1)),
        6: (PriceUnit.SECOND, Decimal(1)),
        20: (PriceUnit.MONTH, Decimal(1)),
        24: (PriceUnit.HOUR, Decimal(24)),
        25: (PriceUnit.HOUR, Decimal(1)),
    }
    SIZED_TIME_UNITS: ClassVar[Dict[PriceUnit, PriceUnit]] = {
        PriceUnit.HOUR: PriceUnit.GIB_HOUR,
        PriceUnit.MONTH: PriceUnit.GIB_MONTH,
        PriceUnit.SECOND: PriceUnit.GIB_SECOND,
    }
    MEASURES: ClassVar[Dict[int, Tuple[PriceUnit, Decimal]]] = {
        9: (PriceUnit.GIB, Decimal(1024)),
        10: (PriceUnit.GIB, Decimal(1)),
        11: (PriceUnit.GIB, Decimal(1) / Decimal(1024)),
        14: (PriceUnit.UNIT, Decimal(1)),
        17: (PriceUnit.GIB, Decimal(1)),
        19: (PriceUnit.YEAR, Decimal(1)),
        21: (PriceUnit.GIB, Decimal(1) / Decimal(1024)),
        23: (PriceUnit.VCPU_HOUR, Decimal(1)),
        30: (PriceUnit.UNIT, Decimal(1)),
        31: (PriceUnit.REQUEST, Decimal(1000)),
        32: (PriceUnit.REQUEST, Decimal(1_000_000)),
        33: (PriceUnit.REQUEST, Decimal(1_000_000_000)),
        39: (PriceUnit.GIB_SECOND, Decimal(1)),
        40: (PriceUnit.REQUEST, Decimal(1)),
        41: (PriceUnit.UNIT, Decimal(1)),
        42: (PriceUnit.UNIT, Decimal(1000)),
        43: (PriceUnit.UNIT, Decimal(1)),
        44: (PriceUnit.UNIT, Decimal(1000)),
        47: (PriceUnit.GIB, Decimal(1024)),
        54: (PriceUnit.REQUEST, Decimal(10_000)),
        56: (PriceUnit.UNIT, Decimal(10_000)),
        68: (PriceUnit.VCPU_HOUR, Decimal(1)),
        70: (PriceUnit.GIB_SECOND, Decimal(1)),
        72: (PriceUnit.GIB_HOUR, Decimal(1)),
        73: (PriceUnit.GIB_HOUR, Decimal(24)),
        93: (PriceUnit.GIB, Decimal(1)),
        94: (PriceUnit.GIB, Decimal(1024)),
        97: (PriceUnit.TOKEN, Decimal(1000)),
        102: (PriceUnit.GIB, Decimal(1)),
        103: (PriceUnit.GIB, Decimal(1024)),
        108: (PriceUnit.TOKEN, Decimal(1)),
        109: (PriceUnit.TOKEN, Decimal(1000)),
        110: (PriceUnit.TOKEN, Decimal(10_000)),
        111: (PriceUnit.TOKEN, Decimal(1_000_000)),
        112: (PriceUnit.TOKEN, Decimal(1_000_000_000)),
        121: (PriceUnit.UNIT, Decimal(1)),
    }
    SIZED: ClassVar[re.Pattern[str]] = re.compile(r"volume|storage|\.obs\b|sfs|disk")
    RESERVED_UNITS: ClassVar[Dict[str, PriceUnit]] = {
        HuaweiReservedAmount.UPFRONT: PriceUnit.ONE_TIME,
        HuaweiReservedAmount.EFFECTIVE: PriceUnit.HOUR,
    }
    TERMS: ClassVar[Dict[int, PriceTerm]] = {
        1: PriceTerm.MONTH,
        3: PriceTerm.THREE_MONTHS,
        6: PriceTerm.SIX_MONTHS,
        12: PriceTerm.ONE_YEAR,
        24: PriceTerm.TWO_YEARS,
        36: PriceTerm.THREE_YEARS,
        48: PriceTerm.FOUR_YEARS,
        60: PriceTerm.FIVE_YEARS,
    }
    MONTHS_PER_YEAR: ClassVar[int] = 12
    VCPUS: ClassVar[re.Pattern[str]] = re.compile(r"vCPUs:(\d+)")
    MEMORY: ClassVar[re.Pattern[str]] = re.compile(r"Memory:(\d+(?:\.\d+)?)\s*(MB|GB)", re.IGNORECASE)
    MB: ClassVar[str] = "MB"
    GIB_PRECISION: ClassVar[Decimal] = Decimal("0.001")
    DESCRIPTION_LENGTH: ClassVar[int] = 500
    GLOBAL_REGION: ClassVar[str] = "global"
    PATH_META: ClassVar[str] = "price_path"
    REGION_META: ClassVar[str] = "price_region"
    SERVICE_META: ClassVar[str] = "price_service"
    CATEGORY_META: ClassVar[str] = "price_category"

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler, allowing the documentation pages.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.allowed_domains.add(self.DOCS_HOST)
        self.whats_new_codes: Optional[Dict[str, str]] = None
        self.price_pending = 0
        self.price_rows = 0

    ############################
    # Internal Helpers Methods #
    ############################

    def _is_docs_catalogue(self, response: Response) -> bool:
        """Tell whether a response is the documentation catalogue JSON.

        Args:
            response (Response): The response.

        Returns:
            bool: Whether it comes from the documentation catalogue host.
        """
        return urlparse(response.url).netloc == urlparse(self.DOCS_URL).netloc

    def _first_text(self, element: Selector, selector: str) -> Optional[str]:
        """Read the text of the first element matching a CSS selector within an element.

        Args:
            element (Selector): The element.
            selector (str): The CSS selector.

        Returns:
            Optional[str]: The text, `None` when no element matches.
        """
        match = element.css(selector).first
        return match.get_all_text(separator=" ", strip=True) if match is not None else None

    def _card_categories(self, response: Response) -> Dict[str, List[str]]:
        """Gather the categories of the desktop cards of the products page, by card link.

        Args:
            response (Response): The products page.

        Returns:
            Dict[str, List[str]]: The category and sub-category labels of each card link (`_url_key`), in page order.

        Notes:
            A product listed in several sections gets the categories of all of them, the marketing sections excepted.
        """
        categories: Dict[str, List[str]] = {}
        for section in response.css(self.SECTIONS):
            category = self._clean_text(self._first_text(section, self.SECTION_TITLE))
            if not category or category in self.MARKETING_SECTIONS:
                self.logger.debug("Skipping the section %r of %s, not a category.", category, response.url)
                continue
            for group in section.css(self.SUB_SECTIONS):
                labels = [category, self._clean_text(self._first_text(group, self.SUB_SECTION_TITLE))]
                for card in group.css(self.CARD):
                    link = self._url_key(urljoin(response.url, card.attrib.get(HtmlAttribute.HREF, "")))
                    categories.setdefault(link, []).extend(labels)
        self.logger.debug("%d categorized product cards in %s.", len(categories), response.url)
        return categories

    def _card_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the desktop cards of the products page.

        Args:
            response (Response): The products page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the page, the featured ones first.
        """
        cards = response.css(self.PRODUCT_CARDS)
        self.logger.debug("%d product cards in %s.", len(cards), response.url)
        categories = self._card_categories(response)
        for card in cards:
            url = urljoin(response.url, card.attrib.get(HtmlAttribute.HREF, ""))
            if product := self._build_product(
                self._first_text(card, ".card-title"),
                self._first_text(card, ".card-description"),
                url,
                categories=categories.get(self._url_key(url), []),
            ):
                yield product

    def _docs_categories(self, response: Response) -> List[JsonValue]:
        """Read the categories of the documentation catalogue.

        Args:
            response (Response): The documentation catalogue JSON.

        Returns:
            List[JsonValue]: The categories.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no `data` list.
        """
        categories = self._as_object(self._json_body(response)).get(HuaweiDocsCatalogueField.DATA)
        if not isinstance(categories, list):
            self.logger.error("The %s documentation catalogue %s has no `data` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the `data` list is missing")
        self.logger.debug("%d documentation categories in %s.", len(categories), response.url)
        return categories

    def _docs_entries(
        self, response: Response
    ) -> Iterator[Tuple[str, Optional[str], Optional[str], str, Optional[str]]]:
        """Walk the documented services, skipping the excluded categories, the guides and the SDK entries.

        Args:
            response (Response): The documentation catalogue JSON.

        Yields:
            Tuple[str, Optional[str], Optional[str], str, Optional[str]]: The name, description, documentation URL,
                category and documentation code of each service.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no `data` list.
        """
        for category in self._docs_categories(response):
            fields = self._as_object(category)
            category_name = self._as_text(fields.get(HuaweiDocsCategoryField.NAME))
            if category_name in self.DOCS_EXCLUDED_CATEGORIES:
                self.logger.debug("Skipping the documentation category %r, not services.", category_name)
                continue
            products = fields.get(HuaweiDocsCategoryField.PRODUCTS)
            for entry in products if isinstance(products, list) else []:
                item = self._as_object(entry)
                title, uri = (
                    self._clean_text(self._as_text(item.get(HuaweiDocsEntryField.TITLE))),
                    self._as_text(item.get(HuaweiDocsEntryField.URI)),
                )
                code = self._as_text(item.get(HuaweiDocsEntryField.CODE))
                if code in self.DOCS_EXCLUDED_CODES or self.DOCS_NOT_PRODUCT.search(uri or ""):
                    self.logger.debug("Skipping the documentation entry %r (%s), not a service.", title, code)
                    continue
                yield (
                    title,
                    self._as_text(item.get(HuaweiDocsEntryField.DESCRIPTION)),
                    uri,
                    self._clean_text(category_name),
                    code,
                )

    def _docs_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the documented services which have a description.

        Args:
            response (Response): The documentation catalogue JSON.

        Yields:
            Iterator[CloudProduct]: Each valid documented service with a description.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no `data` list.

        Notes:
            A service documented in several categories gets all of them.
        """
        entries = list(self._docs_entries(response))
        categories: Dict[str, List[str]] = {}
        for title, _, _, category, _ in entries:
            categories.setdefault(self._name_key(title), []).append(category)
        for title, description, uri, _, _ in entries:
            if self._clean_text(description) and (
                product := self._build_product(title, description, uri, categories=categories[self._name_key(title)])
            ):
                yield product

    def _docs_page_requests(self, response: Response) -> List[Request]:
        """Request the documentation pages of the new documented services without description.

        Args:
            response (Response): The documentation catalogue JSON.

        Returns:
            List[Request]: The documentation page requests, named after the catalogue titles.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no `data` list.
        """
        requests: List[Request] = []
        for title, description, uri, _, _ in self._docs_entries(response):
            if self._clean_text(description) or not title or not uri:
                continue
            if self._name_key(title) in self.seen_products:
                self.logger.debug("Not requesting the documentation of %r, already streamed.", title)
                continue
            if (request := self._product_page_request(uri, title)) is not None:
                requests.append(request)
        self.logger.info("%d %s documentation pages to read for their description.", len(requests), self.name)
        return requests

    def _docs_codes(self, response: Response) -> Dict[str, str]:
        """Read the documentation code of each documented service of the documentation catalogue.

        Args:
            response (Response): The documentation catalogue JSON.

        Returns:
            Dict[str, str]: The documentation code of each service, by normalized name, the first entry of a name
                winning.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no `data` list.
        """
        codes: Dict[str, str] = {}
        for title, _, _, _, code in self._docs_entries(response):
            if title and code:
                codes.setdefault(self._name_key(title), code)
        self.logger.debug("%d documentation codes read from %s.", len(codes), response.url)
        return codes

    async def _whats_new_code_map(self) -> Dict[str, str]:
        """Get the documentation codes of the documented services, fetching the documentation catalogue once.

        Returns:
            Dict[str, str]: The documentation code of each service, by normalized name, empty when the catalogue
                cannot be read.

        Raises:
            CatalogueFormatError: If the documentation catalogue is not JSON or has no `data` list.

        Notes:
            The products page is parsed before the documentation catalogue, so the catalogue is fetched outside the
            crawl queue. An unreadable catalogue is not fetched again during the crawl.
        """
        if self.whats_new_codes is not None:
            return self.whats_new_codes
        response = await self._fetch_launch_page(self.DOCS_URL)
        self.whats_new_codes = {}
        if response is None:
            self.logger.warning("The %s documentation catalogue cannot be read, no product is dated.", self.name)
            return self.whats_new_codes
        self.whats_new_codes = self._docs_codes(response)
        self.logger.info("%d %s documentation codes read to date the products.", len(self.whats_new_codes), self.name)
        return self.whats_new_codes

    def _whats_new_code(self, product: CloudProduct, codes: Dict[str, str]) -> Optional[str]:
        """Find the documentation code of a product, by its normalized name, else by its alias.

        Args:
            product (CloudProduct): The product.
            codes (Dict[str, str]): The documentation code of each service, by normalized name.

        Returns:
            Optional[str]: The documentation code, `None` when the product is not a documented service.
        """
        name_key = self._name_key(product.name)
        alias = self.launch_aliases.get(name_key)
        code = codes.get(name_key) or (codes.get(self._name_key(alias)) if alias else None)
        self.logger.debug("Documentation code of %r: %s.", product.name, code)
        return code

    def _is_missing_page(self, response: Response) -> bool:
        """Tell whether a "What's New" page is missing, served with HTTP 200 (soft 404).

        Args:
            response (Response): The page.

        Returns:
            bool: Whether its title is empty or the `-` placeholder.
        """
        title = self._clean_text(response.css(f"{self.PAGE_TITLE}::text").get())
        return title in ("", self.MISSING_PAGE_TITLE)

    def _heading_date(self, text: str) -> Optional[datetime]:
        """Parse the month of a "What's New" heading, Chinese (`2017年10月`) or English (`April 2018`).

        Args:
            text (str): The heading.

        Returns:
            Optional[datetime]: The first day of the month in UTC, `None` when unreadable or implausible.
        """
        match = self.CHINESE_MONTH.search(text)
        try:
            if match is not None:
                parsed = datetime(int(match.group(1)), int(match.group(2)), 1, tzinfo=UTC)
            else:
                parsed = datetime.strptime(self._clean_text(text), self.ENGLISH_MONTH_FORMAT).replace(tzinfo=UTC)
        except ValueError:
            self.logger.debug("Ignoring the undated heading %r.", text)
            return None
        return parsed if self.EARLIEST_DATE <= parsed <= datetime.now(UTC) else None

    def _earliest_month(self, response: Response) -> Optional[datetime]:
        """Read the earliest month of a "What's New" page.

        Args:
            response (Response): The page.

        Returns:
            Optional[datetime]: The first day of the earliest dated heading, `None` when the page is missing or has
                no dated heading.
        """
        if self._is_missing_page(response):
            self.logger.debug("The %s page %s is missing (placeholder title).", self.name, response.url)
            return None
        texts = [heading.get_all_text(separator=" ", strip=True) for heading in response.css(self.WHATS_NEW_HEADINGS)]
        dates = [date for date in (self._heading_date(text) for text in texts) if date is not None]
        if not dates:
            self.logger.debug("No dated heading in %s.", response.url)
            return None
        return min(dates)

    async def _launch_source(self, product: CloudProduct) -> Optional[Tuple[datetime, DateCaveat]]:
        """Read the launch of a product from the earliest month of its "What's New" pages (Chinese and international).

        Args:
            product (CloudProduct): The product, undated.

        Returns:
            Optional[Tuple[datetime, DateCaveat]]: The launch and its caveat, `None` when the product is not a
                documented service or has no readable "What's New" page.

        Raises:
            CatalogueFormatError: If the documentation catalogue is not JSON or has no `data` list.
        """
        code = self._whats_new_code(product, await self._whats_new_code_map())
        if code is None:
            self.logger.debug("No %s documentation code for %r, it cannot be dated.", self.name, product.name)
            return None
        dates: List[datetime] = []
        for url in self.WHATS_NEW_URLS:
            response = await self._fetch_launch_page(url.format(code=code))
            launched = self._earliest_month(response) if response is not None else None
            if launched is not None:
                self.logger.debug("%r first listed in %s on %s.", product.name, url, launched.date().isoformat())
                dates.append(launched)
        if not dates:
            self.logger.debug("No dated %s What's New page for %r (%s).", self.name, product.name, code)
            return None
        return self._announced(min(dates))

    def _field(self, value: JsonValue, *path: str) -> JsonValue:
        """Follow a path of object fields in a calculator answer.

        Args:
            value (JsonValue): The answer.
            *path (str): The fields, outermost first.

        Returns:
            JsonValue: The value at the end of the path, `None` when a field is missing.
        """
        for field in path:
            value = value.get(field) if isinstance(value, dict) else None
        return value

    def _measure_unit(self, measure: JsonValue, sized: bool) -> Tuple[PriceUnit, Decimal]:
        """Normalize the unit of an on-demand price, from its measure identifier.

        Args:
            measure (JsonValue): The measure identifier (the calculator's `measureID`, e.g. 4 for an hour).
            sized (bool): Whether the resource is priced by its size (a volume, a storage): its time unit is then
                per GiB.

        Returns:
            Tuple[PriceUnit, Decimal]: The unit and the normalized units in one, other when unknown.
        """
        if isinstance(measure, int) and measure in self.TIME_MEASURES:
            unit, factor = self.TIME_MEASURES[measure]
            return (self.SIZED_TIME_UNITS.get(unit, unit) if sized else unit), factor
        if isinstance(measure, int) and measure in self.MEASURES:
            return self.MEASURES[measure]
        self.logger.debug("The Huawei Cloud measure %r has no known unit: kept as other.", measure)
        return PriceUnit.OTHER, Decimal(1)

    def _spec(self, description: str) -> Dict[str, RawValue]:
        """Read the vCPUs and the memory of a resource from its written specification.

        Args:
            description (str): The specification, e.g. `Memory:196608MB` and `vCPUs:24CORE`, semicolon-separated.

        Returns:
            Dict[str, RawValue]: Its `vcpu` and `memory_gib`, those stated.
        """
        found: Dict[str, RawValue] = {}
        vcpus, memory = self.VCPUS.search(description), self.MEMORY.search(description)
        if vcpus is not None and int(vcpus[1]) > 0:
            found["vcpu"] = int(vcpus[1])
        if memory is not None:
            size = Decimal(memory[1])
            found["memory_gib"] = (size / 1024 if memory[2].upper() == self.MB else size).quantize(self.GIB_PRECISION)
        return found

    def _plan_prices(
        self, base: Dict[str, RawValue], key: str, plan: Dict[str, JsonValue], sized: bool
    ) -> Iterator[ServicePrice]:
        """Read one plan of a resource: on demand, a monthly or yearly subscription, or a reserved instance.

        Args:
            base (Dict[str, RawValue]): The fields of the resource.
            key (str): The key of the resource.
            plan (Dict[str, JsonValue]): The plan.
            sized (bool): Whether the resource is priced by its size.

        Yields:
            ServicePrice: Its price, one per tier when tiered (its tiers bound by the quantity of the resource, in
                the measure of its start, an end in another measure being an attribute).
        """
        mode = str(plan.get(HuaweiPriceField.BILLING_MODE) or "")
        periods = plan.get(HuaweiPriceField.PERIOD_NUM)
        periods = periods if isinstance(periods, int) and periods > 0 else 1
        model, term = PriceModel.ON_DEMAND, PriceTerm.NONE
        if mode == HuaweiBillingMode.ON_DEMAND:
            unit, factor = self._measure_unit(plan.get(HuaweiPriceField.MEASURE_UNIT), sized)
        elif mode in (HuaweiBillingMode.MONTHLY, HuaweiBillingMode.YEARLY):
            months = periods * (self.MONTHS_PER_YEAR if mode == HuaweiBillingMode.YEARLY else 1)
            unit, factor = (PriceUnit.GIB_MONTH if sized else PriceUnit.MONTH), Decimal(months)
            model, term = PriceModel.COMMITMENT, self.TERMS.get(months, PriceTerm.NONE)
        elif mode == HuaweiBillingMode.RESERVED:
            amount_type = plan.get(HuaweiPriceField.AMOUNT_TYPE)
            if amount_type not in self.RESERVED_UNITS:
                return
            unit, factor = self.RESERVED_UNITS[str(amount_type)], Decimal(1)
            model = PriceModel.RESERVED
        else:
            self.logger.debug("The Huawei Cloud billing mode %r of %s is unknown: skipped.", mode, key)
            return
        plan_key = "/".join(
            str(part)
            for part in (
                key,
                mode,
                periods,
                plan.get(HuaweiPriceField.PLAN_ID) or "",
                plan.get(HuaweiPriceField.AMOUNT_TYPE) or "",
                plan.get(HuaweiPriceField.PRODUCT_ID) or "",
                plan.get(HuaweiPriceField.USAGE_FACTOR) or "",
                plan.get(HuaweiPriceField.MEASURE_UNIT) or "",
            )
        ).rstrip("/")
        fields: Dict[str, RawValue] = {
            **base,
            "unit": unit,
            "unit_raw": f"{mode}/{plan.get(HuaweiPriceField.MEASURE_UNIT) or periods}",
            "unit_factor": factor,
            "model": model,
            "term": term,
            "attributes": {
                **(base["attributes"] if isinstance(base["attributes"], dict) else {}),
                HuaweiPriceField.PAYMENT_TYPE_KEY.value: plan.get(HuaweiPriceField.PAYMENT_TYPE_KEY),
                HuaweiPriceField.PLAN_ID.value: plan.get(HuaweiPriceField.PLAN_ID),
                HuaweiPriceField.PRODUCT_ID.value: plan.get(HuaweiPriceField.PRODUCT_ID),
                HuaweiPriceField.USAGE_FACTOR.value: plan.get(HuaweiPriceField.USAGE_FACTOR),
            },
        }
        divisions = plan.get(HuaweiPriceField.DIVISION_LIST)
        tiers: List[Tuple[JsonValue, JsonValue, JsonValue, JsonValue, JsonValue]] = (
            [
                (
                    division.get(HuaweiPriceField.AMOUNT),
                    self._field(division, HuaweiPriceField.DIVISION, HuaweiPriceField.BEGIN_VALUE),
                    self._field(division, HuaweiPriceField.DIVISION, HuaweiPriceField.END_VALUE),
                    self._field(division, HuaweiPriceField.DIVISION, HuaweiPriceField.BEGIN_UNIT),
                    self._field(division, HuaweiPriceField.DIVISION, HuaweiPriceField.END_UNIT),
                )
                for division in divisions
                if isinstance(division, dict)
            ]
            if isinstance(divisions, list) and divisions
            else [(plan.get(HuaweiPriceField.AMOUNT), None, None, None, None)]
        )
        for index, (amount, start, end, start_unit, end_unit) in enumerate(tiers):
            if not isinstance(amount, (int, float)):
                continue
            if model is PriceModel.RESERVED and amount == 0:
                continue
            price = Decimal(str(amount))
            attributes = dict(fields["attributes"]) if isinstance(fields["attributes"], dict) else {}
            if start_unit is not None:
                attributes[HuaweiPriceField.BEGIN_UNIT.value] = start_unit
            if start_unit != end_unit and isinstance(end, (int, float)) and end > 0:
                attributes[HuaweiPriceField.END_VALUE.value] = end
                attributes[HuaweiPriceField.END_UNIT.value] = end_unit
                self.logger.debug("A Huawei Cloud tier of %s spans two units: its end is an attribute.", plan_key)
                end = None
            fact = self._price_fact(
                {
                    **fields,
                    "sku_key": f"{plan_key}/{index}" if len(tiers) > 1 else plan_key,
                    "attributes": attributes,
                    "price": price,
                    "model": PriceModel.FREE if price == 0 else model,
                    "tier_start": start if isinstance(start, (int, float)) and start > 0 else 0,
                    "tier_end": end if isinstance(end, (int, float)) and end > 0 else None,
                }
            )
            if fact is not None:
                yield fact

    def _service_prices(self, product: JsonValue, meta: Dict[str, JsonValue]) -> Iterator[ServicePrice]:
        """Read the prices of a service in a region.

        Args:
            product (JsonValue): The priced resources of the service, by kind.
            meta (Dict[str, JsonValue]): The request meta (the service, its category, the region).

        Yields:
            ServicePrice: The prices of every plan of every resource.
        """
        region = str(meta.get(self.REGION_META) or self.GLOBAL_REGION)
        for kind, resources in (product if isinstance(product, dict) else {}).items():
            for resource in resources if isinstance(resources, list) else []:
                if not isinstance(resource, dict):
                    continue
                resource_type = str(resource.get(HuaweiPriceField.RESOURCE_TYPE) or "")
                spec = str(resource.get(HuaweiPriceField.RESOURCE_SPEC_CODE) or "")
                description = str(resource.get(HuaweiPriceField.PRODUCT_SPEC_SYS_DESC) or "")
                sized = self.SIZED.search(resource_type) is not None
                specs = self._spec(description)
                base: Dict[str, RawValue] = {
                    "service": meta.get(self.SERVICE_META),
                    "family": meta.get(self.CATEGORY_META) or None,
                    "region": region,
                    "instance_type": spec if specs.get("vcpu") else None,
                    "attributes": {
                        HuaweiPriceField.RESOURCE_TYPE.value: resource_type,
                        HuaweiPriceField.PRODUCT_SPEC_SYS_DESC.value: description[: self.DESCRIPTION_LENGTH],
                    },
                    "currency": self.PRICE_CURRENCY,
                    "source_url": self.MENU_URL,
                    "source_kind": PriceSourceKind.CALCULATOR,
                    **specs,
                }
                plans = resource.get(HuaweiPriceField.PLAN_LIST)
                for plan in plans if isinstance(plans, list) else []:
                    if isinstance(plan, dict):
                        yield from self._plan_prices(
                            base, f"{meta.get(self.PATH_META)}/{region}/{kind}/{spec}", plan, sized
                        )

    def _price_settled(self) -> None:
        """Count a calculator call as answered, and record the calculator once every call is answered."""
        self.price_pending -= 1
        if self.price_pending == 0 and not self.price_failures:
            self._record_price_source(self.MENU_URL, self.price_rows)
            self.logger.info("The Huawei Cloud calculator is read whole: %d prices.", self.price_rows)

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the calculator menu, listing its services and their regions.

        Yields:
            Request: The menu request.
        """
        self.price_pending = 1
        self.price_rows = 0
        self.logger.info("Reading the Huawei Cloud prices from %s.", self.MENU_URL)
        yield self._price_request(self.MENU_URL)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the calculator menu (requesting each service in each region), or the prices of a service.

        Args:
            response (Response): The menu or the prices of a service in a region.

        Yields:
            PriceFact: The service requests, or the prices of a service.

        Raises:
            CatalogueFormatError: If the answer is not a JSON object.
        """
        data = self._json_body(response)
        meta: Dict[str, JsonValue] = dict(response.meta)
        if not isinstance(data, dict):
            self.price_failures.add(response.url)
            self._price_settled()
            self.logger.error("The Huawei Cloud calculator answered %s with no object.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the calculator answered with no object")
        if self.PATH_META not in meta:
            categories = data.get(HuaweiPriceField.MENU_INFOS)
            for category in categories if isinstance(categories, list) else []:
                services = self._field(category, HuaweiPriceField.SUB_CATEGORY_LISTS)
                for service in services if isinstance(services, list) else []:
                    path = self._field(service, HuaweiPriceField.URL_PATH)
                    regions = self._field(service, HuaweiPriceField.REGION_ONLINE, HuaweiPriceField.REGION_LIST)
                    if not isinstance(path, str) or self._field(service, HuaweiPriceField.HAS_CALCULATOR) is not True:
                        continue
                    for region in regions if isinstance(regions, list) else []:
                        self.price_pending += 1
                        yield self._price_request(
                            self.PRODUCT_URL.format(path=path, region=region),
                            {
                                self.PATH_META: path,
                                self.REGION_META: region,
                                self.SERVICE_META: self._field(service, HuaweiPriceField.CATEGORY_NAME),
                                self.CATEGORY_META: self._field(category, HuaweiPriceField.PARENT_CATEGORY_NAME),
                            },
                        )
            self.logger.info("The Huawei Cloud calculator menu leads to %d calls.", self.price_pending - 1)
        else:
            found = 0
            for fact in self._service_prices(data.get(HuaweiPriceField.PRODUCT), meta):
                found += 1
                yield fact
            self.price_rows += found
            self.logger.debug(
                "Huawei Cloud %s in %s: %d prices.", meta.get(self.PATH_META), meta.get(self.REGION_META), found
            )
        self._price_settled()

    ############################
    # Publicly Exposed Methods #
    ############################

    async def on_start(self, resuming: bool = False) -> None:
        """Forget the documentation codes of a previous crawl, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if not resuming:
            self.whats_new_codes = None
            self.logger.debug("The %s documentation codes will be read again.", self.name)

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products page or of the documentation catalogue.

        Args:
            response (Response): The products page or the documentation catalogue JSON.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.

        Raises:
            CatalogueFormatError: If the documentation catalogue is not JSON or has no `data` list.
        """
        if self._is_docs_catalogue(response):
            return self._docs_products(response)
        return self._card_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the products of a page, then request the documentation pages of the services without description.

        The documentation pages are read by the base crawler.

        Args:
            response (Response): The products page, the documentation catalogue JSON or a documentation page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, then the documentation page requests.

        Raises:
            EmptyCatalogueError: If the products page or the documentation catalogue holds no valid product.
            CatalogueFormatError: If the documentation catalogue is not JSON or has no `data` list.
        """
        async for item in super().parse(response):
            yield item
        if self.PRODUCT_PAGE not in response.meta and self._is_docs_catalogue(response):
            for request in self._docs_page_requests(response):
                yield request
