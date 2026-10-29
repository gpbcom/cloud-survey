from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# Third Party Imports.
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

# First Party Imports.
from models.companies.enums import CompanyFactKind
from models.companies.progress.research_coverage import ResearchCoverage
from models.companies.progress.research_row import ResearchRow


class ProgressTable(QTableWidget):
    """The progress of a patents and papers search, one row per company picked.

    Attributes:
        HEADERS (ClassVar[List[Tuple[str, str]]]): The title and the tooltip of each column.
        ALL (ClassVar[str]): The row counting the facts without company (the patent pages).
        COUNTED (ClassVar[Dict[CompanyFactKind, int]]): The column counting each kind of fact.
        names (Dict[str, str]): The name of each company.
        rows (Dict[str, int]): The table row of each company of the search.
        counts (Dict[str, Dict[CompanyFactKind, int]]): The facts read in this search, by company and kind.
        windows (Dict[str, Dict[str, str]]): The latest state of each search window, by company.
        logger (Logger): The table logger.

    Notes:
        A patent page names its publication only: the pages read are counted on the "All selected" row.
    """

    HEADERS: ClassVar[List[Tuple[str, str]]] = [
        ("Company", "The company searched."),
        ("Status", "Waiting, searching (the latest fact arrived), done or stopped."),
        ("Patents", "The publications found in this search."),
        ("Windows", "The patents search windows read in this search: complete, then the others (split or open)."),
        ("Pages", "The patent pages read in this search (citations, family, classes)."),
        ("Papers", "The research papers found in this search."),
        ("Researchers", "The researcher profiles read in this search."),
        ("Stored", "What the database holds now: patents and papers."),
        ("Last fact", "When the latest fact of the company arrived."),
    ]
    ALL: ClassVar[str] = "All selected"
    COUNTED: ClassVar[Dict[CompanyFactKind, int]] = {
        CompanyFactKind.PATENT: 2,
        CompanyFactKind.PATENT_DETAIL: 4,
        CompanyFactKind.PAPER: 5,
        CompanyFactKind.RESEARCHER: 6,
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
        self.rows: Dict[str, int] = {}
        self.counts: Dict[str, Dict[CompanyFactKind, int]] = {}
        self.windows: Dict[str, Dict[str, str]] = {}
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        for column, (title, tooltip) in enumerate(self.HEADERS):
            item = QTableWidgetItem(title)
            item.setToolTip(tooltip)
            self.setHorizontalHeaderItem(column, item)
        vertical = self.verticalHeader()
        if vertical is not None:
            vertical.setVisible(False)
        horizontal = self.horizontalHeader()
        if horizontal is not None:
            horizontal.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            horizontal.setStretchLastSection(True)

    ############################
    # Internal Helpers Methods #
    ############################

    def _set(self, row: int, column: int, text: str) -> None:
        """Write a cell.

        Args:
            row (int): The row.
            column (int): The column.
            text (str): The text.
        """
        item = self.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            if column:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(row, column, item)
        item.setText(text)

    def _refresh(self, key: str) -> None:
        """Write the counts of a company.

        Args:
            key (str): The company, or the "All selected" row.
        """
        row = self.rows.get(key)
        if row is None:
            return
        counts = self.counts.get(key, {})
        for kind, column in self.COUNTED.items():
            self._set(row, column, f"{counts.get(kind, 0):,}")
        states = list(self.windows.get(key, {}).values())
        done = sum(1 for state in states if state == "complete")
        self._set(row, 3, f"{done} / {len(states)}" if states else "-")

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_coverage(self, coverage: Dict[str, ResearchCoverage]) -> None:
        """Write what the database holds of each company.

        Args:
            coverage (Dict[str, ResearchCoverage]): What is stored, by company.
        """
        for key, row in self.rows.items():
            stored = coverage.get(key)
            self._set(row, 7, f"{stored.patents:,} / {stored.papers:,}" if stored else "-")

    def start(self, companies: Sequence[str], coverage: Dict[str, ResearchCoverage]) -> None:
        """Lay out a new search: one waiting row per company, then the "All selected" row.

        Args:
            companies (Sequence[str]): The companies searched.
            coverage (Dict[str, ResearchCoverage]): What the database holds, by company.
        """
        keys = [*companies, self.ALL]
        self.setRowCount(len(keys))
        self.rows = {key: row for row, key in enumerate(keys)}
        self.counts = {key: {} for key in keys}
        self.windows = {key: {} for key in keys}
        for key, row in self.rows.items():
            self._set(row, 0, self.names.get(key, key))
            self._set(row, 1, "waiting")
            self._set(row, 8, "")
            self._refresh(key)
        self.set_coverage(coverage)
        self.logger.debug("Progress laid out for %d companies.", len(companies))

    def add(self, rows: Sequence[ResearchRow]) -> None:
        """Count the facts of a batch.

        Args:
            rows (Sequence[ResearchRow]): The facts.
        """
        now = datetime.now().strftime("%H:%M:%S")
        touched: List[str] = []
        for fact in rows:
            key = fact.company if fact.company in self.rows else self.ALL
            if fact.kind is CompanyFactKind.PATENT_WINDOW:
                self.windows.setdefault(key, {})[fact.identifier] = fact.detail.split(":", 1)[0]
            else:
                kinds = self.counts.setdefault(key, {})
                kinds[fact.kind] = kinds.get(fact.kind, 0) + 1
            if key not in touched:
                touched.append(key)
        for key in touched:
            self._refresh(key)
            row = self.rows.get(key)
            if row is not None:
                self._set(row, 1, "searching")
                self._set(row, 8, now)
        self.logger.debug("%d facts counted for %d companies.", len(rows), len(touched))

    def finish(self, status: str) -> None:
        """Mark the end of the search.

        Args:
            status (str): The final status (done, stopped, refused or failed).
        """
        for row in self.rows.values():
            self._set(row, 1, status)
        self.logger.debug("Progress finished: %s.", status)

    def count(self, key: str, kind: CompanyFactKind) -> int:
        """Get how many facts of a kind a company got in this search.

        Args:
            key (str): The company, or the "All selected" row.
            kind (CompanyFactKind): The kind of fact.

        Returns:
            int: The facts counted.
        """
        return self.counts.get(key, {}).get(kind, 0)
