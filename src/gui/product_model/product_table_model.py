from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger
from typing import ClassVar, Dict, List, Optional, Union

# Third Party Imports.
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon

# First Party Imports.
from gui.paging.page.paged_table_model import ModelIndex, PagedTableModel
from gui.product_model.product_row import ProductRow
from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.cloud.products.product import CloudProduct
from models.storage.enums import ItemSort
from models.storage.pages.item_query import ItemQuery
from models.storage.pages.page import Page
from models.storage.pages.stored_item import StoredItem
from storage.storage import Storage

CellData = Optional[Union[str, QColor, QIcon, QFont]]


class ProductTableModel(PagedTableModel[CloudProduct, ProductRow]):
    """Table of the stored products, read page by page (see `PagedTableModel`), the deleted ones struck through.

    Attributes:
        PROVIDER (ClassVar[int]): The provider column.
        COUNTRY (ClassVar[int]): The provider country column, with its flag.
        NAME (ClassVar[int]): The product name column.
        CATEGORIES (ClassVar[int]): The column of the categories of the unified taxonomy.
        LABELS (ClassVar[int]): The column of the categories of the catalogue of the provider (source labels), in
            English.
        DESCRIPTION (ClassVar[int]): The product description column.
        ADDED (ClassVar[int]): The column of the date the product was added.
        UPDATED (ClassVar[int]): The column of the date the product was last updated.
        HEADERS (ClassVar[List[str]]): The columns headers.
        LOADING (ClassVar[str]): The text of a row being read.
        SORTS (ClassVar[Dict[int, ItemSort]]): The order of each sortable column.
        theme (Theme): The application theme, for the provider colours and the country flags.
        deleted_font (QFont): The struck through font of the deleted rows.
        warning_icon (QIcon): The icon of the approximate dates.
        crawled_at (Dict[CloudProvider, datetime]): When each catalogue was last crawled.
        taxonomy (TaxonomyCache): The names of the categories and of the source labels.
    """

    PROVIDER: ClassVar[int] = 0
    COUNTRY: ClassVar[int] = 1
    NAME: ClassVar[int] = 2
    CATEGORIES: ClassVar[int] = 3
    LABELS: ClassVar[int] = 4
    DESCRIPTION: ClassVar[int] = 5
    ADDED: ClassVar[int] = 6
    UPDATED: ClassVar[int] = 7
    HEADERS: ClassVar[List[str]] = [
        "Provider",
        "Country",
        "Product",
        "Categories",
        "Source labels",
        "Description",
        "Added",
        "Updated",
    ]
    LOADING: ClassVar[str] = "Loading\u2026"
    SORTS: ClassVar[Dict[int, ItemSort]] = {
        PROVIDER: ItemSort.PROVIDER,
        COUNTRY: ItemSort.PROVIDER,
        NAME: ItemSort.NAME,
        ADDED: ItemSort.ADDED_AT,
        UPDATED: ItemSort.UPDATED_AT,
    }

    def __init__(
        self,
        theme: Theme,
        loop: StorageLoop,
        logger: Optional[Logger] = None,
        taxonomy: Optional[TaxonomyCache] = None,
    ) -> None:
        """Initialize an empty table, read when its query is set.

        Args:
            theme (Theme): The application theme, for the provider colours.
            loop (StorageLoop): The storage thread of the GUI.
            logger (Optional[Logger]): The model logger.
            taxonomy (Optional[TaxonomyCache]): The names of the categories, those of the seed by default.
        """
        super().__init__(loop, self._list, self._row)
        self.theme = theme
        self.taxonomy = taxonomy if taxonomy else TaxonomyCache()
        self.taxonomy.changed.connect(self._on_taxonomy_changed)
        self.deleted_font = QFont()
        self.deleted_font.setStrikeOut(True)
        self.warning_icon = theme.warning_icon()
        self.crawled_at: Dict[CloudProvider, datetime] = {}
        self.logger.debug("Product table ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _list(self, storage: Storage, query: ItemQuery) -> Page[CloudProduct]:  # noqa: E501
        """Read a page of products (storage thread).

        Args:
            storage (Storage): The open storage.
            query (ItemQuery): The page.

        Returns:
            Page[CloudProduct]: The products of the page.
        """
        self.logger.debug("Reading %d products from %d.", query.limit, query.offset)  # noqa: E501
        return await storage.catalogues.list(query)

    def _row(self, stored: StoredItem[CloudProduct]) -> ProductRow:
        """Build the row of a stored product.

        Args:
            stored (StoredItem[CloudProduct]): The stored product.

        Returns:
            ProductRow: Its row, with the crawl date of its catalogue.
        """
        crawled_at = self.crawled_at.get(stored.provider)
        return ProductRow(provider=stored.provider, product=stored.item, crawled_at=crawled_at, id=stored.id)  # noqa: E501

    def _text(self, row: ProductRow, column: int) -> str:
        """Get the text of a cell.

        Args:
            row (ProductRow): The row.
            column (int): The column.

        Returns:
            str: The cell text.
        """
        product = row.product
        match column:
            case self.PROVIDER:
                return self.theme.provider_label(row.provider)
            case self.COUNTRY:
                return self.theme.country_label(row.provider.country)
            case self.NAME:
                return product.name
            case self.CATEGORIES:
                return self.taxonomy.names(product.service_categories)
            case self.LABELS:
                return self.taxonomy.label_names(product.source_label_ids, product.catalogue_categories)
            case self.DESCRIPTION:
                return product.description
            case self.ADDED:
                return self.theme.date_label(product.added_at, product.added_caveat)
            case _:
                return self.theme.date_label(product.updated_at, product.updated_caveat)

    def _tooltip(self, row: ProductRow, column: int) -> str:
        """Get the tooltip of a cell: the dates explained, the deletion of a deleted product, else the text.

        Args:
            row (ProductRow): The row.
            column (int): The column.

        Returns:
            str: The cell tooltip.
        """
        product = row.product
        match column:
            case self.ADDED:
                return (
                    f"Added: {self.theme.date_description(product.added_at, product.added_from, product.added_caveat)}"  # noqa: E501
                )
            case self.UPDATED:
                updated = self.theme.date_description(product.updated_at, product.updated_from, product.updated_caveat)  # noqa: E501
                return f"Updated: {updated}"
            case self.NAME if product.deleted_at:
                return f"{product.name}\nDeleted: {self.theme.date_description(product.deleted_at)}"
            case self.CATEGORIES:  
                return "\n".join(self.taxonomy.path(slug) for slug in product.service_categories)  # noqa: E501
            case self.LABELS:
                return ", ".join(product.catalogue_categories)
            case _:
                return self._text(row, column)

    def _caveat(self, row: ProductRow, column: int) -> bool:
        """Tell whether a cell shows an approximate date.

        Args:
            row (ProductRow): The row.
            column (int): The column.

        Returns:
            bool: Whether the added or updated date of the cell has a caveat.
        """
        product = row.product
        return bool({self.ADDED: product.added_caveat, self.UPDATED: product.updated_caveat}.get(column))  # noqa: E501

    def _foreground(self, row: ProductRow, column: int) -> Optional[QColor]:
        """Get the text colour of a cell: muted when deleted, warning for an approximate date, else the provider's.

        Args:
            row (ProductRow): The row.
            column (int): The column.

        Returns:
            Optional[QColor]: The colour, `None` for the default one.
        """
        if row.product.is_deleted:
            return QColor(self.theme.TEXT_MUTED)
        if self._caveat(row, column):
            return QColor(self.theme.WARNING)
        return self.theme.provider_color(row.provider) if column == self.PROVIDER else None  # noqa: E501

    def _decoration(self, row: ProductRow, column: int) -> Optional[QIcon]:
        """Get the icon of a cell: the warning of an approximate date, the provider icon or the country flag.

        Args:
            row (ProductRow): The row.
            column (int): The column.

        Returns:
            Optional[QIcon]: The icon, `None` without one.
        """
        if self._caveat(row, column):
            return self.warning_icon
        if column == self.PROVIDER:
            return self.theme.provider_icon(row.provider)
        return self.theme.flag_icon(row.provider.country) if column == self.COUNTRY else None  # noqa: E501

    def _on_taxonomy_changed(self) -> None:
        """Show the names read again in the category and label columns."""
        rows = self.rowCount()
        if rows:
            self.logger.debug("Category names of %d products rows refreshed.", rows)
            self.dataChanged.emit(self.index(0, self.CATEGORIES), self.index(rows - 1, self.LABELS))  # noqa: E501

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_crawl_dates(self, crawled_at: Dict[CloudProvider, datetime]) -> None:  # noqa: E501
        """Set when each catalogue was last crawled, shown with the next rows read.

        Args:
            crawled_at (Dict[CloudProvider, datetime]): The last crawl of each stored catalogue.
        """
        self.logger.debug("Crawl dates of %d catalogues set.", len(crawled_at))
        self.crawled_at = dict(crawled_at)

    def columnCount(self, parent: Optional[ModelIndex] = None) -> int:
        """Get the number of columns (Qt override).

        Args:
            parent (Optional[ModelIndex]): The parent index, columns only exist at the top level.

        Returns:
            int: The number of columns.
        """
        return 0 if parent is not None and parent.isValid() else len(self.HEADERS)  # noqa: E501

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole  # noqa: E501
    ) -> Optional[str]:
        """Get a column header (Qt override).

        Args:
            section (int): The column.
            orientation (Qt.Orientation): The header orientation.
            role (int): The requested data role.

        Returns:
            Optional[str]: The column title, `None`
                for other roles or the vertical header.
        """
        if (
            orientation is Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.ToolTipRole
            and section
            in (
                self.ADDED,
                self.UPDATED,
            )
        ):
            return "\u26a0 marks an approximate date published by the website: hover it for the reason."
        if orientation is Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> CellData:  # noqa: E501
        """Get the content of a cell (Qt override).

        Args:
            index (ModelIndex): The cell.
            role (int): The requested data role.

        Returns:
            CellData: The text, colour, icon or flag of
                the cell for the role, `None` otherwise.
        """
        row = self.row_at(index)
        if row is None:
            loading = role == Qt.ItemDataRole.DisplayRole and index.isValid() and index.column() == self.NAME
            return self.LOADING if loading else None
        column = index.column()
        match role:
            case Qt.ItemDataRole.DisplayRole:
                return self._text(row, column)
            case Qt.ItemDataRole.ToolTipRole:
                return self._tooltip(row, column)
            case Qt.ItemDataRole.FontRole:
                return self.deleted_font if row.product.is_deleted else None
            case Qt.ItemDataRole.ForegroundRole:
                return self._foreground(row, column)
            case Qt.ItemDataRole.DecorationRole:
                return self._decoration(row, column)
            case _:
                return None
