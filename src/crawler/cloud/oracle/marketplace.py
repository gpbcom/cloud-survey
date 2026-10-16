from __future__ import annotations

# Standard Library Imports.
import math
import re
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Union

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.marketplace_software import MarketplaceSoftware


class OracleMarketplaceCrawler(BaseMarketplaceCrawler):
    """Oracle Cloud Marketplace crawler.

    Attributes:
        API_URL (ClassVar[str]): The public Oracle Cloud Marketplace API.
        LISTING_URL (ClassVar[str]): The marketplace page of a listing, by slug and identifier.
        PAGE_SIZE (ClassVar[int]): The number of listings per page, the largest one the API accepts.
        PAGE (ClassVar[str]): The meta key holding the number of a listings page.
        DETAIL (ClassVar[str]): The meta key marking a listing detail.
        EXCLUDED_TYPES (ClassVar[FrozenSet[str]]): The listing types of the services.
        EXCLUDED_GROUPS (ClassVar[FrozenSet[str]]): The product groups of the services.
        EXCLUDED_PRODUCTS (ClassVar[FrozenSet[str]]): The products of the partners which are not software publishers.
        NOT_SOFTWARE (ClassVar[re.Pattern[str]]): The names of the advisory, managed and professional services.
        DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery of each listing type, `OTHER` for the others.
        HEADERS (ClassVar[Dict[str, str]]): The API request headers: the marketplace website as referrer, since the
            API answers `NotAuthorizedOrNotFound` (HTTP 404) to the default search engine referrer.

    Notes:
        The listings come from the public marketplace API (`GET /20180828/listings?limit=120&page=n`, its
        `pagination` giving the number of pages). The services (listing type `SERVICE`, product group `SERVICES`,
        system integrators, resellers and advisors, advisory or managed services) are skipped. The publisher is only
        given by the listing detail (`GET /20180828/listings/{id}`, `partner.name`): the detail of each kept listing
        is requested, after the listing pages, and the software is read from it. The OCI applications (images and
        stacks) are delivered on virtual machines, the lead generation listings are SaaS applications and the AI
        agents are called through an API.
    """

    API_URL: ClassVar[str] = "https://public.marketplace.us-ashburn-1.oci.oraclecloud.com/20180828"
    LISTING_URL: ClassVar[str] = "https://marketplace.oracle.com/listings/{slug}/{id}"
    PAGE_SIZE: ClassVar[int] = 120
    PAGE: ClassVar[str] = "page"
    DETAIL: ClassVar[str] = "detail"
    EXCLUDED_TYPES: ClassVar[FrozenSet[str]] = frozenset({"SERVICE"})
    EXCLUDED_GROUPS: ClassVar[FrozenSet[str]] = frozenset({"SERVICES"})
    EXCLUDED_PRODUCTS: ClassVar[FrozenSet[str]] = frozenset(
        {"System Integrators", "Resellers", "Influencers and Advisors"}
    )
    NOT_SOFTWARE: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(?:professional|consulting|managed|implementation) services?\b|\badvisory\b", re.IGNORECASE
    )
    DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        "OCI_APPLICATION": DeliveryMethod.VIRTUAL_MACHINE,
        "LEAD_GENERATION": DeliveryMethod.SAAS,
        "AI_AGENT": DeliveryMethod.API,
    }

    HEADERS: ClassVar[Dict[str, str]] = {"Referer": "https://marketplace.oracle.com/"}

    name = "oracle-marketplace"
    catalogue_url: ClassVar[str] = f"{API_URL}/listings?limit={PAGE_SIZE}&page=1"

    ############################
    # Internal Helpers Methods #
    ############################

    def _page_request(self, page: int) -> Request:
        """Build the request of a listings page.

        Args:
            page (int): The page number, the first page being 1.

        Returns:
            Request: The request, crawled before the listing details (primary priority).
        """
        return self._api_request(
            f"{self.API_URL}/listings?limit={self.PAGE_SIZE}&page={page}",
            headers=dict(self.HEADERS),
            meta={self.PAGE: page},
            priority=self.PRIMARY_PRIORITY,
        )

    def _catalogue_request(self) -> Request:
        """Build the request of the first listings page.

        Returns:
            Request: The request of the HTTP session.
        """
        return self._page_request(1)

    def _as_list(self, value: JsonValue) -> List[JsonValue]:
        """Read a JSON value expected to be a list.

        Args:
            value (JsonValue): The JSON value.

        Returns:
            List[JsonValue]: The list, empty when the value is not a list.
        """
        return value if isinstance(value, list) else []

    def _skip_reason(self, listing: Dict[str, JsonValue]) -> Optional[str]:
        """Tell why a listing is not a software.

        Args:
            listing (Dict[str, JsonValue]): The listing.

        Returns:
            Optional[str]: The reason (service listing type, service product group or partner product, service
                name), `None` for a software.
        """
        products = [self._as_object(product) for product in self._as_list(listing.get("products"))]
        groups = {self._as_text(product.get("productGroup")) for product in products}
        names = {self._as_text(product.get("productName")) for product in products}
        reasons = {
            f"listing type {listing.get('listingType')!r}": listing.get("listingType") in self.EXCLUDED_TYPES,
            "service product group": bool(groups & self.EXCLUDED_GROUPS),
            "partner product": bool(names & self.EXCLUDED_PRODUCTS),
            "service": bool(self.NOT_SOFTWARE.search(self._as_text(listing.get("name")) or "")),
        }
        failed = [reason for reason, matched in reasons.items() if matched]
        return ", ".join(failed) if failed else None

    def _listings(self, response: Response) -> List[Dict[str, JsonValue]]:
        """Read the listings of a listings page.

        Args:
            response (Response): The listings page.

        Returns:
            List[Dict[str, JsonValue]]: The listings.

        Raises:
            CatalogueFormatError: If the page is not JSON, or has no `items` list.
        """
        items = self._as_object(self._json_body(response)).get("items")
        if not isinstance(items, list):
            self.logger.error("The %s listings page %s has no `items` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the `items` list is missing")
        return [self._as_object(item) for item in items]

    def _page_count(self, response: Response) -> int:
        """Read the number of listings pages, from the first page.

        Args:
            response (Response): The first listings page.

        Returns:
            int: The number of pages, from `pagination.totalPages`, else from `pagination.totalItems`, at least 1.
        """
        pagination = self._as_object(self._as_object(self._json_body(response)).get("pagination"))
        pages, total = pagination.get("totalPages"), pagination.get("totalItems")
        if isinstance(pages, int) and pages > 0:
            return pages
        return max(1, math.ceil(total / self.PAGE_SIZE)) if isinstance(total, int) else 1

    def _listing_requests(self, response: Response) -> Iterator[Request]:
        """Request the details of the software listings of a listings page, and the next pages from the first one.

        Args:
            response (Response): The listings page.

        Yields:
            Request: The listing detail requests, then the next listings pages requests.

        Raises:
            CatalogueFormatError: If the page is not JSON, or has no `items` list.
        """
        page = int(str(response.meta.get(self.PAGE, 1)))
        listings = self._listings(response)
        kept = 0
        for listing in listings:
            identifier, name = self._as_text(listing.get("id")), self._as_text(listing.get("name"))
            if identifier is None:
                self.logger.debug("Skipping the listing %r, it has no identifier.", name)
                continue
            if reason := self._skip_reason(listing):
                self.logger.debug("Skipping the listing %r (%s).", name, reason)
                continue
            kept += 1
            yield self._api_request(
                f"{self.API_URL}/listings/{identifier}",
                headers=dict(self.HEADERS),
                meta={self.DETAIL: identifier, self.MAY_BE_EMPTY: True},
            )
        self.logger.info(
            "%s listings page %d: %d software listings of %d requested.", self.name, page, kept, len(listings)
        )
        if page != 1:
            return
        pages = self._page_count(response)
        self.logger.info("%d %s listings pages to read.", pages, self.name)
        for number in range(2, pages + 1):
            if not self._within_page_limit(number):
                break
            yield self._page_request(number)

    def _listing_url(self, identifier: str, name: str) -> str:
        """Build the marketplace page URL of a listing.

        Args:
            identifier (str): The listing identifier.
            name (str): The listing name.

        Returns:
            str: The listing page, e.g. `https://marketplace.oracle.com/listings/almalinux-os-10/ocid1...`.
        """
        slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "listing"
        return self.LISTING_URL.format(slug=slug, id=identifier)

    def _categories(self, listing: Dict[str, JsonValue]) -> List[str]:
        """Read the marketplace categories of a listing: its products and their categories.

        Args:
            listing (Dict[str, JsonValue]): The listing.

        Returns:
            List[str]: The product names and category names, without duplicates.
        """
        labels: List[str] = []
        for entry in self._as_list(listing.get("products")):
            product = self._as_object(entry)
            names = [self._as_text(product.get("productName"))]
            names += [
                self._as_text(self._as_object(category).get("name"))
                for category in self._as_list(product.get("categories"))
            ]
            labels += [label for label in names if label and label not in labels]
        return labels

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a listing detail.

        Args:
            response (Response): The listing detail (`DETAIL` meta).

        Yields:
            MarketplaceSoftware: The software, with its listing (`timeCreated`) and update (`timeUpdated`) dates,
                unless the detail is missing (HTTP error) or invalid.

        Raises:
            CatalogueFormatError: If the detail is not JSON.
        """
        identifier = str(response.meta.get(self.DETAIL))
        if response.status >= 400:
            self.logger.warning(
                "Skipping the %s listing %s, its detail is missing (HTTP %s).", self.name, identifier, response.status
            )
            return
        listing = self._as_object(self._json_body(response))
        name = self._as_text(listing.get("name")) or ""
        software = self._build_software(
            name,
            self._as_text(listing.get("shortDescription")) or self._as_text(listing.get("tagline")),
            url=self._listing_url(identifier, name),
            publisher=self._as_text(self._as_object(listing.get("partner")).get("name")),
            delivery=self.DELIVERIES.get(self._as_text(listing.get("listingType")) or "", DeliveryMethod.OTHER),
            marketplace_categories=self._categories(listing),
            added_at=self._parse_date(listing.get("timeCreated"), name),
            updated_at=self._parse_date(listing.get("timeUpdated"), name),
        )
        if software is not None:
            yield software

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Request the listing details of a listings page, or stream the software of a listing detail.

        Args:
            response (Response): A listings page, or a listing detail (`DETAIL` meta).

        Yields:
            Union[Dict[str, JsonValue], Request]: The detail and next pages requests of a listings page, the software
                of a listing detail.

        Raises:
            CatalogueFormatError: If a page is not JSON, or if a listings page has no `items` list.
        """
        if self.DETAIL not in response.meta:
            for request in self._listing_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
