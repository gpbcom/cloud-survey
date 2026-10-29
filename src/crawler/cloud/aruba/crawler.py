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
from crawler.cloud.aruba.enums import ArubaMenuMarkup, ArubaPriceColumn, ArubaPricePeriod, ArubaPricingCardName
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class ArubaCloudCrawler(BaseCloudCrawler):
    """Aruba Cloud catalogue crawler.

    Attributes:
        PRICING_URL (ClassVar[str]): The pricing page, listing the products by family.
        PRICING_ALIASES (ClassVar[Dict[str, str]]): The menu name of each pricing card (`ArubaPricingCardName`)
            naming a product otherwise.
        ITALIAN_WORDS (ClassVar[re.Pattern[str]]): Common Italian words, revealing an untranslated menu description.
        HTML_TAG (ClassVar[re.Pattern[str]]): An HTML tag left in a meta description, e.g. `<br/>`.
        MENU_ITEM (ClassVar[ArubaMenuMarkup]): The class of the menu items, whose links label the menu groups.
        PRICE_PAGE (ClassVar[re.Pattern[str]]): The path of a product pricing page, `/pricing/<family>/<product>`.
        PRICE_CELL (ClassVar[re.Pattern[str]]): A price of a pricing table, e.g. `€ 13.20 + VAT / month`,
            `€ 0.0164 + VAT / Mtoken (input)` or `€ 0.00028 + VAT / hour every 10 GB`.
        FREE_CELL (ClassVar[str]): The text of a free price.
        AMOUNT_FIRST (ClassVar[re.Pattern[str]]): A price written amount first, its period being its column header,
            e.g. `19.99 € + VAT` under `Monthly price`.
        HEADER_PERIODS (ClassVar[Dict[str, ArubaPricePeriod]]): The period of such a price, by its column header.
        SOLD_OUT (ClassVar[str]): The mark of a server no longer sold.
        PAGE_TITLE (ClassVar[re.Pattern[str]]): The brand suffix of the page titles.
        PERIOD_UNITS (ClassVar[Dict[ArubaPricePeriod, Tuple[PriceUnit, Decimal]]]): The unit of a price by its
            period, and the normalized units in one.
        SIZE_UNITS (ClassVar[Dict[ArubaPricePeriod, PriceUnit]]): The unit of a price of a storage size by its
            period.
        SPEC_COLUMNS (ClassVar[Tuple[ArubaPriceColumn, ...]]): The columns read as the hot columns of a server.
        SIZE (ClassVar[re.Pattern[str]]): A size in GB or TB, e.g. `4 TB`.
        PRICE_CURRENCY (ClassVar[str]): The currency of the prices.
        REGION (ClassVar[str]): The region of the prices (one price for every data center).
        SERVICE_META (ClassVar[str]): The request meta holding the service of a pricing page.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): The product pages are read too: several show prices (e.g. the
            Container Registry) the pricing pages do not.
        PAGE_TEXT_PRICES (ClassVar[bool]): A product page without price table is read for the prices in its text.
        untranslated (List[Tuple[str, str, List[str]]]): The product pages (URL, menu name and menu categories) of
            the menu entries described in Italian, to read for their English description.

    Notes:
        The main source is the products menu of the https://www.arubacloud.com/ home page: its links holding a
        description (`span.description`) are the products, with a name (`strong`), once the solution pages are
        filtered out. The product cards of the pricing page (a name and a description) complete it with the products
        missing from the menu. Some pricing cards name a menu product differently (e.g. `Server Bare Metal` for
        `Dedicated Servers`): they are renamed after the menu product, so that they are recognized as duplicates.
        A few menu descriptions are left in Italian: those products are read from their (English) product page
        instead, named after the menu label, with the page meta description.
        The catalogue categories of a menu product are the labels of the menu items holding it: its top menu (e.g.
        `Public Cloud`), then its menu group (e.g. `Container`), gathered over all the menu entries of the product.
        Those of a pricing card are the title of its pricing family section (e.g. `Public Cloud`).
        In price mode it reads the product pricing pages linked by the pricing cards (the service being the card
        name, renamed as above): each table row prices a model (a server, a resource, a license, a domain) in euros
        without VAT, one price per price cell (hourly, monthly, yearly or per million tokens, a price of a storage
        size being per GB). A yearly price next to a monthly one is a one-year commitment, alone a yearly fee. The
        specification cells are attributes, the vCPUs, memory and storage of a server its hot columns. Each page is
        a source.
    """

    PRICING_URL: ClassVar[str] = "https://www.arubacloud.com/pricing"
    PRICING_ALIASES: ClassVar[Dict[str, str]] = {
        ArubaPricingCardName.SERVER_BARE_METAL: "Dedicated Servers",
        ArubaPricingCardName.VIRTUAL_PRIVATE_SERVERS: "VPS - Virtual Private Server",
        ArubaPricingCardName.BACKUP_AGENTLESS: "Agentless Backup",
        ArubaPricingCardName.DISASTER_RECOVERY: "Disaster Recovery for VMware",
        ArubaPricingCardName.CLOUD_BARE_METAL_BACKUP: "Backup for VMware",
        ArubaPricingCardName.AI_TOOLS_TEXT_MANAGEMENT: "AI Tools",
    }
    ITALIAN_WORDS: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(?:il|della|delle|dei|degli|con|e|sviluppato|privato|connetti|ambienti|infrastrutture|semplice|modo)\b",
        re.IGNORECASE,
    )
    HTML_TAG: ClassVar[re.Pattern[str]] = re.compile(r"<[^>]*>")
    MENU_ITEM: ClassVar[ArubaMenuMarkup] = ArubaMenuMarkup.NAV_ITEM
    PRICE_PAGE: ClassVar[re.Pattern[str]] = re.compile(r"^/pricing/[^/]+/[^/]+$")
    PRICE_CELL: ClassVar[re.Pattern[str]] = re.compile(
        r"€\s*(?P<amount>\d[\d,]*(?:\.\d+)?)\s*\+\s*VAT\s*/\s*(?P<period>hour|month|year|Mtoken)"
        r"(?:\s*\((?P<side>input|output)\))?(?:\s*every\s*(?P<count>\d+)\s*(?P<size>GB|TB))?"
    )
    FREE_CELL: ClassVar[str] = "FREE"
    AMOUNT_FIRST: ClassVar[re.Pattern[str]] = re.compile(r"(?P<amount>\d[\d,]*(?:\.\d+)?)\s*€\s*\+\s*VAT")
    HEADER_PERIODS: ClassVar[Dict[str, ArubaPricePeriod]] = {
        "Monthly price": ArubaPricePeriod.MONTH,
        "Hourly price": ArubaPricePeriod.HOUR,
        "Annual price": ArubaPricePeriod.YEAR,
    }
    SOLD_OUT: ClassVar[str] = "SOLD OUT"
    PAGE_TITLE: ClassVar[re.Pattern[str]] = re.compile(r"\s*\|\s*Cloud\s*$")
    PERIOD_UNITS: ClassVar[Dict[ArubaPricePeriod, Tuple[PriceUnit, Decimal]]] = {
        ArubaPricePeriod.HOUR: (PriceUnit.HOUR, Decimal(1)),
        ArubaPricePeriod.MONTH: (PriceUnit.MONTH, Decimal(1)),
        ArubaPricePeriod.YEAR: (PriceUnit.YEAR, Decimal(1)),
        ArubaPricePeriod.MILLION_TOKENS: (PriceUnit.TOKEN, Decimal(1_000_000)),
    }
    SIZE_UNITS: ClassVar[Dict[ArubaPricePeriod, PriceUnit]] = {
        ArubaPricePeriod.HOUR: PriceUnit.GIB_HOUR,
        ArubaPricePeriod.MONTH: PriceUnit.GIB_MONTH,
    }
    SPEC_COLUMNS: ClassVar[Tuple[ArubaPriceColumn, ...]] = (
        ArubaPriceColumn.VCPUS,
        ArubaPriceColumn.RAM,
        ArubaPriceColumn.STORAGE,
    )
    SIZE: ClassVar[re.Pattern[str]] = re.compile(r"(?P<size>\d+(?:[.,]\d+)?)\s*(?P<unit>GB|TB)")
    PRICE_CURRENCY: ClassVar[str] = "EUR"
    REGION: ClassVar[str] = "global"
    SERVICE_META: ClassVar[str] = "price_service"
    PRODUCT_PAGE_PRICES: ClassVar[bool] = True
    PAGE_TEXT_PRICES: ClassVar[bool] = True

    name = "aruba"
    catalogue_url: ClassVar[str] = "https://www.arubacloud.com/"
    complement_urls: ClassVar[Tuple[str, ...]] = (PRICING_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Aruba Cloud ", "Aruba ")

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.untranslated: List[Tuple[str, str, List[str]]] = []

    ############################
    # Internal Helpers Methods #
    ############################

    def _page_description(self, response: Response) -> Optional[str]:
        """Read the product description of a product page, without the HTML tags some meta descriptions hold.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The description, `None` when the page has none.
        """
        description = super()._page_description(response)
        if not description:
            self.logger.debug("The %s product page %s has no description.", self.name, response.url)
            return None
        return self._clean_text(self.HTML_TAG.sub(" ", description))

    def _is_italian(self, text: str) -> bool:
        """Tell whether a menu description is written in Italian (at least two common Italian words).

        Args:
            text (str): The menu description.

        Returns:
            bool: Whether the description is in Italian.
        """
        return len(self.ITALIAN_WORDS.findall(text)) >= 2

    def _menu_categories(self, link: Selector) -> List[str]:
        """Read the menu categories of a menu link: the labels of the menu items holding its own item.

        Args:
            link (Selector): The menu link.

        Returns:
            List[str]: The labels, the top menu first, e.g. `["Public Cloud", "Container"]`, empty out of a menu.
        """
        labels: List[str] = []
        node = link.parent
        own_item = True
        while node is not None:
            if (
                node.tag == ArubaMenuMarkup.LIST_ITEM
                and self.MENU_ITEM in node.attrib.get(HtmlAttribute.CLASS, "").split()
            ):
                label = node.css(":scope > a").first
                if not own_item and label is not None:
                    labels.insert(0, self._clean_text(label.get_all_text(separator=" ", strip=True)))
                own_item = False
            node = node.parent
        return labels

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the home page menu: the links with a description, except the solutions.

        Args:
            response (Response): The home page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menu, once, with the menu categories of all its entries.

        Notes:
            A product listed by several menu groups (e.g. `Hybrid Connect`) is read from its first entry.
        """
        links = response.css("a.nav-link")
        self.logger.debug("%d menu links in %s.", len(links), response.url)
        entries: Dict[str, Tuple[Optional[str], str, str, List[str]]] = {}
        for link in links:
            description = link.css("span.description").first
            if description is None:
                continue
            heading = link.css("strong").first
            name = str(heading.get_all_text(separator=" ", strip=True)) if heading is not None else None
            url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, ""))
            if "/solutions/" in urlparse(url).path:
                self.logger.debug("Skipping the menu entry %r (%s), a solution page.", name, url)
                continue
            text = self._clean_text(description.get_all_text(separator=" ", strip=True))
            key = self._name_key(name) if name and self._clean_text(name) else url
            categories = self._menu_categories(link)
            if key in entries:
                self.logger.debug("The menu entry %r is listed again, under %s.", name, categories)
                entries[key][3].extend(categories)
                continue
            entries[key] = (name, text, url, categories)
        for name, text, url, categories in entries.values():
            if name and self._is_italian(text):
                self.logger.debug("The menu entry %r is described in Italian, reading its page %s.", name, url)
                self.untranslated.append((url, self._clean_text(name), categories))
                continue
            if product := self._build_product(name, text, url, categories=categories):
                yield product

    def _untranslated_requests(self) -> List[Request]:
        """Request the product pages of the menu entries described in Italian, once.

        Returns:
            List[Request]: The product page requests, named after the menu labels, with their menu categories.
        """
        pages, self.untranslated = self.untranslated, []
        requests: List[Request] = []
        for url, name, categories in pages:
            if (request := self._product_page_request(url, name, categories=categories)) is not None:
                requests.append(request)
        if requests:
            self.logger.info("%d %s product pages to read for an English description.", len(requests), self.name)
        return requests

    def _pricing_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the product cards of the pricing page: the card bodies holding a heading.

        Args:
            response (Response): The pricing page.

        Yields:
            Iterator[CloudProduct]: Each valid product card, renamed after the menu product when aliased, once, with
                the pricing families of all its cards.
        """
        entries: Dict[str, Tuple[str, Optional[str], Optional[str], List[str]]] = {}
        for section in response.css("section"):
            title = section.css("h2").first
            family = self._clean_text(title.get_all_text(separator=" ", strip=True)) if title is not None else ""
            cards = section.css("div.card-body")
            self.logger.debug("%d pricing card bodies in the family %r of %s.", len(cards), family, response.url)
            for card in cards:
                heading = card.css(":scope > h3").first
                if heading is None:
                    continue
                name = self._clean_text(heading.get_all_text(separator=" ", strip=True))
                if alias := self.PRICING_ALIASES.get(name):
                    self.logger.debug("The pricing card %r is the menu product %r.", name, alias)
                    name = alias
                key = self._name_key(name) if name else ""
                if key in entries:
                    entries[key][3].append(family)
                    continue
                description = card.css("p").first
                link = card.css("a[href]").first
                url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, "")) if link is not None else None
                text = str(description.get_all_text(separator=" ", strip=True)) if description is not None else None
                entries[key] = (name, text, url, [family])
        for name, text, url, families in entries.values():
            if product := self._build_product(name, text, url, categories=families):
                yield product

    def _price_pages(self, response: Response) -> Dict[str, str]:
        """Read the product pricing pages linked by the pricing cards, with their service.

        Args:
            response (Response): The pricing page.

        Returns:
            Dict[str, str]: The service of each pricing page (its card name, renamed after the menu product when
                aliased), by URL.
        """
        pages: Dict[str, str] = {}
        for card in response.css("div.card-body"):
            heading = card.css(":scope > h3").first
            name = self._clean_text(heading.get_all_text(separator=" ", strip=True)) if heading is not None else ""
            for link in card.css("a[href]"):
                url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, ""))
                if name and self.PRICE_PAGE.match(urlparse(url).path):
                    pages.setdefault(url, self.PRICING_ALIASES.get(name, name))
        for link in response.css("a[href]"):
            url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, ""))
            if self.PRICE_PAGE.match(urlparse(url).path) and url not in pages:
                pages[url] = ""
        return pages

    def _size_gib(self, text: str) -> Optional[Decimal]:
        """Read a size in GiB.

        Args:
            text (str): The cell, e.g. `RAM 4 GB` or `Storage 4 TB`.

        Returns:
            Optional[Decimal]: The size in GiB, None when not written.
        """
        match = self.SIZE.search(text)
        if match is None:
            return None
        size = Decimal(match.group("size").replace(",", "."))
        return size * 1024 if match.group("unit") == "TB" else size

    def _cell_price(
        self, base: Dict[str, RawValue], header: str, text: str, yearly_commitment: bool
    ) -> Optional[ServicePrice]:
        """Read a price cell of a pricing table row.

        Args:
            base (Dict[str, RawValue]): The fields of the row.
            header (str): The header of the cell column.
            text (str): The cell.
            yearly_commitment (bool): Whether a yearly price is a one-year commitment (the row has a monthly price).

        Returns:
            Optional[ServicePrice]: The price, None when the cell holds none.
        """
        attributes: Dict[str, JsonValue] = dict(base["attributes"]) if isinstance(base["attributes"], dict) else {}
        if header and header != ArubaPriceColumn.PRICE:
            attributes["column"] = header
        if text == self.FREE_CELL:
            price, period, unit, factor = Decimal(0), header, PriceUnit.UNIT, Decimal(1)
            term, model = PriceTerm.NONE, PriceModel.FREE
        else:
            match = self.PRICE_CELL.search(text)
            if match is None:
                return None
            price = Decimal(match.group("amount").replace(",", ""))
            period = match.group("period")
            unit, factor = self.PERIOD_UNITS[ArubaPricePeriod(period)]
            if match.group("size"):
                size = Decimal(match.group("count")) * (1024 if match.group("size") == "TB" else 1)
                unit, factor = self.SIZE_UNITS.get(ArubaPricePeriod(period), PriceUnit.GIB), size
            if match.group("side"):
                attributes["side"] = match.group("side")
            term, model = PriceTerm.NONE, PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND
            if period == ArubaPricePeriod.YEAR and yearly_commitment:
                unit, factor, term = PriceUnit.MONTH, Decimal(12), PriceTerm.ONE_YEAR
                model = PriceModel.FREE if price == 0 else PriceModel.COMMITMENT
        return self._price_fact(
            {
                **base,
                "sku_key": f"{base['sku_key']}/{header}/{period}/{attributes.get('side', '')}".rstrip("/"),
                "attributes": attributes,
                "unit": unit,
                "unit_raw": text[:120],
                "unit_factor": factor,
                "price": price,
                "model": model,
                "term": term,
            }
        )

    def _table_prices(self, url: str, service: str, group: str, rows: List[List[str]]) -> Iterator[ServicePrice]:
        """Read the prices of a pricing table.

        Args:
            url (str): Its pricing page.
            service (str): The service of the page.
            group (str): The heading of the table.
            rows (List[List[str]]): Its rows, the first being its header.

        Yields:
            ServicePrice: One price per price cell of each row.
        """
        if len(rows) < 2:
            return
        header = rows[0]
        path = urlparse(url).path.removeprefix("/pricing/")
        for row in rows[1:]:
            model = row[0]
            cells = dict(zip(header, row, strict=False))
            attributes: Dict[str, JsonValue] = {"vat": "excluded", "group": group}
            for column, cell in list(cells.items())[1:]:
                if (
                    not self.PRICE_CELL.search(cell)
                    and not self.AMOUNT_FIRST.search(cell)
                    and cell not in (self.FREE_CELL, column, self.SOLD_OUT)
                ):
                    attributes[column] = cell.removeprefix(column).strip()
            vcpus = re.search(r"\d+", cells.get(ArubaPriceColumn.VCPUS, ""))
            base: Dict[str, RawValue] = {
                "sku_key": f"{path}/{group}/{model}",
                "service": service,
                "family": path.split("/")[0],
                "region": self.REGION,
                "instance_type": model if vcpus else None,
                "vcpu": int(vcpus.group()) if vcpus else None,
                "memory_gib": self._size_gib(cells.get(ArubaPriceColumn.RAM, "")),
                "storage_gib": self._size_gib(cells.get(ArubaPriceColumn.STORAGE, "")),
                "attributes": attributes,
                "currency": self.PRICE_CURRENCY,
                "source_url": url,
                "source_kind": PriceSourceKind.PAGE,
            }
            yearly_commitment = any(f"/ {ArubaPricePeriod.MONTH.value}" in cell for cell in row)
            for index, cell in enumerate(row[1:], start=1):
                column = header[index] if index < len(header) else header[-1]
                for part in self.PRICE_CELL.finditer(cell):
                    fact = self._cell_price(base, column, part.group(0), yearly_commitment)
                    if fact is not None:
                        yield fact
                first = self.AMOUNT_FIRST.search(cell) if not self.PRICE_CELL.search(cell) else None
                if first is not None and column in self.HEADER_PERIODS:
                    written = f"€ {first.group('amount')} + VAT / {self.HEADER_PERIODS[column].value}"
                    sold_out = self.SOLD_OUT in cell
                    fact = self._cell_price(
                        {**base, "attributes": {**attributes, "status": "sold out"}} if sold_out else base,
                        column,
                        written,
                        yearly_commitment,
                    )
                    if fact is not None:
                        yield fact
                if cell == self.FREE_CELL and (fact := self._cell_price(base, column, cell, False)) is not None:
                    yield fact

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the pricing page, whose cards link to the product pricing pages.

        Yields:
            Request: Its request.
        """
        self.logger.info("Reading the %s pricing pages from %s.", self.name, self.PRICING_URL)
        yield self._price_request(self.PRICING_URL)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the pricing page, or a product pricing page.

        Args:
            response (Response): The page.

        Yields:
            PriceFact: The requests of the product pricing pages, or the prices of one.

        Raises:
            CatalogueFormatError: If the pricing page links to no product pricing page.
        """
        service = response.meta.get(self.SERVICE_META)
        if not isinstance(service, str):
            pages = self._price_pages(response)
            if not pages:
                self.logger.error("The %s pricing page %s links to no product pricing page.", self.name, response.url)
                raise CatalogueFormatError(self.name, response.url, "the pricing page links to no product pricing")
            self.logger.info("%d %s product pricing pages to read.", len(pages), self.name)
            for url, name in pages.items():
                yield self._price_request(url, {self.SERVICE_META: name})
            return
        url = str(response.url)
        title = self._clean_text(response.css("title::text").get())
        service = service or self.PAGE_TITLE.sub("", title) or urlparse(url).path.rsplit("/", 1)[-1]
        found = 0
        seen: Dict[str, int] = {}
        for group, rows in self._price_tables(response):
            for fact in self._table_prices(url, service, group, rows):
                count = seen.get(fact.sku_key, 0)
                seen[fact.sku_key] = count + 1
                found += 1
                yield fact if not count else fact.model_copy(update={"sku_key": f"{fact.sku_key}#{count}"})
        self._record_price_source(url, found)
        self.logger.debug("The %s pricing page %s gave %d prices.", self.name, url, found)

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the home page menu or of the pricing page.

        Args:
            response (Response): The home page or the pricing page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.
        """
        if urlparse(response.url).path.rstrip("/") == urlparse(self.PRICING_URL).path:
            self.logger.debug("Extracting the %s products of the pricing page %s.", self.name, response.url)
            return self._pricing_products(response)
        self.logger.debug("Extracting the %s products of the menu of %s.", self.name, response.url)
        return self._menu_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the products of the menu or of the pricing page, or the product of a product page.

        Args:
            response (Response): The home page, the pricing page or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, or the product page requests.

        Raises:
            EmptyCatalogueError: If the home page or the pricing page holds no product.
        """
        async for item in super().parse(response):
            yield item
        self.logger.debug("Read the %s page %s, looking for the products still untranslated.", self.name, response.url)
        for request in self._untranslated_requests():
            yield request
