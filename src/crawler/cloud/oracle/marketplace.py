from __future__ import annotations

# Standard Library Imports.
import math
import re
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Union

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.oracle.enums import (
    OracleCategoryField,
    OracleHeader,
    OracleListingField,
    OracleListingsPageField,
    OracleListingType,
    OracleMarketplaceMeta,
    OraclePartnerProduct,
    OracleProductField,
    OracleProductGroup,
)
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class OracleMarketplaceCrawler(BaseMarketplaceCrawler):
    """Oracle Cloud Marketplace crawler.

    Attributes:
        API_URL (ClassVar[str]): The public Oracle Cloud Marketplace API.
        LISTING_URL (ClassVar[str]): The marketplace page of a listing, by slug and identifier.
        PAGE_SIZE (ClassVar[int]): The number of listings per page, the largest one the API accepts.
        PAGE (ClassVar[OracleMarketplaceMeta]): The meta key holding the number of a listings page.
        DETAIL (ClassVar[OracleMarketplaceMeta]): The meta key marking a listing detail.
        EXCLUDED_TYPES (ClassVar[FrozenSet[OracleListingType]]): The listing types of the services.
        EXCLUDED_GROUPS (ClassVar[FrozenSet[OracleProductGroup]]): The product groups of the services.
        EXCLUDED_PRODUCTS (ClassVar[FrozenSet[OraclePartnerProduct]]): The products of the partners which are not
            software publishers.
        NOT_SOFTWARE (ClassVar[re.Pattern[str]]): The names of the advisory, managed and professional services.
        DELIVERIES (ClassVar[Dict[OracleListingType, DeliveryMethod]]): The delivery of each listing type, `OTHER` for
            the others.
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
    PAGE: ClassVar[OracleMarketplaceMeta] = OracleMarketplaceMeta.PAGE
    DETAIL: ClassVar[OracleMarketplaceMeta] = OracleMarketplaceMeta.DETAIL
    EXCLUDED_TYPES: ClassVar[FrozenSet[OracleListingType]] = frozenset({OracleListingType.SERVICE})
    EXCLUDED_GROUPS: ClassVar[FrozenSet[OracleProductGroup]] = frozenset({OracleProductGroup.SERVICES})
    EXCLUDED_PRODUCTS: ClassVar[FrozenSet[OraclePartnerProduct]] = frozenset(
        {
            OraclePartnerProduct.SYSTEM_INTEGRATORS,
            OraclePartnerProduct.RESELLERS,
            OraclePartnerProduct.INFLUENCERS_AND_ADVISORS,
        }
    )
    NOT_SOFTWARE: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(?:professional|consulting|managed|implementation) services?\b|\badvisory\b", re.IGNORECASE
    )
    DELIVERIES: ClassVar[Dict[OracleListingType, DeliveryMethod]] = {
        OracleListingType.OCI_APPLICATION: DeliveryMethod.VIRTUAL_MACHINE,
        OracleListingType.LEAD_GENERATION: DeliveryMethod.SAAS,
        OracleListingType.AI_AGENT: DeliveryMethod.API,
    }

    HEADERS: ClassVar[Dict[str, str]] = {OracleHeader.REFERER: "https://marketplace.oracle.com/"}

    name = "oracle-marketplace"
    catalogue_url: ClassVar[str] = f"{API_URL}/listings?limit={PAGE_SIZE}&page=1"

    def __init__(
        self,
        crawldir: Optional[Union[str, Path]] = None,
        interval: float = 300.0,
        classifier: Optional[SoftwareClassifier] = None,
    ) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
            classifier (Optional[SoftwareClassifier]): The software classifier, the project rules by default.
        """
        super().__init__(crawldir=crawldir, interval=interval, classifier=classifier)

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
        products = [self._as_object(product) for product in self._as_list(listing.get(OracleListingField.PRODUCTS))]
        groups = {self._as_text(product.get(OracleProductField.PRODUCT_GROUP)) for product in products}
        names = {self._as_text(product.get(OracleProductField.PRODUCT_NAME)) for product in products}
        reasons = {
            f"listing type {listing.get(OracleListingField.LISTING_TYPE)!r}": listing.get(
                OracleListingField.LISTING_TYPE
            )
            in self.EXCLUDED_TYPES,
            "service product group": bool(groups & self.EXCLUDED_GROUPS),
            "partner product": bool(names & self.EXCLUDED_PRODUCTS),
            "service": bool(self.NOT_SOFTWARE.search(self._as_text(listing.get(OracleListingField.NAME)) or "")),
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
        items = self._as_object(self._json_body(response)).get(OracleListingsPageField.ITEMS)
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
        pagination = self._as_object(self._as_object(self._json_body(response)).get(OracleListingsPageField.PAGINATION))
        pages = pagination.get(OracleListingsPageField.TOTAL_PAGES)
        total = pagination.get(OracleListingsPageField.TOTAL_ITEMS)
        if isinstance(pages, int) and pages > 0:
            self.logger.debug("The %s listings span %d pages.", self.name, pages)
            return pages
        if isinstance(total, int):
            count = max(1, math.ceil(total / self.PAGE_SIZE))
            self.logger.debug("No %s page count: %d pages computed from %d listings.", self.name, count, total)
            return count
        self.logger.warning("No %s page count nor listing total in %s: one page is assumed.", self.name, response.url)
        return 1

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
            identifier = self._as_text(listing.get(OracleListingField.ID))
            name = self._as_text(listing.get(OracleListingField.NAME))
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
        for entry in self._as_list(listing.get(OracleListingField.PRODUCTS)):
            product = self._as_object(entry)
            names = [self._as_text(product.get(OracleProductField.PRODUCT_NAME))]
            names += [
                self._as_text(self._as_object(category).get(OracleCategoryField.NAME))
                for category in self._as_list(product.get(OracleProductField.CATEGORIES))
            ]
            labels += [label for label in names if label and label not in labels]
        return labels

    def _category_paths(self, listing: Dict[str, JsonValue]) -> List[Optional[MarketplaceCategory]]:
        """Read the category paths of a listing: the categories of its products, not the products themselves.

        Args:
            listing (Dict[str, JsonValue]): The listing.

        Returns:
            List[Optional[MarketplaceCategory]]: One path per product category (its `name`), identified by its `code`.
        """
        paths: List[Optional[MarketplaceCategory]] = []
        for entry in self._as_list(listing.get(OracleListingField.PRODUCTS)):
            for raw in self._as_list(self._as_object(entry).get(OracleProductField.CATEGORIES)):
                category = self._as_object(raw)
                label = self._as_text(category.get(OracleCategoryField.NAME))
                paths.append(self._category([label], self._as_text(category.get(OracleCategoryField.CODE))))
        self.logger.debug(
            "%d category paths for the %s listing %r.", len(paths), self.name, listing.get(OracleListingField.NAME)
        )
        return paths

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
        name = self._as_text(listing.get(OracleListingField.NAME)) or ""
        listing_type = self._as_text(listing.get(OracleListingField.LISTING_TYPE)) or ""
        software = self._build_software(
            name,
            self._as_text(listing.get(OracleListingField.SHORT_DESCRIPTION))
            or self._as_text(listing.get(OracleListingField.TAGLINE)),
            url=self._listing_url(identifier, name),
            publisher=self._as_text(
                self._as_object(listing.get(OracleListingField.PARTNER)).get(OracleListingField.NAME)
            ),
            delivery=self.DELIVERIES[OracleListingType(listing_type)]
            if listing_type in self.DELIVERIES
            else DeliveryMethod.OTHER,
            marketplace_categories=self._categories(listing),
            marketplace_category_paths=self._category_paths(listing),
            added_at=self._parse_date(listing.get(OracleListingField.TIME_CREATED), name),
            updated_at=self._parse_date(listing.get(OracleListingField.TIME_UPDATED), name),
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
            self.logger.debug("Reading the %s listings page %s.", self.name, response.url)
            for request in self._listing_requests(response):
                yield request
            return
        self.logger.debug("Reading the %s listing details %s.", self.name, response.url)
        async for item in super().parse(response):
            yield item
