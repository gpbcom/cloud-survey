from __future__ import annotations

# Standard Library Imports.
from pathlib import Path
from typing import ClassVar, Dict, FrozenSet, Iterator, List, Optional, Union
from urllib.parse import urljoin

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.cloudru.enums import CloudRuCatalogueTab, CloudRuProductField
from crawler.cloud.next_flight_data import NextFlightData
from crawler.exception import CatalogueFormatError
from models.cloud.products.product import CloudProduct


class CloudRuCrawler(BaseCloudCrawler):
    """Cloud.ru (formerly SberCloud) catalogue crawler.

    Attributes:
        SITE_URL (ClassVar[str]): The website root, the product links being relative to it.
        PRODUCT_PATH (ClassVar[str]): The path of a product page, filled with the product slug.
        MARKETING_CATEGORIES (ClassVar[FrozenSet[CloudRuCatalogueTab]]): The slugs of the catalogue tabs which are
            selections, not categories (`Популярное`).
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The services catalogue page.
        flight (NextFlightData): The reader of the Next.js flight data of the pages.

    Notes:
        The https://cloud.ru/products page is rendered by the Next.js App Router (no `__NEXT_DATA__` script): its
        product grid is drawn in the browser from the flight data of the page (see `NextFlightData`), which
        holds the whole catalogue in an object with a `categories` list (the catalogue tabs) and a `products` list.
        Each product gives its name (`title`), its description, its page (`customLink`, else
        `/products/<slug>`) and its tabs (`categories`, e.g. `Инфраструктура`), kept as written (in Russian). The
        `Популярное` tab is a selection of products, not a category: it is left out. The catalogue taxonomy is flat
        (no sub-category). The cloud platform of each product (`productPlatforms`: Evolution, Advanced,
        Облако VMware) is another filter of the page, already part of most product names: it is not a category. A
        product listed several times gets the categories of all its entries. The products marked unavailable are
        skipped. The page gives no date, and the sitemap dates every page with its generation day: the products are
        not dated.
    """

    SITE_URL: ClassVar[str] = "https://cloud.ru/"
    PRODUCT_PATH: ClassVar[str] = "/products/{slug}"
    MARKETING_CATEGORIES: ClassVar[FrozenSet[CloudRuCatalogueTab]] = frozenset({CloudRuCatalogueTab.POPULAR})

    name = "cloudru"
    catalogue_url: ClassVar[str] = "https://cloud.ru/products"

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.flight = NextFlightData(self.name, self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _catalogue(self, response: Response) -> List[JsonValue]:
        """Read the products of the catalogue held by the flight data of the page.

        Args:
            response (Response): The catalogue page.

        Returns:
            List[JsonValue]: The raw products, in the order of the catalogue.

        Raises:
            CatalogueFormatError: If the flight data holds no catalogue.
        """
        catalogue = self.flight.find(
            self.flight.documents(response), CloudRuProductField.PRODUCTS, CloudRuProductField.CATEGORIES
        )
        if catalogue is None:
            self.logger.error("The %s page %s holds no products catalogue.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the flight data holds no products catalogue")
        products = catalogue.get(CloudRuProductField.PRODUCTS)
        listed = products if isinstance(products, list) else []
        self.logger.debug("%d products in the %s catalogue of %s.", len(listed), self.name, response.url)
        return listed

    def _categories(self, product: Dict[str, JsonValue]) -> List[str]:
        """Read the catalogue tabs a product is filed under, without the selections.

        Args:
            product (Dict[str, JsonValue]): The raw product.

        Returns:
            List[str]: The category labels, as written on the website, in order.
        """
        categories = product.get(CloudRuProductField.CATEGORIES)
        labels: List[str] = []
        for category in categories if isinstance(categories, list) else []:
            fields = self._as_object(category)
            if self._as_text(fields.get(CloudRuProductField.SLUG)) in self.MARKETING_CATEGORIES:
                continue
            if label := self._as_text(fields.get(CloudRuProductField.TITLE)):
                labels.append(label)
        return labels

    def _product_url(self, product: Dict[str, JsonValue]) -> Optional[str]:
        """Get the absolute page URL of a product.

        Args:
            product (Dict[str, JsonValue]): The raw product.

        Returns:
            Optional[str]: Its custom link, else its `/products/<slug>` page, `None` without either.
        """
        link = (self._as_text(product.get(CloudRuProductField.CUSTOM_LINK)) or "").strip()
        slug = (self._as_text(product.get(CloudRuProductField.SLUG)) or "").strip()
        if not link and slug:
            link = self.PRODUCT_PATH.format(slug=slug)
        return urljoin(self.SITE_URL, link) if link else None

    def _product(self, value: JsonValue) -> Optional[CloudProduct]:
        """Build the product of a catalogue entry.

        Args:
            value (JsonValue): The raw product.

        Returns:
            Optional[CloudProduct]: The product, `None` for an unavailable or invalid entry (logged).
        """
        product = self._as_object(value)
        name = self._as_text(product.get(CloudRuProductField.TITLE))
        if product.get(CloudRuProductField.AVAILABLE) is False:
            self.logger.debug("Skipping the %s product %r, marked unavailable.", self.name, name)
            return None
        return self._build_product(
            name,
            self._as_text(product.get(CloudRuProductField.DESCRIPTION)),
            self._product_url(product),
            categories=self._categories(product),
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the catalogue, filed under their catalogue tabs.

        Args:
            response (Response): The catalogue page.

        Yields:
            Iterator[CloudProduct]: Each valid product, once, with the categories of all its entries.
        """
        products = [product for product in map(self._product, self._catalogue(response)) if product]
        yield from self._merge_categories(products)
