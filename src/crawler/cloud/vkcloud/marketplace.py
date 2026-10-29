from __future__ import annotations

# Standard Library Imports.
from pathlib import Path
from typing import ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.vkcloud.enums import (
    VkCloudCatalogueField,
    VkCloudProductType,
    VkCloudSoftwareField,
    VkCloudTagField,
    VkCloudTagType,
)
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DateCaveat, DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class VKCloudMarketplaceCrawler(BaseMarketplaceCrawler):
    """VK Cloud marketplace crawler.

    Attributes:
        SITE_URL (ClassVar[str]): The website the software pages are on.
        CATEGORY_TAG (ClassVar[VkCloudTagType]): The type of the tags naming a marketplace category.
        PRODUCT_TYPE_TAG (ClassVar[VkCloudTagType]): The type of the tags naming how a software is delivered.
        DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery method of each product type tag, keyed by
            `VkCloudProductType` members.
        PUBLISHER_FIELDS (ClassVar[Tuple[VkCloudSoftwareField, ...]]): The fields naming the publisher of a
            listing, by preference: its developer company, else its developer or provider.
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The catalogue API of the marketplace page.

    Notes:
        The https://cloud.vk.ru/marketplace/ page loads its catalogue from the `/api/v-s/getCatalog/` API of the
        website: one JSON response lists every software (`data`, no pagination, the page shows them ten by ten),
        with its name, description, developer (`company`) and tags (`tags`), and the filters of the page
        (`filterValues`). The tags are typed: the `category` ones are the marketplace categories (e.g. `Базы
        данных`), the `product_type` one tells the delivery (`Image Based` virtual machine images, `SaaS`, `Заявка`
        offers sold on request). The marketplace taxonomy is flat: each category path is a category tag title,
        identified by its tag (e.g. `database`). The software listed by the CMS (the operating systems, under
        `/marketplace/os/`) are kept like the others. Each software page is the `href` of its listing, with the
        trailing slash the website redirects to. The listing date (`releaseDate`) is when the marketplace entry was
        released or last updated (a new version), not the launch of the software: it is the last update, with the
        `CATALOGUE_ENTRY` caveat.
    """

    SITE_URL: ClassVar[str] = "https://cloud.vk.ru/"
    CATEGORY_TAG: ClassVar[VkCloudTagType] = VkCloudTagType.CATEGORY
    PRODUCT_TYPE_TAG: ClassVar[VkCloudTagType] = VkCloudTagType.PRODUCT_TYPE
    DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        VkCloudProductType.IMAGE_BASED: DeliveryMethod.VIRTUAL_MACHINE,
        VkCloudProductType.SAAS: DeliveryMethod.SAAS,
        VkCloudProductType.APPLICATION: DeliveryMethod.OTHER,
    }
    PUBLISHER_FIELDS: ClassVar[Tuple[VkCloudSoftwareField, ...]] = (
        VkCloudSoftwareField.COMPANY,
        VkCloudSoftwareField.DEVELOPER,
        VkCloudSoftwareField.PROVIDER,
    )

    name = "vkcloud-marketplace"
    catalogue_url: ClassVar[str] = "https://cloud.vk.ru/api/v-s/getCatalog/"

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

    def _listings(self, response: Response) -> List[JsonValue]:
        """Read the software listed by the catalogue API.

        Args:
            response (Response): The catalogue API response.

        Returns:
            List[JsonValue]: The listings (`data`).

        Raises:
            CatalogueFormatError: If the response is not a JSON object with a software list.
        """
        listings = self._as_object(self._json_body(response)).get(VkCloudCatalogueField.DATA)
        if not isinstance(listings, list):
            self.logger.error("The %s catalogue %s has no software list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the catalogue has no software list")
        self.logger.info("%d software listed by the %s catalogue %s.", len(listings), self.name, response.url)
        return listings

    def _tags(self, listing: Dict[str, JsonValue], kind: VkCloudTagType) -> List[Dict[str, JsonValue]]:
        """Read the tags of a type of a listing.

        Args:
            listing (Dict[str, JsonValue]): The listing.
            kind (VkCloudTagType): The tag type, e.g. `category`.

        Returns:
            List[Dict[str, JsonValue]]: The tags of that type (`tags`, else `labels`), in the listing order.
        """
        tags = listing.get(VkCloudSoftwareField.TAGS)
        if not isinstance(tags, list):
            tags = listing.get(VkCloudSoftwareField.LABELS)
        found = [
            tag
            for tag in map(self._as_object, tags if isinstance(tags, list) else [])
            if tag.get(VkCloudTagField.TYPE) == kind
        ]
        self.logger.debug(
            "%d %s tags for the %s listing %r.", len(found), kind, self.name, listing.get(VkCloudSoftwareField.TITLE)
        )
        return found

    def _publisher(self, listing: Dict[str, JsonValue]) -> Optional[str]:
        """Read the publisher of a listing: its developer company, else its developer or provider.

        Args:
            listing (Dict[str, JsonValue]): The listing.

        Returns:
            Optional[str]: The publisher, `None` when the listing names none.
        """
        for key in self.PUBLISHER_FIELDS:
            publisher = self._as_text(listing.get(key))
            if publisher and publisher.strip():
                return publisher
        self.logger.debug("No publisher for the %s listing %r.", self.name, listing.get(VkCloudSoftwareField.TITLE))
        return None

    def _delivery(self, listing: Dict[str, JsonValue]) -> DeliveryMethod:
        """Read the delivery method of a listing from its product type tag.

        Args:
            listing (Dict[str, JsonValue]): The listing.

        Returns:
            DeliveryMethod: The delivery method, `OTHER` without known product type.
        """
        for tag in self._tags(listing, self.PRODUCT_TYPE_TAG):
            if (delivery := self.DELIVERIES.get(self._as_text(tag.get(VkCloudTagField.TAG)) or "")) is not None:
                return delivery
        self.logger.debug(
            "No known product type for the %s listing %r.", self.name, listing.get(VkCloudSoftwareField.TITLE)
        )
        return DeliveryMethod.OTHER

    def _url(self, listing: Dict[str, JsonValue]) -> Optional[str]:
        """Build the software page URL of a listing.

        Args:
            listing (Dict[str, JsonValue]): The listing.

        Returns:
            Optional[str]: The absolute page URL with its trailing slash, `None` without `href`.
        """
        href = self._as_text(listing.get(VkCloudSoftwareField.HREF))
        if not href or not href.strip():
            self.logger.debug("No page for the %s listing %r.", self.name, listing.get(VkCloudSoftwareField.TITLE))
            return None
        url = urljoin(self.SITE_URL, href.strip())
        return url if url.endswith("/") or "?" in url or "#" in url else f"{url}/"

    def _software(self, listing: Dict[str, JsonValue]) -> Optional[MarketplaceSoftware]:
        """Build the software of a listing, filed under its category tags.

        Args:
            listing (Dict[str, JsonValue]): The listing.

        Returns:
            Optional[MarketplaceSoftware]: The software, `None` (logged) when the listing is invalid.
        """
        name = self._as_text(listing.get(VkCloudSoftwareField.TITLE))
        labels: List[Optional[str]] = []
        paths: List[Optional[MarketplaceCategory]] = []
        for tag in self._tags(listing, self.CATEGORY_TAG):
            label, slug = self._as_text(tag.get(VkCloudTagField.TITLE)), self._as_text(tag.get(VkCloudTagField.TAG))
            labels.append(label)
            paths.append(self._category([label], slug) if label else None)
        released = listing.get(VkCloudSoftwareField.RELEASE_DATE)
        return self._build_software(
            name,
            self._as_text(listing.get(VkCloudSoftwareField.TEXT)),
            self._url(listing),
            self._publisher(listing),
            self._delivery(listing),
            labels,
            paths,
            updated_at=self._parse_date(released, name) if released else None,
            updated_caveat=DateCaveat.CATALOGUE_ENTRY,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of the catalogue API response.

        Args:
            response (Response): The catalogue API response.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid software, in the catalogue order.
        """
        for entry in self._listings(response):
            listing = self._as_object(entry)
            if not listing:
                self.logger.warning("Skipping a %s listing which is not an object: %r.", self.name, entry)
                continue
            if (software := self._software(listing)) is not None:
                yield software
