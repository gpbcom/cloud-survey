from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, FrozenSet, Iterator, List

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Response

# First Party Imports.
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.marketplace_software import MarketplaceSoftware


class ScalewayMarketplaceCrawler(BaseMarketplaceCrawler):
    """Scaleway marketplace crawler.

    Attributes:
        EXCLUDED_CATEGORIES (ClassVar[FrozenSet[str]]): The category slugs of the listings which are not software (the
            operating system images).
        DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery method of each marketplace delivery label.

    Notes:
        The Next.js data of the https://www.scaleway.com/en/marketplace/catalog/ page lists every application
        (`allApps`, no pagination), with its vendor and category slugs: the vendor names come from the page filters
        (`allFilters.vendors`), the category titles from the side navigation (`navigation.sideNav.category_pages`).
        The operating systems are skipped. The marketplace API is disallowed by its `robots.txt`: it is not used.
    """

    EXCLUDED_CATEGORIES: ClassVar[FrozenSet[str]] = frozenset({"os"})
    DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        "SaaS & APIs": DeliveryMethod.SAAS,
        "Virtual machines": DeliveryMethod.VIRTUAL_MACHINE,
        "Container images": DeliveryMethod.CONTAINER,
        "Kubernetes apps": DeliveryMethod.KUBERNETES,
        "Other": DeliveryMethod.OTHER,
    }

    name = "scaleway-marketplace"
    catalogue_url: ClassVar[str] = "https://www.scaleway.com/en/marketplace/catalog/"

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
            slug, text = self._as_text(fields.get("slug")), self._as_text(fields.get(label))
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
        slugs = filters.get("categories")
        return [slug for slug in (self._as_text(value) for value in slugs) if slug] if isinstance(slugs, list) else []

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
        props = self._as_object(self._as_object(self._next_data(response).get("props")).get("pageProps"))
        apps = props.get("allApps")
        if not isinstance(apps, list):
            self.logger.error("The %s page %s data has no applications list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the page data has no applications list")
        vendors = self._labels(self._as_object(props.get("allFilters")).get("vendors"), "name")
        side_nav = self._as_object(self._as_object(props.get("navigation")).get("sideNav"))
        categories = self._labels(side_nav.get("category_pages"), "title")
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
            name, slug = self._as_text(app.get("title")), self._as_text(app.get("slug"))
            filters = self._as_object(app.get("filters"))
            slugs = self._category_slugs(filters)
            if excluded := sorted(self.EXCLUDED_CATEGORIES.intersection(slugs)):
                self.logger.debug("Skipping the %s application %r, category %s.", self.name, name, ", ".join(excluded))
                continue
            vendor = self._as_text(filters.get("vendor"))
            software = self._build_software(
                name,
                self._as_text(app.get("description")),
                f"{self.catalogue_url}{slug}/" if slug else None,
                vendors.get(vendor, vendor) if vendor else None,
                self.DELIVERIES.get(self._as_text(app.get("deliveryMethod")) or "", DeliveryMethod.OTHER),
                [categories.get(category, category) for category in slugs],
            )
            if software is not None:
                yield software
