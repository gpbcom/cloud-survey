from __future__ import annotations

# Standard Library Imports.
import base64
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.gcp.enums import (
    GcpCatalogueMeta,
    GcpCatalogueParameter,
    GcpHostPrefix,
    GcpHtmlAttribute,
    GcpPriceUnit,
    GcpSkuField,
)
from crawler.enums import HtmlAttribute, TextEncoding
from crawler.exception import CatalogueFormatError
from models.cloud.enums import DateCaveat, PriceModel, PriceSourceKind, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class GoogleCloudPlatformCrawler(BaseCloudCrawler):
    """Google Cloud Platform catalogue crawler.

    Attributes:
        PRODUCT_LINKS (ClassVar[str]): The CSS selector of the products menu links.
        CATEGORY_FILTERS (ClassVar[str]): The CSS selector of the catalogue category filters.
        CATEGORY_URL (ClassVar[str]): The catalogue page of a category, from its `pds` code.
        MENU_URL (ClassVar[str]): The catalogue page read for its products menu, after the categories.
        CATALOGUE_DATA (ClassVar[re.Pattern[str]]): The catalogue data embedded in a category page.
        PRODUCT_ID (ClassVar[re.Pattern[str]]): The identifier of a catalogue product, a UUID.
        NOT_PRODUCT (ClassVar[re.Pattern[str]]): The menu links which are not products (solutions, use cases).
        CATEGORY_LABEL (ClassVar[GcpHtmlAttribute]): The attribute of a category filter holding its label.
        CATEGORY_META (ClassVar[GcpCatalogueMeta]): The meta key of a category page request, holding the category label.
        MENU_HEADLINE (ClassVar[GcpHtmlAttribute]): The attribute of a menu link holding the headline of its menu group,
            if any.
        MARKETING_GROUP (ClassVar[re.Pattern[str]]): The product groups which are not categories ("Featured").
        SEE_ALL (ClassVar[re.Pattern[str]]): The menu links closing a menu category ("See all ...").
        RELEASE_NOTES_URL (ClassVar[str]): A release notes page of a product, from its path and the page name.
        RELEASE_NOTES_PAGES (ClassVar[Tuple[str, ...]]): The release notes pages read, the archive of the oldest notes
            first.
        RELEASE_NOTES_HOSTS (ClassVar[Tuple[str, ...]]): The hosts of the product pages whose path names the release
            notes.
        IGNORED_SEGMENTS (ClassVar[Tuple[str, ...]]): The path segments which do not name the product.
        DATE_HEADINGS (ClassVar[str]): The CSS selector of the dated headings of a release notes page.
        DATE_ATTRIBUTE (ClassVar[str]): The heading attribute holding its date.
        HEADING_DATE_FORMAT (ClassVar[str]): The format of the heading dates, e.g. `February 14, 2017`.
        PRICES_URL (ClassVar[str]): The SKU search of the public SKUs page (no key), every SKU in dollars.
        JSON_PREFIX (ClassVar[str]): The anti-hijacking prefix of its JSON.
        WRITTEN_PRICE (ClassVar[re.Pattern[str]]): A price as the search writes it, e.g. `0.02 USD per 1 gibibyte
            month, for 0 gibibyte to 5 gibibyte, per 1 month per account`: its tier may count another unit than its
            price (`per 3,600 second, for 0 minute to 30 minute`) and renew every day or month, per account or
            project.
        NO_PRICE (ClassVar[str]): What the search writes for a SKU without price.
        NO_PRICE_REASON (ClassVar[str]): Why such a SKU has no price.
        PRICE_UNITS (ClassVar[Dict[GcpPriceUnit, Tuple[PriceUnit, Decimal]]]): The normalized unit of a written unit,
            and the normalized units in one.
        GLOBAL_REGION (ClassVar[str]): The region of a SKU without region.
        MULTI_REGION (ClassVar[str]): The region of a SKU of several regions (listed in its attributes).
        price_rows (int): The prices read, in price mode.

    Notes:
        The catalogue is split by category: `https://cloud.google.com/products` lists the categories, and each
        category page embeds (server-side) the data of all its products. The products menu completes it with the
        products not listed in the catalogue. The class names of the pages are generated, so the crawler relies on
        tracking attributes and data structures only.
        A category page groups its products by sub-category (e.g. `AI/ML` > `Generative AI`), a product being
        listed in each of its groups: its categories are the category of the page then its groups, gathered over
        the whole page before it is streamed. A product of several category pages keeps the categories of the
        first one. In the products menu, the category of a product is the headline of its group, else the last
        category link above it.
        The catalogue dates no product: each product is dated by the earliest note of its release notes
        (`dates_launches`), at `https://cloud.google.com/<path>/docs/release-notes`, `<path>` being the path of its
        catalogue page without the segments that do not name it, e.g. `spanner`. The oldest notes of the long-lived
        products are moved to a `release-notes-archive` page, read first. A product page nested under another
        product's is looked up under its whole path only, never under its parent's, whose notes date the parent. A
        missing page is served as a page without dated headings (HTTP 200), it dates nothing.
        In price mode it reads the SKU search behind the public SKUs page (`PRICES_URL`, no Billing API key), page
        by page (`pageToken`): every SKU of every service, its prices written out, one per tier of the monthly
        usage of an account (`for 0 gibibyte to 5 gibibyte`). The search is one source, recorded once its last page
        is read.
    """

    PRODUCT_LINKS: ClassVar[str] = 'a[track-type="nav"][track-metadata-position="nav - products"]'
    CATEGORY_FILTERS: ClassVar[str] = '[track-type="category-filter"][data-category-id]'
    CATEGORY_URL: ClassVar[str] = "https://cloud.google.com/products?pds={code}"
    MENU_URL: ClassVar[str] = "https://cloud.google.com/products?hl=en"
    CATALOGUE_DATA: ClassVar[re.Pattern[str]] = re.compile(
        r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(.*), sideChannel", re.DOTALL
    )
    PRODUCT_ID: ClassVar[re.Pattern[str]] = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    NOT_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(
        r"/(solutions|use-cases)/|console\.cloud\.google\.com", re.IGNORECASE
    )
    CATEGORY_LABEL: ClassVar[GcpHtmlAttribute] = GcpHtmlAttribute.EVENT_DETAIL
    CATEGORY_META: ClassVar[GcpCatalogueMeta] = GcpCatalogueMeta.CATEGORY
    MENU_HEADLINE: ClassVar[GcpHtmlAttribute] = GcpHtmlAttribute.MODULE_HEADLINE
    MARKETING_GROUP: ClassVar[re.Pattern[str]] = re.compile(r"^\s*featured\b", re.IGNORECASE)
    SEE_ALL: ClassVar[re.Pattern[str]] = re.compile(r"^\s*see all\b", re.IGNORECASE)

    name = "gcp"
    catalogue_url: ClassVar[str] = "https://cloud.google.com/products"
    complement_urls: ClassVar[Tuple[str, ...]] = (MENU_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Google Cloud ", "Google ")
    dates_launches: ClassVar[bool] = True
    RELEASE_NOTES_URL: ClassVar[str] = "https://cloud.google.com/{path}/docs/{page}"
    RELEASE_NOTES_PAGES: ClassVar[Tuple[str, ...]] = ("release-notes-archive", "release-notes")
    RELEASE_NOTES_HOSTS: ClassVar[Tuple[str, ...]] = ("cloud.google.com", "docs.cloud.google.com")
    IGNORED_SEGMENTS: ClassVar[Tuple[str, ...]] = ("products", "security", "docs", "overview")
    DATE_HEADINGS: ClassVar[str] = "h2[data-text]"
    DATE_ATTRIBUTE: ClassVar[str] = "data-text"
    HEADING_DATE_FORMAT: ClassVar[str] = "%B %d, %Y"
    PRICES_URL: ClassVar[str] = "https://cloud.google.com/__/json/searchskus?filter=*&currency=USD"
    JSON_PREFIX: ClassVar[str] = ")]}'\n"
    WRITTEN_PRICE: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<price>[\d.,]+) (?P<currency>[A-Z]{3})(?P<free> \(Free\))? "
        r"per (?:(?P<quantity>[\d.,]+) )?(?P<unit>[a-z ]+?)"
        r"(?:, for (?P<start>[\d.,]+)(?: (?P<start_unit>[a-z ]+?))? +"
        r"(?:to (?P<end>[\d.,]+) (?P<end_unit>[a-z ]+?)|and above))?"
        r"(?:, per [\d.,]+ (?P<period>[a-z]+) per (?P<scope>account|project))?$"
    )
    NO_PRICE: ClassVar[str] = "Non existing price"
    NO_PRICE_REASON: ClassVar[str] = "The Google Cloud SKUs page states no price for the SKU."
    PRICE_UNITS: ClassVar[Dict[GcpPriceUnit, Tuple[PriceUnit, Decimal]]] = {
        GcpPriceUnit.HOUR: (PriceUnit.HOUR, Decimal(1)),
        GcpPriceUnit.MINUTE: (PriceUnit.MINUTE, Decimal(1)),
        GcpPriceUnit.SECOND: (PriceUnit.SECOND, Decimal(1)),
        GcpPriceUnit.MONTH: (PriceUnit.MONTH, Decimal(1)),
        GcpPriceUnit.DAY: (PriceUnit.HOUR, Decimal(24)),
        GcpPriceUnit.YEAR: (PriceUnit.YEAR, Decimal(1)),
        GcpPriceUnit.GIBIBYTE: (PriceUnit.GIB, Decimal(1)),
        GcpPriceUnit.MEBIBYTE: (PriceUnit.GIB, Decimal(1) / Decimal(1024)),
        GcpPriceUnit.TEBIBYTE: (PriceUnit.GIB, Decimal(1024)),
        GcpPriceUnit.GIGABYTE: (PriceUnit.GIB, Decimal(1)),
        GcpPriceUnit.GIBIBYTE_HOUR: (PriceUnit.GIB_HOUR, Decimal(1)),
        GcpPriceUnit.GIGABYTE_HOUR: (PriceUnit.GIB_HOUR, Decimal(1)),
        GcpPriceUnit.GIBIBYTE_MONTH: (PriceUnit.GIB_MONTH, Decimal(1)),
        GcpPriceUnit.GIBIBYTE_DAY: (PriceUnit.GIB_HOUR, Decimal(24)),
        GcpPriceUnit.GIBIBYTE_SECOND: (PriceUnit.GIB_SECOND, Decimal(1)),
        GcpPriceUnit.TEBIBYTE_MONTH: (PriceUnit.GIB_MONTH, Decimal(1024)),
        GcpPriceUnit.COUNT: (PriceUnit.REQUEST, Decimal(1)),
    }
    GLOBAL_REGION: ClassVar[str] = "global"
    MULTI_REGION: ClassVar[str] = "multi-region"

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.price_rows = 0

    ############################
    # Internal Helpers Methods #
    ############################

    def _release_notes_path(self, url: str) -> Optional[str]:
        """Get the path naming a product's release notes from its catalogue page.

        Args:
            url (str): The catalogue page of the product.

        Returns:
            Optional[str]: The path, e.g. `spanner`, `None` when the page is not on a Google Cloud host.
        """
        link = urlparse(url)
        if link.netloc not in self.RELEASE_NOTES_HOSTS:
            return None
        segments = [segment for segment in link.path.split("/") if segment and segment not in self.IGNORED_SEGMENTS]
        return "/".join(segments) or None

    def _release_notes_pages(self, url: Optional[str]) -> List[str]:
        """Get the release notes pages of a product, the archive first.

        Args:
            url (Optional[str]): The catalogue page of the product, if any.

        Returns:
            List[str]: The pages, none when the catalogue page is not on a Google Cloud host.
        """
        path = self._release_notes_path(url) if url else None
        if not path:
            return []
        return [self.RELEASE_NOTES_URL.format(path=path, page=page) for page in self.RELEASE_NOTES_PAGES]

    def _heading_date(self, text: str) -> Optional[datetime]:
        """Parse the date of a release notes heading.

        Args:
            text (str): The heading date, e.g. `February 14, 2017`.

        Returns:
            Optional[datetime]: The date in UTC, `None` when unreadable or implausible.
        """
        try:
            parsed = datetime.strptime(text.strip(), self.HEADING_DATE_FORMAT).replace(tzinfo=UTC)
        except ValueError:
            return None
        return parsed if self.EARLIEST_DATE <= parsed <= datetime.now(UTC) else None

    def _earliest_note(self, response: Response) -> Optional[datetime]:
        """Read the date of the earliest note of a release notes page.

        Args:
            response (Response): The release notes page.

        Returns:
            Optional[datetime]: The earliest dated heading, `None` when the page has none.
        """
        texts = [heading.attrib.get(self.DATE_ATTRIBUTE, "") for heading in response.css(self.DATE_HEADINGS)]
        dates = [date for date in (self._heading_date(text) for text in texts) if date is not None]
        if not dates:
            self.logger.debug("No dated release note in %s.", response.url)
            return None
        return min(dates)

    async def _launch_source(self, product: CloudProduct) -> Optional[Tuple[datetime, DateCaveat]]:
        """Read the launch of a product from the earliest note of its release notes (archive first).

        Args:
            product (CloudProduct): The product, undated.

        Returns:
            Optional[Tuple[datetime, DateCaveat]]: The launch and its caveat, `None` when the product has no
                readable release notes.
        """
        for page in self._release_notes_pages(product.url):
            response = await self._fetch_launch_page(page)
            launched = self._earliest_note(response) if response is not None else None
            if launched is not None:
                return self._announced(launched)
        return None

    def _url_key(self, url: str) -> str:
        """Compare the documentation links (`docs.cloud.google.com`) as product site links.

        Args:
            url (str): The absolute product URL.

        Returns:
            str: The generic URL key, without the `docs.` sub-domain.
        """
        return super()._url_key(url).removeprefix(GcpHostPrefix.DOCS)

    def _category_code(self, category_id: int) -> str:
        """Encode a category identifier as the `pds` parameter of its catalogue page (protobuf field 1, base64).

        Args:
            category_id (int): The category identifier.

        Returns:
            str: The `pds` code, e.g. `CAE` for the category 1.
        """
        varint = bytearray()
        value = category_id
        while value > 0x7F:
            varint.append((value & 0x7F) | 0x80)
            value >>= 7
        varint.append(value)
        return base64.urlsafe_b64encode(bytes([0x08]) + bytes(varint)).decode().rstrip("=")

    def _category_labels(self, response: Response) -> Dict[int, str]:
        """Get the label of each category of the catalogue home page.

        Args:
            response (Response): The catalogue home page.

        Returns:
            Dict[int, str]: The label of each category identifier, in category order, empty when unlabelled.
        """
        labels: Dict[int, str] = {}
        for category in response.css(self.CATEGORY_FILTERS):
            label = category.attrib.get(self.CATEGORY_LABEL) or category.get_all_text(separator=" ", strip=True)
            identifier = int(category.attrib.get(GcpHtmlAttribute.CATEGORY_ID, 0))
            labels[identifier] = labels.get(identifier) or self._clean_text(label)
        return dict(sorted(labels.items()))

    def _catalogue_data(self, response: Response) -> JsonValue:
        """Read the catalogue data embedded in a category page.

        Args:
            response (Response): The category page.

        Returns:
            JsonValue: The catalogue data.

        Raises:
            CatalogueFormatError: If the page does not embed the catalogue data.
        """
        for script in response.css("script::text").getall():
            if match := self.CATALOGUE_DATA.search(script):
                try:
                    data: JsonValue = json.loads(match.group(1))
                except json.JSONDecodeError as e:
                    self.logger.error("The %s catalogue data of %s is not JSON: %s", self.name, response.url, e)
                    raise CatalogueFormatError(self.name, response.url, "the catalogue data is not JSON") from e
                return data
        self.logger.error("The %s catalogue data (`ds:1`) of %s is missing.", self.name, response.url)
        raise CatalogueFormatError(self.name, response.url, "the catalogue data (`ds:1`) is missing")

    def _catalogue_entries(
        self, value: JsonValue, group: Optional[str] = None
    ) -> Iterator[Tuple[List[JsonValue], Optional[str]]]:
        """Find the products of the catalogue data: the lists starting with a UUID, the product name at index 6.

        Args:
            value (JsonValue): The catalogue data.
            group (Optional[str]): The title of the product group holding the data, if any.

        Yields:
            Tuple[List[JsonValue], Optional[str]]: Each product entry, depth first, with the title of its group.

        Notes:
            A product group is a list of its product entries, then a null, then its title (and its description).
        """
        if not isinstance(value, list):
            return
        identifier = value[0] if value else None
        if len(value) > 7 and isinstance(identifier, str) and self.PRODUCT_ID.match(identifier):
            yield value, group
            return
        if len(value) > 2 and isinstance(value[0], list) and isinstance(value[2], str):
            group = value[2]
        for child in value:
            yield from self._catalogue_entries(child, group)

    def _entry_text(self, entry: List[JsonValue], index: int, sub_index: int = -1) -> str:
        """Read a text of a catalogue product entry.

        Args:
            entry (List[JsonValue]): The product entry.
            index (int): The position of the text, or of the list holding it.
            sub_index (int): The position of the text in that list, `-1` when the text is directly at `index`.

        Returns:
            str: The text, empty when missing.
        """
        value = entry[index] if index < len(entry) else None
        if sub_index >= 0:
            value = value[sub_index] if isinstance(value, list) and sub_index < len(value) else None
        return value if isinstance(value, str) else ""

    def _former_names(self, entry: List[JsonValue]) -> List[str]:
        """Read the former names (aliases) of a catalogue product entry, e.g. `Vertex AI`.

        Args:
            entry (List[JsonValue]): The product entry.

        Returns:
            List[str]: The former names.
        """
        aliases = entry[24] if len(entry) > 24 else None
        names: List[str] = []
        for alias in aliases if isinstance(aliases, list) else []:
            names.extend(name for name in (alias if isinstance(alias, list) else [alias]) if isinstance(name, str))
        return names

    def _category_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of a category page.

        Args:
            response (Response): The category page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the category, its former names remembered once it was handled.

        Raises:
            CatalogueFormatError: If the page does not embed the catalogue data.
        """
        entries = list(self._catalogue_entries(self._catalogue_data(response)))
        self.logger.debug("%d catalogue entries in %s.", len(entries), response.url)
        category = response.meta.get(self.CATEGORY_META)
        former_names: Dict[str, List[str]] = {}
        products: List[CloudProduct] = []
        for entry, group in entries:
            url = urljoin(response.url, self._entry_text(entry, 1, 2)) if self._entry_text(entry, 1, 2) else None
            if group and self.MARKETING_GROUP.search(group):
                self.logger.debug("Ignoring the marketing group %r of %r.", group, self._entry_text(entry, 6))
                group = None
            categories = [category if isinstance(category, str) else None, group]
            name, description = self._entry_text(entry, 6), self._entry_text(entry, 7)
            if product := self._build_product(name, description, url, categories=categories):
                products.append(product)
                former_names.setdefault(self._name_key(product.name), []).extend(self._former_names(entry))
        for product in self._merge_categories(products):
            yield product
            self._remember(former_names.get(self._name_key(product.name), []))

    def _menu_links(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the product links of the products menu, skipping category headers, "See all" and solution links.

        Args:
            response (Response): A catalogue page.

        Yields:
            Iterator[CloudProduct]: Each valid product link of the menu, with its category, if any.
        """
        links = response.css(self.PRODUCT_LINKS)
        self.logger.debug("%d products menu links in %s.", len(links), response.url)
        heading: Optional[str] = None
        for link in links:
            texts = [
                text for text in (child.get_all_text(separator=" ", strip=True) for child in link.children) if text
            ]
            href = link.attrib.get(HtmlAttribute.HREF, "")
            if len(texts) == 1:
                heading = None if self.SEE_ALL.search(texts[0]) else texts[0]
            headline = link.attrib.get(self.MENU_HEADLINE)
            category = None if headline and self.MARKETING_GROUP.search(headline) else headline or heading
            if len(texts) != 2 or self.NOT_PRODUCT.search(href):
                self.logger.debug(
                    "Skipping the menu link %r, not a product.", link.attrib.get(GcpHtmlAttribute.TRACK_NAME)
                )
            elif product := self._build_product(texts[0], texts[1], urljoin(response.url, href), categories=[category]):
                yield product

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products menu.

        Args:
            response (Response): A catalogue page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menu, with the categories of all its links.
        """
        yield from self._merge_categories(self._menu_links(response))

    def _is_home_page(self, response: Response) -> bool:
        """Tell whether a page is the catalogue home page, which lists the categories.

        Args:
            response (Response): A catalogue page.

        Returns:
            bool: Whether the page is the catalogue home page.
        """
        return not parse_qs(urlparse(response.url).query)

    def _sku_page(self, response: Response) -> Dict[str, JsonValue]:
        """Read a page of the SKU search, behind its anti-hijacking prefix (`)]}'`).

        Args:
            response (Response): The page.

        Returns:
            Dict[str, JsonValue]: The page.

        Raises:
            CatalogueFormatError: If it is not a JSON object.
        """
        text = response.body.decode(TextEncoding.UTF_8, errors=TextEncoding.REPLACE)
        if text.startswith(self.JSON_PREFIX):
            text = text[len(self.JSON_PREFIX) :]
        try:
            data: JsonValue = json.loads(text)
        except json.JSONDecodeError as e:
            self.logger.error("The Google Cloud SKU page %s is not JSON: %s", response.url, e)
            raise CatalogueFormatError(self.name, response.url, "the SKU page is not JSON") from e
        if not isinstance(data, dict):
            self.logger.error("The Google Cloud SKU page %s is not an object.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the SKU page is not a JSON object")
        return data

    def _written_unit(self, unit: str) -> Tuple[PriceUnit, Decimal]:
        """Normalize the unit a SKU price is written per.

        Args:
            unit (str): The unit, e.g. `gibibyte month`.

        Returns:
            Tuple[PriceUnit, Decimal]: The normalized unit and the normalized units in one, other when unknown.
        """
        try:
            return self.PRICE_UNITS[GcpPriceUnit(unit.strip())]
        except ValueError:
            self.logger.debug("The Google Cloud price unit %r has no known unit: kept as other.", unit)
            return PriceUnit.OTHER, Decimal(1)

    def _sku_prices(self, service: Dict[str, JsonValue], sku: Dict[str, JsonValue]) -> Iterator[ServicePrice]:
        """Read the prices of a SKU, one per tier.

        Args:
            service (Dict[str, JsonValue]): Its service.
            sku (Dict[str, JsonValue]): The SKU.

        Yields:
            ServicePrice: One price per written price (a tier of the daily or monthly usage of an account or a
                project, its unit, period and scope in its attributes), a SKU without price as not public.
        """
        regions = sku.get(GcpSkuField.SERVICE_REGIONS)
        regions = [region for region in regions if isinstance(region, str)] if isinstance(regions, list) else []
        region = regions[0] if len(regions) == 1 else self.MULTI_REGION if regions else self.GLOBAL_REGION
        written = sku.get(GcpSkuField.PRICES)
        for index, text in enumerate(written if isinstance(written, list) else []):
            match = self.WRITTEN_PRICE.match(text) if isinstance(text, str) else None
            if text == self.NO_PRICE:
                fact = self._price_fact(
                    {
                        "sku_key": f"{sku.get(GcpSkuField.SKU_ID)}/{index}",
                        "service": service.get(GcpSkuField.CATEGORY),
                        "family": service.get(GcpSkuField.CATEGORY),
                        "region": region,
                        "attributes": {GcpSkuField.DESCRIPTION.value: sku.get(GcpSkuField.DESCRIPTION)},
                        "unit": PriceUnit.OTHER,
                        "unit_raw": self.NO_PRICE,
                        "model": PriceModel.NOT_PUBLIC,
                        "reason": self.NO_PRICE_REASON,
                        "source_url": self.PRICES_URL,
                        "source_kind": PriceSourceKind.CALCULATOR,
                    }
                )
                if fact is not None:
                    yield fact
                continue
            if match is None:
                self.logger.warning("The Google Cloud price %r of %s is unreadable.", text, sku.get(GcpSkuField.SKU_ID))
                continue
            unit, factor = self._written_unit(match["unit"])
            price = Decimal(match["price"].replace(",", ""))
            tier_unit = (match["end_unit"] or match["start_unit"] or "").strip()
            tier: Dict[str, JsonValue] = {
                key: value
                for key, value in (
                    ("tier_unit", tier_unit if tier_unit and tier_unit != match["unit"] else None),
                    ("tier_period", match["period"]),
                    ("tier_scope", match["scope"]),
                )
                if value
            }
            fields: Dict[str, RawValue] = {
                "sku_key": f"{sku.get(GcpSkuField.SKU_ID)}/{index}",
                "service": service.get(GcpSkuField.CATEGORY),
                "family": service.get(GcpSkuField.CATEGORY),
                "region": region,
                "attributes": {
                    GcpSkuField.DESCRIPTION.value: sku.get(GcpSkuField.DESCRIPTION),
                    GcpSkuField.CLOUD_SERVICE_ID.value: service.get(GcpSkuField.CLOUD_SERVICE_ID),
                    **({GcpSkuField.SERVICE_REGIONS.value: list(regions)} if len(regions) > 1 else {}),
                    **tier,
                },
                "unit": unit,
                "unit_raw": f"{match['quantity'] or 1} {match['unit']}",
                "unit_factor": factor * Decimal((match["quantity"] or "1").replace(",", "")),
                "price": price,
                "currency": match["currency"],
                "model": PriceModel.FREE if price == 0 or match["free"] else PriceModel.ON_DEMAND,
                "tier_start": Decimal(match["start"].replace(",", "")) if match["start"] else Decimal(0),
                "tier_end": Decimal(match["end"].replace(",", "")) if match["end"] else None,
                "source_url": self.PRICES_URL,
                "source_kind": PriceSourceKind.CALCULATOR,
            }
            fact = self._price_fact(fields)
            if fact is not None:
                yield fact

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the first page of the SKU search, every SKU in dollars.

        Yields:
            Request: The request of the first page.
        """
        self.price_rows = 0
        self.logger.info("Reading the Google Cloud prices from %s.", self.PRICES_URL)
        yield self._price_request(self.PRICES_URL)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read a page of the SKU search: the next page first, then its prices.

        Args:
            response (Response): The page.

        Yields:
            PriceFact: The request of the next page, then the prices of the page.

        Raises:
            CatalogueFormatError: If the page is not a JSON object listing services.
        """
        data = self._sku_page(response)
        services = data.get(GcpSkuField.SKUS)
        if not isinstance(services, list):
            self.logger.error("The Google Cloud SKU page %s lists no services.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the SKU page lists no services")
        token = data.get(GcpSkuField.PAGE_TOKEN)
        if isinstance(token, str) and token:
            yield self._price_request(f"{self.PRICES_URL}&{urlencode({GcpSkuField.PAGE_TOKEN.value: token})}")
        found = 0
        for service in services:
            skus = service.get(GcpSkuField.SKUS) if isinstance(service, dict) else None
            for sku in skus if isinstance(service, dict) and isinstance(skus, list) else []:
                if isinstance(sku, dict) and isinstance(service, dict):
                    for fact in self._sku_prices(service, sku):
                        found += 1
                        yield fact
        self.price_rows += found
        self.logger.debug("Google Cloud SKU page: %d services, %d prices.", len(services), found)
        if not (isinstance(token, str) and token):
            self._record_price_source(self.PRICES_URL, self.price_rows)
            self.logger.info("The Google Cloud SKUs are read whole: %d prices.", self.price_rows)

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of a category page, or of the products menu.

        Args:
            response (Response): A category page, or the page read for its products menu.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.

        Raises:
            CatalogueFormatError: If a category page does not embed the catalogue data.
        """
        if GcpCatalogueParameter.PDS in parse_qs(urlparse(response.url).query):
            return self._category_products(response)
        return self._menu_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Request the category pages from the catalogue home page, or stream the products of the other pages.

        Args:
            response (Response): A catalogue page.

        Yields:
            Union[Dict[str, JsonValue], Request]: The category page requests, or each product not streamed yet.

        Raises:
            CatalogueFormatError: If the catalogue home page lists no category.
        """
        if not self._is_home_page(response):
            async for item in super().parse(response):
                yield item
            return
        labels = self._category_labels(response)
        if not labels:
            self.logger.error("The %s catalogue home page %s lists no category.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "no catalogue category found")
        self.logger.info("Requesting the %d %s catalogue categories.", len(labels), self.name)
        for category_id, label in labels.items():
            url = self.CATEGORY_URL.format(code=self._category_code(category_id))
            yield Request(url, priority=self.PRIMARY_PRIORITY, meta={self.CATEGORY_META: label})
