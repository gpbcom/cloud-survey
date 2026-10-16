from __future__ import annotations

# Standard Library Imports.
import json
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.marketplace_software import MarketplaceSoftware


class AWSMarketplaceCrawler(BaseMarketplaceCrawler):
    """AWS Marketplace crawler: the software listings, by fulfillment option.

    Attributes:
        API_URL (ClassVar[str]): The discovery API proxy of the marketplace pages (`SearchListings`).
        LISTING_URL (ClassVar[str]): The listing page, formatted with the listing identifier.
        INTEGRATION_ID (ClassVar[str]): The known integration identifier, used when the browse page holds none.
        PAGE_SIZE (ClassVar[int]): The listings read per page, the API maximum.
        DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery of each software fulfillment option, queried
            in this order.
        OPTION (ClassVar[str]): The meta key holding the queried fulfillment option.
        PAGE (ClassVar[str]): The meta key holding the page number within a fulfillment option, from 1.
        INTEGRATION (ClassVar[str]): The meta key holding the integration identifier.
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): A browse page of the marketplace, carrying the integration identifier.

    Notes:
        The marketplace pages search the listings through a JSON proxy of the discovery service: a `POST` envelope
        whose `contentString` holds the `SearchListings` request. It needs the integration identifier of the pages,
        read from the `integrationId` meta of a browse page (the search page is disallowed by `robots.txt`). The
        listings are queried once per software fulfillment option (SaaS, machine images, containers...), which keeps
        each query under the 10,000 results window, and read page after page with the `NextToken` cursor. The
        professional services and data exchange options are not queried. A listing of several options is streamed
        once, with the delivery of its first software option.
    """

    API_URL: ClassVar[str] = "https://aws.amazon.com/marketplace/api/awsmpdiscovery"
    LISTING_URL: ClassVar[str] = "https://aws.amazon.com/marketplace/pp/{}"
    INTEGRATION_ID: ClassVar[str] = "integ-kzv5xkq73lzjw"
    PAGE_SIZE: ClassVar[int] = 100
    DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        "SAAS": DeliveryMethod.SAAS,
        "AMAZON_MACHINE_IMAGE": DeliveryMethod.VIRTUAL_MACHINE,
        "CONTAINER": DeliveryMethod.CONTAINER,
        "HELM": DeliveryMethod.KUBERNETES,
        "EKS_ADD_ON": DeliveryMethod.KUBERNETES,
        "CLOUDFORMATION_TEMPLATE": DeliveryMethod.VIRTUAL_MACHINE,
        "EC2_IMAGE_BUILDER_COMPONENT": DeliveryMethod.VIRTUAL_MACHINE,
        "SAGEMAKER_MODEL": DeliveryMethod.AI_MODEL,
        "SAGEMAKER_ALGORITHM": DeliveryMethod.AI_MODEL,
        "API": DeliveryMethod.API,
    }
    OPTION: ClassVar[str] = "fulfillment_option"
    PAGE: ClassVar[str] = "page"
    INTEGRATION: ClassVar[str] = "integration_id"

    name = "aws-marketplace"
    catalogue_url: ClassVar[str] = "https://aws.amazon.com/marketplace/b/579164ab-a400-4924-9c9c-590e45580b7d"

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
        if integration_id := self._meta_content(response, "integrationId"):
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
            "MaxResults": self.PAGE_SIZE,
            "RequestContext": {"IntegrationId": integration_id},
            "Filters": [{"Type": "FULFILLMENT_OPTION_TYPE", "Values": [option]}],
        }
        if token:
            content["NextToken"] = token
        envelope: Dict[str, JsonValue] = {
            "region": "us-east-1",
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": "AWSMPDiscoveryService.SearchListings",
            },
            "contentString": json.dumps(content),
            "method": "POST",
            "operation": "SearchListings",
            "path": "/",
        }
        meta: Dict[str, JsonValue] = {self.OPTION: option, self.PAGE: page, self.INTEGRATION: integration_id}
        if page == 1:
            meta[self.MAY_BE_EMPTY] = True
        return self._api_request(
            self.API_URL, method="POST", json=envelope, headers={"content-type": "application/json"}, meta=meta
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
        listings = data.get("ListingSummaries")
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
        options = listing.get("FulfillmentOptionTypes")
        for option in options if isinstance(options, list) else []:
            value = self._as_text(self._as_object(option).get("Value"))
            if value in self.DELIVERIES:
                return self.DELIVERIES[value]
        return None

    def _publisher(self, listing: Dict[str, JsonValue]) -> Optional[str]:
        """Get the publisher of a listing: its creator, else the manufacturer of its product.

        Args:
            listing (Dict[str, JsonValue]): The listing summary.

        Returns:
            Optional[str]: The publisher name, `None` when unknown.
        """
        if creator := self._as_text(self._as_object(listing.get("ListingCreator")).get("DisplayName")):
            return creator
        entities = listing.get("AssociatedEntities")
        for entity in entities if isinstance(entities, list) else []:
            manufacturer = self._as_object(self._as_object(entity).get("Manufacturer"))
            if name := self._as_text(manufacturer.get("DisplayName")):
                return name
        return None

    def _categories(self, listing: Dict[str, JsonValue]) -> List[str]:
        """Get the category labels of a listing, each preceded by its parent category when the listing names it.

        Args:
            listing (Dict[str, JsonValue]): The listing summary.

        Returns:
            List[str]: The category labels, without duplicates.
        """
        raw = listing.get("Categories")
        categories = [self._as_object(category) for category in (raw if isinstance(raw, list) else [])]
        names = {
            str(category.get("Value")): label
            for category in categories
            if (label := self._as_text(category.get("DisplayName")))
        }
        labels: List[str] = []
        for category in categories:
            parent = names.get(str(category.get("ParentValue")))
            labels.extend(label for label in (parent, self._as_text(category.get("DisplayName"))) if label)
        return list(dict.fromkeys(labels))

    def _listing_software(self, listing: Dict[str, JsonValue]) -> Optional[MarketplaceSoftware]:
        """Build the software of a listing summary.

        Args:
            listing (Dict[str, JsonValue]): The listing summary.

        Returns:
            Optional[MarketplaceSoftware]: The software, `None` when the listing is not software or is invalid.
        """
        attributes = self._as_object(listing.get("DisplayAttributes"))
        title = self._as_text(attributes.get("Title"))
        delivery = self._delivery(listing)
        if delivery is None:
            self.logger.debug("Skipping the %s listing %r, not software.", self.name, title)
            return None
        listing_id = self._as_text(listing.get("Id"))
        return self._build_software(
            title,
            self._as_text(attributes.get("ShortDescription")) or self._as_text(attributes.get("LongDescription")),
            self.LISTING_URL.format(listing_id) if listing_id else None,
            self._publisher(listing),
            delivery,
            self._categories(listing),
        )

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
        """Request the listings of each fulfillment option from the browse page, or stream a page of listings.

        Args:
            response (Response): The browse page, or a discovery API response (`OPTION` meta).

        Yields:
            Union[Dict[str, JsonValue], Request]: The first page request of each fulfillment option, or each software
                not streamed yet then the next page request.
        """
        option = response.meta.get(self.OPTION)
        if not isinstance(option, str):
            integration_id = self._integration_id(response)
            self.logger.info("Requesting the %s listings of %d fulfillment options.", self.name, len(self.DELIVERIES))
            for value in self.DELIVERIES:
                yield self._search_request(integration_id, value, 1)
            return
        async for item in super().parse(response):
            yield item
        listings, data = self._search_page(response)
        token = self._as_text(data.get("NextToken"))
        page = response.meta.get(self.PAGE)
        page = page if isinstance(page, int) else 1
        if not token or not listings:
            total = data.get("TotalResults")
            self.logger.info("Last %s page of the %s listings: %d (%s in total).", self.name, option, page, total)
            return
        if self._within_page_limit(page + 1):
            integration_id = str(response.meta.get(self.INTEGRATION) or self.INTEGRATION_ID)
            self.logger.info("Requesting the %s page %d of the %s listings.", self.name, page + 1, option)
            yield self._search_request(integration_id, option, page + 1, token)
