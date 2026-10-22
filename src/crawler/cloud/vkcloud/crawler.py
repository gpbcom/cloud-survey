from __future__ import annotations

# Standard Library Imports.
from pathlib import Path
from typing import ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.next_flight_data import NextFlightData
from crawler.cloud.vkcloud.enums import VkCloudCmsComponent, VkCloudCmsField, VkCloudHost
from models.cloud.products.product import CloudProduct


class VKCloudCrawler(BaseCloudCrawler):
    """VK Cloud (formerly Mail.ru Cloud Solutions) catalogue crawler.

    Attributes:
        MENU_COMPONENT (ClassVar[VkCloudCmsComponent]): The CMS component of the products menu of the page header.
        MENU_LISTS (ClassVar[Tuple[VkCloudCmsField, ...]]): The lists of products of a products menu group.
        LEGACY_HOSTS (ClassVar[FrozenSet[VkCloudHost]]): The former hosts of the website, redirected to the current
            one.
        SITE_HOST (ClassVar[VkCloudHost]): The current host of the website.
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The services catalogue page.
        dates_sitemaps (ClassVar[Tuple[str, ...]]): The sitemap dating the product pages.
        name_prefixes (ClassVar[Tuple[str, ...]]): The brand prefixes ignored when comparing product names.
        flight (NextFlightData): The reader of the Next.js flight data of the pages.

    Notes:
        The website moved from cloud.vk.com to cloud.vk.ru. Its English version (https://cloud.vk.ru/en/) is a
        single page showing a dozen products, the Russian one is the complete catalogue: the source is the
        https://cloud.vk.ru/cloud-platform/ page, listing all the services and solutions. It is a Next.js application
        whose CMS data is embedded in the page as flight data (`self.__next_f.push` scripts): the catalogue
        (`catalog.items`) lists its groups (e.g. `Вычисления`), each listing its services with their card title,
        description (`service.text`) and page (`service.url.url`). The products menu of the page header
        (`header.header-menu` component) is read too: its groups (e.g. `Data-платформа`) list a few products the
        catalogue does not (e.g. Cloud Streams, Cloud Flink, Registry). A product is filed under every group listing
        it, the catalogue ones first, and gets the name and description of its first listing. The listings of a
        product are matched by name or by page, e.g. the catalogue `Load Balancer` and the menu `Load Balancing`.
        The groups are flat: each listing gives one category. The links to the former host are rewritten to the
        current one, so that the product pages are dated by the sitemap.
    """

    MENU_COMPONENT: ClassVar[VkCloudCmsComponent] = VkCloudCmsComponent.HEADER_MENU
    MENU_LISTS: ClassVar[Tuple[VkCloudCmsField, ...]] = (VkCloudCmsField.DROPDOWN, VkCloudCmsField.DROPDOWN_ITEMS)
    LEGACY_HOSTS: ClassVar[FrozenSet[VkCloudHost]] = frozenset({VkCloudHost.LEGACY, VkCloudHost.LEGACY_WWW})
    SITE_HOST: ClassVar[VkCloudHost] = VkCloudHost.CURRENT

    name = "vkcloud"
    catalogue_url: ClassVar[str] = "https://cloud.vk.ru/cloud-platform/"
    dates_sitemaps: ClassVar[Tuple[str, ...]] = ("https://cloud.vk.ru/sitemap.xml",)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("VK Cloud ", "VK ")

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

    def _link(self, value: JsonValue, response: Response) -> Optional[str]:
        """Read the absolute page URL of a CMS link object (`{url: "/cloud-servers/", ...}`).

        Args:
            value (JsonValue): The link object.
            response (Response): The page, against which the relative links are resolved.

        Returns:
            Optional[str]: The URL on the current host of the website, `None` when the link has none.
        """
        href = self._as_text(self._as_object(value).get(VkCloudCmsField.URL))
        if not href or not href.strip():
            return None
        link = urlparse(urljoin(response.url, href.strip()))
        if link.netloc in self.LEGACY_HOSTS:
            self.logger.debug("Moving the %s link %s to the host %s.", self.name, link.geturl(), self.SITE_HOST)
            link = link._replace(netloc=self.SITE_HOST)
        return link.geturl()

    def _items(self, holder: Dict[str, JsonValue]) -> List[Dict[str, JsonValue]]:
        """Read the `items` list of a CMS object, e.g. the groups of the catalogue.

        Args:
            holder (Dict[str, JsonValue]): The CMS object.

        Returns:
            List[Dict[str, JsonValue]]: The items (those which are not objects are empty),
                empty without a list.
        """
        items = holder.get(VkCloudCmsField.ITEMS)
        return [self._as_object(item) for item in items] if isinstance(items, list) else []

    def _catalogue_groups(self, rows: List[JsonValue]) -> List[Dict[str, JsonValue]]:
        """Find the groups of the services catalogue (`catalog.items`) in the flight data.

        Args:
            rows (List[JsonValue]): The flight data rows.

        Returns:
            List[Dict[str, JsonValue]]: The groups of the first catalogue listing some, empty without catalogue.
        """
        for row in rows:
            for candidate in self._walk_objects(row):
                if groups := self._items(self._as_object(candidate.get(VkCloudCmsField.CATALOG))):
                    return groups
        return []

    def _menu_groups(self, rows: List[JsonValue]) -> List[Dict[str, JsonValue]]:
        """Find the groups of the products menu (`header.header-menu` component) in the flight data.

        Args:
            rows (List[JsonValue]): The flight data rows.

        Returns:
            List[Dict[str, JsonValue]]: The groups of the first products menu listing some, empty without menu.

        Notes:
            The page data repeats the header: only its first occurrence is read.
        """
        for row in rows:
            for candidate in self._walk_objects(row):
                if candidate.get(VkCloudCmsField.COMPONENT) == self.MENU_COMPONENT and (
                    groups := self._items(candidate)
                ):
                    return groups
        return []

    def _catalogue_products(self, rows: List[JsonValue], response: Response) -> List[CloudProduct]:
        """Extract the services of the catalogue, filed under their group, an occurrence per listing.

        Args:
            rows (List[JsonValue]): The flight data rows of the catalogue page.
            response (Response): The catalogue page.

        Returns:
            List[CloudProduct]: The valid services, in the catalogue order.
        """
        groups = self._catalogue_groups(rows)
        if not groups:
            self.logger.warning("The %s page %s holds no services catalogue.", self.name, response.url)
        products: List[CloudProduct] = []
        for group in groups:
            title = self._as_text(group.get(VkCloudCmsField.TITLE))
            services = group.get(VkCloudCmsField.SERVICES)
            for entry in services if isinstance(services, list) else []:
                card = self._as_object(entry)
                service = self._as_object(card.get(VkCloudCmsField.SERVICE))
                product = self._build_product(
                    self._as_text(card.get(VkCloudCmsField.TITLE)) or self._as_text(service.get(VkCloudCmsField.TITLE)),
                    self._as_text(service.get(VkCloudCmsField.TEXT)),
                    self._link(service.get(VkCloudCmsField.URL), response),
                    categories=[title],
                )
                if product is not None:
                    products.append(product)
        self.logger.info("%d %s catalogue listings in %d groups.", len(products), self.name, len(groups))
        return products

    def _menu_products(self, rows: List[JsonValue], response: Response) -> List[CloudProduct]:
        """Extract the products of the products menu, filed under their group, an occurrence per listing.

        Args:
            rows (List[JsonValue]): The flight data rows of the catalogue page.
            response (Response): The catalogue page.

        Returns:
            List[CloudProduct]: The valid products, in the menu order.
        """
        groups = self._menu_groups(rows)
        if not groups:
            self.logger.warning("The %s page %s has no products menu.", self.name, response.url)
        products: List[CloudProduct] = []
        for group in groups:
            title = self._as_text(group.get(VkCloudCmsField.TITLE))
            for key in self.MENU_LISTS:
                entries = group.get(key)
                for entry in entries if isinstance(entries, list) else []:
                    link = self._as_object(entry)
                    product = self._build_product(
                        self._as_text(link.get(VkCloudCmsField.TITLE)),
                        self._as_text(link.get(VkCloudCmsField.TEXT)),
                        self._link(link.get(VkCloudCmsField.URL), response),
                        categories=[title],
                    )
                    if product is not None:
                        products.append(product)
        self.logger.info("%d %s products menu listings in %d groups.", len(products), self.name, len(groups))
        return products

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the services catalogue and of the products menu.

        Args:
            response (Response): The catalogue page.

        Returns:
            Iterator[CloudProduct]: Each valid product once, with the groups of all its listings.
        """
        rows = self.flight.rows(response)
        listings = [*self._catalogue_products(rows, response), *self._menu_products(rows, response)]
        return iter(self._merge_categories(listings))
