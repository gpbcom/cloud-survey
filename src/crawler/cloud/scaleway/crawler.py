from __future__ import annotations

# Standard Library Imports.
import re
from datetime import datetime
from typing import ClassVar, Dict, FrozenSet, Iterable, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import urljoin

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.scaleway.enums import (
    ScalewayBlockField,
    ScalewayCmsComponent,
    ScalewayEntryField,
    ScalewayLinkField,
    ScalewayMenuGroup,
    ScalewayNextDataField,
    ScalewayPageField,
)
from models.cloud.enums import DateCaveat
from models.cloud.products.product import CloudProduct


class ScalewayCrawler(BaseCloudCrawler):
    """Scaleway catalogue crawler.

    Attributes:
        PRODUCTS_BLOCK (ClassVar[ScalewayCmsComponent]): The page block type listing the products of a category.
        SITE_URL (ClassVar[str]): The website root, the menu links being relative to it.
        MENU_GROUPS (ClassVar[FrozenSet[ScalewayMenuGroup]]): The header menu groups listing products.
        NOT_PRODUCT (ClassVar[re.Pattern[str]]): The header menu entries which are not products.
        DATE_CAVEATS (ClassVar[Tuple[DateCaveat, DateCaveat]]): The caveats of the added and updated dates.

    Notes:
        It reads the Next.js data of the https://www.scaleway.com/en/all-products/ page, as the class names of the
        rendered page are generated: the product columns of the page first, then the products of the header menu
        missing from them (same page, no extra request). A product is dated by its website page record: its creation
        (`link.page.createdAt`, often the date of the CMS migration rather than of the launch) and its last update
        (`link.page.updatedAt`), both with a caveat. A link to a URL without website page (`page: null`) gives no
        date. A product of the columns is filed under the column title (e.g. `Containers`), a product of the menu
        under its groups (e.g. `AI` then `Clusters`).
    """

    PRODUCTS_BLOCK: ClassVar[ScalewayCmsComponent] = ScalewayCmsComponent.GENERIC_COLUMNS
    DATE_CAVEATS: ClassVar[Tuple[DateCaveat, DateCaveat]] = (DateCaveat.WEBSITE_RECORD, DateCaveat.PAGE_MODIFIED)
    SITE_URL: ClassVar[str] = "https://www.scaleway.com/en/"
    MENU_GROUPS: ClassVar[FrozenSet[ScalewayMenuGroup]] = frozenset(
        {ScalewayMenuGroup.AI, ScalewayMenuGroup.CLOUD, ScalewayMenuGroup.BARE_METAL}
    )
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
        page = self._as_object(fields.get(ScalewayLinkField.PAGE))
        url = self._as_text(fields.get(ScalewayLinkField.URL)) or self._as_text(page.get(ScalewayPageField.PATH))
        return urljoin(self.SITE_URL, url.lstrip("/")) if url else None

    def _link_dates(self, link: JsonValue, name: Optional[str]) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Get the creation and the last update of the website page of a link.

        Args:
            link (JsonValue): The link data.
            name (Optional[str]): The product of the link, for the logs.

        Returns:
            Tuple[Optional[datetime], Optional[datetime]]: The page `createdAt` and `updatedAt`, `None` without
                website page or when unreadable.

        Notes:
            Both are dates of the website's page record (`WEBSITE_RECORD` and `PAGE_MODIFIED` caveats): many records
            were created by a migration of the website, long after the product launch.
        """
        page = self._as_object(self._as_object(link).get(ScalewayLinkField.PAGE))
        created = self._parse_date(page.get(ScalewayPageField.CREATED_AT), name)
        return created, self._parse_date(page.get(ScalewayPageField.UPDATED_AT), name)

    def _categories(self, labels: Sequence[Optional[str]], name: Optional[str]) -> List[str]:
        """Clean the categories of a product: blank, repeated (case-insensitive) labels and its own name dropped.

        Args:
            labels (Sequence[Optional[str]]): The category labels, top level first.
            name (Optional[str]): The product name, e.g. `Serverless Jobs` for the menu group of the same name.

        Returns:
            List[str]: The category labels, in order.
        """
        categories: List[str] = []
        known = {self._clean_text(name).casefold()}
        for label in labels:
            text = self._clean_text(label)
            if text and text.casefold() not in known:
                categories.append(text)
                known.add(text.casefold())
        return categories

    def _merge_entries(
        self, entries: Iterable[Tuple[Optional[str], Optional[str], JsonValue, List[str]]]
    ) -> List[Tuple[Optional[str], Optional[str], JsonValue, List[str]]]:
        """Merge the entries of a product listed several times, gathering all its categories.

        Args:
            entries (Iterable[Tuple[Optional[str], Optional[str], JsonValue, List[str]]]): The name, description,
                link and categories of each entry, in order.

        Returns:
            List[Tuple[Optional[str], Optional[str], JsonValue, List[str]]]: The first entry of each product, with
                the categories of all its entries.

        Notes:
            The entries of a product are matched by name or by URL, as the streamed products are.
        """
        merged: List[Tuple[Optional[str], Optional[str], JsonValue, List[str]]] = []
        positions: Dict[str, int] = {}
        for name, description, link, categories in entries:
            url = self._link_url(link)
            keys = [f"name:{self._name_key(name or '')}"] + ([f"url:{self._url_key(url)}"] if url else [])
            position = next((positions[key] for key in keys if key in positions), None)
            if position is None:
                position = len(merged)
                merged.append((name, description, link, self._categories(categories, name)))
            else:
                first = merged[position]
                self.logger.debug("Product %r listed again, under %s.", name, categories)
                merged[position] = (*first[:3], self._categories([*first[3], *categories], first[0]))
            positions.update(dict.fromkeys(keys, position))
        return merged

    def _product(
        self, name: Optional[str], description: Optional[str], link: JsonValue, categories: List[str]
    ) -> Optional[CloudProduct]:
        """Build the product of a catalogue entry, dated by its website page record.

        Args:
            name (Optional[str]): The product name.
            description (Optional[str]): The product description.
            link (JsonValue): The link data.
            categories (List[str]): The categories of the product.

        Returns:
            Optional[CloudProduct]: The product, `None` (logged) when the entry is invalid.
        """
        added_at, updated_at = self._link_dates(link, name)
        url, (added_caveat, updated_caveat) = self._link_url(link), self.DATE_CAVEATS
        return self._build_product(
            name, description, url, added_at, updated_at, added_caveat, updated_caveat, categories=categories
        )

    def _columns_entries(self, data: JsonValue) -> Iterator[Tuple[Optional[str], Optional[str], JsonValue, List[str]]]:
        """Read the entries of the page columns, filed under the title of their column.

        Args:
            data (JsonValue): The page data.

        Yields:
            Tuple[Optional[str], Optional[str], JsonValue, List[str]]: The name, description, link and category of
                each entry of the columns.
        """
        for block in self._walk_objects(data):
            if block.get(ScalewayBlockField.COMPONENT) != self.PRODUCTS_BLOCK:
                continue
            items = block.get(ScalewayBlockField.ITEMS)
            if not isinstance(items, list):
                self.logger.warning(
                    "Skipping the %r products block without items list.", block.get(ScalewayBlockField.TITLE)
                )
                continue
            title = self._as_text(block.get(ScalewayBlockField.TITLE))
            self.logger.debug("Products block %r: %d items.", title, len(items))
            for item in items:
                fields = self._as_object(item)
                name = self._as_text(fields.get(ScalewayEntryField.TITLE))
                description = self._as_text(fields.get(ScalewayEntryField.DESCRIPTION))
                yield name, description, fields.get(ScalewayEntryField.LINK), [title] if title else []

    def _menu_leaves(self, value: JsonValue, path: Tuple[str, ...] = ()) -> Iterator[Tuple[JsonValue, Tuple[str, ...]]]:
        """Walk the header menu entries without children, with the names of their groups.

        Args:
            value (JsonValue): A header menu entry.
            path (Tuple[str, ...]): The names of the groups above the entry, top level first.

        Yields:
            Tuple[JsonValue, Tuple[str, ...]]: Each entry without children and the names of its groups.
        """
        children = self._as_object(value).get(ScalewayEntryField.CHILDREN)
        if isinstance(children, list) and children:
            group = self._clean_text(self._as_text(self._as_object(value).get(ScalewayEntryField.GROUP_NAME)))
            for child in children:
                yield from self._menu_leaves(child, (*path, group))
        else:
            yield value, path

    def _menu_entries(self, data: JsonValue) -> Iterator[Tuple[Optional[str], Optional[str], JsonValue, List[str]]]:
        """Read the product entries of the header menu product groups, filed under their groups.

        Args:
            data (JsonValue): The page data.

        Yields:
            Tuple[Optional[str], Optional[str], JsonValue, List[str]]: The name, description, link and categories
                (top level group first) of each product entry of the menu.
        """
        props = self._as_object(self._as_object(data).get(ScalewayNextDataField.PROPS))
        header = self._as_object(props.get(ScalewayNextDataField.PAGE_PROPS)).get(ScalewayNextDataField.HEADER)
        groups = self._as_object(header).get(ScalewayNextDataField.MAIN_NAVIGATION_ITEMS)
        for group in groups if isinstance(groups, list) else []:
            if self._as_text(self._as_object(group).get(ScalewayEntryField.GROUP_NAME)) not in self.MENU_GROUPS:
                continue
            for leaf, path in self._menu_leaves(group):
                fields = self._as_object(leaf)
                name = self._as_text(fields.get(ScalewayEntryField.GROUP_NAME))
                description = self._as_text(fields.get(ScalewayEntryField.DESCRIPTION))
                if not (description or "").strip() or self.NOT_PRODUCT.search(name or ""):
                    self.logger.debug("Skipping the header menu entry %r, not a product.", name)
                    continue
                yield name, description, fields.get(ScalewayEntryField.LINK), list(path)

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the page columns, then of the header menu, with their categories.

        Args:
            response (Response): The catalogue page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the page.

        Notes:
            A product listed in several columns is filed under all their titles, and a product listed in several
            menu groups under all of them. A product of the columns keeps their categories: its menu entries are
            then duplicates, skipped when streamed.
        """
        data = self._next_data(response)
        for entries in (self._columns_entries(data), self._menu_entries(data)):
            for name, description, link, categories in self._merge_entries(entries):
                if product := self._product(name, description, link, categories):
                    yield product
