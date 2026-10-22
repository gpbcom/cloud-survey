from __future__ import annotations

# Standard Library Imports.
import base64
import json
import re
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import parse_qs, urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.gcp.enums import GcpCatalogueMeta, GcpCatalogueParameter, GcpHostPrefix, GcpHtmlAttribute
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
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

    ############################
    # Internal Helpers Methods #
    ############################

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
