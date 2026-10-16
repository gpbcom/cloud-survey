from __future__ import annotations

# Standard Library Imports.
import re
from datetime import datetime
from typing import ClassVar, FrozenSet, Iterator, Optional, Tuple
from urllib.parse import urljoin

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from models.cloud.product import CloudProduct


class ScalewayCrawler(BaseCloudCrawler):
    """Scaleway catalogue crawler.

    Attributes:
        PRODUCTS_BLOCK (ClassVar[str]): The page block type listing the products of a category.
        SITE_URL (ClassVar[str]): The website root, the menu links being relative to it.
        MENU_GROUPS (ClassVar[FrozenSet[str]]): The header menu groups listing products.
        NOT_PRODUCT (ClassVar[re.Pattern[str]]): The header menu entries which are not products.

    Notes:
        It reads the Next.js data of the https://www.scaleway.com/en/all-products/ page, as the class names of the
        rendered page are generated: the product columns of the page first, then the products of the header menu
        missing from them (same page, no extra request). A product is dated by the last update of its website page
        (`link.page.updatedAt`), not added: the page `createdAt` is the date of the CMS migration, not of the product
        launch. A link to a URL without website page (`page: null`) gives no date.
    """

    PRODUCTS_BLOCK: ClassVar[str] = "blocks.generic-columns"
    SITE_URL: ClassVar[str] = "https://www.scaleway.com/en/"
    MENU_GROUPS: ClassVar[FrozenSet[str]] = frozenset({"AI", "Cloud", "Bare Metal"})
    NOT_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(r"^Compare our|Program$", re.IGNORECASE)

    name = "scaleway"
    catalogue_url: ClassVar[str] = "https://www.scaleway.com/en/all-products/"
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Scaleway ",)

    ############################
    # Internal Helpers Methods #
    ############################

    def _link_url(self, link: JsonValue) -> Optional[str]:
        """Get the absolute URL of a page link, which holds either a URL or a website page path.

        Args:
            link (JsonValue): The link data.

        Returns:
            Optional[str]: The absolute URL, `None` without link.
        """
        fields = self._as_object(link)
        url = self._as_text(fields.get("url")) or self._as_text(self._as_object(fields.get("page")).get("path"))
        return urljoin(self.SITE_URL, url.lstrip("/")) if url else None

    def _link_updated(self, link: JsonValue, name: Optional[str]) -> Optional[datetime]:
        """Get the last update of the website page of a link.

        Args:
            link (JsonValue): The link data.
            name (Optional[str]): The product of the link, for the logs.

        Returns:
            Optional[datetime]: The page `updatedAt`, `None` without website page or when unreadable.
        """
        return self._parse_date(self._as_object(self._as_object(link).get("page")).get("updatedAt"), name)

    def _columns_products(self, data: JsonValue) -> Iterator[CloudProduct]:
        """Extract the products of the page columns.

        Args:
            data (JsonValue): The page data.

        Yields:
            Iterator[CloudProduct]: Each valid product of the columns.
        """
        for block in self._walk_objects(data):
            if block.get("__component") != self.PRODUCTS_BLOCK:
                continue
            items = block.get("items")
            if not isinstance(items, list):
                self.logger.warning("Skipping the %r products block without items list.", block.get("title"))
                continue
            self.logger.debug("Products block %r: %d items.", block.get("title"), len(items))
            for item in items:
                fields = self._as_object(item)
                name, description = self._as_text(fields.get("title")), self._as_text(fields.get("description"))
                link = fields.get("link")
                updated_at = self._link_updated(link, name)
                if product := self._build_product(name, description, self._link_url(link), updated_at=updated_at):
                    yield product

    def _menu_leaves(self, value: JsonValue) -> Iterator[JsonValue]:
        """Walk the header menu entries without children.

        Args:
            value (JsonValue): A header menu entry.

        Yields:
            JsonValue: Each entry without children.
        """
        children = self._as_object(value).get("children")
        if isinstance(children, list) and children:
            for child in children:
                yield from self._menu_leaves(child)
        else:
            yield value

    def _menu_products(self, data: JsonValue) -> Iterator[CloudProduct]:
        """Extract the products of the header menu product groups.

        Args:
            data (JsonValue): The page data.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menu.
        """
        header = self._as_object(self._as_object(self._as_object(data).get("props")).get("pageProps")).get("header")
        groups = self._as_object(header).get("mainNavigationItems")
        for group in groups if isinstance(groups, list) else []:
            if self._as_text(self._as_object(group).get("groupName")) not in self.MENU_GROUPS:
                continue
            for leaf in self._menu_leaves(group):
                fields = self._as_object(leaf)
                name, description = self._as_text(fields.get("groupName")), self._as_text(fields.get("description"))
                if not (description or "").strip() or self.NOT_PRODUCT.search(name or ""):
                    self.logger.debug("Skipping the header menu entry %r, not a product.", name)
                    continue
                link = fields.get("link")
                updated_at = self._link_updated(link, name)
                if product := self._build_product(name, description, self._link_url(link), updated_at=updated_at):
                    yield product

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the page columns, then of the header menu.

        Args:
            response (Response): The catalogue page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the page.
        """
        data = self._next_data(response)
        yield from self._columns_products(data)
        yield from self._menu_products(data)
