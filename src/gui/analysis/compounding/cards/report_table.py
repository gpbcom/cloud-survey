from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem


class ReportTable(QTableWidget):
    """A read-only table of the Service compounding results, sized to its rows.

    Attributes:
        MAX_ROWS (ClassVar[int]): The most rows shown before the table scrolls.
        logger (Logger): The table logger.

    Notes:
        Every column but the first is aligned right. The header tooltips explain the columns.
    """

    MAX_ROWS: ClassVar[int] = 14

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Build an empty table.

        Args:
            logger (Optional[Logger]): The table logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        vertical = self.verticalHeader()
        if vertical is not None:
            vertical.setVisible(False)
        horizontal = self.horizontalHeader()
        if horizontal is not None:
            horizontal.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.setFixedHeight(60)

    ############################
    # Publicly Exposed Methods #
    ############################

    def fill(self, headers: Sequence[str], tooltips: Sequence[str], rows: List[List[str]]) -> None:
        """Write the rows.

        Args:
            headers (Sequence[str]): The column titles.
            tooltips (Sequence[str]): The explanation of each column.
            rows (List[List[str]]): The cells, one list per row.
        """
        self.setSortingEnabled(False)
        self.clear()
        self.setColumnCount(len(headers))
        self.setRowCount(len(rows))
        for column, (header, tooltip) in enumerate(zip(headers, tooltips, strict=True)):
            item = QTableWidgetItem(header)
            item.setToolTip(tooltip)
            self.setHorizontalHeaderItem(column, item)
        for row, cells in enumerate(rows):
            for column, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if column:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.setItem(row, column, cell)
        horizontal = self.horizontalHeader()
        shown = min(len(rows), self.MAX_ROWS)
        height = (horizontal.height() if horizontal else 24) + sum(self.rowHeight(row) for row in range(shown))
        self.setFixedHeight(height + 2 * self.frameWidth() + 4)
        self.logger.debug("Compounding table filled: %d rows, %d columns.", len(rows), len(headers))

    def cells(self) -> List[List[str]]:
        """Read the cells back (tests and the CSV export).

        Returns:
            List[List[str]]: The text of each cell, one list per row.
        """
        return [
            [item.text() if (item := self.item(row, column)) else "" for column in range(self.columnCount())]
            for row in range(self.rowCount())
        ]

    def headers(self) -> List[str]:
        """Read the column titles back.

        Returns:
            List[str]: The titles.
        """
        return [
            item.text() if (item := self.horizontalHeaderItem(column)) else "" for column in range(self.columnCount())
        ]
