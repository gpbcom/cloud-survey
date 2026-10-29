from __future__ import annotations

# Standard Library Imports.
import json
import re
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
from crawler.cloud.civo.enums import (
    CivoFooterColumn,
    CivoJsonLdField,
    CivoPriceColumn,
    CivoPriceOption,
    CivoPricingAnchor,
)
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class CivoCrawler(BaseCloudCrawler):
    """Civo catalogue crawler.

    Attributes:
        SITE_URL (ClassVar[str]): The website root, the links being relative to it.
        PRIVATE_CLOUD_URL (ClassVar[str]): The Private Cloud hub page.
        AI_URL (ClassVar[str]): The Civo AI hub page, also listing the GPU models and read for its footer.
        PRICING_URL (ClassVar[str]): The pricing page, whose navigation lists the priced services.
        LD_JSON (ClassVar[str]): The CSS selector of the JSON-LD scripts.
        GPU_CARDS (ClassVar[str]): The CSS selector of the GPU model cards of the Civo AI hub.
        PRICING_NAV (ClassVar[str]): The CSS selector of the pricing navigation entries.
        FOOTER_COLUMNS (ClassVar[FrozenSet[CivoFooterColumn]]): The footer columns listing products.
        FOOTER_NOT_PRODUCT (ClassVar[re.Pattern[str]]): The footer links which are not product pages.
        URL_ALIASES (ClassVar[Dict[str, str]]): The short paths redirecting to a product page, by redirected path.
        PRICING_PAGES (ClassVar[Dict[str, str]]): The product page path covering a pricing anchor, by
            `CivoPricingAnchor`.
        PRICING_NOT_PRODUCT (ClassVar[FrozenSet[CivoPricingAnchor]]): The pricing anchors which are not products.
        HUB_CATEGORIES (ClassVar[Dict[str, CivoFooterColumn]]): The category of the products of each hub page, by
            hub page: the label of its footer column.
        PRICE_CURRENCY (ClassVar[str]): The currency of the pricing page.
        PRICE_VALUE (ClassVar[str]): The CSS selector of a price of a table cell (`data-option` hourly or monthly).
        OPTION_ATTRIBUTE (ClassVar[str]): The attribute of a price telling whether it is hourly or monthly.
        AMOUNT (ClassVar[re.Pattern[str]]): A written price, e.g. `$1,883.40`.
        TERM_ID (ClassVar[re.Pattern[str]]): The id of a commitment price container, e.g. `12_months`.
        TERMS (ClassVar[Dict[str, PriceTerm]]): The term of a commitment, by its months.
        PER_GIB (ClassVar[re.Pattern[str]]): A row priced per GB (a storage).
        SIZE (ClassVar[re.Pattern[str]]): A memory or storage size, in GB or TB.
        COUNT (ClassVar[re.Pattern[str]]): The count a cell starts with (cores).
        TB (ClassVar[str]): The terabyte unit of a size.
        GIB_PER_TB (ClassVar[Decimal]): The GiB of a TB.
        FREE (ClassVar[str]): The word of a free row (case-folded).
        TRAFFIC_UNIT (ClassVar[str]): The unit written for a free traffic row.
        PRICING_SECTION (ClassVar[str]): The id of the pricing page container (not a service).
        ON_DEMAND (ClassVar[str]): The key part of an on-demand price.
        HEADING_ATTRIBUTE (ClassVar[str]): The attribute holding the heading of a table.
        ROW_ATTRIBUTE (ClassVar[str]): The attribute holding the plain cells of a row.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): The catalogue product pages are read too, for their price tables.
        PAGE_TEXT_PRICES (ClassVar[bool]): A product page without price table is read for the prices in its text.

    Notes:
        The main source is the JSON-LD service of the three hub pages (https://www.civo.com/public-cloud,
        `/private-cloud` and `/ai`): its offer catalogue (`hasOfferCatalog.itemListElement`) gives the name,
        description and URL of each product. The Civo AI hub also lists the GPU models as cards. The pricing
        navigation adds the priced services without a product page (Object Store), the other entries being
        covered by their product pages. Last, the footer columns "Public Cloud", "Private Cloud" and "Civo AI"
        link to the remaining product pages, read for their description and named after the footer label.
        A hub product is filed under its hub (`HUB_CATEGORIES`, e.g. `Civo AI`), a footer product under its footer
        columns, a priced service under none (the pricing navigation is not grouped).
        The JSON-LD links are short paths redirecting to the product pages: they are replaced by the product page
        URLs, and compared with them, through `URL_ALIASES`.
        In price mode it reads the tables of the pricing page (`PRICING_URL`, in dollars): each row has an hourly
        and a monthly price (`data-option`), on demand and, for a GPU, per commitment term (`6_months` to
        `36_months`), its service and group being the ids of its sections. A storage row is priced per GB, the free
        traffic as free.
    """

    SITE_URL: ClassVar[str] = "https://www.civo.com/"
    PRIVATE_CLOUD_URL: ClassVar[str] = "https://www.civo.com/private-cloud"
    AI_URL: ClassVar[str] = "https://www.civo.com/ai"
    PRICING_URL: ClassVar[str] = "https://www.civo.com/pricing"
    LD_JSON: ClassVar[str] = 'script[type="application/ld+json"]::text'
    GPU_CARDS: ClassVar[str] = "div[data-card] article a[href]"
    PRICING_NAV: ClassVar[str] = "aside.pricing-nav a.pricing-nav-item"
    FOOTER_COLUMNS: ClassVar[FrozenSet[CivoFooterColumn]] = frozenset(
        {CivoFooterColumn.PUBLIC_CLOUD, CivoFooterColumn.PRIVATE_CLOUD, CivoFooterColumn.CIVO_AI}
    )
    FOOTER_NOT_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(r"^/pricing\b")
    URL_ALIASES: ClassVar[Dict[str, str]] = {
        "/kubernetes": "/public-cloud/kubernetes",
        "/compute": "/public-cloud/compute",
        "/databases": "/public-cloud/databases",
        "/load-balancers": "/public-cloud/load-balancers",
        "/features/block-storage": "/public-cloud/block-storage",
        "/civostack-enterprise": "/private-cloud/civostack-enterprise",
        "/flexcore": "/private-cloud/flexcore",
        "/vmware-alternative": "/private-cloud/vmware-alternative",
        "/ai/kubernetes": "/ai/kubernetes-gpu",
        "/ai/compute": "/ai/gpu-compute",
    }
    PRICING_PAGES: ClassVar[Dict[str, str]] = {
        CivoPricingAnchor.KUBERNETES: "/public-cloud/kubernetes",
        CivoPricingAnchor.COMPUTE_INSTANCES: "/public-cloud/compute",
        CivoPricingAnchor.DATABASES: "/public-cloud/databases",
        CivoPricingAnchor.LOAD_BALANCERS: "/public-cloud/load-balancers",
        CivoPricingAnchor.VOLUMES: "/public-cloud/block-storage",
        CivoPricingAnchor.NVIDIA_GPUS: "/ai/cloud-gpu",
    }
    PRICING_NOT_PRODUCT: ClassVar[FrozenSet[CivoPricingAnchor]] = frozenset({CivoPricingAnchor.DATA_TRANSFER})
    HUB_CATEGORIES: ClassVar[Dict[str, CivoFooterColumn]] = {
        "https://www.civo.com/public-cloud": CivoFooterColumn.PUBLIC_CLOUD,
        PRIVATE_CLOUD_URL: CivoFooterColumn.PRIVATE_CLOUD,
        AI_URL: CivoFooterColumn.CIVO_AI,
    }

    PRODUCT_PAGE_PRICES: ClassVar[bool] = True
    PAGE_TEXT_PRICES: ClassVar[bool] = True
    name = "civo"
    catalogue_url: ClassVar[str] = "https://www.civo.com/public-cloud"
    complement_urls: ClassVar[Tuple[str, ...]] = (PRIVATE_CLOUD_URL, AI_URL, PRICING_URL)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Civo ",)
    PRICE_CURRENCY: ClassVar[str] = "USD"
    PRICE_VALUE: ClassVar[str] = ".price-value[data-option]"
    OPTION_ATTRIBUTE: ClassVar[str] = "data-option"
    AMOUNT: ClassVar[re.Pattern[str]] = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")
    TERM_ID: ClassVar[re.Pattern[str]] = re.compile(r"^(\d+)_months$")
    TERMS: ClassVar[Dict[str, PriceTerm]] = {
        "6": PriceTerm.SIX_MONTHS,
        "12": PriceTerm.ONE_YEAR,
        "24": PriceTerm.TWO_YEARS,
        "36": PriceTerm.THREE_YEARS,
    }
    PER_GIB: ClassVar[re.Pattern[str]] = re.compile(r"^Per (?:1 )?GB$", re.IGNORECASE)
    SIZE: ClassVar[re.Pattern[str]] = re.compile(r"([\d.]+)\s*(GB|TB)\b", re.IGNORECASE)
    COUNT: ClassVar[re.Pattern[str]] = re.compile(r"^(\d+)")
    TB: ClassVar[str] = "TB"
    GIB_PER_TB: ClassVar[Decimal] = Decimal(1024)
    FREE: ClassVar[str] = "free"
    TRAFFIC_UNIT: ClassVar[str] = "GB"
    PRICING_SECTION: ClassVar[str] = "pricing"
    ON_DEMAND: ClassVar[str] = "on-demand"
    HEADING_ATTRIBUTE: ClassVar[str] = "heading"
    ROW_ATTRIBUTE: ClassVar[str] = "row"

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

    def _url_key(self, url: str) -> str:
        """Compare the short paths with the product pages they redirect to, and the pricing anchors apart.

        Args:
            url (str): The absolute product URL.

        Returns:
            str: The URL key of the product page, e.g. `civo.com/public-cloud/databases` for `/databases`, with the
                anchor for the pricing page entries (`civo.com/pricing#object-store`).
        """
        link = urlparse(url.casefold())
        path = link.path.rstrip("/")
        path = self.URL_ALIASES.get(path, path)
        anchor = f"#{link.fragment}" if path == "/pricing" and link.fragment else ""
        return f"{link.netloc.removeprefix('www.')}{path}{anchor}"

    def _canonical_url(self, link: str) -> str:
        """Get the product page URL of a JSON-LD link, which may be a short path redirecting to it.

        Args:
            link (str): The absolute or relative link.

        Returns:
            str: The absolute product page URL, e.g. `https://www.civo.com/public-cloud/databases` for `/databases`.
        """
        url = urljoin(self.SITE_URL, link)
        path = urlparse(url).path.rstrip("/")
        return urljoin(self.SITE_URL, self.URL_ALIASES[path]) if path in self.URL_ALIASES else url

    def _offer_catalogues(self, response: Response) -> Iterator[List[JsonValue]]:
        """Find the offer catalogues of the JSON-LD scripts of a hub page.

        Args:
            response (Response): The hub page.

        Yields:
            List[JsonValue]: The `itemListElement` list of each offer catalogue.
        """
        for raw in response.css(self.LD_JSON).getall():
            try:
                data: JsonValue = json.loads(str(raw))
            except json.JSONDecodeError as e:
                self.logger.debug("Skipping a JSON-LD script of %s which is not JSON: %s", response.url, e)
                continue
            for node in self._walk_objects(data):
                items = self._as_object(node.get(CivoJsonLdField.HAS_OFFER_CATALOG)).get(
                    CivoJsonLdField.ITEM_LIST_ELEMENT
                )
                if isinstance(items, list):
                    self.logger.debug(
                        "Offer catalogue %r of %s: %d entries.",
                        node.get(CivoJsonLdField.NAME),
                        response.url,
                        len(items),
                    )
                    yield items

    def _offer_products(self, response: Response, categories: List[str]) -> Iterator[CloudProduct]:
        """Extract the products of the JSON-LD offer catalogues of a hub page.

        Args:
            response (Response): The hub page.
            categories (List[str]): The categories of the products of the hub.

        Yields:
            Iterator[CloudProduct]: Each valid product of the offer catalogues.
        """
        for items in self._offer_catalogues(response):
            for item in items:
                fields = self._as_object(item)
                name, description = (
                    self._as_text(fields.get(CivoJsonLdField.NAME)),
                    self._as_text(fields.get(CivoJsonLdField.DESCRIPTION)),
                )
                url = self._canonical_url(link) if (link := self._as_text(fields.get(CivoJsonLdField.URL))) else None
                if product := self._build_product(name, description, url, categories=categories):
                    yield product

    def _gpu_products(self, response: Response, categories: List[str]) -> Iterator[CloudProduct]:
        """Extract the GPU models of the cards of a hub page (only the Civo AI hub has some).

        Args:
            response (Response): The hub page.
            categories (List[str]): The categories of the products of the hub.

        Yields:
            Iterator[CloudProduct]: Each valid GPU model.
        """
        cards = response.css(self.GPU_CARDS)
        self.logger.debug("%d GPU cards in %s.", len(cards), response.url)
        for card in cards:
            name, description = card.css("h3").first, card.css("p").first
            if product := self._build_product(
                name.get_all_text(separator=" ", strip=True) if name is not None else None,
                description.get_all_text(separator=" ", strip=True) if description is not None else None,
                urljoin(self.SITE_URL, card.attrib.get(HtmlAttribute.HREF, "")),
                categories=categories,
            ):
                yield product

    def _hub_categories(self, response: Response) -> List[str]:
        """Get the categories of the products of a hub page.

        Args:
            response (Response): The hub page.

        Returns:
            List[str]: The category of the hub, e.g. `["Public Cloud"]`, empty for another page.
        """
        hubs = {self._url_key(url): label for url, label in self.HUB_CATEGORIES.items()}
        label = hubs.get(self._url_key(response.url))
        if label is None:
            self.logger.debug("The %s page %s is not a hub, its products are uncategorized.", self.name, response.url)
        return [label] if label else []

    def _hub_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of a hub page: its JSON-LD offer catalogue, then its GPU cards, filed under the hub.

        Args:
            response (Response): The hub page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the page.
        """
        categories = self._hub_categories(response)
        self.logger.debug("Extracting the %s hub products of %s under %s.", self.name, response.url, categories)
        yield from self._offer_products(response, categories)
        yield from self._gpu_products(response, categories)

    def _pricing_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the priced services of the pricing navigation which have no product page.

        Args:
            response (Response): The pricing page.

        Yields:
            Iterator[CloudProduct]: Each valid priced service without product page, e.g. Object Store.
        """
        entries = response.css(self.PRICING_NAV)
        self.logger.debug("%d pricing navigation entries in %s.", len(entries), response.url)
        for entry in entries:
            anchor = entry.attrib.get(HtmlAttribute.HREF, "")
            title, description = entry.css("h4").first, entry.css("p").first
            name = title.get_all_text(separator=" ", strip=True) if title is not None else None
            if anchor in self.PRICING_NOT_PRODUCT:
                self.logger.debug("Skipping the pricing entry %r, not a product.", name)
                continue
            if anchor in self.PRICING_PAGES:
                self.logger.debug("Skipping the pricing entry %r, covered by %s.", name, self.PRICING_PAGES[anchor])
                continue
            text = description.get_all_text(separator=" ", strip=True) if description is not None else None
            if product := self._build_product(name, text, urljoin(self.PRICING_URL, anchor)):
                yield product

    def _footer_links(self, response: Response) -> List[Tuple[str, str, List[str]]]:
        """Gather the product pages of the footer product columns with all the columns linking them.

        Args:
            response (Response): A page of the website.

        Returns:
            List[Tuple[str, str, List[str]]]: The first URL and footer label of each product page, in order, and the
                columns of all its links (matched by URL key).
        """
        links: Dict[str, Tuple[str, str, List[str]]] = {}
        for heading in response.css("footer h3.footer-heading"):
            column = self._clean_text(heading.get_all_text(separator=" ", strip=True))
            if column not in self.FOOTER_COLUMNS or heading.parent is None:
                continue
            for link in heading.parent.css("a.footer-link"):
                label = self._clean_text(link.get_all_text(separator=" ", strip=True))
                url = urljoin(self.SITE_URL, link.attrib.get(HtmlAttribute.HREF, ""))
                if self.FOOTER_NOT_PRODUCT.search(urlparse(url).path):
                    self.logger.debug("Skipping the footer link %r (%s), not a product page.", label, url)
                    continue
                columns = links.setdefault(self._url_key(url), (url, label, []))[2]
                if column not in columns:
                    columns.append(column)
        return list(links.values())

    def _footer_requests(self, response: Response) -> List[Request]:
        """Request the product pages of the footer product columns which were not streamed yet.

        Args:
            response (Response): A page of the website.

        Returns:
            List[Request]: The product page requests, named after the footer labels, filed under their footer
                columns (`PRODUCT_CATEGORIES` meta).
        """
        requests: List[Request] = []
        for url, label, columns in self._footer_links(response):
            if (request := self._product_page_request(url, label, categories=columns)) is not None:
                requests.append(request)
        self.logger.info("%d %s product pages to read from the footer of %s.", len(requests), self.name, response.url)
        return requests

    def _size_gib(self, text: str) -> Optional[Decimal]:
        """Read a memory or storage size in GiB, e.g. `96 GB`, `2.5TB`, `200GB NVMe`.

        Args:
            text (str): The size.

        Returns:
            Optional[Decimal]: The size, `None` when unreadable.
        """
        match = self.SIZE.search(text)
        if match is None:
            return None
        return Decimal(match[1]) * (self.GIB_PER_TB if match[2].upper() == self.TB else 1)

    def _row_specs(self, headers: List[str], cells: List[str]) -> Dict[str, RawValue]:
        """Read the hardware of a row of a pricing table.

        Args:
            headers (List[str]): The headers of its table.
            cells (List[str]): Its cells.

        Returns:
            Dict[str, RawValue]: Its `vcpu`, `memory_gib` and `storage_gib`, those stated.
        """
        specs: Dict[str, RawValue] = {}
        for header, cell in zip(headers, cells, strict=False):
            count = self.COUNT.match(cell)
            if header in (CivoPriceColumn.CPU, CivoPriceColumn.VCPU) and count:
                specs["vcpu"] = int(count[1])
            elif header == CivoPriceColumn.RAM and self._size_gib(cell) is not None:
                specs["memory_gib"] = self._size_gib(cell)
            elif header == CivoPriceColumn.STORAGE and self._size_gib(cell) is not None:
                specs["storage_gib"] = self._size_gib(cell)
        return specs

    def _value_price(
        self, value: Selector, base: Dict[str, RawValue], group: str, plain: List[str], per_gib: bool
    ) -> Iterator[ServicePrice]:
        """Read one price of a row: hourly or monthly, on demand or for a commitment term.

        Args:
            value (Selector): The price element (`data-option` hourly or monthly).
            base (Dict[str, RawValue]): The fields of the row.
            group (str): The table group of the row.
            plain (List[str]): The cells of the row which are not prices (its identity).
            per_gib (bool): Whether the row is priced per GiB (a storage).

        Yields:
            ServicePrice: The price, when stated (not `N/A`).
        """
        option = value.attrib.get(self.OPTION_ATTRIBUTE) or ""
        amount = self.AMOUNT.search(" ".join(value.css("::text").getall()))
        if amount is None:
            return
        price = Decimal(amount[1].replace(",", ""))
        term_id = next(
            (
                match[1]
                for ident in value.xpath("ancestor::div[@id]/@id").getall()
                if (match := self.TERM_ID.match(ident))
            ),
            None,
        )
        hourly = option == CivoPriceOption.HOURLY
        unit = (
            (PriceUnit.GIB_HOUR if hourly else PriceUnit.GIB_MONTH)
            if per_gib
            else PriceUnit.HOUR
            if hourly
            else PriceUnit.MONTH
        )
        fact = self._price_fact(
            {
                **base,
                "sku_key": f"{group}/{' | '.join(plain)}/{option}/{term_id or self.ON_DEMAND}",
                "unit": unit,
                "unit_raw": option,
                "price": price,
                "model": PriceModel.FREE if price == 0 else PriceModel.COMMITMENT if term_id else PriceModel.ON_DEMAND,
                "term": self.TERMS.get(term_id or "", PriceTerm.NONE),
            }
        )
        if fact is not None:
            yield fact

    def _table_prices(self, table: Selector) -> Iterator[ServicePrice]:
        """Read the prices of a table of the pricing page.

        Args:
            table (Selector): The table.

        Yields:
            ServicePrice: For each row, an hourly and a monthly price, on demand and per commitment term (a GPU),
                per GiB for a storage row, a free row as free.
        """
        ids = table.xpath("ancestor::*[@id]/@id").getall()
        group = ids[-1] if ids else self.PRICING_SECTION
        section = ids[-2] if len(ids) > 1 and ids[-2] != self.PRICING_SECTION else group
        heading = self._clean_text(" ".join(table.xpath("preceding::h3[1]//text()").getall()))
        headers = [self._clean_text(" ".join(cell.css("::text").getall())) for cell in table.css("thead th")]
        for row in table.css("tbody tr"):
            cells = row.css("td")
            texts = [self._clean_text(" ".join(cell.css("::text").getall())) for cell in cells]
            plain = [text for cell, text in zip(cells, texts, strict=True) if not cell.css(self.PRICE_VALUE)]
            name = plain[0] if plain else group
            per_gib = self.PER_GIB.search(name) is not None
            base: Dict[str, RawValue] = {
                "service": section.replace("-", " ").title(),
                "family": group,
                "instance_type": name if not per_gib else None,
                "attributes": {self.HEADING_ATTRIBUTE: heading, self.ROW_ATTRIBUTE: " | ".join(plain)},
                "currency": self.PRICE_CURRENCY,
                "source_url": self.PRICING_URL,
                "source_kind": PriceSourceKind.PAGE,
                **self._row_specs(headers, texts),
            }
            values = row.css(self.PRICE_VALUE)
            if not values and texts and texts[-1].casefold() == self.FREE:
                fact = self._price_fact(
                    {
                        **base,
                        "sku_key": f"{group}/{name}",
                        "unit": PriceUnit.GIB,
                        "unit_raw": self.TRAFFIC_UNIT,
                        "price": Decimal(0),
                        "model": PriceModel.FREE,
                    }
                )
                if fact is not None:
                    yield fact
            for value in values:
                yield from self._value_price(value, base, group, plain, per_gib)

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the pricing page.

        Yields:
            Request: The request of the pricing page.
        """
        self.logger.info("Reading the Civo prices from %s.", self.PRICING_URL)
        yield self._price_request(self.PRICING_URL)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the prices of the tables of the pricing page.

        Args:
            response (Response): The pricing page.

        Yields:
            PriceFact: The prices of its tables.

        Raises:
            CatalogueFormatError: If the page has no pricing table.
        """
        tables = response.css("table")
        if not tables:
            self.logger.error("The Civo pricing page %s has no table.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the pricing page has no table")
        found = 0
        for table in tables:
            for fact in self._table_prices(table):
                found += 1
                yield fact
        self._record_price_source(self.PRICING_URL, found)
        self.logger.info("The Civo pricing page is read: %d prices of %d tables.", found, len(tables))

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of a hub page or of the pricing page.

        Args:
            response (Response): The hub page or the pricing page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.
        """
        if self._url_key(response.url) == self._url_key(self.PRICING_URL):
            self.logger.debug("Extracting the %s products of the pricing page %s.", self.name, response.url)
            return self._pricing_products(response)
        return self._hub_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the products of a page, then request the footer product pages from the Civo AI hub.

        Args:
            response (Response): A hub page, the pricing page or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, then the product page requests.

        Raises:
            EmptyCatalogueError: If a hub page or the pricing page holds no valid product.
        """
        async for item in super().parse(response):
            yield item
        if self.PRODUCT_PAGE not in response.meta and self._url_key(response.url) == self._url_key(self.AI_URL):
            self.logger.debug("Requesting the %s footer product pages of the AI hub %s.", self.name, response.url)
            for request in self._footer_requests(response):
                yield request
