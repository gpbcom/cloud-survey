from __future__ import annotations

# Standard Library Imports.
import json
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import urlencode

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.marketplace_software import MarketplaceSoftware


class AzureMarketplaceCrawler(BaseMarketplaceCrawler):
    """Microsoft Marketplace crawler: the apps of Azure Marketplace and AppSource, unified.

    Attributes:
        TILES_URL (ClassVar[str]): The tiles API of the marketplace search pages.
        QUERY (ClassVar[Dict[str, str]]): The tiles API parameters of every query: the apps of the US marketplace.
        PAGE_SIZE (ClassVar[int]): The tiles given per page.
        TAXONOMY_URL (ClassVar[str]): The search page, whose initial state holds the category taxonomy.
        STATE_MARKER (ClassVar[str]): The script statement assigning the initial state of the search page.
        PRODUCT_URL (ClassVar[str]): The app page, formatted with the escaped lower case app identifier.
        DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery of each catalog offer type.
        EXCLUDED_OFFER_TYPES (ClassVar[FrozenSet[str]]): The catalog offer types which are services, not software.
        PAGE (ClassVar[str]): The meta key holding the page number within a query, from 1.
        FILTERS (ClassVar[str]): The meta key holding the category filters of a query.
        LABELS (ClassVar[str]): The meta key holding the category labels of a query.
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The first page of every app.
        complement_urls (ClassVar[Tuple[str, ...]]): The search page giving the category taxonomy.

    Notes:
        The marketplace search pages read their tiles from a JSON API, 60 tiles per page: every app is read first,
        page after page. Most tiles name no category, so a tagging pass queries each subcategory (or each category
        without subcategories) of the taxonomy found in the initial state of the search page, and streams its apps
        again with the category and subcategory labels. The consulting and managed services are skipped. The
        `robots.txt` crawl delay (2 seconds) applies to every request: the page limit applies to each query.
    """

    TILES_URL: ClassVar[str] = "https://marketplace.microsoft.com/view/tiledata"
    QUERY: ClassVar[Dict[str, str]] = {
        "ReviewsMyCommentsFilter": "true",
        "country": "US",
        "entityType": "App",
        "region": "ALL",
    }
    PAGE_SIZE: ClassVar[int] = 60
    TAXONOMY_URL: ClassVar[str] = "https://marketplace.microsoft.com/en-us/search/products"
    STATE_MARKER: ClassVar[str] = "window.__INITIAL_STATE__ = "
    PRODUCT_URL: ClassVar[str] = "https://marketplace.microsoft.com/en-us/product/{}"
    DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        "VirtualMachine": DeliveryMethod.VIRTUAL_MACHINE,
        "SaaS": DeliveryMethod.SAAS,
        "Office365": DeliveryMethod.SAAS,
        "PowerBIVisuals": DeliveryMethod.SAAS,
        "AADApps": DeliveryMethod.SAAS,
        "DynamicsBC": DeliveryMethod.SAAS,
        "DynamicsCE": DeliveryMethod.SAAS,
        "DynamicsOps": DeliveryMethod.SAAS,
        "Containers": DeliveryMethod.CONTAINER,
        "ContainerApps": DeliveryMethod.CONTAINER,
        "IotEdgeModules": DeliveryMethod.CONTAINER,
        "AzureApplication": DeliveryMethod.OTHER,
        "SolutionTemplate": DeliveryMethod.OTHER,
        "ManagedApplication": DeliveryMethod.OTHER,
    }
    EXCLUDED_OFFER_TYPES: ClassVar[FrozenSet[str]] = frozenset({"ConsultingServices", "ManagedServices"})
    PAGE: ClassVar[str] = "page"
    FILTERS: ClassVar[str] = "filters"
    LABELS: ClassVar[str] = "labels"

    name = "azure-marketplace"
    catalogue_url: ClassVar[str] = f"{TILES_URL}?{urlencode({**QUERY, 'page': 1})}"
    complement_urls: ClassVar[Tuple[str, ...]] = (TAXONOMY_URL,)

    ############################
    # Internal Helpers Methods #
    ############################

    def _tiles_request(self, page: int, filters: Dict[str, str], labels: List[str]) -> Request:
        """Build the request of a page of tiles.

        Args:
            page (int): The page number, from 1.
            filters (Dict[str, str]): The category filters of the query, e.g. `{"category": "devops"}`, none for
                every app.
            labels (List[str]): The category labels of the query, given to its apps.

        Returns:
            Request: The request. Every app is read first (primary priority), the first page of a category query may
                list nothing.
        """
        meta: Dict[str, JsonValue] = {self.PAGE: page, self.FILTERS: dict(filters), self.LABELS: list(labels)}
        if filters and page == 1:
            meta[self.MAY_BE_EMPTY] = True
        url = f"{self.TILES_URL}?{urlencode({**self.QUERY, **filters, 'page': page})}"
        return self._api_request(url, meta=meta, priority=0 if filters else self.PRIMARY_PRIORITY)

    def _meta_labels(self, response: Response) -> List[str]:
        """Get the category labels of the query of a page of tiles.

        Args:
            response (Response): The tiles API response.

        Returns:
            List[str]: The category labels, none for every app.
        """
        labels = response.meta.get(self.LABELS)
        return [label for label in (labels if isinstance(labels, list) else []) if isinstance(label, str)]

    def _catalogue_request(self) -> Request:
        """Build the request of the first page of every app.

        Returns:
            Request: The request, crawled first (primary priority).
        """
        return self._tiles_request(1, {}, [])

    def _initial_state(self, response: Response) -> Dict[str, JsonValue]:
        """Read the initial state of the search page.

        Args:
            response (Response): The search page.

        Returns:
            Dict[str, JsonValue]: The initial state.

        Raises:
            CatalogueFormatError: If the page has no JSON initial state.
        """
        text = response.body.decode("utf-8", errors="replace")
        start = text.find(self.STATE_MARKER)
        if start < 0:
            self.logger.error("The %s page %s has no initial state.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "no `__INITIAL_STATE__` script")
        try:
            state, _ = json.JSONDecoder().raw_decode(text, start + len(self.STATE_MARKER))
        except json.JSONDecodeError as e:
            self.logger.error("The initial state of the %s page %s is not JSON: %s", self.name, response.url, e)
            raise CatalogueFormatError(self.name, response.url, "the `__INITIAL_STATE__` script is not JSON") from e
        return self._as_object(state)

    def _taxonomy(self, response: Response) -> Dict[str, JsonValue]:
        """Read the app category taxonomy of the search page.

        Args:
            response (Response): The search page.

        Returns:
            Dict[str, JsonValue]: The categories, by key.

        Raises:
            CatalogueFormatError: If the initial state holds no category.
        """
        data_map = self._as_object(self._as_object(self._initial_state(response).get("apps")).get("dataMap"))
        categories = self._as_object(data_map.get("categories"))
        if not categories:
            self.logger.error("The initial state of the %s page %s holds no category.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "no `apps.dataMap.categories` object")
        return categories

    def _label(self, entry: Dict[str, JsonValue], key: str) -> str:
        """Get the readable label of a taxonomy entry.

        Args:
            entry (Dict[str, JsonValue]): The category or subcategory.
            key (str): Its key in the taxonomy, the fallback label.

        Returns:
            str: Its long title, else its title, else its key.
        """
        return self._as_text(entry.get("LongTitle")) or self._as_text(entry.get("Title")) or key

    def _category_requests(self, response: Response) -> Iterator[Request]:
        """Build the requests of the tagging pass: one query per subcategory, or per category without subcategories.

        Args:
            response (Response): The search page.

        Yields:
            Request: The first page request of each query.

        Raises:
            CatalogueFormatError: If the search page has no category taxonomy.
        """
        for key, raw in self._taxonomy(response).items():
            category = self._as_object(raw)
            filters = {"category": self._as_text(category.get("UrlKey")) or key}
            labels = [self._label(category, key)]
            subcategories = self._as_object(category.get("SubCategoryDataMapping"))
            if not subcategories:
                yield self._tiles_request(1, filters, labels)
            for sub_key, sub_raw in subcategories.items():
                subcategory = self._as_object(sub_raw)
                sub_filters = {**filters, "subcategories": self._as_text(subcategory.get("UrlKey")) or sub_key}
                yield self._tiles_request(1, sub_filters, [*labels, self._label(subcategory, sub_key)])

    def _tiles(self, response: Response) -> Tuple[List[JsonValue], Optional[int]]:
        """Read a page of tiles.

        Args:
            response (Response): The tiles API response.

        Returns:
            Tuple[List[JsonValue], Optional[int]]: The app tiles of the page, and the app count of the query.

        Raises:
            CatalogueFormatError: If the page has no `apps.galleryTiles` list.
        """
        apps = self._as_object(self._as_object(self._json_body(response)).get("apps"))
        tiles = apps.get("galleryTiles")
        if not isinstance(tiles, list):
            self.logger.error("The %s page %s has no `apps.galleryTiles` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "`apps.galleryTiles` is not a list")
        count = apps.get("count")
        return tiles, count if isinstance(count, int) else None

    def _delivery(self, offer_type: str) -> DeliveryMethod:
        """Get the delivery of a catalog offer type.

        Args:
            offer_type (str): The catalog offer type, e.g. `VirtualMachine`.

        Returns:
            DeliveryMethod: The delivery, SaaS for the Dynamics 365 apps, `OTHER` when unknown.
        """
        if offer_type.startswith("Dynamics"):
            return DeliveryMethod.SAAS
        if offer_type not in self.DELIVERIES:
            self.logger.debug("Unknown %s offer type %r: delivery %s.", self.name, offer_type, DeliveryMethod.OTHER)
        return self.DELIVERIES.get(offer_type, DeliveryMethod.OTHER)

    def _product_url(self, tile: Dict[str, JsonValue]) -> Optional[str]:
        """Get the app page of a tile.

        Args:
            tile (Dict[str, JsonValue]): The app tile.

        Returns:
            Optional[str]: The app page, `None` without an app identifier.
        """
        entity_id = self._as_text(tile.get("entityIdLoweredCased")) or self._as_text(tile.get("entityId"))
        return self.PRODUCT_URL.format(entity_id.casefold().replace("|", "%7c")) if entity_id else None

    def _tile_software(self, tile: Dict[str, JsonValue], labels: List[str]) -> Optional[MarketplaceSoftware]:
        """Build the software of an app tile.

        Args:
            tile (Dict[str, JsonValue]): The app tile.
            labels (List[str]): The category labels of the query.

        Returns:
            Optional[MarketplaceSoftware]: The software, `None` when the app is a service or is invalid.
        """
        title = self._as_text(tile.get("title"))
        offer_type = self._as_text(tile.get("catalogOfferType")) or ""
        if offer_type in self.EXCLUDED_OFFER_TYPES:
            self.logger.debug("Skipping the %s app %r, a service (%s).", self.name, title, offer_type)
            return None
        details = tile.get("categoriesDetails")
        categories = [
            self._as_text(self._as_object(detail).get("longTitle"))
            for detail in (details if isinstance(details, list) else [])
        ]
        return self._build_software(
            title,
            self._as_text(tile.get("shortDescription")),
            self._product_url(tile),
            self._as_text(tile.get("publisher")),
            self._delivery(offer_type),
            list(dict.fromkeys([*categories, *labels])),
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a page of tiles.

        Args:
            response (Response): The tiles API response.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid software app of the page, with the category labels of its query.

        Raises:
            CatalogueFormatError: If the page has no `apps.galleryTiles` list.
        """
        tiles, _ = self._tiles(response)
        labels = self._meta_labels(response)
        self.logger.debug("%d %s tiles in %s.", len(tiles), self.name, response.url)
        for tile in tiles:
            if software := self._tile_software(self._as_object(tile), labels):
                yield software

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Request the tagging queries from the search page, or stream a page of tiles then request the next one.

        Args:
            response (Response): The search page, or a tiles API response (`PAGE` meta).

        Yields:
            Union[Dict[str, JsonValue], Request]: The first page request of each tagging query, or each software not
                streamed yet (or with new categories) then the next page request.
        """
        page = response.meta.get(self.PAGE)
        if not isinstance(page, int):
            requests = list(self._category_requests(response))
            self.logger.info("Requesting the %d %s category queries.", len(requests), self.name)
            for request in requests:
                yield request
            return
        async for item in super().parse(response):
            yield item
        tiles, count = self._tiles(response)
        if not tiles or count is None or page * self.PAGE_SIZE >= count:
            self.logger.info("Last %s page %s (%s apps in total).", self.name, response.url, count)
            return
        if self._within_page_limit(page + 1):
            raw_filters = self._as_object(response.meta.get(self.FILTERS))
            filters = {key: value for key, value in raw_filters.items() if isinstance(value, str)}
            self.logger.info("Requesting the %s page %d of %s.", self.name, page + 1, filters or "every app")
            yield self._tiles_request(page + 1, filters, self._meta_labels(response))
