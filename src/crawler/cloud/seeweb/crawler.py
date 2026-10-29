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
from crawler.exception import EmptyCatalogueError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue


class SeewebCrawler(BaseCloudCrawler):
    """Seeweb catalogue crawler.

    Attributes:
        MENU_COLUMNS (ClassVar[str]): The CSS selector of the products menu columns.
        MENU_LINKS (ClassVar[str]): The CSS selector of the links of a products menu column.
        PRODUCT_PATH (ClassVar[re.Pattern[str]]): The path of a product page, e.g. `/en/products/cloud-server`.
        INTRO_TEXT (ClassVar[str]): The CSS selector of the introduction paragraphs of a product page (the two
            page layouts).
        SPACE_BEFORE_PUNCTUATION (ClassVar[re.Pattern[str]]): The space left before a punctuation mark when the
            texts of the introduction elements are joined.
        SENTENCE_END (ClassVar[re.Pattern[str]]): The end of a sentence, where a too long introduction is cut.
        MAX_DESCRIPTION (ClassVar[int]): The maximum length of a product description, in characters.
        CARDS (ClassVar[str]): The CSS selector of the plan cards of a product page.
        CARD_TITLE (ClassVar[str]): The CSS selector of the title of a plan card.
        CARD_NAME (ClassVar[str]): The CSS selector of the model of a plan card (e.g. `NVIDIA H100`).
        CARD_SPECS (ClassVar[Tuple[str, ...]]): The classes of the specification cells of a plan card.
        CARD_PRICES (ClassVar[str]): The CSS selector of the price paragraphs of a plan card (their class naming the
            period, e.g. `hourly` or `hourly_3mnths`).
        RESERVATION (ClassVar[re.Pattern[str]]): The class of a reserved price, e.g. `hourly_3mnths`.
        PERIODS (ClassVar[Dict[str, PriceUnit]]): The unit of a price by the class of its paragraph.
        TERMS (ClassVar[Dict[int, PriceTerm]]): The term of a reserved price by its months.
        NUMBER (ClassVar[re.Pattern[str]]): A number of a price or a specification.
        PRICE_CURRENCY (ClassVar[str]): The currency of the prices.
        REGION (ClassVar[str]): The region of the prices (Italy).
        SERVICE_META (ClassVar[str]): The request meta holding the service of a product page.
        FAMILY_META (ClassVar[str]): The request meta holding the menu column of a product page.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): The catalogue product pages are read too, for their prices.
        PAGE_TEXT_PRICES (ClassVar[bool]): A product page without price table is read for the prices in its text.

    Notes:
        The main source is the products menu of the https://www.seeweb.it/en home page: its columns (Compute,
        Services, Storage, Dedicated Infrastructures, Security) list the product names and links only. Each product
        page is read for its description, the product name being the menu label: its English introduction
        paragraph (cut at a sentence end when too long), else its meta description, often written in Italian. The
        solution pages are skipped. The catalogue categories of a product are the titles of the menu columns
        listing it (e.g. `Services`).
        In price mode it reads the plan cards of the product pages of the menu (e.g. the GPU, NPU, shared CPU and
        high memory servers): a card gives a model, its specification (cores, memory, GPU memory, disk) and its
        price in euros, hourly or monthly, with reserved hourly prices for 3, 6 and 12 months (commitments). The
        pages whose price is computed in the browser by a configurator (e.g. Cloud Server, priced by computing
        units) have no plan card and give no price. Each page is a source.
    """

    MENU_COLUMNS: ClassVar[str] = "div.product-column"
    MENU_LINKS: ClassVar[str] = "ul li a"
    PRODUCT_PATH: ClassVar[re.Pattern[str]] = re.compile(r"^/en/products/[^/]+/?$")
    INTRO_TEXT: ClassVar[str] = ".cont-title p, div.title > p"
    SPACE_BEFORE_PUNCTUATION: ClassVar[re.Pattern[str]] = re.compile(r"\s+(?=[.,:!?)])")
    SENTENCE_END: ClassVar[re.Pattern[str]] = re.compile(r"[.!?](?=\s|$)")
    MAX_DESCRIPTION: ClassVar[int] = 1000
    CARDS: ClassVar[str] = "div.cardType"
    CARD_TITLE: ClassVar[str] = "div.card-header h2"
    CARD_NAME: ClassVar[str] = "span.cardname"
    CARD_SPECS: ClassVar[Tuple[str, ...]] = ("cpuCore", "ram", "gpuRam", "disk", "traffic")
    CARD_PRICES: ClassVar[str] = 'p[class^="hourly"], p[class^="monthly"]'
    RESERVATION: ClassVar[re.Pattern[str]] = re.compile(r"^(?P<period>hourly|monthly)_(?P<months>\d+)mnths$")
    PERIODS: ClassVar[Dict[str, PriceUnit]] = {"hourly": PriceUnit.HOUR, "monthly": PriceUnit.MONTH}
    TERMS: ClassVar[Dict[int, PriceTerm]] = {
        3: PriceTerm.THREE_MONTHS,
        6: PriceTerm.SIX_MONTHS,
        12: PriceTerm.ONE_YEAR,
        24: PriceTerm.TWO_YEARS,
        36: PriceTerm.THREE_YEARS,
    }
    NUMBER: ClassVar[re.Pattern[str]] = re.compile(r"\d+(?:[.,]\d+)?")
    PRICE_CURRENCY: ClassVar[str] = "EUR"
    REGION: ClassVar[str] = "it"
    SERVICE_META: ClassVar[str] = "price_service"
    FAMILY_META: ClassVar[str] = "price_family"

    PRODUCT_PAGE_PRICES: ClassVar[bool] = True
    PAGE_TEXT_PRICES: ClassVar[bool] = True
    name = "seeweb"
    catalogue_url: ClassVar[str] = "https://www.seeweb.it/en"
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Seeweb ",)

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

    def _shorten(self, text: str) -> str:
        """Cut a too long description at its last sentence end within the maximum length.

        Args:
            text (str): The description.

        Returns:
            str: The description, whole when short enough, else its first sentences, else its first words
                followed by an ellipsis.
        """
        if len(text) <= self.MAX_DESCRIPTION:
            return text
        head = text[: self.MAX_DESCRIPTION]
        ends = [match.end() for match in self.SENTENCE_END.finditer(head)]
        shortened = head[: ends[-1]] if ends else f"{head[: self.MAX_DESCRIPTION - 1].rsplit(' ', 1)[0]}\u2026"
        self.logger.debug("Description cut from %d to %d characters.", len(text), len(shortened))
        return shortened

    def _introduction(self, response: Response) -> Optional[str]:
        """Read the introduction of a product page: its first non-empty paragraph below the heading.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The introduction, cut at a sentence end when too long, `None` when the page has none.
        """
        for paragraph in response.css(self.INTRO_TEXT):
            text = self.SPACE_BEFORE_PUNCTUATION.sub("", self._clean_text(paragraph.get_all_text(separator=" ")))
            if text:
                return self._shorten(text)
        return None

    def _page_description(self, response: Response) -> Optional[str]:
        """Read the product description of a product page: its English introduction, else its meta description.

        The meta descriptions of the English pages are often written in Italian.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The description, `None` when the page has none.
        """
        return self._introduction(response) or super()._page_description(response)

    def _menu_entries(self, response: Response) -> Dict[str, Tuple[str, str, List[str]]]:
        """Read the product links of the products menu, once per product page, with the titles of their columns.

        Args:
            response (Response): The home page.

        Returns:
            Dict[str, Tuple[str, str, List[str]]]: The product page URL, menu label and column titles, by URL key, in
                the menu order.
        """
        entries: Dict[str, Tuple[str, str, List[str]]] = {}
        for column in response.css(self.MENU_COLUMNS):
            heading = column.css(":scope > p").first
            title = self._clean_text(heading.get_all_text(separator=" ", strip=True)) if heading is not None else ""
            links = column.css(self.MENU_LINKS)
            self.logger.debug("%d links in the products menu column %r of %s.", len(links), title, response.url)
            for link in links:
                label = self._clean_text(link.get_all_text(separator=" ", strip=True))
                url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, ""))
                path = urlparse(url).path
                if "/solutions/" in path or not self.PRODUCT_PATH.match(path):
                    self.logger.debug("Skipping the menu entry %r (%s), not a product page.", label, url)
                    continue
                if not label:
                    self.logger.debug("Skipping the menu entry %s, unnamed.", url)
                    continue
                if (key := self._url_key(url)) in entries:
                    self.logger.debug("The menu entry %r (%s) is listed again, under %r.", label, url, title)
                    entries[key][2].append(title)
                    continue
                entries[key] = (url, label, [title])
        return entries

    def _menu_requests(self, response: Response) -> List[Request]:
        """Request the product pages of the products menu, in order and without duplicates.

        Args:
            response (Response): The home page.

        Returns:
            List[Request]: The product page requests, named after the menu labels, with their menu columns.

        Raises:
            EmptyCatalogueError: If the menu links to no product page.
        """
        entries = self._menu_entries(response)
        requests: List[Request] = []
        for url, label, categories in entries.values():
            labels = [category for category in categories if category]
            if (request := self._product_page_request(url, label, categories=labels)) is not None:
                requests.append(request)
        if not entries:
            self.logger.error("The %s products menu of %s links to no product page.", self.name, response.url)
            raise EmptyCatalogueError(self.name, response.url)
        self.logger.info("%d %s product pages to read from the products menu.", len(requests), self.name)
        return requests

    def _number(self, text: str) -> Optional[Decimal]:
        """Read the first number of a text.

        Args:
            text (str): The text, e.g. `2.35 €` or `256`.

        Returns:
            Optional[Decimal]: The number, None when there is none.
        """
        match = self.NUMBER.search(text)
        return Decimal(match.group().replace(",", ".")) if match else None

    def _card_specs(self, card: Selector) -> Dict[str, str]:
        """Read the specification of a plan card.

        Args:
            card (Selector): The plan card.

        Returns:
            Dict[str, str]: Each specification written, by its class (e.g. `ram`: `256`).
        """
        specs: Dict[str, str] = {}
        for spec in self.CARD_SPECS:
            cell = card.css(f".{spec}").first
            if cell is not None and (text := self._clean_text(cell.get_all_text(separator=" ", strip=True))):
                specs[spec] = text
        return specs

    def _card_prices(self, card: Selector, base: Dict[str, RawValue]) -> Iterator[ServicePrice]:
        """Read the prices of a plan card.

        Args:
            card (Selector): The plan card.
            base (Dict[str, RawValue]): The fields of the card.

        Yields:
            ServicePrice: Its hourly or monthly price, and its reserved prices (commitments).
        """
        for paragraph in card.css(self.CARD_PRICES):
            kind = paragraph.attrib.get("class", "").split(" ")[0]
            value = paragraph.css("span").first
            price = self._number(value.get_all_text(strip=True)) if value is not None else None
            reserved = self.RESERVATION.match(kind)
            period = reserved.group("period") if reserved else kind
            if price is None or period not in self.PERIODS:
                continue
            months = int(reserved.group("months")) if reserved else 0
            fact = self._price_fact(
                {
                    **base,
                    "sku_key": f"{base['sku_key']}/{kind}",
                    "unit": self.PERIODS[period],
                    "unit_raw": kind,
                    "unit_factor": Decimal(1),
                    "price": price,
                    "model": PriceModel.FREE
                    if price == 0
                    else PriceModel.COMMITMENT
                    if months
                    else PriceModel.ON_DEMAND,
                    "term": self.TERMS.get(months, PriceTerm.NONE),
                }
            )
            if fact is not None:
                yield fact

    def _page_prices(self, response: Response) -> Iterator[ServicePrice]:
        """Read the plan cards of a product page.

        Args:
            response (Response): The product page.

        Yields:
            ServicePrice: The prices of each plan card.
        """
        url = str(response.url)
        for card in response.css(self.CARDS):
            title_node = card.css(self.CARD_TITLE).first
            name_node = card.css(self.CARD_NAME).first
            title = self._clean_text(title_node.get_all_text(separator=" ", strip=True)) if title_node else ""
            model = self._clean_text(name_node.get_all_text(separator=" ", strip=True)) if name_node else title
            if not model:
                continue
            specs = self._card_specs(card)
            cores, ram = self._number(specs.get("cpuCore", "")), self._number(specs.get("ram", ""))
            base: Dict[str, RawValue] = {
                "sku_key": f"{urlparse(url).path.strip('/')}/{card.attrib.get('id') or model}",
                "service": response.meta.get(self.SERVICE_META),
                "family": response.meta.get(self.FAMILY_META) or None,
                "region": self.REGION,
                "instance_type": model,
                "vcpu": int(cores) if cores is not None and cores == int(cores) and cores > 0 else None,
                "memory_gib": ram if ram is not None and ram > 0 else None,
                "attributes": {"title": title, **specs},
                "currency": self.PRICE_CURRENCY,
                "source_url": url,
                "source_kind": PriceSourceKind.PAGE,
            }
            yield from self._card_prices(card, base)

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the home page, whose products menu lists the product pages.

        Yields:
            Request: Its request.
        """
        self.logger.info("Reading the %s product pages listed by %s for their prices.", self.name, self.catalogue_url)
        yield self._price_request(self.catalogue_url)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the home page menu, or the plan cards of a product page.

        Args:
            response (Response): The page.

        Yields:
            PriceFact: The product page requests, or the prices of a product page.

        Raises:
            EmptyCatalogueError: If the menu lists no product page.
        """
        if self.SERVICE_META not in response.meta:
            entries = self._menu_entries(response)
            if not entries:
                self.logger.error("The %s menu of %s lists no product page.", self.name, response.url)
                raise EmptyCatalogueError(self.name, response.url)
            self.logger.info("%d %s product pages to read for their plans.", len(entries), self.name)
            for url, label, categories in entries.values():
                meta: Dict[str, JsonValue] = {
                    self.SERVICE_META: label,
                    self.FAMILY_META: categories[0] if categories else "",
                }
                yield self._price_request(url, meta)
            return
        url = str(response.url)
        facts = list(self._page_prices(response))
        for fact in facts:
            yield fact
        self._record_price_source(url, len(facts))
        self.logger.debug("The %s product page %s gave %d prices.", self.name, url, len(facts))

    ############################
    # Publicly Exposed Methods #
    ############################

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Request the product pages of the products menu, or stream the product of a product page.

        Args:
            response (Response): The home page or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: The product page requests, or the product not streamed yet.

        Raises:
            EmptyCatalogueError: If the products menu links to no product page.
        """
        if self.PRODUCT_PAGE not in response.meta:
            self.logger.debug("Reading the %s menu of %s.", self.name, response.url)
            for request in self._menu_requests(response):
                yield request
            return
        self.logger.debug("Reading the %s product page %s.", self.name, response.url)
        async for item in super().parse(response):
            yield item
