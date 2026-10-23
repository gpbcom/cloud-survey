from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

# First Party Imports.
from analytics.history.chronology_timeline import ChronologyTimeline
from gui.theme import Theme
from models.history.timeline.timeline_entry import TimelineEntry


class ChronologyTable(QTableWidget):
    """The chronology printed in the analysis: a line per change of leader and per notable event, by date.

    Attributes:
        COLUMNS (ClassVar[Tuple[str, ...]]): The headers.
        WRAPPED (ClassVar[Tuple[int, ...]]): The columns of long texts, wrapped and shown whole in their tooltip.
        VISIBLE_ROWS (ClassVar[int]): The rows shown before the table scrolls.
        ROW_HEIGHT (ClassVar[int]): The height of a line: three lines of text, the rest in its tooltip.
        WIDTHS (ClassVar[Tuple[Tuple[int, int], ...]]): The column and the starting width of the resizable columns.
        picked (pyqtSignal): Emitted with the key of the reign or event of a clicked line.
        theme (Theme): The application theme.
        keys (List[str]): The reign or event key of each line, in date order.
        logger (Logger): The table logger.

    Notes:
        The kind is coloured like the chart: the changes of leader in the accent colour, the events in the
        policy-shock colour of their markers. Clicking a line highlights its band or marker in the chart, and a band or
        marker clicked in the chart selects its line here.
    """

    COLUMNS: ClassVar[Tuple[str, ...]] = ("Date", "Kind", "Segment", "Companies", "What happened", "Effect", "Source")
    WRAPPED: ClassVar[Tuple[int, ...]] = (3, 4, 5, 6)
    VISIBLE_ROWS: ClassVar[int] = 12
    ROW_HEIGHT: ClassVar[int] = 58
    WIDTHS: ClassVar[Tuple[Tuple[int, int], ...]] = ((3, 170), (5, 240), (6, 210))

    picked = pyqtSignal(str)

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build an empty table.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The table logger.
        """
        super().__init__(0, len(self.COLUMNS))
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.keys: List[str] = []
        self.setHorizontalHeaderLabels(list(self.COLUMNS))
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setWordWrap(True)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        header = self.horizontalHeader()
        if header is not None:
            for column in range(len(self.COLUMNS)):
                mode = QHeaderView.ResizeMode.Stretch if column == 4 else QHeaderView.ResizeMode.ResizeToContents
                header.setSectionResizeMode(column, mode)
            for column, width in self.WIDTHS:
                header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
                header.resizeSection(column, width)
        vertical = self.verticalHeader()
        if vertical is not None:
            vertical.setVisible(False)
            vertical.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            vertical.setDefaultSectionSize(self.ROW_HEIGHT)
        self.cellClicked.connect(self._on_clicked)

    ############################
    # Internal Helpers Methods #
    ############################

    def _on_clicked(self, row: int, _: int) -> None:
        """Tell which reign or event a clicked line is about.

        Args:
            row (int): The line.
            _ (int): The column (unused).
        """
        item = self.item(row, 0)
        key = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if key:
            self.logger.debug("Chronology line %s picked.", key)
            self.picked.emit(str(key))

    def _fit(self) -> None:
        """Fit the table to `VISIBLE_ROWS` lines (it scrolls beyond)."""
        header = self.horizontalHeader()
        rows = min(self.rowCount(), self.VISIBLE_ROWS) * self.ROW_HEIGHT
        self.setFixedHeight((header.sizeHint().height() if header else 24) + rows + 2 * self.frameWidth() + 2)

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_entries(self, entries: List[TimelineEntry], timeline: ChronologyTimeline) -> None:
        """Print the chronology.

        Args:
            entries (List[TimelineEntry]): The lines, in date order.
            timeline (ChronologyTimeline): Tells a change of leader from an event.
        """
        self.setSortingEnabled(False)
        self.setRowCount(len(entries))
        self.keys = []
        for row, entry in enumerate(entries):
            cells = [entry.date, entry.kind, entry.segment, entry.companies, entry.what, entry.effect, entry.source]
            leadership = entry.kind == timeline.LEADERSHIP
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column in self.WRAPPED:
                    item.setToolTip(text)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, entry.key)
                if column == 1:
                    item.setForeground(QColor(self.theme.ACCENT if leadership else self.theme.POLICY_SHOCK))
                self.setItem(row, column, item)
            self.keys.append(entry.key)
        self._fit()
        self.logger.debug("Chronology table of %d lines.", len(entries))

    def select_key(self, key: str) -> None:
        """Select the first line of a reign or an event, and scroll to it.

        Args:
            key (str): The key of the reign or event.
        """
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == key:
                self.selectRow(row)
                self.scrollToItem(item, QTableWidget.ScrollHint.PositionAtCenter)
                return
