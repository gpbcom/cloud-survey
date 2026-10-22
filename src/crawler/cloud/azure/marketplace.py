from __future__ import annotations

# Standard Library Imports.
import json
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import urlencode, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.azure.enums import (
    AzureCatalogApiVersion,
    AzureCatalogParameter,
    AzureMarketplaceMeta,
    AzureOfferField,
    AzureOfferType,
    AzureScriptMarker,
    AzureStateField,
    AzureTaxonomyField,
    AzureTileCategoryField,
    AzureTileField,
    AzureTilesField,
    AzureTilesParameter,
    AzureTilesParameterValue,
)
from crawler.enums import TextEncoding
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DateCaveat, DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class AzureMarketplaceCrawler(BaseMarketplaceCrawler):
    """Microsoft Marketplace crawler: the apps of Azure Marketplace and AppSource, unified.

    Attributes:
        TILES_URL (ClassVar[str]): The tiles API of the marketplace search pages.
        QUERY (ClassVar[Dict[str, str]]): The tiles API parameters of every query: the apps of the US marketplace.
        PAGE_SIZE (ClassVar[int]): The tiles given per page.
        TAXONOMY_URL (ClassVar[str]): The search page, whose initial state holds the category taxonomy.
        STATE_MARKER (ClassVar[AzureScriptMarker]): The script statement assigning the initial state of the search page.
        PRODUCT_URL (ClassVar[str]): The app page, formatted with the escaped lower case app identifier.
        DELIVERIES (ClassVar[Dict[AzureOfferType, DeliveryMethod]]): The delivery of each catalog offer type.
        EXCLUDED_OFFER_TYPES (ClassVar[FrozenSet[AzureOfferType]]): The catalog offer types which are services, not
            software.
        PAGE (ClassVar[AzureMarketplaceMeta]): The meta key holding the page number within a query, from 1.
        FILTERS (ClassVar[AzureMarketplaceMeta]): The meta key holding the category filters of a query.
        LABELS (ClassVar[AzureMarketplaceMeta]): The meta key holding the category labels of a query.
        CATEGORY_FILTER (ClassVar[AzureTilesParameter]): The tiles API parameter filtering a category, by its URL key.
        SUBCATEGORY_FILTER (ClassVar[AzureTilesParameter]): The tiles API parameter filtering a subcategory, by its URL
            key.
        CATALOG_API_URL (ClassVar[str]): The public catalog REST API of the marketplace, giving the offer dates.
        CATALOG_TOP (ClassVar[int]): The most offers given by the catalog API, above their number.
        CATALOG_QUERY (ClassVar[Dict[str, str]]): The catalog API parameters: every offer (`$top` caps the total, not
            the page size), the dates only.
        OFFER_DATES (ClassVar[AzureMarketplaceMeta]): The meta key marking a catalog API request.
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The first page of every app.
        complement_urls (ClassVar[Tuple[str, ...]]): The search page giving the category taxonomy.
        offer_dates (Dict[str, Tuple[Optional[str], Optional[str]]]): The creation and last modification (raw) of
            each offer of the catalog API, by lower case offer identifier.

    Notes:
        The marketplace search pages read their tiles from a JSON API, 60 tiles per page: every app is read first,
        page after page. Most tiles name no category, so a tagging pass queries each subcategory (or each category
        without subcategories) of the taxonomy found in the initial state of the search page, and streams its apps
        again with the category and subcategory labels. The consulting and managed services are skipped. The
        `robots.txt` crawl delay (2 seconds) applies to every request: the page limit applies to each query.
        The tiles give no date: the catalog REST API is read first (about 275 pages of 265 offers, trimmed to the
        dates), and an app is dated by its offer: added at the offer creation (`creationDate`), updated at the last
        modification of its catalog entry (`bigCatLastModifiedDate`, `CATALOGUE_ENTRY` caveat). The apps are matched
        by identifier (`publisher.offer`, or `WA...` for the Microsoft 365 apps).
    """

    TILES_URL: ClassVar[str] = "https://marketplace.microsoft.com/view/tiledata"
    QUERY: ClassVar[Dict[str, str]] = {
        AzureTilesParameter.REVIEWS_MY_COMMENTS_FILTER: AzureTilesParameterValue.TRUE,
        AzureTilesParameter.COUNTRY: AzureTilesParameterValue.UNITED_STATES,
        AzureTilesParameter.ENTITY_TYPE: AzureTilesParameterValue.APP,
        AzureTilesParameter.REGION: AzureTilesParameterValue.ALL_REGIONS,
    }
    PAGE_SIZE: ClassVar[int] = 60
    TAXONOMY_URL: ClassVar[str] = "https://marketplace.microsoft.com/en-us/search/products"
    STATE_MARKER: ClassVar[AzureScriptMarker] = AzureScriptMarker.INITIAL_STATE
    PRODUCT_URL: ClassVar[str] = "https://marketplace.microsoft.com/en-us/product/{}"
    DELIVERIES: ClassVar[Dict[AzureOfferType, DeliveryMethod]] = {
        AzureOfferType.VIRTUAL_MACHINE: DeliveryMethod.VIRTUAL_MACHINE,
        AzureOfferType.SAAS: DeliveryMethod.SAAS,
        AzureOfferType.OFFICE_365: DeliveryMethod.SAAS,
        AzureOfferType.POWER_BI_VISUALS: DeliveryMethod.SAAS,
        AzureOfferType.AAD_APPS: DeliveryMethod.SAAS,
        AzureOfferType.DYNAMICS_BC: DeliveryMethod.SAAS,
        AzureOfferType.DYNAMICS_CE: DeliveryMethod.SAAS,
        AzureOfferType.DYNAMICS_OPS: DeliveryMethod.SAAS,
        AzureOfferType.CONTAINERS: DeliveryMethod.CONTAINER,
        AzureOfferType.CONTAINER_APPS: DeliveryMethod.CONTAINER,
        AzureOfferType.IOT_EDGE_MODULES: DeliveryMethod.CONTAINER,
        AzureOfferType.AZURE_APPLICATION: DeliveryMethod.OTHER,
        AzureOfferType.SOLUTION_TEMPLATE: DeliveryMethod.OTHER,
        AzureOfferType.MANAGED_APPLICATION: DeliveryMethod.OTHER,
    }
    EXCLUDED_OFFER_TYPES: ClassVar[FrozenSet[AzureOfferType]] = frozenset(
        {AzureOfferType.CONSULTING_SERVICES, AzureOfferType.MANAGED_SERVICES}
    )
    PAGE: ClassVar[AzureMarketplaceMeta] = AzureMarketplaceMeta.PAGE
    FILTERS: ClassVar[AzureMarketplaceMeta] = AzureMarketplaceMeta.FILTERS
    LABELS: ClassVar[AzureMarketplaceMeta] = AzureMarketplaceMeta.LABELS
    CATEGORY_FILTER: ClassVar[AzureTilesParameter] = AzureTilesParameter.CATEGORY
    SUBCATEGORY_FILTER: ClassVar[AzureTilesParameter] = AzureTilesParameter.SUBCATEGORIES
    CATALOG_API_URL: ClassVar[str] = "https://catalogapi.azure.com/offers"
    CATALOG_TOP: ClassVar[int] = 100000
    CATALOG_QUERY: ClassVar[Dict[str, str]] = {
        AzureCatalogParameter.API_VERSION: AzureCatalogApiVersion.V2018_08_01_BETA,
        AzureCatalogParameter.TOP: str(CATALOG_TOP),
        AzureCatalogParameter.SELECT: ",".join(
            (AzureOfferField.ID, AzureOfferField.CREATION_DATE, AzureOfferField.BIG_CAT_LAST_MODIFIED_DATE)
        ),
    }
    OFFER_DATES: ClassVar[AzureMarketplaceMeta] = AzureMarketplaceMeta.OFFER_DATES

    name = "azure-marketplace"
    catalogue_url: ClassVar[str] = f"{TILES_URL}?{urlencode({**QUERY, AzureTilesParameter.PAGE: 1})}"
    complement_urls: ClassVar[Tuple[str, ...]] = (TAXONOMY_URL,)

    def __init__(
        self,
        crawldir: Optional[Union[str, Path]] = None,
        interval: float = 300.0,
        classifier: Optional[SoftwareClassifier] = None,
    ) -> None:
        """Initialize the crawler, allowed to read the catalog API too.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
            classifier (Optional[SoftwareClassifier]): The software classifier, the project rules by default.
        """
        super().__init__(crawldir=crawldir, interval=interval, classifier=classifier)
        self.allowed_domains.add(urlparse(self.CATALOG_API_URL).netloc)
        self.offer_dates: Dict[str, Tuple[Optional[str], Optional[str]]] = {}

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
        url = f"{self.TILES_URL}?{urlencode({**self.QUERY, **filters, AzureTilesParameter.PAGE: page})}"
        return self._api_request(url, meta=meta, priority=0 if filters else self.PRIMARY_PRIORITY)

    def _catalog_request(self, url: str) -> Request:
        """Build the request of a page of the catalog API, read before the tiles.

        Args:
            url (str): The page URL.

        Returns:
            Request: The request, crawled first (dates priority).
        """
        return self._api_request(url, meta={self.OFFER_DATES: True}, priority=self.DATES_PRIORITY)

    def _record_offer_dates(self, response: Response) -> Optional[Request]:
        """Remember the dates of the offers of a catalog API page.

        Args:
            response (Response): A catalog API page.

        Returns:
            Optional[Request]: The next page request, `None` after the last page or for an unusable page (logged:
                the remaining apps are not dated).
        """
        if response.status >= 400:
            self.logger.warning(
                "The %s catalog API page %s failed (HTTP %s).", self.name, response.url, response.status
            )
            return None
        try:
            page = json.loads(response.body)
        except ValueError:
            self.logger.warning("The %s catalog API page %s is not JSON.", self.name, response.url)
            return None
        data = self._as_object(page)
        offers = data.get(AzureOfferField.ITEMS)
        for offer in offers if isinstance(offers, list) else []:
            fields = self._as_object(offer)
            identifier = self._as_text(fields.get(AzureOfferField.ID))
            if identifier:
                created = fields.get(AzureOfferField.CREATION_DATE)
                modified = fields.get(AzureOfferField.BIG_CAT_LAST_MODIFIED_DATE)
                self.offer_dates[identifier.casefold()] = (
                    created if isinstance(created, str) else None,
                    modified if isinstance(modified, str) else None,
                )
        next_page = self._as_text(data.get(AzureOfferField.NEXT_PAGE_LINK))
        self.logger.info("%d %s offers dated so far.", len(self.offer_dates), self.name)
        return self._catalog_request(next_page) if next_page else None

    def _meta_labels(self, response: Response) -> List[str]:
        """Get the category labels of the query of a page of tiles.

        Args:
            response (Response): The tiles API response.

        Returns:
            List[str]: The category labels, none for every app.
        """
        labels = response.meta.get(self.LABELS)
        return [label for label in (labels if isinstance(labels, list) else []) if isinstance(label, str)]

    def _query_path(self, response: Response) -> Optional[MarketplaceCategory]:
        """Get the category path of the query of a page of tiles.

        Args:
            response (Response): The tiles API response.

        Returns:
            Optional[MarketplaceCategory]: The queried category, under its parent category for a subcategory,
                identified by its URL key. `None` for every app.
        """
        labels = self._meta_labels(response)
        if not labels:
            self.logger.debug("No category queried by the %s page %s.", self.name, response.url)
            return None
        filters = self._as_object(response.meta.get(self.FILTERS))
        key = self._as_text(filters.get(self.SUBCATEGORY_FILTER)) or self._as_text(filters.get(self.CATEGORY_FILTER))
        return self._category(labels, key or None)

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
        text = response.body.decode(TextEncoding.UTF_8, errors=TextEncoding.REPLACE)
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
        apps = self._as_object(self._initial_state(response).get(AzureStateField.APPS))
        data_map = self._as_object(apps.get(AzureStateField.DATA_MAP))
        categories = self._as_object(data_map.get(AzureStateField.CATEGORIES))
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
        long_title = self._as_text(entry.get(AzureTaxonomyField.LONG_TITLE))
        return long_title or self._as_text(entry.get(AzureTaxonomyField.TITLE)) or key

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
            filters: Dict[str, str] = {
                self.CATEGORY_FILTER: self._as_text(category.get(AzureTaxonomyField.URL_KEY)) or key
            }
            labels = [self._label(category, key)]
            subcategories = self._as_object(category.get(AzureTaxonomyField.SUB_CATEGORY_DATA_MAPPING))
            if not subcategories:
                yield self._tiles_request(1, filters, labels)
            for sub_key, sub_raw in subcategories.items():
                subcategory = self._as_object(sub_raw)
                sub_filters = {
                    **filters,
                    self.SUBCATEGORY_FILTER: self._as_text(subcategory.get(AzureTaxonomyField.URL_KEY)) or sub_key,
                }
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
        apps = self._as_object(self._as_object(self._json_body(response)).get(AzureTilesField.APPS))
        tiles = apps.get(AzureTilesField.GALLERY_TILES)
        if not isinstance(tiles, list):
            self.logger.error("The %s page %s has no `apps.galleryTiles` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "`apps.galleryTiles` is not a list")
        count = apps.get(AzureTilesField.COUNT)
        return tiles, count if isinstance(count, int) else None

    def _delivery(self, offer_type: str) -> DeliveryMethod:
        """Get the delivery of a catalog offer type.

        Args:
            offer_type (str): The catalog offer type, e.g. `VirtualMachine`.

        Returns:
            DeliveryMethod: The delivery, SaaS for the Dynamics 365 apps, `OTHER` when unknown.
        """
        if offer_type.startswith(AzureOfferType.DYNAMICS):
            return DeliveryMethod.SAAS
        if offer_type not in self.DELIVERIES:
            self.logger.debug("Unknown %s offer type %r: delivery %s.", self.name, offer_type, DeliveryMethod.OTHER)
            return DeliveryMethod.OTHER
        return self.DELIVERIES[AzureOfferType(offer_type)]

    def _product_url(self, tile: Dict[str, JsonValue]) -> Optional[str]:
        """Get the app page of a tile.

        Args:
            tile (Dict[str, JsonValue]): The app tile.

        Returns:
            Optional[str]: The app page, `None` without an app identifier.
        """
        lowered = self._as_text(tile.get(AzureTileField.ENTITY_ID_LOWERED_CASED))
        entity_id = lowered or self._as_text(tile.get(AzureTileField.ENTITY_ID))
        return self.PRODUCT_URL.format(entity_id.casefold().replace("|", "%7c")) if entity_id else None

    def _tile_paths(self, tile: Dict[str, JsonValue]) -> List[Optional[MarketplaceCategory]]:
        """Get the category paths of an app tile.

        Args:
            tile (Dict[str, JsonValue]): The app tile.

        Returns:
            List[Optional[MarketplaceCategory]]: The top category of each `categoriesDetails` entry, identified by
                its URL key.
        """
        details = tile.get(AzureTileField.CATEGORIES_DETAILS)
        paths: List[Optional[MarketplaceCategory]] = []
        for raw in details if isinstance(details, list) else []:
            detail = self._as_object(raw)
            label = self._as_text(detail.get(AzureTileCategoryField.LONG_TITLE))
            paths.append(self._category([label], self._as_text(detail.get(AzureTileCategoryField.URL_KEY))))
        self.logger.debug("%d category paths for the %s app %r.", len(paths), self.name, tile.get(AzureTileField.TITLE))
        return paths

    def _tile_software(
        self, tile: Dict[str, JsonValue], labels: List[str], query_path: Optional[MarketplaceCategory]
    ) -> Optional[MarketplaceSoftware]:
        """Build the software of an app tile.

        Args:
            tile (Dict[str, JsonValue]): The app tile.
            labels (List[str]): The category labels of the query.
            query_path (Optional[MarketplaceCategory]): The category path of the query, `None` for every app.

        Returns:
            Optional[MarketplaceSoftware]: The software, `None` when the app is a service or is invalid.
        """
        title = self._as_text(tile.get(AzureTileField.TITLE))
        offer_type = self._as_text(tile.get(AzureTileField.CATALOG_OFFER_TYPE)) or ""
        if offer_type in self.EXCLUDED_OFFER_TYPES:
            self.logger.debug("Skipping the %s app %r, a service (%s).", self.name, title, offer_type)
            return None
        details = tile.get(AzureTileField.CATEGORIES_DETAILS)
        categories = [
            self._as_text(self._as_object(detail).get(AzureTileCategoryField.LONG_TITLE))
            for detail in (details if isinstance(details, list) else [])
        ]
        identifier = self._as_text(tile.get(AzureTileField.ENTITY_ID)) or ""
        created, modified = self.offer_dates.get(identifier.casefold(), (None, None))
        return self._build_software(
            title,
            self._as_text(tile.get(AzureTileField.SHORT_DESCRIPTION)),
            self._product_url(tile),
            self._as_text(tile.get(AzureTileField.PUBLISHER)),
            self._delivery(offer_type),
            list(dict.fromkeys([*categories, *labels])),
            marketplace_category_paths=[*self._tile_paths(tile), query_path],
            added_at=self._parse_date(created, title) if created else None,
            updated_at=self._parse_date(modified, title) if modified else None,
            updated_caveat=DateCaveat.CATALOGUE_ENTRY,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Start with the catalog API (for the dates), then the tiles of every app and the search page.

        Yields:
            Request: The first catalog API page request, then the base requests.
        """
        self.offer_dates.clear()
        self.logger.debug("Requesting the %s catalog API for the dates of the offers.", self.name)
        yield self._catalog_request(f"{self.CATALOG_API_URL}?{urlencode(self.CATALOG_QUERY)}")
        async for request in super().start_requests():
            yield request

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
        query_path = self._query_path(response)
        self.logger.debug("%d %s tiles in %s.", len(tiles), self.name, response.url)
        for tile in tiles:
            if software := self._tile_software(self._as_object(tile), labels, query_path):
                yield software

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Read the offer dates, request the tagging queries, or stream a page of tiles then request the next one.

        Args:
            response (Response): A catalog API page (`OFFER_DATES` meta), the search page, or a tiles API response
                (`PAGE` meta).

        Yields:
            Union[Dict[str, JsonValue], Request]: The first page request of each tagging query, or each software not
                streamed yet (or with new categories) then the next page request.
        """
        if self.OFFER_DATES in response.meta:
            if (request := self._record_offer_dates(response)) is not None:
                yield request
            return
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
