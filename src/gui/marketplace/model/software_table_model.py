from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger
from typing import ClassVar, Dict, List, Optional, Union

# Third Party Imports.
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon

# First Party Imports.
from gui.marketplace.model.software_row import SoftwareRow
from gui.paging.page.paged_table_model import ModelIndex, PagedTableModel
from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.enums import ItemSort
from models.storage.pages.item_query import ItemQuery
from models.storage.pages.page import Page
from models.storage.pages.stored_item import StoredItem
from storage.storage import Storage

CellData = Optional[Union[str, QColor, QIcon, QFont]]


class SoftwareTableModel(PagedTableModel[MarketplaceSoftware, SoftwareRow]):
    """Table of the stored marketplace software, read page by page (see `PagedTableModel`).

    The deleted software is struck through.

    Attributes:
        PROVIDER (ClassVar[int]): The provider column.
        COUNTRY (ClassVar[int]): The provider country column, with its flag.
        NAME (ClassVar[int]): The software name column.
        PUBLISHER (ClassVar[int]): The software publisher column.
        CATEGORIES (ClassVar[int]): The column of the categories of the unified taxonomy.
        LABELS (ClassVar[int]): The column of the categories of the marketplace (source labels), in English.
        AUDIENCE (ClassVar[int]): The column of who the software is meant for.
        DELIVERY (ClassVar[int]): The delivery method column.
        ADDED (ClassVar[int]): The column of the date the software was listed.
        UPDATED (ClassVar[int]): The column of the date the software was last updated.
        HEADERS (ClassVar[List[str]]): The columns headers.
        LOADING (ClassVar[str]): The text of a row being read.
        SORTS (ClassVar[Dict[int, ItemSort]]): The order of each sortable column.
        theme (Theme): The application theme.
        deleted_font (QFont): The struck through font of the deleted rows.
        warning_icon (QIcon): The icon of the approximate dates.
        crawled_at (Dict[CloudProvider, datetime]): When each marketplace was last crawled.
        taxonomy (TaxonomyCache): The names of the categories and of the source labels.
    """

    PROVIDER: ClassVar[int] = 0
    COUNTRY: ClassVar[int] = 1
    NAME: ClassVar[int] = 2
    PUBLISHER: ClassVar[int] = 3
    CATEGORIES: ClassVar[int] = 4
    LABELS: ClassVar[int] = 5
    AUDIENCE: ClassVar[int] = 6
    DELIVERY: ClassVar[int] = 7
    ADDED: ClassVar[int] = 8
    UPDATED: ClassVar[int] = 9
    HEADERS: ClassVar[List[str]] = [
        "Provider",
        "Country",
        "Software",
        "Publisher",
        "Categories",
        "Source labels",
        "Audience",
        "Delivery",
        "Added",
        "Updated",
    ]
    LOADING: ClassVar[str] = "Loading\u2026"
    SORTS: ClassVar[Dict[int, ItemSort]] = {
        PROVIDER: ItemSort.PROVIDER,
        COUNTRY: ItemSort.PROVIDER,
        NAME: ItemSort.NAME,
        PUBLISHER: ItemSort.PUBLISHER,
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
            theme (Theme): The application theme.
            loop (StorageLoop): The storage thread of the GUI.
            logger (Optional[Logger]): The model logger.
            taxonomy (Optional[TaxonomyCache]): The names of the categories, those of the seed by default.
        """
        super().__init__(loop, self._list, self._row, logger)
        self.theme = theme
        self.taxonomy = taxonomy if taxonomy else TaxonomyCache(logger=self.logger)
        self.taxonomy.changed.connect(self._on_taxonomy_changed)
        self.deleted_font = QFont()
        self.deleted_font.setStrikeOut(True)
        self.warning_icon = theme.warning_icon()
        self.crawled_at: Dict[CloudProvider, datetime] = {}
        self.logger.debug("Software table ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _list(self, storage: Storage, query: ItemQuery) -> Page[MarketplaceSoftware]:
        """Read a page of software (storage thread).

        Args:
            storage (Storage): The open storage.
            query (ItemQuery): The page.

        Returns:
            Page[MarketplaceSoftware]: The software of the page.
        """
        self.logger.debug("Reading %d software from %d.", query.limit, query.offset)
        return await storage.marketplaces.list(query)

    def _row(self, stored: StoredItem[MarketplaceSoftware]) -> SoftwareRow:
        """Build the row of a stored software.

        Args:
            stored (StoredItem[MarketplaceSoftware]): The stored software.

        Returns:
            SoftwareRow: Its row, with the crawl date of its marketplace.
        """
        crawled_at = self.crawled_at.get(stored.provider)
        return SoftwareRow(provider=stored.provider, software=stored.item, crawled_at=crawled_at, id=stored.id)

    def _text(self, row: SoftwareRow, column: int) -> str:
        """Get the text of a cell.

        Args:
            row (SoftwareRow): The row.
            column (int): The column.

        Returns:
            str: The cell text.
        """
        software = row.software
        match column:
            case self.PROVIDER:
                return self.theme.provider_label(row.provider)
            case self.COUNTRY:
                return self.theme.country_label(row.provider.country)
            case self.NAME:
                return software.name
            case self.PUBLISHER:
                return software.publisher or ""
            case self.CATEGORIES:
                return self.taxonomy.names(software.service_categories)
            case self.LABELS:
                return self.taxonomy.label_names(software.source_label_ids, software.marketplace_categories)
            case self.AUDIENCE:
                return ", ".join(self.theme.category_label(category) for category in software.categories)
            case self.ADDED:
                return self.theme.date_label(software.added_at, software.added_caveat)
            case self.UPDATED:
                return self.theme.date_label(software.updated_at, software.updated_caveat)
            case _:
                return self.theme.delivery_label(software.delivery)

    def _tooltip(self, row: SoftwareRow, column: int) -> str:
        """Get the tooltip of a cell: the dates explained, the description of the name, else the text.

        Args:
            row (SoftwareRow): The row.
            column (int): The column.

        Returns:
            str: The cell tooltip.
        """
        software = row.software
        match column:
            case self.ADDED:
                added = self.theme.date_description(software.added_at, software.added_from, software.added_caveat)
                return f"Added: {added}"
            case self.UPDATED:
                updated = self.theme.date_description(
                    software.updated_at, software.updated_from, software.updated_caveat
                )
                return f"Updated: {updated}"
            case self.NAME if software.deleted_at:
                return f"{software.description}\nDeleted: {self.theme.date_description(software.deleted_at)}"
            case self.NAME:
                return software.description
            case self.CATEGORIES:
                return "\n".join(self.taxonomy.path(slug) for slug in software.service_categories)
            case self.LABELS:
                return ", ".join(software.marketplace_categories)
            case _:
                return self._text(row, column)

    def _caveat(self, row: SoftwareRow, column: int) -> bool:
        """Tell whether a cell shows an approximate date.

        Args:
            row (SoftwareRow): The row.
            column (int): The column.

        Returns:
            bool: Whether the added or updated date of the cell has a caveat.
        """
        software = row.software
        return bool({self.ADDED: software.added_caveat, self.UPDATED: software.updated_caveat}.get(column))

    def _foreground(self, row: SoftwareRow, column: int) -> Optional[QColor]:
        """Get the text colour of a cell: muted when deleted, warning for an approximate date, else the provider's.

        Args:
            row (SoftwareRow): The row.
            column (int): The column.

        Returns:
            Optional[QColor]: The colour, `None` for the default one.
        """
        if row.software.is_deleted:
            return QColor(self.theme.TEXT_MUTED)
        if self._caveat(row, column):
            return QColor(self.theme.WARNING)
        return self.theme.provider_color(row.provider) if column == self.PROVIDER else None

    def _decoration(self, row: SoftwareRow, column: int) -> Optional[QIcon]:
        """Get the icon of a cell: the warning of an approximate date, the provider icon or the country flag.

        Args:
            row (SoftwareRow): The row.
            column (int): The column.

        Returns:
            Optional[QIcon]: The icon, `None` without one.
        """
        if self._caveat(row, column):
            return self.warning_icon
        if column == self.PROVIDER:
            return self.theme.provider_icon(row.provider)
        return self.theme.flag_icon(row.provider.country) if column == self.COUNTRY else None

    def _on_taxonomy_changed(self) -> None:
        """Show the names read again in the category and label columns."""
        rows = self.rowCount()
        if rows:
            self.logger.debug("Category names of %d software rows refreshed.", rows)
            self.dataChanged.emit(self.index(0, self.CATEGORIES), self.index(rows - 1, self.LABELS))

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_crawl_dates(self, crawled_at: Dict[CloudProvider, datetime]) -> None:
        """Set when each marketplace was last crawled, shown with the next rows read.

        Args:
            crawled_at (Dict[CloudProvider, datetime]): The last crawl of each stored marketplace.
        """
        self.logger.debug("Crawl dates of %d marketplaces set.", len(crawled_at))
        self.crawled_at = dict(crawled_at)

    def columnCount(self, parent: Optional[ModelIndex] = None) -> int:
        """Get the number of columns (Qt override).

        Args:
            parent (Optional[ModelIndex]): The parent index, columns only exist at the top level.

        Returns:
            int: The number of columns.
        """
        return 0 if parent is not None and parent.isValid() else len(self.HEADERS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Optional[str]:
        """Get a column header (Qt override).

        Args:
            section (int): The column.
            orientation (Qt.Orientation): The header orientation.
            role (int): The requested data role.

        Returns:
            Optional[str]: The column title, `None` for other roles or the vertical header.
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

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> CellData:
        """Get the content of a cell (Qt override).

        Args:
            index (ModelIndex): The cell.
            role (int): The requested data role.

        Returns:
            CellData: The text, colour, icon or flag of the cell for the role, `None` otherwise.
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
                return self.deleted_font if row.software.is_deleted else None
            case Qt.ItemDataRole.ForegroundRole:
                return self._foreground(row, column)
            case Qt.ItemDataRole.DecorationRole:
                return self._decoration(row, column)
            case _:
                return None
