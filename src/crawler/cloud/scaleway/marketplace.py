from __future__ import annotations

# Standard Library Imports.
from pathlib import Path
from typing import ClassVar, Dict, FrozenSet, Iterator, List, Optional, Union

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.scaleway.enums import (
    ScalewayAppCategory,
    ScalewayAppField,
    ScalewayAppFilterField,
    ScalewayCatalogFiltersField,
    ScalewayDeliveryLabel,
    ScalewayLabelField,
    ScalewayNavigationField,
    ScalewayNextDataField,
)
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class ScalewayMarketplaceCrawler(BaseMarketplaceCrawler):
    """Scaleway marketplace crawler.

    Attributes:
        EXCLUDED_CATEGORIES (ClassVar[FrozenSet[ScalewayAppCategory]]): The category slugs of the listings which are not
            software (the operating system images).
        DELIVERIES (ClassVar[Dict[ScalewayDeliveryLabel, DeliveryMethod]]): The delivery method of each marketplace
            delivery label.

    Notes:
        The Next.js data of the https://www.scaleway.com/en/marketplace/catalog/ page lists every application
        (`allApps`, no pagination), with its vendor and category slugs: the vendor names come from the page filters
        (`allFilters.vendors`), the category titles from the side navigation (`navigation.sideNav.category_pages`).
        The marketplace taxonomy is flat: each category path is a side navigation title, identified by its slug.
        The operating systems are skipped. The marketplace API is disallowed by its `robots.txt`: it is not used.
    """

    EXCLUDED_CATEGORIES: ClassVar[FrozenSet[ScalewayAppCategory]] = frozenset({ScalewayAppCategory.OS})
    DELIVERIES: ClassVar[Dict[ScalewayDeliveryLabel, DeliveryMethod]] = {
        ScalewayDeliveryLabel.SAAS_AND_APIS: DeliveryMethod.SAAS,
        ScalewayDeliveryLabel.VIRTUAL_MACHINES: DeliveryMethod.VIRTUAL_MACHINE,
        ScalewayDeliveryLabel.CONTAINER_IMAGES: DeliveryMethod.CONTAINER,
        ScalewayDeliveryLabel.KUBERNETES_APPS: DeliveryMethod.KUBERNETES,
        ScalewayDeliveryLabel.OTHER: DeliveryMethod.OTHER,
    }

    name = "scaleway-marketplace"
    catalogue_url: ClassVar[str] = "https://www.scaleway.com/en/marketplace/catalog/"

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

    def _labels(self, entries: JsonValue, label: str) -> Dict[str, str]:
        """Read the labels of a list of `{slug, <label>}` objects, e.g. the vendor names.

        Args:
            entries (JsonValue): The list of objects.
            label (str): The key of the label, e.g. `name`.

        Returns:
            Dict[str, str]: The label of each slug.
        """
        labels: Dict[str, str] = {}
        for entry in entries if isinstance(entries, list) else []:
            fields = self._as_object(entry)
            slug = self._as_text(fields.get(ScalewayLabelField.SLUG))
            text = self._as_text(fields.get(label))
            if slug and text:
                labels[slug] = text
        return labels

    def _category_slugs(self, filters: Dict[str, JsonValue]) -> List[str]:
        """Read the category slugs of an application.

        Args:
            filters (Dict[str, JsonValue]): The application filters.

        Returns:
            List[str]: The category slugs.
        """
        slugs = filters.get(ScalewayAppFilterField.CATEGORIES)
        return [slug for slug in (self._as_text(value) for value in slugs) if slug] if isinstance(slugs, list) else []

    def _category_paths(self, slugs: List[str], titles: Dict[str, str]) -> List[Optional[MarketplaceCategory]]:
        """Build the marketplace taxonomy categories of an application, the untitled slugs skipped.

        Args:
            slugs (List[str]): The category slugs of the application.
            titles (Dict[str, str]): The side navigation title of each category slug.

        Returns:
            List[Optional[MarketplaceCategory]]: One single level category per titled slug, identified by its slug.
        """
        paths: List[Optional[MarketplaceCategory]] = []
        for slug in slugs:
            title = titles.get(slug)
            if title is None:
                self.logger.debug("No %s side navigation title for the category slug %r.", self.name, slug)
                continue
            paths.append(self._category([title], slug))
        self.logger.debug("%d of %d %s category slugs have a title.", len(paths), len(slugs), self.name)
        return paths

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of the catalog page, the operating systems excluded.

        Args:
            response (Response): The catalog page.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid software of the page.

        Raises:
            CatalogueFormatError: If the page data has no applications list.
        """
        page = self._as_object(self._next_data(response).get(ScalewayNextDataField.PROPS))
        props = self._as_object(page.get(ScalewayNextDataField.PAGE_PROPS))
        apps = props.get(ScalewayNextDataField.ALL_APPS)
        if not isinstance(apps, list):
            self.logger.error("The %s page %s data has no applications list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the page data has no applications list")
        filters_data = self._as_object(props.get(ScalewayNextDataField.ALL_FILTERS))
        vendors = self._labels(filters_data.get(ScalewayCatalogFiltersField.VENDORS), ScalewayLabelField.NAME)
        navigation = self._as_object(props.get(ScalewayNextDataField.NAVIGATION))
        side_nav = self._as_object(navigation.get(ScalewayNavigationField.SIDE_NAV))
        categories = self._labels(side_nav.get(ScalewayNavigationField.CATEGORY_PAGES), ScalewayLabelField.TITLE)
        self.logger.info(
            "%d applications, %d vendors and %d categories listed by the %s page %s.",
            len(apps),
            len(vendors),
            len(categories),
            self.name,
            response.url,
        )
        for entry in apps:
            app = self._as_object(entry)
            name = self._as_text(app.get(ScalewayAppField.TITLE))
            slug = self._as_text(app.get(ScalewayAppField.SLUG))
            filters = self._as_object(app.get(ScalewayAppField.FILTERS))
            slugs = self._category_slugs(filters)
            if excluded := sorted(self.EXCLUDED_CATEGORIES.intersection(slugs)):
                self.logger.debug("Skipping the %s application %r, category %s.", self.name, name, ", ".join(excluded))
                continue
            vendor = self._as_text(filters.get(ScalewayAppFilterField.VENDOR))
            delivery = self._as_text(app.get(ScalewayAppField.DELIVERY_METHOD)) or ""
            software = self._build_software(
                name,
                self._as_text(app.get(ScalewayAppField.DESCRIPTION)),
                f"{self.catalogue_url}{slug}/" if slug else None,
                vendors.get(vendor, vendor) if vendor else None,
                self.DELIVERIES[ScalewayDeliveryLabel(delivery)]
                if delivery in self.DELIVERIES
                else DeliveryMethod.OTHER,
                [categories.get(category, category) for category in slugs],
                marketplace_category_paths=self._category_paths(slugs, categories),
            )
            if software is not None:
                yield software
