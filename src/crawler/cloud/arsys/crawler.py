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
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue


class ArsysCrawler(BaseCloudCrawler):
    """Arsys catalogue crawler.

    Attributes:
        MENU_SECTIONS (ClassVar[str]): The CSS selector of the main menu sections, each one the drop-down of a menu
            entry.
        SECTION_LINKS (ClassVar[str]): The CSS selector of the links of a menu section, its main and "more" lists.
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The menu links to tools, prices, company pages and partners.
        NOT_PRODUCT_LABEL (ClassVar[re.Pattern[str]]): The menu labels which are not products.
        TRADEMARKS (ClassVar[re.Pattern[str]]): The trademark signs removed from the menu labels.
        PRICES_URL (ClassVar[str]): The cloud price list page, priced by resource.
        PRICE_CELL (ClassVar[re.Pattern[str]]): A price of the price list, e.g. `0.0045 €/GB/hour` or
            `0.04 €/GB 30 days`.
        FREE_CELL (ClassVar[re.Pattern[str]]): A free price of the price list.
        UNITS (ClassVar[Dict[str, Tuple[PriceUnit, Decimal]]]): The unit of a price list price by its written unit,
            and the normalized units in one.
        TIER (ClassVar[re.Pattern[str]]): The usage range of a tiered price, e.g. `from 2TB to 10TB`.
        OFFER_PRODUCTS (ClassVar[str]): The CSS selector of the schema.org products of a product page.
        OFFERS (ClassVar[str]): The CSS selector of the offers of a product (one per billing cycle).
        OFFER_FIELD (ClassVar[str]): The CSS selector of a shop field of the current price of an offer.
        PRODUCT_LINE (ClassVar[str]): The XPath of the product line holding a product (its specification).
        SPEC_CELLS (ClassVar[Dict[str, str]]): The CSS selector of each specification of a product line.
        TERMS (ClassVar[Dict[int, PriceTerm]]): The term of an offer by its months.
        PRICE_CURRENCY (ClassVar[str]): The currency of the prices.
        REGION (ClassVar[str]): The region of the prices (Spain).
        SERVICE_META (ClassVar[str]): The request meta holding the service of a product page.
        FAMILY_META (ClassVar[str]): The request meta holding the menu section of a product page.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): The catalogue product pages are read too, for their prices.
        PAGE_TEXT_PRICES (ClassVar[bool]): A product page without price table is read for the prices in its text.

    Notes:
        The main source is the main menu of the https://www.arsys.net/ home page (English website). Each section of
        the menu (domains, e-mail, websites, hosting, servers, cloud, security, managed services...) lists its
        products, without description, so each product page is requested and its product is read from its meta
        description, the menu label giving the product name. The catalogue categories of a product are the labels
        of the menu entries whose sections list it (e.g. `Domains` and `Security` for the SSL certificates).
        In price mode it reads the cloud price list (https://www.arsys.net/cloud/prices), whose tables price each
        resource (per hour, per GB and hour, per GB and month, per GB, with usage tiers), and the product pages of
        the main menu, whose schema.org products (e.g. `VPS 1_2_60`) give one offer per billing cycle: its months,
        its regular and current price. An offer of several months is a commitment, its first-period promotion an
        attribute. Prices are in euros without VAT. Each page is a source.
    """

    MENU_SECTIONS: ClassVar[str] = "div.section"
    SECTION_LINKS: ClassVar[str] = "ul.main a[href], ul.more a[href]"
    NOT_PRODUCT_LINK: ClassVar[re.Pattern[str]] = re.compile(
        r"/tools(/|$)|prices|/about(/|$)|/contact|partners|generator|/whois", re.IGNORECASE
    )
    NOT_PRODUCT_LABEL: ClassVar[re.Pattern[str]] = re.compile(r"^(use cases|customer support)$", re.IGNORECASE)
    TRADEMARKS: ClassVar[re.Pattern[str]] = re.compile(r"[®™]")
    PRICES_URL: ClassVar[str] = "https://www.arsys.net/cloud/prices"
    PRICE_CELL: ClassVar[re.Pattern[str]] = re.compile(r"(?P<amount>\d+(?:[.,]\d+)?)\s*€\s*/\s*(?P<unit>.+)$")
    FREE_CELL: ClassVar[re.Pattern[str]] = re.compile(r"^free$", re.IGNORECASE)
    UNITS: ClassVar[Dict[str, Tuple[PriceUnit, Decimal]]] = {
        "hour": (PriceUnit.HOUR, Decimal(1)),
        "hour/period": (PriceUnit.HOUR, Decimal(1)),
        "GB/hour": (PriceUnit.GIB_HOUR, Decimal(1)),
        "GB/month": (PriceUnit.GIB_MONTH, Decimal(1)),
        "GB 30 days": (PriceUnit.GIB_MONTH, Decimal(1)),
        "GB": (PriceUnit.GIB, Decimal(1)),
        "unit": (PriceUnit.UNIT, Decimal(1)),
    }
    TIER: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:from\s*(?P<start>\d+)\s*TB\s*to|up to)\s*(?P<end>\d+)\s*TB|more than\s*(?P<above>\d+)\s*TB",
        re.IGNORECASE,
    )
    OFFER_PRODUCTS: ClassVar[str] = '[itemtype="https://schema.org/Product"]'
    OFFERS: ClassVar[str] = 'table[itemprop="offers"]'
    OFFER_FIELD: ClassVar[str] = 'tr.current meta[data-name="{field}"]'
    PRODUCT_LINE: ClassVar[str] = "ancestor::div[contains(concat(' ', @class, ' '), ' productLine ')][1]"
    SPEC_CELLS: ClassVar[Dict[str, str]] = {"cpu": ".cpu span", "ram": ".ram span", "disk": ".disk span"}
    TERMS: ClassVar[Dict[int, PriceTerm]] = {
        1: PriceTerm.MONTH,
        3: PriceTerm.THREE_MONTHS,
        6: PriceTerm.SIX_MONTHS,
        12: PriceTerm.ONE_YEAR,
        24: PriceTerm.TWO_YEARS,
        36: PriceTerm.THREE_YEARS,
    }
    PRICE_CURRENCY: ClassVar[str] = "EUR"
    REGION: ClassVar[str] = "es"
    SERVICE_META: ClassVar[str] = "price_service"
    FAMILY_META: ClassVar[str] = "price_family"

    PRODUCT_PAGE_PRICES: ClassVar[bool] = True
    PAGE_TEXT_PRICES: ClassVar[bool] = True
    name = "arsys"
    catalogue_url: ClassVar[str] = "https://www.arsys.net/"
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Arsys ",)

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

    def _section_label(self, section: Selector) -> Optional[str]:
        """Read the label of the menu entry a menu section drops down from.

        Args:
            section (Selector): The menu section.

        Returns:
            Optional[str]: The label, e.g. `Domains`, `None` when the section is not under a menu entry.
        """
        parent = section.parent
        link = parent.css(":scope > a").first if parent is not None else None
        if link is None:
            return None
        return self._clean_text(link.get_all_text(separator=" ", strip=True)) or None

    def _menu_entries(self, response: Response) -> Dict[str, Tuple[str, str, List[str]]]:
        """Read the product links of the main menu, once per page, with their label and their menu sections.

        Args:
            response (Response): The home page.

        Returns:
            Dict[str, Tuple[str, str, List[str]]]: The product page URL, label and menu section labels, by URL key,
                in the menu order.

        Raises:
            CatalogueFormatError: If the page has no main menu.
        """
        entries: Dict[str, Tuple[str, str, List[str]]] = {}
        count = 0
        for section in response.css(self.MENU_SECTIONS):
            category = self._section_label(section)
            links = section.css(self.SECTION_LINKS)
            count += len(links)
            for link in links:
                label = self._clean_text(self.TRADEMARKS.sub("", link.get_all_text(separator=" ", strip=True)))
                url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, ""))
                parsed = urlparse(url)
                if parsed.query or self.NOT_PRODUCT_LINK.search(parsed.path) or self.NOT_PRODUCT_LABEL.match(label):
                    self.logger.debug("Skipping the menu link %r (%s), not a product.", label, url)
                    continue
                key = self._url_key(url)
                if key in entries:
                    self.logger.debug("The menu link %r (%s) is listed again, under %r.", label, url, category)
                    if category:
                        entries[key][2].append(category)
                    continue
                entries[key] = (url, label, [category] if category else [])
        if not count:
            self.logger.error("The %s page %s has no main menu (%s).", self.name, response.url, self.MENU_SECTIONS)
            raise CatalogueFormatError(self.name, response.url, "the main menu is missing")
        self.logger.debug("%d product links in the %s menu (%d links).", len(entries), self.name, count)
        return entries

    def _menu_requests(self, response: Response) -> List[Request]:
        """Request the product pages listed by the main menu.

        Args:
            response (Response): The home page.

        Returns:
            List[Request]: The product page requests, with their menu sections.

        Raises:
            CatalogueFormatError: If the page has no main menu.
        """
        requests: List[Request] = []
        for url, label, categories in self._menu_entries(response).values():
            if (request := self._product_page_request(url, label, categories=categories)) is not None:
                requests.append(request)
        self.logger.info("%d %s product pages to read from the menu of %s.", len(requests), self.name, response.url)
        return requests

    def _list_price(self, url: str, group: str, section: str, name: str, cell: str) -> Optional[ServicePrice]:
        """Read a price of the cloud price list.

        Args:
            url (str): The price list page.
            group (str): The service of its table (the heading before it).
            section (str): The section of the table (its header row).
            name (str): The resource priced.
            cell (str): Its price.

        Returns:
            Optional[ServicePrice]: The price, None when the cell holds none.
        """
        match = self.PRICE_CELL.search(cell)
        if match is None and not self.FREE_CELL.match(cell):
            return None
        price = Decimal(match.group("amount").replace(",", ".")) if match else Decimal(0)
        written = match.group("unit").strip() if match else ""
        unit, factor = (
            self.UNITS.get(written, (PriceUnit.OTHER, Decimal(1))) if written else (PriceUnit.UNIT, Decimal(1))
        )
        tier = self.TIER.search(name)
        start = end = None
        if tier is not None and tier.group("above"):
            start = Decimal(tier.group("above")) * 1024
        elif tier is not None:
            start, end = Decimal(tier.group("start") or 0) * 1024, Decimal(tier.group("end")) * 1024
        if tier is not None and unit == PriceUnit.UNIT:
            unit = PriceUnit.GIB
        return self._price_fact(
            {
                "sku_key": f"cloud/{group}/{section}/{name}",
                "service": group,
                "family": section or None,
                "region": self.REGION,
                "attributes": {"vat": "excluded"},
                "unit": unit,
                "unit_raw": cell,
                "unit_factor": factor,
                "price": price,
                "currency": self.PRICE_CURRENCY,
                "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
                "term": PriceTerm.NONE,
                "tier_start": start if start is not None else Decimal(0),
                "tier_end": end,
                "source_url": url,
                "source_kind": PriceSourceKind.PAGE,
            }
        )

    def _list_prices(self, response: Response) -> Iterator[ServicePrice]:
        """Read the prices of the cloud price list tables.

        Args:
            response (Response): The price list page.

        Yields:
            ServicePrice: The price of each resource of each table.
        """
        url = str(response.url)
        for group, rows in self._price_tables(response):
            section = rows[0][0] if rows and len(set(rows[0])) == 1 else ""
            for row in rows:
                if len(row) > 1 and (fact := self._list_price(url, group, section, row[0], row[1])) is not None:
                    yield fact

    def _offer_field(self, offer: Selector, field: str) -> Optional[str]:
        """Read a shop field of the current price of an offer.

        Args:
            offer (Selector): The offer.
            field (str): The field, e.g. `shop-original-price`.

        Returns:
            Optional[str]: Its value, None when missing.
        """
        meta = offer.css(self.OFFER_FIELD.format(field=field)).first
        return meta.attrib.get("content") if meta is not None else None

    def _offer_price(
        self, offer: Selector, product: str, specs: Dict[str, str], base: Dict[str, RawValue]
    ) -> Optional[ServicePrice]:
        """Read the price of an offer of a product page.

        Args:
            offer (Selector): The offer (a billing cycle).
            product (str): The schema.org product name, e.g. `VPS 1_2_60`.
            specs (Dict[str, str]): The specification of its product line.
            base (Dict[str, RawValue]): The fields of its page.

        Returns:
            Optional[ServicePrice]: The regular price for its months, None without price.
        """
        months_text, original, current = (
            self._offer_field(offer, "shop-period"),
            self._offer_field(offer, "shop-original-price"),
            self._offer_field(offer, "shop-current-price"),
        )
        amount = original if self._offer_field(offer, "shop-promotion-id") else current
        if not months_text or not months_text.isdigit() or amount is None:
            return None
        try:
            price = Decimal(amount)
        except ArithmeticError:
            self.logger.debug("The %s offer of %s has an unreadable price %r.", self.name, product, amount)
            return None
        months = int(months_text)
        attributes: Dict[str, JsonValue] = {"vat": "excluded", **specs}
        if current is not None and current != amount:
            attributes["first_period_price"] = current
        cpu = re.search(r"\d+", specs.get("cpu", ""))
        ram = re.search(r"\d+(?:\.\d+)?", specs.get("ram", ""))
        return self._price_fact(
            {
                **base,
                "sku_key": f"{base['sku_key']}/{product}/{months}",
                "instance_type": product,
                "vcpu": int(cpu.group()) if cpu else None,
                "memory_gib": Decimal(ram.group()) if ram else None,
                "attributes": attributes,
                "unit": PriceUnit.MONTH,
                "unit_raw": f"{months} months",
                "unit_factor": Decimal(months),
                "price": price,
                "model": PriceModel.FREE
                if price == 0
                else PriceModel.COMMITMENT
                if months > 1
                else PriceModel.ON_DEMAND,
                "term": self.TERMS.get(months, PriceTerm.NONE) if months > 1 else PriceTerm.NONE,
            }
        )

    def _offer_prices(self, response: Response) -> Iterator[ServicePrice]:
        """Read the offers of the schema.org products of a product page.

        Args:
            response (Response): The product page.

        Yields:
            ServicePrice: The price of each offer of each product, once.
        """
        url = str(response.url)
        base: Dict[str, RawValue] = {
            "sku_key": urlparse(url).path.strip("/"),
            "service": response.meta.get(self.SERVICE_META),
            "family": response.meta.get(self.FAMILY_META) or None,
            "region": self.REGION,
            "currency": self.PRICE_CURRENCY,
            "source_url": url,
            "source_kind": PriceSourceKind.PAGE,
        }
        seen: set[str] = set()
        for product in response.css(self.OFFER_PRODUCTS):
            name_meta = product.css(':scope > meta[itemprop="name"]').first
            name = name_meta.attrib.get("content", "") if name_meta is not None else ""
            line = product.xpath(self.PRODUCT_LINE).first
            specs: Dict[str, str] = {}
            for spec, selector in self.SPEC_CELLS.items():
                cell = line.css(selector).first if line is not None else None
                if cell is not None:
                    specs[spec] = self._clean_text(cell.get_all_text(separator=" ", strip=True))
            for offer in product.css(self.OFFERS):
                fact = self._offer_price(offer, name, specs, base) if name else None
                if fact is not None and fact.sku_key not in seen:
                    seen.add(fact.sku_key)
                    yield fact

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the cloud price list and the home page, whose menu lists the product pages.

        Yields:
            Request: Their requests.
        """
        self.logger.info("Reading the %s prices from %s and the product pages.", self.name, self.PRICES_URL)
        yield self._price_request(self.PRICES_URL, {self.SERVICE_META: ""})
        yield self._price_request(self.catalogue_url)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the home page menu, the cloud price list or a product page.

        Args:
            response (Response): The page.

        Yields:
            PriceFact: The product page requests, or the prices of a page.

        Raises:
            CatalogueFormatError: If the home page has no main menu.
        """
        service = response.meta.get(self.SERVICE_META)
        if not isinstance(service, str):
            entries = self._menu_entries(response)
            self.logger.info("%d %s product pages to read for their offers.", len(entries), self.name)
            for url, label, categories in entries.values():
                yield self._price_request(
                    url, {self.SERVICE_META: label, self.FAMILY_META: categories[0] if categories else ""}
                )
            return
        url = str(response.url)
        facts = list(self._offer_prices(response) if service else self._list_prices(response))
        for fact in facts:
            yield fact
        self._record_price_source(url, len(facts))
        self.logger.debug("The %s page %s gave %d prices.", self.name, url, len(facts))

    ############################
    # Publicly Exposed Methods #
    ############################

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Request the product pages of the main menu, or stream the product of a product page.

        Args:
            response (Response): The home page or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: The product page requests,
                or the product of a product page.

        Raises:
            CatalogueFormatError: If the home page has no main menu.
        """
        if self.PRODUCT_PAGE in response.meta:
            async for item in super().parse(response):
                yield item
            return
        self.logger.debug("Reading the %s main menu of %s.", self.name, response.url)
        for request in self._menu_requests(response):
            yield request
