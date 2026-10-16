from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple, Union

# Third Party Imports.
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PyQt6.QtGui import QColor, QFont, QIcon

# First Party Imports.
from gui.marketplace.software_row import SoftwareRow
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.cloud.marketplace import CloudMarketplace

ModelIndex = Union[QModelIndex, QPersistentModelIndex]
CellData = Optional[Union[str, QColor, QIcon, QFont]]


class SoftwareTableModel(QAbstractTableModel):
    """Table of the software of every loaded marketplace, the deleted ones struck through.

    Attributes:
        PROVIDER (ClassVar[int]): The provider column.
        COUNTRY (ClassVar[int]): The provider country column, with its flag.
        NAME (ClassVar[int]): The software name column.
        PUBLISHER (ClassVar[int]): The software publisher column.
        CATEGORIES (ClassVar[int]): The software categories column.
        TYPES (ClassVar[int]): The software types column.
        DELIVERY (ClassVar[int]): The delivery method column.
        ADDED (ClassVar[int]): The column of the date the software was listed.
        UPDATED (ClassVar[int]): The column of the date the software was last updated.
        HEADERS (ClassVar[List[str]]): The columns headers.
        theme (Theme): The application theme.
        deleted_font (QFont): The struck through font of the deleted rows.
        provider_rows (Dict[CloudProvider, Tuple[CloudMarketplace, List[SoftwareRow]]]): The rows built for each
            loaded marketplace, reused while the marketplace is unchanged.
        rows (List[SoftwareRow]): The table rows.
    """

    PROVIDER: ClassVar[int] = 0
    COUNTRY: ClassVar[int] = 1
    NAME: ClassVar[int] = 2
    PUBLISHER: ClassVar[int] = 3
    CATEGORIES: ClassVar[int] = 4
    TYPES: ClassVar[int] = 5
    DELIVERY: ClassVar[int] = 6
    ADDED: ClassVar[int] = 7
    UPDATED: ClassVar[int] = 8
    HEADERS: ClassVar[List[str]] = [
        "Provider",
        "Country",
        "Software",
        "Publisher",
        "Categories",
        "Types",
        "Delivery",
        "Added",
        "Updated",
    ]

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Initialize an empty table.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The model logger.
        """
        super().__init__()
        self.theme = theme
        self.deleted_font = QFont()
        self.deleted_font.setStrikeOut(True)
        self.provider_rows: Dict[CloudProvider, Tuple[CloudMarketplace, List[SoftwareRow]]] = {}
        self.rows: List[SoftwareRow] = []
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _text(self, row: SoftwareRow, column: int) -> str:
        """Get the text of a cell, computed for that column only (the table may hold a hundred thousand rows).

        Args:
            row (SoftwareRow): The row.
            column (int): The column.

        Returns:
            str: The cell text.
        """
        software = row.software
        if column == self.PROVIDER:
            return self.theme.provider_label(row.provider)
        if column == self.COUNTRY:
            return self.theme.country_label(row.provider.country)
        if column == self.NAME:
            return software.name
        if column == self.PUBLISHER:
            return software.publisher or ""
        if column == self.CATEGORIES:
            return ", ".join(self.theme.category_label(category) for category in software.categories)
        if column == self.TYPES:
            return ", ".join(self.theme.type_label(kind) for kind in software.types)
        if column == self.ADDED:
            return self.theme.date_label(software.added_at)
        if column == self.UPDATED:
            return self.theme.date_label(software.updated_at)
        return self.theme.delivery_label(software.delivery)

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_marketplaces(self, marketplaces: Dict[CloudProvider, CloudMarketplace]) -> None:
        """Replace the table content with the software of the marketplaces, rebuilding the changed ones only.

        Args:
            marketplaces (Dict[CloudProvider, CloudMarketplace]): The loaded marketplaces, by cloud provider.
        """
        provider_rows: Dict[CloudProvider, Tuple[CloudMarketplace, List[SoftwareRow]]] = {}
        for provider, marketplace in marketplaces.items():
            cached = self.provider_rows.get(provider)
            if cached is not None and cached[0] is marketplace:
                provider_rows[provider] = cached
                continue
            rows = [
                SoftwareRow(provider=marketplace.provider, software=software, crawled_at=marketplace.crawled_at)
                for software in marketplace.software
            ]
            provider_rows[provider] = (marketplace, rows)
        self.beginResetModel()
        self.provider_rows = provider_rows
        self.rows = [row for _, rows in provider_rows.values() for row in rows]
        self.endResetModel()
        self.logger.debug("Software table reloaded: %d rows from %d marketplaces.", len(self.rows), len(marketplaces))

    def row_at(self, index: ModelIndex) -> Optional[SoftwareRow]:
        """Get the row of a table index.

        Args:
            index (ModelIndex): The table index.

        Returns:
            Optional[SoftwareRow]: The row, `None` for an invalid index.
        """
        return self.rows[index.row()] if index.isValid() and index.row() < len(self.rows) else None

    def rowCount(self, parent: Optional[ModelIndex] = None) -> int:
        """Get the number of rows (Qt override).

        Args:
            parent (Optional[ModelIndex]): The parent index, rows only exist at the top level.

        Returns:
            int: The number of software.
        """
        return 0 if parent is not None and parent.isValid() else len(self.rows)

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
            return None
        column, software = index.column(), row.software
        if role == Qt.ItemDataRole.DisplayRole:
            return self._text(row, column)
        if role == Qt.ItemDataRole.ToolTipRole:
            if column == self.ADDED:
                return f"Added: {self.theme.date_description(software.added_at, software.added_from)}"
            if column == self.UPDATED:
                return f"Updated: {self.theme.date_description(software.updated_at, software.updated_from)}"
            if column == self.NAME and software.deleted_at:
                return f"{software.description}\nDeleted: {self.theme.date_description(software.deleted_at)}"
            return software.description if column == self.NAME else self._text(row, column)
        if role == Qt.ItemDataRole.FontRole and software.is_deleted:
            return self.deleted_font
        if role == Qt.ItemDataRole.ForegroundRole and software.is_deleted:
            return QColor(self.theme.TEXT_MUTED)
        if role == Qt.ItemDataRole.DecorationRole and column == self.PROVIDER:
            return self.theme.provider_icon(row.provider)
        if role == Qt.ItemDataRole.DecorationRole and column == self.COUNTRY:
            return self.theme.flag_icon(row.provider.country)
        if role == Qt.ItemDataRole.ForegroundRole and column == self.PROVIDER:
            return self.theme.provider_color(row.provider)
        return None
