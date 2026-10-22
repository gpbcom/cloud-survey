from __future__ import annotations

# Standard Library Imports.
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.gcp.enums import (
    GcpBrowseRequestField,
    GcpBrowseRequestValue,
    GcpBrowseResultField,
    GcpCardField,
    GcpCategoryFacetValue,
    GcpFacet,
    GcpHeader,
    GcpMarketplaceMeta,
    GcpMediaType,
    GcpProductFamily,
    GcpProductType,
)
from crawler.enums import HttpMethod
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class GoogleCloudMarketplaceCrawler(BaseMarketplaceCrawler):
    """Google Cloud Marketplace crawler: the software products of the marketplace browse page.

    Attributes:
        API_URL (ClassVar[str]): The console entity service giving the browse results (`MARKETPLACE_BROWSE_PRODUCTS`).
        HEADERS (ClassVar[Dict[str, str]]): The request headers the entity service expects: its origin and referer
            must match (the HTTP session would otherwise send a search engine referer).
        PRODUCT_URL (ClassVar[str]): The product page, formatted with the product display name.
        CATEGORY_FACET (ClassVar[GcpFacet]): The facet of the product categories.
        PATH_ONLY_CATEGORIES (ClassVar[FrozenSet[GcpCategoryFacetValue]]): The category facet values queried for their
            category path only: the managed services and the catch-all category, whose labels say nothing of the
            software, are not given as marketplace categories (the classifier reads those).
        EXCLUDED_TYPES (ClassVar[FrozenSet[GcpProductType]]): The product types which are not software: professional
            services, datasets, Google Cloud services and provisioned model throughput.
        EXCLUDED_FAMILIES (ClassVar[FrozenSet[GcpProductFamily]]): The product families of the same kinds, in case a
            type is renamed.
        DELIVERIES (ClassVar[Dict[GcpProductType, DeliveryMethod]]): The delivery of each product type.
        PAGE (ClassVar[GcpMarketplaceMeta]): The meta key holding the page number within a query, from 1.
        FACET (ClassVar[GcpMarketplaceMeta]): The meta key holding the facet value of a category query.
        LABEL (ClassVar[GcpMarketplaceMeta]): The meta key holding the category label of a category query.
        PATHS_ONLY (ClassVar[GcpMarketplaceMeta]): The meta key of the category queries giving their products the
            category path only.
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The entity service, queried for every product first.

    Notes:
        The console browse page reads its product cards from a JSON entity service (`POST`, 40 cards per page, with a
        `nextPageToken` cursor). Every product is read first, then each category facet value listed by the first
        page is queried to give the products their category, since the cards carry none: the products are streamed
        again with it. The managed services and catch-all categories give their category path only. The page limit
        applies to each query.
    """

    API_URL: ClassVar[str] = (
        "https://cloudconsole-pa.clients6.google.com/v3/entityServices/MarketplaceEntityService/entities/"
        "MARKETPLACE_BROWSE_PRODUCTS:get?key=AIzaSyCI-zsRP85UVOi0DjtiCwWBwQ1djDy741g&alt=json&prettyPrint=false"
    )
    HEADERS: ClassVar[Dict[str, str]] = {
        GcpHeader.CONTENT_TYPE: GcpMediaType.JSON,
        GcpHeader.ORIGIN: "https://console.cloud.google.com",
        GcpHeader.REFERER: "https://console.cloud.google.com/marketplace/browse",
    }
    PRODUCT_URL: ClassVar[str] = "https://console.cloud.google.com/marketplace/product/{}"
    CATEGORY_FACET: ClassVar[GcpFacet] = GcpFacet.CATEGORY
    PATH_ONLY_CATEGORIES: ClassVar[FrozenSet[GcpCategoryFacetValue]] = frozenset(
        {GcpCategoryFacetValue.MANAGED_SERVICES, GcpCategoryFacetValue.OTHERS}
    )
    EXCLUDED_TYPES: ClassVar[FrozenSet[GcpProductType]] = frozenset(
        {
            GcpProductType.PROFESSIONAL_SERVICES,
            GcpProductType.DATA,
            GcpProductType.DATASETS,
            GcpProductType.GOOGLE_CLOUD_PLATFORM,
            GcpProductType.PROVISIONED_THROUGHPUT,
        }
    )
    EXCLUDED_FAMILIES: ClassVar[FrozenSet[GcpProductFamily]] = frozenset(
        {
            GcpProductFamily.PROFESSIONAL_SERVICES_PRODUCT,
            GcpProductFamily.DATASET,
            GcpProductFamily.ANALYTICS_HUB_LISTING,
            GcpProductFamily.GCP,
            GcpProductFamily.PROVISIONED_THROUGHPUT_PRODUCT,
        }
    )
    DELIVERIES: ClassVar[Dict[GcpProductType, DeliveryMethod]] = {
        GcpProductType.SAAS_AND_APIS: DeliveryMethod.SAAS,
        GcpProductType.AI_AGENT_AS_A_SERVICE: DeliveryMethod.SAAS,
        GcpProductType.VIRTUAL_MACHINES: DeliveryMethod.VIRTUAL_MACHINE,
        GcpProductType.KUBERNETES_APPS: DeliveryMethod.KUBERNETES,
        GcpProductType.CONTAINER_IMAGES: DeliveryMethod.CONTAINER,
        GcpProductType.VERTEX_AI: DeliveryMethod.AI_MODEL,
    }
    PAGE: ClassVar[GcpMarketplaceMeta] = GcpMarketplaceMeta.PAGE
    FACET: ClassVar[GcpMarketplaceMeta] = GcpMarketplaceMeta.FACET
    LABEL: ClassVar[GcpMarketplaceMeta] = GcpMarketplaceMeta.LABEL
    PATHS_ONLY: ClassVar[GcpMarketplaceMeta] = GcpMarketplaceMeta.PATHS_ONLY

    name = "gcp-marketplace"
    catalogue_url: ClassVar[str] = API_URL

    ############################
    # Internal Helpers Methods #
    ############################

    def _browse_request(
        self,
        page: int,
        token: str = "",
        facet: Optional[str] = None,
        label: Optional[str] = None,
        paths_only: bool = False,
    ) -> Request:
        """Build the request of a page of browse results.

        Args:
            page (int): The page number, from 1.
            token (str): The cursor of the page, empty for the first page.
            facet (Optional[str]): The category facet value of the query, `None` for every product.
            label (Optional[str]): The category label of the query, given to its products.
            paths_only (bool): Whether the products are given the category path of the query only, not its label.

        Returns:
            Request: The `POST` request. Every product is read first (primary priority), the first page of a category
                query may list nothing.
        """
        selected: List[JsonValue] = (
            [{GcpBrowseRequestField.FACET_ID: self.CATEGORY_FACET, GcpBrowseRequestField.FACET_VALUE_ID: facet}]
            if facet
            else []
        )
        body: Dict[str, JsonValue] = {
            GcpBrowseRequestField.ENTITY_REQUEST: {
                GcpBrowseRequestField.ENTITY_NAME: GcpBrowseRequestValue.BROWSE_PRODUCTS,
                GcpBrowseRequestField.REQUEST_PAYLOAD: {
                    GcpBrowseRequestField.PARAMETERS: {
                        GcpBrowseRequestField.LOCALE: GcpBrowseRequestValue.ENGLISH,
                        GcpBrowseRequestField.SOLUTION_SCOPE_ID: GcpBrowseRequestValue.LAUNCHER,
                        GcpBrowseRequestField.SELECTED_FACET_VALUES: selected,
                        GcpBrowseRequestField.QUERY: GcpBrowseRequestValue.EVERYTHING,
                        GcpBrowseRequestField.PAGE_TOKEN: token,
                        GcpBrowseRequestField.IS_PRIVATE_CATALOG: False,
                        GcpBrowseRequestField.RESPONSE_TYPE: GcpBrowseRequestValue.SEARCH_RESULTS,
                    },
                    GcpBrowseRequestField.TYPE: "type.googleapis.com/google.internal.cloud.console.clientapi."
                    "marketplace.BrowseProductsRequest",
                },
            },
            GcpBrowseRequestField.REQUEST_CONTEXT: {GcpBrowseRequestField.PAGE_PATH: "/marketplace/browse"},
        }
        meta: Dict[str, JsonValue] = {self.PAGE: page, self.FACET: facet, self.LABEL: label}
        if facet and page == 1:
            meta[self.MAY_BE_EMPTY] = True
        if paths_only:
            meta[self.PATHS_ONLY] = True
        return self._api_request(
            self.API_URL,
            method=HttpMethod.POST,
            json=body,
            headers=dict(self.HEADERS),
            meta=meta,
            priority=0 if facet else self.PRIMARY_PRIORITY,
        )

    def _catalogue_request(self) -> Request:
        """Build the request of the first page of every product.

        Returns:
            Request: The request, crawled first (primary priority).
        """
        return self._browse_request(1)

    def _browse_result(self, response: Response) -> Tuple[List[JsonValue], Dict[str, JsonValue]]:
        """Read a page of browse results.

        Args:
            response (Response): The entity service response.

        Returns:
            Tuple[List[JsonValue], Dict[str, JsonValue]]: The product cards of the page, and the browse results.

        Raises:
            CatalogueFormatError: If the page has no browse results with a `searchResult.cards` list.
        """
        data = self._json_body(response)
        first = self._as_object(data[0] if isinstance(data, list) and data else None)
        successful = self._as_object(first.get(GcpBrowseResultField.SUCCESSFUL_RESULT))
        result = self._as_object(successful.get(GcpBrowseResultField.RESULT_DATA))
        browse = self._as_object(result.get(GcpBrowseResultField.MARKETPLACE_BROWSE_PRODUCTS))
        cards = self._as_object(browse.get(GcpBrowseResultField.SEARCH_RESULT)).get(GcpBrowseResultField.CARDS)
        if not isinstance(cards, list):
            self.logger.error("The %s page %s has no `searchResult.cards` list.", self.name, response.url)
            raise CatalogueFormatError(
                self.name, response.url, "`marketplaceBrowseProducts.searchResult.cards` missing"
            )
        return cards, browse

    def _category_requests(self, browse: Dict[str, JsonValue]) -> Iterator[Request]:
        """Build the first page request of each category query, from the facets of the browse results.

        Args:
            browse (Dict[str, JsonValue]): The browse results of the first page of every product.

        Yields:
            Request: The first page request of each category query.
        """
        facets = browse.get(GcpBrowseResultField.FACET_VALUE_LINK_LISTS)
        for facet in facets if isinstance(facets, list) else []:
            if self._as_object(facet).get(GcpBrowseResultField.FACET_ID) != self.CATEGORY_FACET:
                continue
            links = self._as_object(facet).get(GcpBrowseResultField.FACET_VALUE_LINKS)
            for link in links if isinstance(links, list) else []:
                binding = self._as_object(self._as_object(link).get(GcpBrowseResultField.FACET_BINDING))
                value = self._as_text(binding.get(GcpBrowseResultField.FACET_VALUE_ID))
                label = self._as_text(self._as_object(link).get(GcpBrowseResultField.DISPLAY_NAME))
                if not value:
                    self.logger.debug("Skipping the %s category %r without a facet value.", self.name, label)
                    continue
                paths_only = value in self.PATH_ONLY_CATEGORIES
                if paths_only:
                    self.logger.debug("The %s category %r (%s) gives category paths only.", self.name, label, value)
                yield self._browse_request(1, facet=value, label=label or value, paths_only=paths_only)

    def _html_to_text(self, fragment: Optional[str]) -> Optional[str]:
        """Get the text of an HTML fragment, such as a long description.

        Args:
            fragment (Optional[str]): The HTML fragment.

        Returns:
            Optional[str]: The fragment text, `None` when missing.
        """
        if fragment is None:
            return None
        return Selector(f"<div>{fragment}</div>").get_all_text(separator=" ", strip=True)

    def _query_path(self, response: Response) -> Optional[MarketplaceCategory]:
        """Get the category path of the query of a page of browse results.

        Args:
            response (Response): The entity service response.

        Returns:
            Optional[MarketplaceCategory]: The queried category facet value (a top category of the marketplace),
                identified by its facet value identifier. `None` for every product.
        """
        facet = self._as_text(response.meta.get(self.FACET))
        if not facet:
            self.logger.debug("No category queried by the %s page %s.", self.name, response.url)
            return None
        return self._category([self._as_text(response.meta.get(self.LABEL)) or facet], facet)

    def _card_software(
        self, card: Dict[str, JsonValue], label: Optional[str], query_path: Optional[MarketplaceCategory]
    ) -> Optional[MarketplaceSoftware]:
        """Build the software of a product card.

        Args:
            card (Dict[str, JsonValue]): The product card.
            label (Optional[str]): The category label of the query, if any.
            query_path (Optional[MarketplaceCategory]): The category path of the query, if any.

        Returns:
            Optional[MarketplaceSoftware]: The software, `None` when the product is not software or is invalid.
        """
        title = self._as_text(card.get(GcpCardField.TITLE))
        product_type = self._as_text(card.get(GcpCardField.PRODUCT_TYPE)) or ""
        family = self._as_text(card.get(GcpCardField.FAMILY_TYPE)) or ""
        if product_type in self.EXCLUDED_TYPES or family in self.EXCLUDED_FAMILIES:
            self.logger.debug(
                "Skipping the %s product %r, not software (%s, %s).", self.name, title, product_type, family
            )
            return None
        if product_type not in self.DELIVERIES:
            self.logger.debug(
                "Unknown %s product type %r of %r: delivery %s.", self.name, product_type, title, DeliveryMethod.OTHER
            )
        display_name = self._as_text(card.get(GcpCardField.PRODUCT_DISPLAY_NAME))
        return self._build_software(
            title,
            self._as_text(card.get(GcpCardField.DESCRIPTION))
            or self._html_to_text(self._as_text(card.get(GcpCardField.LONG_DESCRIPTION))),
            self.PRODUCT_URL.format(display_name) if display_name else None,
            self._as_text(card.get(GcpCardField.SUBTITLE)),
            self.DELIVERIES[GcpProductType(product_type)] if product_type in self.DELIVERIES else DeliveryMethod.OTHER,
            [label] if label else [],
            marketplace_category_paths=[query_path],
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a page of browse results.

        Args:
            response (Response): The entity service response.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid software product of the page, with the category of its query.

        Raises:
            CatalogueFormatError: If the page has no `searchResult.cards` list.
        """
        cards, _ = self._browse_result(response)
        label = None if response.meta.get(self.PATHS_ONLY) else self._as_text(response.meta.get(self.LABEL))
        query_path = self._query_path(response)
        self.logger.debug("%d %s cards in the %s page.", len(cards), self.name, label or "every product")
        for card in cards:
            if software := self._card_software(self._as_object(card), label, query_path):
                yield software

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream a page of browse results, then request the next page, and the category queries after the first page.

        Args:
            response (Response): The entity service response.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each software not streamed yet (or with a new category), the next
                page request, then (first page of every product) the first page request of each category query.
        """
        async for item in super().parse(response):
            yield item
        cards, browse = self._browse_result(response)
        page = response.meta.get(self.PAGE)
        page = page if isinstance(page, int) else 1
        facet = self._as_text(response.meta.get(self.FACET))
        token = self._as_text(browse.get(GcpBrowseResultField.NEXT_PAGE_TOKEN))
        if not token or not cards:
            self.logger.info(
                "Last %s page %d of %s (%s products).",
                self.name,
                page,
                facet or "every product",
                browse.get(GcpBrowseResultField.TOTAL_COUNT),
            )
        elif self._within_page_limit(page + 1):
            self.logger.info("Requesting the %s page %d of %s.", self.name, page + 1, facet or "every product")
            yield self._browse_request(
                page + 1,
                token,
                facet,
                self._as_text(response.meta.get(self.LABEL)),
                bool(response.meta.get(self.PATHS_ONLY)),
            )
        if facet is None and page == 1:
            requests = list(self._category_requests(browse))
            self.logger.info("Requesting the %d %s category queries.", len(requests), self.name)
            for request in requests:
                yield request
