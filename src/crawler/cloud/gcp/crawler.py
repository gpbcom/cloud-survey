from __future__ import annotations

# Standard Library Imports.
import base64
import json
import re
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Tuple, Union
from urllib.parse import parse_qs, urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError
from models.cloud.product import CloudProduct


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

    Notes:
        The catalogue is split by category: `https://cloud.google.com/products` lists the categories, and each
        category page embeds (server-side) the data of all its products. The products menu completes it with the
        products not listed in the catalogue. The class names of the pages are generated, so the crawler relies on
        tracking attributes and data structures only.
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
        return super()._url_key(url).removeprefix("docs.")

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

    def _category_urls(self, response: Response) -> List[str]:
        """Get the catalogue page of each category.

        Args:
            response (Response): The catalogue home page.

        Returns:
            List[str]: The category pages, in category order.
        """
        ids = {int(value) for value in response.css(self.CATEGORY_FILTERS).css("::attr(data-category-id)").getall()}
        return [self.CATEGORY_URL.format(code=self._category_code(category_id)) for category_id in sorted(ids)]

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

    def _catalogue_entries(self, value: JsonValue) -> Iterator[List[JsonValue]]:
        """Find the products of the catalogue data: the lists starting with a UUID, the product name at index 6.

        Args:
            value (JsonValue): The catalogue data.

        Yields:
            List[JsonValue]: Each product entry, depth first.
        """
        if not isinstance(value, list):
            return
        identifier = value[0] if value else None
        if len(value) > 7 and isinstance(identifier, str) and self.PRODUCT_ID.match(identifier):
            yield value
            return
        for child in value:
            yield from self._catalogue_entries(child)

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
        for entry in entries:
            url = urljoin(response.url, self._entry_text(entry, 1, 2)) if self._entry_text(entry, 1, 2) else None
            product = self._build_product(self._entry_text(entry, 6), self._entry_text(entry, 7), url)
            if product:
                yield product
                self._remember(self._former_names(entry))

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products menu, skipping category headers, "See all" and solution links.

        Args:
            response (Response): A catalogue page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menu.
        """
        links = response.css(self.PRODUCT_LINKS)
        self.logger.debug("%d products menu links in %s.", len(links), response.url)
        for link in links:
            texts = [
                text for text in (child.get_all_text(separator=" ", strip=True) for child in link.children) if text
            ]
            href = link.attrib.get("href", "")
            if len(texts) != 2 or self.NOT_PRODUCT.search(href):
                self.logger.debug("Skipping the menu link %r, not a product.", link.attrib.get("track-name"))
            elif product := self._build_product(texts[0], texts[1], urljoin(response.url, href)):
                yield product

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
        if "pds" in parse_qs(urlparse(response.url).query):
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
        urls = self._category_urls(response)
        if not urls:
            self.logger.error("The %s catalogue home page %s lists no category.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "no catalogue category found")
        self.logger.info("Requesting the %d %s catalogue categories.", len(urls), self.name)
        for url in urls:
            yield Request(url, priority=self.PRIMARY_PRIORITY)
