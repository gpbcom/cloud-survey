from __future__ import annotations

# Standard Library Imports.
import re
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.combell.enums import CombellCssClass
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue


class CombellCrawler(BaseCloudCrawler):
    """Combell catalogue crawler.

    Attributes:
        MANAGED_SERVICES_URL (ClassVar[str]): The managed services page, listing the IT solutions.
        MENU_LINKS (ClassVar[str]): The CSS selector of the main menu links.
        SOLUTION_LINKS (ClassVar[str]): The CSS selector of the IT solutions links of the managed services page.
        NOT_PRODUCT_ID (ClassVar[re.Pattern[str]]): The menu link identifiers of the overviews and partner programmes.
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The links to prices, partner programmes, the technology page
            and the business needs pages of the managed services (performance, collaboration, security, uptime).
        NOT_PRODUCT_LABEL (ClassVar[re.Pattern[str]]): The link labels which are not products (overviews, tools).
        MENU_CATEGORY (ClassVar[Tuple[CombellCssClass, str]]): The class of the main menu items and the CSS selector
            of their label, the category of the links they hold.
        SOLUTION_CATEGORY (ClassVar[Tuple[CombellCssClass, str]]): The class of the IT solutions cards and the CSS
            selector of their title, the category of the links they hold.
        OPENSTACK_PRICES_URL (ClassVar[str]): The OpenStack cloud price list, priced by instance and resource.
        AMOUNT (ClassVar[re.Pattern[str]]): A price in euros, e.g. `€ 4.91`.
        SIZE (ClassVar[re.Pattern[str]]): A size in GB or TB, e.g. `25 GB SSD`.
        COUNT (ClassVar[re.Pattern[str]]): A count, e.g. `2 cores`.
        PACKAGES (ClassVar[str]): The CSS selector of the package cards of a product page.
        PACKAGE_NAME (ClassVar[str]): The CSS selector of the name of a package.
        PACKAGE_PRICES (ClassVar[str]): The CSS selector of the prices of a package (a former price first).
        PACKAGE_PERIOD (ClassVar[str]): The CSS selector of the period of a package price.
        PACKAGE_PROMOTION (ClassVar[str]): The CSS selector of the promotion badge of a package.
        PERIODS (ClassVar[Dict[str, PriceUnit]]): The unit of a package price by its period.
        PRICE_CURRENCY (ClassVar[str]): The currency of the prices.
        REGION (ClassVar[str]): The region of the prices (Belgium).
        SERVICE_META (ClassVar[str]): The request meta holding the service of a product page.
        FAMILY_META (ClassVar[str]): The request meta holding the menu category of a product page.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): The catalogue product pages are read too, for their prices.
        PAGE_TEXT_PRICES (ClassVar[bool]): A product page without price table is read for the prices in its text.

    Notes:
        The main source is the main menu of the https://www.combell.com/en/ home page (domain names, hosting,
        websites, e-mail, tools, servers, managed services). The IT solutions of the managed services page complete
        it. Both only give the product names, so each product page is requested and its product is read from its
        meta description, the link label giving the product name. The catalogue categories of a product are the
        main menu entries listing it (e.g. `Servers`), or the IT solutions cards listing it (e.g.
        `Cloud & infrastructure`). The titles of the menu columns are left out, as many are slogans.
        In price mode it reads the OpenStack price list (https://www.combell.com/en/openstack-cloud/pricing), whose
        tables price each instance (with its vCPUs, memory and storage) and resource per month (a storage volume per
        GB and month), and the package cards of the product pages of the main menu: a package gives its monthly or
        yearly price, its regular price when discounted (the discounted price being an attribute). Prices are in
        euros. Each page is a source.
    """

    MANAGED_SERVICES_URL: ClassVar[str] = "https://www.combell.com/en/managed-services"
    MENU_LINKS: ClassVar[str] = 'a.dropdown__link[id^="sel-nav-"][href]'
    SOLUTION_LINKS: ClassVar[str] = "#solutions a[href]"
    NOT_PRODUCT_ID: ClassVar[re.Pattern[str]] = re.compile(r"overview|partners", re.IGNORECASE)
    NOT_PRODUCT_LINK: ClassVar[re.Pattern[str]] = re.compile(
        r"/prices|/partners|/affiliate|commission-partner|/technology$|/performance-optimisation$|"
        r"/digital-collaboration$|/tailored-security$|/avoid-downtime$",
        re.IGNORECASE,
    )
    NOT_PRODUCT_LABEL: ClassVar[re.Pattern[str]] = re.compile(
        r"^(all |more |learn more|find out|discover|generate )", re.IGNORECASE
    )
    MENU_CATEGORY: ClassVar[Tuple[CombellCssClass, str]] = (CombellCssClass.MENU_ITEM, ":scope > a.menu__link")
    SOLUTION_CATEGORY: ClassVar[Tuple[CombellCssClass, str]] = (CombellCssClass.CARD_BODY, "h3")
    OPENSTACK_PRICES_URL: ClassVar[str] = "https://www.combell.com/en/openstack-cloud/pricing"
    AMOUNT: ClassVar[re.Pattern[str]] = re.compile(r"€\s*(?P<amount>\d[\d,]*(?:\.\d+)?)")
    SIZE: ClassVar[re.Pattern[str]] = re.compile(r"(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>GB|TB)")
    COUNT: ClassVar[re.Pattern[str]] = re.compile(r"\d+")
    PACKAGES: ClassVar[str] = "div.ordertable__package"
    PACKAGE_NAME: ClassVar[str] = "div.ordertable__package__header > p"
    PACKAGE_PRICES: ClassVar[str] = "div.ordertable__package__content__price span.price__value"
    PACKAGE_PERIOD: ClassVar[str] = "div.ordertable__package__content__price span.price__period"
    PACKAGE_PROMOTION: ClassVar[str] = "div.ordertable__package__header span.badge"
    PERIODS: ClassVar[Dict[str, PriceUnit]] = {"/month": PriceUnit.MONTH, "/year": PriceUnit.YEAR}
    PRICE_CURRENCY: ClassVar[str] = "EUR"
    REGION: ClassVar[str] = "be"
    SERVICE_META: ClassVar[str] = "price_service"
    FAMILY_META: ClassVar[str] = "price_family"

    PRODUCT_PAGE_PRICES: ClassVar[bool] = True
    PAGE_TEXT_PRICES: ClassVar[bool] = True
    name = "combell"
    catalogue_url: ClassVar[str] = "https://www.combell.com/en/"
    complement_urls: ClassVar[Tuple[str, ...]] = (MANAGED_SERVICES_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Combell ",)

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)

    ############################
    # Internal Helpers Methods #
    ############################

    def _link_category(self, link: Selector, scope: Tuple[CombellCssClass, str]) -> Optional[str]:
        """Read the category of a link: the label of the closest element of a class holding it.

        Args:
            link (Selector): The link.
            scope (Tuple[CombellCssClass, str]): The class of the category elements and the CSS selector of their label.

        Returns:
            Optional[str]: The category, e.g. `Servers`, `None` when the link is not in such an element.
        """
        container, heading = scope
        node = link.parent
        while node is not None:
            if container in node.attrib.get(HtmlAttribute.CLASS, "").split():
                title = node.css(heading).first
                if title is None:
                    return None
                return self._clean_text(title.get_all_text(separator=" ", strip=True)) or None
            node = node.parent
        return None

    def _link_label(self, link: Selector) -> str:
        """Read the label of a link, without its badges and notes (`small`, `span` children).

        Args:
            link (Selector): The link.

        Returns:
            str: The label, e.g. `Private cloud` for `Private cloud <small>Most popular</small>`.
        """
        return self._clean_text(str(link.text or "")) or self._clean_text(link.get_all_text(separator=" ", strip=True))

    def _is_product_link(self, link: Selector, label: str, url: str) -> bool:
        """Tell whether a link leads to a product page.

        Args:
            link (Selector): The link.
            label (str): Its label.
            url (str): Its absolute URL.

        Returns:
            bool: Whether the link is not an overview, a partner programme, a price list, a tool or a page section.
        """
        parsed = urlparse(url)
        reasons = {
            "overview or partners": bool(self.NOT_PRODUCT_ID.search(link.attrib.get(HtmlAttribute.ID, ""))),
            "prices, partners, technology or business need page": bool(
                self.NOT_PRODUCT_LINK.search(parsed.path.rstrip("/"))
            ),
            "page section": bool(parsed.fragment or parsed.query),
            "overview or tool label": bool(self.NOT_PRODUCT_LABEL.match(label)),
        }
        if failed := [reason for reason, matched in reasons.items() if matched]:
            self.logger.debug("Skipping the link %r (%s): %s.", label, url, ", ".join(failed))
            return False
        return True

    def _product_links(
        self, response: Response, selector: str, scope: Tuple[CombellCssClass, str]
    ) -> Dict[str, Tuple[str, str, List[str]]]:
        """Read the product links of a page, once per product page, with their most descriptive label.

        Args:
            response (Response): The page.
            selector (str): The CSS selector of the links.
            scope (Tuple[CombellCssClass, str]): The class of the elements giving the category of the links they hold,
                and the CSS selector of their label.

        Returns:
            Dict[str, Tuple[str, str, List[str]]]: The product page URL, label and categories (of all its links), by
                URL key, in the page order.

        Raises:
            CatalogueFormatError: If the page has no such link.
        """
        links = response.css(selector)
        if not links:
            self.logger.error("The %s page %s has no product links (%s).", self.name, response.url, selector)
            raise CatalogueFormatError(self.name, response.url, f"the product links `{selector}` are missing")
        entries: Dict[str, Tuple[str, str, List[str]]] = {}
        for link in links:
            label = self._link_label(link)
            url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, ""))
            if not label or not self._is_product_link(link, label, url):
                continue
            key = self._url_key(url)
            category = self._link_category(link, scope)
            categories = [*(entries[key][2] if key in entries else []), *([category] if category else [])]
            if key in entries and len(entries[key][1]) >= len(label):
                entries[key] = (entries[key][0], entries[key][1], categories)
                continue
            entries[key] = (entries[key][0] if key in entries else url, label, categories)
        self.logger.debug("%d product links in %s (%d links).", len(entries), response.url, len(links))
        return entries

    def _page_requests(self, response: Response) -> List[Request]:
        """Request the product pages listed by the main menu or by the IT solutions of the managed services page.

        Args:
            response (Response): The home page or the managed services page.

        Returns:
            List[Request]: The product page requests, with their categories.

        Raises:
            CatalogueFormatError: If the page has no product links.
        """
        if self._url_key(response.url) == self._url_key(self.MANAGED_SERVICES_URL):
            entries = self._product_links(response, self.SOLUTION_LINKS, self.SOLUTION_CATEGORY)
        else:
            entries = self._product_links(response, self.MENU_LINKS, self.MENU_CATEGORY)
        requests: List[Request] = []
        for url, label, categories in entries.values():
            if (request := self._product_page_request(url, label, categories=categories)) is not None:
                requests.append(request)
        self.logger.info("%d %s product pages to read from %s.", len(requests), self.name, response.url)
        return requests

    def _size_gib(self, text: str) -> Optional[Decimal]:
        """Read a size in GiB.

        Args:
            text (str): The cell, e.g. `25 GB SSD`.

        Returns:
            Optional[Decimal]: The size in GiB, None when not written.
        """
        match = self.SIZE.search(text)
        if match is None:
            return None
        size = Decimal(match.group("size"))
        return size * 1024 if match.group("unit") == "TB" else size

    def _table_prices(self, url: str, group: str, rows: List[List[str]]) -> Iterator[ServicePrice]:
        """Read the prices of a table of the OpenStack price list.

        Args:
            url (str): The price list page.
            group (str): The service of the table (the heading before it).
            rows (List[List[str]]): Its rows, the first being its header.

        Yields:
            ServicePrice: The monthly price of each row, a storage volume priced per GB and month.
        """
        if len(rows) < 2:
            return
        header = rows[0]
        column = next((index for index, text in enumerate(header) if text.startswith("Price")), len(header) - 1)
        for row in rows[1:]:
            cells = dict(zip(header, row, strict=False))
            amount = self.AMOUNT.search(row[column]) if column < len(row) else None
            if amount is None:
                continue
            price = Decimal(amount.group("amount").replace(",", ""))
            vcpu = self.COUNT.search(cells.get("vCPU", ""))
            volume = self._size_gib(row[0]) if header[0] == "Storage" else None
            fields: Dict[str, RawValue] = {
                "sku_key": f"openstack/{group}/{row[0]}",
                "service": group,
                "family": "OpenStack",
                "region": self.REGION,
                "instance_type": row[0] if vcpu else None,
                "vcpu": int(vcpu.group()) if vcpu else None,
                "memory_gib": self._size_gib(cells.get("RAM", "")),
                "storage_gib": self._size_gib(cells.get("Storage", "")) if vcpu else volume,
                "attributes": {key: value for key, value in cells.items() if key not in (header[0], header[column])},
                "unit": PriceUnit.GIB_MONTH if volume else PriceUnit.MONTH,
                "unit_raw": row[column],
                "unit_factor": volume or Decimal(1),
                "price": price,
                "currency": self.PRICE_CURRENCY,
                "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
                "term": PriceTerm.NONE,
                "source_url": url,
                "source_kind": PriceSourceKind.PAGE,
            }
            if (fact := self._price_fact(fields)) is not None:
                yield fact

    def _package_prices(self, response: Response) -> Iterator[ServicePrice]:
        """Read the package cards of a product page.

        Args:
            response (Response): The product page.

        Yields:
            ServicePrice: The regular price of each package, per month or year.
        """
        url = str(response.url)
        service = str(response.meta.get(self.SERVICE_META) or "")
        family = response.meta.get(self.FAMILY_META)
        for package in response.css(self.PACKAGES):
            name_node = package.css(self.PACKAGE_NAME).first
            name = self._clean_text(name_node.get_all_text(separator=" ", strip=True)) if name_node is not None else ""
            values = [self._clean_text(value.get_all_text(strip=True)) for value in package.css(self.PACKAGE_PRICES)]
            period_node = package.css(self.PACKAGE_PERIOD).first
            period = self._clean_text(period_node.get_all_text(strip=True)) if period_node is not None else ""
            if not name or not values or not re.fullmatch(r"\d+(?:\.\d+)?", values[0]):
                continue
            price = Decimal(values[0])
            attributes: Dict[str, JsonValue] = {}
            if len(values) > 1 and values[-1] != values[0]:
                attributes["discounted_price"] = values[-1]
                badge = package.css(self.PACKAGE_PROMOTION).first
                if badge is not None:
                    attributes["promotion"] = self._clean_text(badge.get_all_text(separator=" ", strip=True))
            unit = self.PERIODS.get(period, PriceUnit.OTHER)
            fact = self._price_fact(
                {
                    "sku_key": f"{urlparse(url).path.strip('/')}/{name}",
                    "service": service,
                    "family": family or None,
                    "region": self.REGION,
                    "instance_type": name,
                    "attributes": attributes,
                    "unit": unit,
                    "unit_raw": period or None,
                    "unit_factor": Decimal(1),
                    "price": price,
                    "currency": self.PRICE_CURRENCY,
                    "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
                    "term": PriceTerm.NONE,
                    "source_url": url,
                    "source_kind": PriceSourceKind.PAGE,
                }
            )
            if fact is not None:
                yield fact

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the OpenStack price list and the home page, whose menu lists the product pages.

        Yields:
            Request: Their requests.
        """
        self.logger.info("Reading the %s prices from %s and the product pages.", self.name, self.OPENSTACK_PRICES_URL)
        yield self._price_request(self.OPENSTACK_PRICES_URL, {self.SERVICE_META: ""})
        yield self._price_request(self.catalogue_url)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the home page menu, the OpenStack price list or a product page.

        Args:
            response (Response): The page.

        Yields:
            PriceFact: The product page requests, or the prices of a page.

        Raises:
            CatalogueFormatError: If the home page has no product links.
        """
        service = response.meta.get(self.SERVICE_META)
        if not isinstance(service, str):
            entries = self._product_links(response, self.MENU_LINKS, self.MENU_CATEGORY)
            self.logger.info("%d %s product pages to read for their packages.", len(entries), self.name)
            for url, label, categories in entries.values():
                meta: Dict[str, JsonValue] = {
                    self.SERVICE_META: label,
                    self.FAMILY_META: categories[0] if categories else "",
                }
                yield self._price_request(url, meta)
            return
        url = str(response.url)
        if service:
            facts = list(self._package_prices(response))
        else:
            facts = [
                fact for group, rows in self._price_tables(response) for fact in self._table_prices(url, group, rows)
            ]
        for fact in facts:
            yield fact
        self._record_price_source(url, len(facts))
        self.logger.debug("The %s page %s gave %d prices.", self.name, url, len(facts))

    ############################
    # Publicly Exposed Methods #
    ############################

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Request the product pages of the menu or of the IT solutions, or stream the product of a product page.

        Args:
            response (Response): The home page, the managed services page or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: The product page requests, or the product of a product page.

        Raises:
            CatalogueFormatError: If the home page or the managed services page has no product links.
        """
        if self.PRODUCT_PAGE in response.meta:
            async for item in super().parse(response):
                yield item
            return
        for request in self._page_requests(response):
            yield request
