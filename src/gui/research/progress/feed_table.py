from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# Third Party Imports.
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

# First Party Imports.
from models.companies.enums import CompanyFactKind
from models.companies.progress.research_row import ResearchRow


class FeedTable(QTableWidget):
    """The patents, windows, pages, papers and researchers of a search as they arrive, the newest on top.

    Attributes:
        MAX_ROWS (ClassVar[int]): The most rows kept (the oldest go first).
        HEADERS (ClassVar[List[Tuple[str, str]]]): The title and the tooltip of each column.
        KINDS (ClassVar[Dict[CompanyFactKind, str]]): The name of each kind of fact.
        names (Dict[str, str]): The name of each company.
        received (int): The facts received since the search started.
        logger (Logger): The table logger.

    Notes:
        Hovering a row shows the page it was read from.
    """

    MAX_ROWS: ClassVar[int] = 1000
    HEADERS: ClassVar[List[Tuple[str, str]]] = [
        ("Time", "When the fact arrived."),
        ("Company", "The company searched (none for a patent page, which names its publication only)."),
        ("Kind", "Patent, search window, patent page, paper, researcher or yearly paper count."),
        ("Identifier", "The publication number, the DOI or OpenAlex work, the author or the window."),
        ("Title", "The title, the researcher's name or the assignee searched."),
        ("Date", "The priority date, the publication day or the start of the window."),
        ("Detail", "The window's counts, the citations or the h-index."),
    ]
    KINDS: ClassVar[Dict[CompanyFactKind, str]] = {
        CompanyFactKind.PATENT: "patent",
        CompanyFactKind.PATENT_WINDOW: "window",
        CompanyFactKind.PATENT_DETAIL: "patent page",
        CompanyFactKind.PAPER: "paper",
        CompanyFactKind.RESEARCHER: "researcher",
        CompanyFactKind.PAPER_COUNT: "papers per year",
    }

    def __init__(self, names: Dict[str, str], logger: Optional[Logger] = None) -> None:
        """Build an empty table.

        Args:
            names (Dict[str, str]): The name of each company.
            logger (Optional[Logger]): The table logger.
        """
        super().__init__(0, len(self.HEADERS))
        self.names = names
        self.logger = logger if logger else getLogger(__name__)
        self.received = 0
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        for column, (title, tooltip) in enumerate(self.HEADERS):
            item = QTableWidgetItem(title)
            item.setToolTip(tooltip)
            self.setHorizontalHeaderItem(column, item)
        vertical = self.verticalHeader()
        if vertical is not None:
            vertical.setVisible(False)
        horizontal = self.horizontalHeader()
        if horizontal is not None:
            horizontal.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            horizontal.setStretchLastSection(True)
            for column, width in enumerate((70, 140, 100, 170, 420, 90)):
                self.setColumnWidth(column, width)

    ############################
    # Publicly Exposed Methods #
    ############################

    def clear_rows(self) -> None:
        """Empty the table for a new search."""
        self.setRowCount(0)
        self.received = 0

    def add(self, rows: Sequence[ResearchRow]) -> None:
        """Put the facts of a batch on top.

        Args:
            rows (Sequence[ResearchRow]): The facts, in the order they came.
        """
        now = datetime.now().strftime("%H:%M:%S")
        for fact in rows:
            self.insertRow(0)
            cells = [
                now,
                self.names.get(fact.company, fact.company) if fact.company else "-",
                self.KINDS.get(fact.kind, fact.kind.value),
                fact.identifier,
                fact.title,
                fact.day.isoformat() if fact.day else "",
                fact.detail,
            ]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if fact.url:
                    item.setToolTip(fact.url)
                self.setItem(0, column, item)
        self.received += len(rows)
        while self.rowCount() > self.MAX_ROWS:
            self.removeRow(self.rowCount() - 1)
        self.logger.debug("%d facts streamed (%d since the start).", len(rows), self.received)
