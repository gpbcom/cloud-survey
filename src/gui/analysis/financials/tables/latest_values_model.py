from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence, Tuple, Union

# Third Party Imports.
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QObject, QPersistentModelIndex, Qt

type LatestRow = Tuple[str, str, str, str, str, str, str, str, str]
type Index = Union[QModelIndex, QPersistentModelIndex]


class LatestValuesModel(QAbstractTableModel):
    """The latest value of each indicator of the companies picked, with where it was read.

    Attributes:
        HEADERS (ClassVar[Tuple[str, ...]]): The column titles.
        SOURCE_COLUMN (ClassVar[int]): The column of the document read (opened by a double-click).
        INPUTS_COLUMN (ClassVar[int]): The column of the formula and its sources.
        rows (List[LatestRow]): The rows: company, indicator, period, value, currency, US dollars, basis, inputs,
            document.
        logger (Logger): The model logger.
    """

    HEADERS: ClassVar[Tuple[str, ...]] = (
        "Company",
        "Indicator",
        "Period",
        "Value",
        "Currency",
        "US dollars",
        "Basis",
        "Computed from",
        "Source",
    )
    SOURCE_COLUMN: ClassVar[int] = 8
    INPUTS_COLUMN: ClassVar[int] = 7

    def __init__(self, parent: Optional[QObject] = None, logger: Optional[Logger] = None) -> None:
        """Build an empty model.

        Args:
            parent (Optional[QObject]): The Qt parent.
            logger (Optional[Logger]): The model logger.
        """
        super().__init__(parent)
        self.logger = logger if logger else getLogger(__name__)
        self.rows: List[LatestRow] = []

    ############################
    # Publicly Exposed Methods #
    ############################

    def rowCount(self, parent: Optional[Index] = None) -> int:
        """Count the rows (Qt override).

        Args:
            parent (Optional[Index]): The parent index (none: a flat table).

        Returns:
            int: The number of rows.
        """
        return 0 if parent is not None and parent.isValid() else len(self.rows)

    def columnCount(self, parent: Optional[Index] = None) -> int:
        """Count the columns (Qt override).

        Args:
            parent (Optional[Index]): The parent index (none: a flat table).

        Returns:
            int: The number of columns.
        """
        return 0 if parent is not None and parent.isValid() else len(self.HEADERS)

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> Optional[str]:
        """Get a cell (Qt override): its text, and its full text as tooltip.

        Args:
            index (Index): The cell.
            role (int): The role asked.

        Returns:
            Optional[str]: The text, `None` for another role or an invalid cell.
        """
        if not index.isValid() or role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return None
        return self.rows[index.row()][index.column()]

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Optional[str]:
        """Get a column title (Qt override).

        Args:
            section (int): The column.
            orientation (Qt.Orientation): Horizontal for the column titles.
            role (int): The role asked.

        Returns:
            Optional[str]: The title, `None` otherwise.
        """
        if orientation is Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def set_rows(self, rows: Sequence[LatestRow]) -> None:
        """Replace the rows.

        Args:
            rows (Sequence[LatestRow]): The new rows.
        """
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()
        self.logger.debug("%d latest values shown.", len(self.rows))

    def source(self, row: int) -> str:
        """Get the document of a row.

        Args:
            row (int): The row.

        Returns:
            str: Its address, empty when none is known.
        """
        return self.rows[row][self.SOURCE_COLUMN] if 0 <= row < len(self.rows) else ""
