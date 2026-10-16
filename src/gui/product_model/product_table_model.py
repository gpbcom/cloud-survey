from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Union

# Third Party Imports.
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PyQt6.QtGui import QColor, QFont, QIcon

# First Party Imports.
from gui.product_model.product_row import ProductRow
from gui.theme import Theme
from models.cloud.catalogue import CloudCatalogue
from models.cloud.enums import CloudProvider

ModelIndex = Union[QModelIndex, QPersistentModelIndex]
CellData = Optional[Union[str, QColor, QIcon, QFont]]


class ProductTableModel(QAbstractTableModel):
    """Table of the products of every loaded catalogue, the deleted ones struck through.

    Attributes:
        PROVIDER (ClassVar[int]): The provider column.
        COUNTRY (ClassVar[int]): The provider country column, with its flag.
        NAME (ClassVar[int]): The product name column.
        DESCRIPTION (ClassVar[int]): The product description column.
        ADDED (ClassVar[int]): The column of the date the product was added.
        UPDATED (ClassVar[int]): The column of the date the product was last updated.
        HEADERS (ClassVar[List[str]]): The columns headers.
        theme (Theme): The application theme, for the provider colours and the country flags.
        deleted_font (QFont): The struck through font of the deleted rows.
        rows (List[ProductRow]): The table rows.
    """

    PROVIDER: ClassVar[int] = 0
    COUNTRY: ClassVar[int] = 1
    NAME: ClassVar[int] = 2
    DESCRIPTION: ClassVar[int] = 3
    ADDED: ClassVar[int] = 4
    UPDATED: ClassVar[int] = 5
    HEADERS: ClassVar[List[str]] = ["Provider", "Country", "Product", "Description", "Added", "Updated"]

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Initialize an empty table.

        Args:
            theme (Theme): The application theme, for the provider colours.
            logger (Optional[Logger]): The model logger.
        """
        super().__init__()
        self.theme = theme
        self.deleted_font = QFont()
        self.deleted_font.setStrikeOut(True)
        self.rows: List[ProductRow] = []
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_catalogues(self, catalogues: Dict[CloudProvider, CloudCatalogue]) -> None:
        """Replace the table content with the products of the catalogues.

        Args:
            catalogues (Dict[CloudProvider, CloudCatalogue]): The loaded catalogues, by cloud provider.
        """
        self.beginResetModel()
        self.rows = [
            ProductRow(provider=catalogue.provider, product=product, crawled_at=catalogue.crawled_at)
            for catalogue in catalogues.values()
            for product in catalogue.products
        ]
        self.endResetModel()
        self.logger.debug("Product table reloaded: %d rows from %d catalogues.", len(self.rows), len(catalogues))

    def row_at(self, index: ModelIndex) -> Optional[ProductRow]:
        """Get the row of a table index.

        Args:
            index (ModelIndex): The table index.

        Returns:
            Optional[ProductRow]: The row, `None` for an invalid index.
        """
        return self.rows[index.row()] if index.isValid() and index.row() < len(self.rows) else None

    def rowCount(self, parent: Optional[ModelIndex] = None) -> int:
        """Get the number of rows (Qt override).

        Args:
            parent (Optional[ModelIndex]): The parent index, rows only exist at the top level.

        Returns:
            int: The number of products.
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
        column, product = index.column(), row.product
        if role == Qt.ItemDataRole.ToolTipRole and column in (self.ADDED, self.UPDATED):
            if column == self.ADDED:
                return f"Added: {self.theme.date_description(product.added_at, product.added_from)}"
            return f"Updated: {self.theme.date_description(product.updated_at, product.updated_from)}"
        if role == Qt.ItemDataRole.ToolTipRole and column == self.NAME and product.deleted_at:
            return f"{product.name}\nDeleted: {self.theme.date_description(product.deleted_at)}"
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            texts = {
                self.PROVIDER: self.theme.provider_label(row.provider),
                self.COUNTRY: self.theme.country_label(row.provider.country),
                self.NAME: product.name,
                self.DESCRIPTION: product.description,
                self.ADDED: self.theme.date_label(product.added_at),
                self.UPDATED: self.theme.date_label(product.updated_at),
            }
            return texts[column]
        if role == Qt.ItemDataRole.FontRole and product.is_deleted:
            return self.deleted_font
        if role == Qt.ItemDataRole.ForegroundRole and product.is_deleted:
            return QColor(self.theme.TEXT_MUTED)
        if role == Qt.ItemDataRole.DecorationRole and column == self.PROVIDER:
            return self.theme.provider_icon(row.provider)
        if role == Qt.ItemDataRole.DecorationRole and column == self.COUNTRY:
            return self.theme.flag_icon(row.provider.country)
        if role == Qt.ItemDataRole.ForegroundRole and column == self.PROVIDER:
            return self.theme.provider_color(row.provider)
        return None
