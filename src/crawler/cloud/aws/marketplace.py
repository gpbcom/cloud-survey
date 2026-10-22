from __future__ import annotations

# Standard Library Imports.
import json
import re
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Set, Tuple, Union

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.aws.enums import (
    AwsDiscoveryHeader,
    AwsDiscoveryOperation,
    AwsFulfillmentOption,
    AwsIntegrationId,
    AwsListingField,
    AwsMarketplaceMeta,
    AwsMediaType,
    AwsPageMeta,
    AwsProxyEnvelopeField,
    AwsProxyHeader,
    AwsRegion,
    AwsSearchFilterType,
    AwsSearchPageField,
    AwsSearchRequestField,
)
from crawler.enums import HttpMethod, TextEncoding
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DateCaveat, DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class AWSMarketplaceCrawler(BaseMarketplaceCrawler):
    """AWS Marketplace crawler: the software listings, by fulfillment option.

    Attributes:
        API_URL (ClassVar[str]): The discovery API proxy of the marketplace pages (`SearchListings`).
        LISTING_URL (ClassVar[str]): The listing page, formatted with the listing identifier.
        INTEGRATION_ID (ClassVar[AwsIntegrationId]): The known integration identifier, used when the browse page
            holds none.
        PAGE_SIZE (ClassVar[int]): The listings read per page, the API maximum.
        DELIVERIES (ClassVar[Dict[AwsFulfillmentOption, DeliveryMethod]]): The delivery of each software fulfillment
            option, queried in this order.
        OPTION (ClassVar[AwsMarketplaceMeta]): The meta key holding the queried fulfillment option.
        PAGE (ClassVar[AwsMarketplaceMeta]): The meta key holding the page number within a fulfillment option, from 1.
        INTEGRATION (ClassVar[AwsMarketplaceMeta]): The meta key holding the integration identifier.
        LISTING_PAGE (ClassVar[AwsMarketplaceMeta]): The meta key marking a listing page request, holding the
            software identity.
        LISTING_PRIORITY (ClassVar[int]): The priority of the listing pages, read after every search.
        CATEGORY_DEPTH (ClassVar[int]): The most levels of a category path.
        OPTION_DATE (ClassVar[re.Pattern[str]]): A fulfillment option of a listing page and its creation date.
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): A browse page of the marketplace, carrying the integration identifier.
        streamed (Dict[str, Dict[str, JsonValue]]): The last streamed item of each software, by identity.
        listing_pages (List[str]): The software identities whose listing page is still to request.
        requested_listings (Set[str]): The software identities whose listing page was requested.

    Notes:
        The marketplace pages search the listings through a JSON proxy of the discovery service: a `POST` envelope
        whose `contentString` holds the `SearchListings` request. It needs the integration identifier of the pages,
        read from the `integrationId` meta of a browse page (the search page is disallowed by `robots.txt`). The
        listings are queried once per software fulfillment option (SaaS, machine images, containers...), which keeps
        each query under the 10,000 results window, and read page after page with the `NextToken` cursor. The
        professional services and data exchange options are not queried. A listing of several options is streamed
        once, with the delivery of its first software option.
        The search gives no date: once every search is read, the page of each listing is read for the creation
        date of each fulfillment option (each version, or the SaaS subscription). The software is streamed again,
        added at its oldest option (`OLDEST_VERSION` caveat when there are several, older versions may have been
        removed) and updated at its newest one (only when there are several). About 18,000 pages of 570 KB: the
        dates take hours.
    """

    API_URL: ClassVar[str] = "https://aws.amazon.com/marketplace/api/awsmpdiscovery"
    LISTING_URL: ClassVar[str] = "https://aws.amazon.com/marketplace/pp/{}"
    INTEGRATION_ID: ClassVar[AwsIntegrationId] = AwsIntegrationId.MARKETPLACE_PAGES
    PAGE_SIZE: ClassVar[int] = 100
    DELIVERIES: ClassVar[Dict[AwsFulfillmentOption, DeliveryMethod]] = {
        AwsFulfillmentOption.SAAS: DeliveryMethod.SAAS,
        AwsFulfillmentOption.AMAZON_MACHINE_IMAGE: DeliveryMethod.VIRTUAL_MACHINE,
        AwsFulfillmentOption.CONTAINER: DeliveryMethod.CONTAINER,
        AwsFulfillmentOption.HELM: DeliveryMethod.KUBERNETES,
        AwsFulfillmentOption.EKS_ADD_ON: DeliveryMethod.KUBERNETES,
        AwsFulfillmentOption.CLOUDFORMATION_TEMPLATE: DeliveryMethod.VIRTUAL_MACHINE,
        AwsFulfillmentOption.EC2_IMAGE_BUILDER_COMPONENT: DeliveryMethod.VIRTUAL_MACHINE,
        AwsFulfillmentOption.SAGEMAKER_MODEL: DeliveryMethod.AI_MODEL,
        AwsFulfillmentOption.SAGEMAKER_ALGORITHM: DeliveryMethod.AI_MODEL,
        AwsFulfillmentOption.API: DeliveryMethod.API,
    }
    OPTION: ClassVar[AwsMarketplaceMeta] = AwsMarketplaceMeta.FULFILLMENT_OPTION
    PAGE: ClassVar[AwsMarketplaceMeta] = AwsMarketplaceMeta.PAGE
    INTEGRATION: ClassVar[AwsMarketplaceMeta] = AwsMarketplaceMeta.INTEGRATION_ID
    LISTING_PAGE: ClassVar[AwsMarketplaceMeta] = AwsMarketplaceMeta.LISTING_PAGE
    LISTING_PRIORITY: ClassVar[int] = -1
    CATEGORY_DEPTH: ClassVar[int] = 6
    OPTION_DATE: ClassVar[re.Pattern[str]] = re.compile(
        r'"fulfillmentOptionId":"(fo-[a-z0-9]+)"(?:(?!"fulfillmentOptionId").){0,800}?"creationDate":"([^"]+)"',
        re.DOTALL,
    )

    name = "aws-marketplace"
    catalogue_url: ClassVar[str] = "https://aws.amazon.com/marketplace/b/579164ab-a400-4924-9c9c-590e45580b7d"

    def __init__(
        self,
        crawldir: Optional[Union[str, Path]] = None,
        interval: float = 300.0,
        classifier: Optional[SoftwareClassifier] = None,
    ) -> None:
        """Initialize the crawler, without any listing read yet.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
            classifier (Optional[SoftwareClassifier]): The software classifier, the project rules by default.
        """
        super().__init__(crawldir=crawldir, interval=interval, classifier=classifier)
        self.streamed: Dict[str, Dict[str, JsonValue]] = {}
        self.listing_pages: List[str] = []
        self.requested_listings: Set[str] = set()

    ############################
    # Internal Helpers Methods #
    ############################

    def _integration_id(self, response: Response) -> str:
        """Read the integration identifier of the marketplace pages.

        Args:
            response (Response): The browse page.

        Returns:
            str: The `integrationId` meta content, else the known identifier.
        """
        if integration_id := self._meta_content(response, AwsPageMeta.INTEGRATION_ID):
            self.logger.debug("Integration identifier of the %s pages: %s.", self.name, integration_id)
            return integration_id
        self.logger.warning(
            "No integration identifier in the %s page %s: using %s.", self.name, response.url, self.INTEGRATION_ID
        )
        return self.INTEGRATION_ID

    def _search_request(self, integration_id: str, option: str, page: int, token: Optional[str] = None) -> Request:
        """Build the request of a page of the listings of a fulfillment option.

        Args:
            integration_id (str): The integration identifier of the marketplace pages.
            option (str): The fulfillment option, e.g. `SAAS`.
            page (int): The page number, from 1.
            token (Optional[str]): The cursor of the page, `None` for the first page.

        Returns:
            Request: The `POST` request of the discovery API proxy. A first page may list nothing.
        """
        content: Dict[str, JsonValue] = {
            AwsSearchRequestField.MAX_RESULTS: self.PAGE_SIZE,
            AwsSearchRequestField.REQUEST_CONTEXT: {AwsSearchRequestField.INTEGRATION_ID: integration_id},
            AwsSearchRequestField.FILTERS: [
                {
                    AwsSearchRequestField.TYPE: AwsSearchFilterType.FULFILLMENT_OPTION_TYPE,
                    AwsSearchRequestField.VALUES: [option],
                }
            ],
        }
        if token:
            content[AwsSearchRequestField.NEXT_TOKEN] = token
        envelope: Dict[str, JsonValue] = {
            AwsProxyEnvelopeField.REGION: AwsRegion.US_EAST_1,
            AwsProxyEnvelopeField.HEADERS: {
                AwsDiscoveryHeader.ACCEPT: AwsMediaType.JSON,
                AwsDiscoveryHeader.CONTENT_TYPE: AwsMediaType.AMZ_JSON,
                AwsDiscoveryHeader.TARGET: AwsDiscoveryOperation.SEARCH_LISTINGS_TARGET,
            },
            AwsProxyEnvelopeField.CONTENT_STRING: json.dumps(content),
            AwsProxyEnvelopeField.METHOD: HttpMethod.POST,
            AwsProxyEnvelopeField.OPERATION: AwsDiscoveryOperation.SEARCH_LISTINGS,
            AwsProxyEnvelopeField.PATH: "/",
        }
        meta: Dict[str, JsonValue] = {self.OPTION: option, self.PAGE: page, self.INTEGRATION: integration_id}
        if page == 1:
            meta[self.MAY_BE_EMPTY] = True
        return self._api_request(
            self.API_URL,
            method=HttpMethod.POST,
            json=envelope,
            headers={AwsProxyHeader.CONTENT_TYPE: AwsMediaType.JSON},
            meta=meta,
        )

    def _search_page(self, response: Response) -> Tuple[List[JsonValue], Dict[str, JsonValue]]:
        """Read a page of listings.

        Args:
            response (Response): The discovery API response.

        Returns:
            Tuple[List[JsonValue], Dict[str, JsonValue]]: The listing summaries of the page, and the page data.

        Raises:
            CatalogueFormatError: If the page is not a JSON object with a `ListingSummaries` list.
        """
        data = self._as_object(self._json_body(response))
        listings = data.get(AwsSearchPageField.LISTING_SUMMARIES)
        if not isinstance(listings, list):
            self.logger.error("The %s page %s has no `ListingSummaries` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "`ListingSummaries` is not a list")
        return listings, data

    def _delivery(self, listing: Dict[str, JsonValue]) -> Optional[DeliveryMethod]:
        """Get the delivery of a listing from its first software fulfillment option.

        Args:
            listing (Dict[str, JsonValue]): The listing summary.

        Returns:
            Optional[DeliveryMethod]: The delivery, `None` when the listing has no software option (e.g. a
                professional service).
        """
        options = listing.get(AwsListingField.FULFILLMENT_OPTION_TYPES)
        for option in options if isinstance(options, list) else []:
            value = self._as_text(self._as_object(option).get(AwsListingField.VALUE))
            if value in self.DELIVERIES:
                return self.DELIVERIES[AwsFulfillmentOption(value)]
        return None

    def _publisher(self, listing: Dict[str, JsonValue]) -> Optional[str]:
        """Get the publisher of a listing: its creator, else the manufacturer of its product.

        Args:
            listing (Dict[str, JsonValue]): The listing summary.

        Returns:
            Optional[str]: The publisher name, `None` when unknown.
        """
        creator_fields = self._as_object(listing.get(AwsListingField.LISTING_CREATOR))
        if creator := self._as_text(creator_fields.get(AwsListingField.DISPLAY_NAME)):
            return creator
        entities = listing.get(AwsListingField.ASSOCIATED_ENTITIES)
        for entity in entities if isinstance(entities, list) else []:
            manufacturer = self._as_object(self._as_object(entity).get(AwsListingField.MANUFACTURER))
            if name := self._as_text(manufacturer.get(AwsListingField.DISPLAY_NAME)):
                return name
        return None

    def _categories(self, listing: Dict[str, JsonValue]) -> List[str]:
        """Get the category labels of a listing, each preceded by its parent category when the listing names it.

        Args:
            listing (Dict[str, JsonValue]): The listing summary.

        Returns:
            List[str]: The category labels, without duplicates.
        """
        raw = listing.get(AwsListingField.CATEGORIES)
        categories = [self._as_object(category) for category in (raw if isinstance(raw, list) else [])]
        names = {
            str(category.get(AwsListingField.VALUE)): label
            for category in categories
            if (label := self._as_text(category.get(AwsListingField.DISPLAY_NAME)))
        }
        labels: List[str] = []
        for category in categories:
            parent = names.get(str(category.get(AwsListingField.PARENT_VALUE)))
            labels.extend(
                label for label in (parent, self._as_text(category.get(AwsListingField.DISPLAY_NAME))) if label
            )
        return list(dict.fromkeys(labels))

    def _category_paths(self, listing: Dict[str, JsonValue]) -> List[Optional[MarketplaceCategory]]:
        """Get the category paths of a listing, each category preceded by the ancestors the listing names.

        Args:
            listing (Dict[str, JsonValue]): The listing summary.

        Returns:
            List[Optional[MarketplaceCategory]]: The path of each category of the listing, from its root (the
                `ParentValue` chain within the listing categories), identified by its `Value`.
        """
        raw = listing.get(AwsListingField.CATEGORIES)
        categories = [self._as_object(category) for category in (raw if isinstance(raw, list) else [])]
        by_value = {
            str(category.get(AwsListingField.VALUE)): category
            for category in categories
            if category.get(AwsListingField.VALUE)
        }
        paths: List[Optional[MarketplaceCategory]] = []
        for category in categories:
            labels = [self._as_text(category.get(AwsListingField.DISPLAY_NAME))]
            seen = {str(category.get(AwsListingField.VALUE))}
            parent = by_value.get(str(category.get(AwsListingField.PARENT_VALUE)))
            while (
                parent is not None
                and str(parent.get(AwsListingField.VALUE)) not in seen
                and len(labels) < self.CATEGORY_DEPTH
            ):
                seen.add(str(parent.get(AwsListingField.VALUE)))
                labels.insert(0, self._as_text(parent.get(AwsListingField.DISPLAY_NAME)))
                parent = by_value.get(str(parent.get(AwsListingField.PARENT_VALUE)))
            paths.append(self._category(labels, self._as_text(category.get(AwsListingField.VALUE))))
        self.logger.debug(
            "%d category paths for the %s listing %s.", len(paths), self.name, listing.get(AwsListingField.ID)
        )
        return paths

    def _listing_software(self, listing: Dict[str, JsonValue]) -> Optional[MarketplaceSoftware]:
        """Build the software of a listing summary.

        Args:
            listing (Dict[str, JsonValue]): The listing summary.

        Returns:
            Optional[MarketplaceSoftware]: The software, `None` when the listing is not software or is invalid.
        """
        attributes = self._as_object(listing.get(AwsListingField.DISPLAY_ATTRIBUTES))
        title = self._as_text(attributes.get(AwsListingField.TITLE))
        delivery = self._delivery(listing)
        if delivery is None:
            self.logger.debug("Skipping the %s listing %r, not software.", self.name, title)
            return None
        listing_id = self._as_text(listing.get(AwsListingField.ID))
        return self._build_software(
            title,
            self._as_text(attributes.get(AwsListingField.SHORT_DESCRIPTION))
            or self._as_text(attributes.get(AwsListingField.LONG_DESCRIPTION)),
            self.LISTING_URL.format(listing_id) if listing_id else None,
            self._publisher(listing),
            delivery,
            self._categories(listing),
            marketplace_category_paths=self._category_paths(listing),
        )

    def _stream_software(self, software: MarketplaceSoftware) -> Optional[Dict[str, JsonValue]]:
        """Stream a software as the base crawler does, and remember it to date it from its listing page.

        Args:
            software (MarketplaceSoftware): The extracted software.

        Returns:
            Optional[Dict[str, JsonValue]]: The streamed item, `None` when it brings nothing new.
        """
        item = super()._stream_software(software)
        if item is not None:
            identity = software.identity()
            self.streamed[identity] = item
            if identity not in self.requested_listings and software.url:
                self.requested_listings.add(identity)
                self.listing_pages.append(identity)
        return item

    def _listing_request(self, identity: str) -> Request:
        """Build the request of the page of a listing, read for its dates after every search.

        Args:
            identity (str): The software identity: its listing page URL, lower case.

        Returns:
            Request: The listing page request (HTTP session, lowest priority).
        """
        url = str(self.streamed[identity].get("url") or identity)
        return self._api_request(url, meta={self.LISTING_PAGE: identity}, priority=self.LISTING_PRIORITY)

    def _option_dates(self, response: Response, name: Optional[str]) -> List[datetime]:
        """Read the creation dates of the fulfillment options of a listing page.

        Args:
            response (Response): The listing page.
            name (Optional[str]): The software, for the logs.

        Returns:
            List[datetime]: The creation date of each fulfillment option, oldest first, none when the page has none.
        """
        body = response.body.decode(TextEncoding.UTF_8, errors=TextEncoding.REPLACE)
        raw = {option: created for option, created in self.OPTION_DATE.findall(body)}
        dates = [date for date in (self._parse_date(value, name) for value in raw.values()) if date is not None]
        return sorted(dates)

    def _dated_item(self, response: Response) -> Optional[Dict[str, JsonValue]]:
        """Date a streamed software from its listing page: added at its oldest option, updated at its newest one.

        Args:
            response (Response): The listing page (`LISTING_PAGE` meta).

        Returns:
            Optional[Dict[str, JsonValue]]: The software item with its dates, `None` when the page is missing or
                gives no date (logged).
        """
        identity = str(response.meta[self.LISTING_PAGE])
        item = self.streamed[identity]
        if response.status >= 400:
            self.logger.debug("The %s listing page %s is missing (HTTP %s).", self.name, response.url, response.status)
            return None
        dates = self._option_dates(response, str(item.get("name")))
        if not dates:
            self.logger.debug("The %s listing page %s gives no date.", self.name, response.url)
            return None
        several = len(dates) > 1
        software = MarketplaceSoftware.model_validate(
            {
                **item,
                "added_at": dates[0],
                "added_caveat": DateCaveat.OLDEST_VERSION if several else None,
                "updated_at": dates[-1] if several else None,
            }
        )
        dated = software.item_dump()
        self.streamed[identity] = dated
        self.logger.debug(
            "%s dated from its %d fulfillment options: added %s.", software.name, len(dates), dates[0].isoformat()
        )
        return dated

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a page of listings.

        Args:
            response (Response): The discovery API response.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid software listing of the page.

        Raises:
            CatalogueFormatError: If the page has no `ListingSummaries` list.
        """
        listings, _ = self._search_page(response)
        option = response.meta.get(self.OPTION)
        self.logger.debug("%d %s listings in the %s page %s.", len(listings), option, self.name, response.url)
        for listing in listings:
            if software := self._listing_software(self._as_object(listing)):
                yield software

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Request the listings of each fulfillment option, stream a page of listings, or date a listing.

        Args:
            response (Response): The browse page, a discovery API response (`OPTION` meta) or a listing page
                (`LISTING_PAGE` meta).

        Yields:
            Union[Dict[str, JsonValue], Request]: The first page request of each fulfillment option, each software
                not streamed yet then its listing page request and the next page request, or the dated software.
        """
        if self.LISTING_PAGE in response.meta:
            if (dated := self._dated_item(response)) is not None:
                yield dated
            return
        option = response.meta.get(self.OPTION)
        if not isinstance(option, str):
            integration_id = self._integration_id(response)
            self.logger.info("Requesting the %s listings of %d fulfillment options.", self.name, len(self.DELIVERIES))
            for value in self.DELIVERIES:
                yield self._search_request(integration_id, value, 1)
            return
        async for item in super().parse(response):
            yield item
        for identity in self.listing_pages:
            yield self._listing_request(identity)
        self.listing_pages.clear()
        listings, data = self._search_page(response)
        token = self._as_text(data.get(AwsSearchPageField.NEXT_TOKEN))
        page = response.meta.get(self.PAGE)
        page = page if isinstance(page, int) else 1
        if not token or not listings:
            total = data.get(AwsSearchPageField.TOTAL_RESULTS)
            self.logger.info("Last %s page of the %s listings: %d (%s in total).", self.name, option, page, total)
            return
        if self._within_page_limit(page + 1):
            integration_id = str(response.meta.get(self.INTEGRATION) or self.INTEGRATION_ID)
            self.logger.info("Requesting the %s page %d of the %s listings.", self.name, page + 1, option)
            yield self._search_request(integration_id, option, page + 1, token)
