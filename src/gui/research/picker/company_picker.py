from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Tuple

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from models.companies.progress.research_coverage import ResearchCoverage


class CompanyPicker(QWidget):
    """The companies whose patents and papers are searched: one alone, or several at once.

    Attributes:
        changed (pyqtSignal): Emitted when the companies picked change.
        companies (List[Tuple[str, str]]): The key and the name of each company offered, in name order.
        search (QLineEdit): Filters the list by name or key.
        list (QListWidget): The companies: a click picks one alone, Ctrl or Shift + click several.
        all_button (QPushButton): Picks every company shown.
        none_button (QPushButton): Picks none.
        count (QLabel): How many companies are picked.
        logger (Logger): The picker logger.
    """

    changed = pyqtSignal()

    def __init__(self, companies: Sequence[Tuple[str, str]], logger: Optional[Logger] = None) -> None:
        """Build the picker, no company picked.

        Args:
            companies (Sequence[Tuple[str, str]]): The key and the name of each company offered.
            logger (Optional[Logger]): The picker logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.companies = sorted(companies, key=lambda company: company[1].lower())
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter the companies…")
        self.search.setClearButtonEnabled(True)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setToolTip("Click a company to search it alone, Ctrl + click or Shift + click to add others.")
        for key, name in self.companies:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setToolTip(f"{name} ({key}): nothing stored yet")
            self.list.addItem(item)
        self.all_button = QPushButton("Select all")
        self.none_button = QPushButton("Clear")
        self.count = QLabel()
        self.count.setObjectName("muted")
        self.search.textChanged.connect(self._filter)
        self.list.itemSelectionChanged.connect(self._on_selection)
        self.all_button.clicked.connect(self.select_all)
        self.none_button.clicked.connect(self.list.clearSelection)
        buttons = QHBoxLayout()
        buttons.addWidget(self.all_button)
        buttons.addWidget(self.none_button)
        buttons.addStretch(1)
        buttons.addWidget(self.count)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.search)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        self._on_selection()
        self.logger.debug("Company picker built with %d companies.", len(self.companies))

    ############################
    # Internal Helpers Methods #
    ############################

    def _filter(self, text: str) -> None:
        """Show only the companies matching the filter.

        Args:
            text (str): The filter.
        """
        wanted = text.strip().lower()
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item is not None:
                key = str(item.data(Qt.ItemDataRole.UserRole))
                item.setHidden(bool(wanted) and wanted not in item.text().lower() and wanted not in key)
        self.logger.debug("Company picker filtered on %r.", wanted)

    def _picked(self) -> List[str]:
        """Get the companies picked.

        Returns:
            List[str]: Their keys, in list order.
        """
        return [
            str(item.data(Qt.ItemDataRole.UserRole))
            for row in range(self.list.count())
            if (item := self.list.item(row)) is not None and item.isSelected()
        ]

    def _on_selection(self) -> None:
        """Count the companies picked and tell the view."""
        picked = len(self._picked())
        self.count.setText(f"{picked} of {len(self.companies)} picked")
        self.changed.emit()

    ############################
    # Publicly Exposed Methods #
    ############################

    def selected(self) -> List[str]:
        """Get the companies picked.

        Returns:
            List[str]: Their keys, in list order.
        """
        return self._picked()

    def select(self, keys: Sequence[str]) -> None:
        """Pick some companies, and only them.

        Args:
            keys (Sequence[str]): Their keys.
        """
        wanted = set(keys)
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item is not None:
                item.setSelected(str(item.data(Qt.ItemDataRole.UserRole)) in wanted)
        self.logger.debug("%d companies picked.", len(wanted))

    def select_all(self) -> None:
        """Pick every company shown by the filter."""
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item is not None and not item.isHidden():
                item.setSelected(True)

    def set_coverage(self, coverage: Dict[str, ResearchCoverage]) -> None:
        """Show what is stored of each company in its tooltip and next to its name.

        Args:
            coverage (Dict[str, ResearchCoverage]): What is stored, by company.
        """
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item is None:
                continue
            key = str(item.data(Qt.ItemDataRole.UserRole))
            name = dict(self.companies).get(key, key)
            stored = coverage.get(key)
            if stored is None or not (stored.patents or stored.papers or stored.windows_done or stored.windows_open):
                item.setText(name)
                item.setToolTip(f"{name} ({key}): nothing stored yet")
                continue
            item.setText(f"{name}  ·  {stored.patents:,} patents, {stored.papers:,} papers")
            item.setToolTip(
                f"{name} ({key}): {stored.patents:,} patents ({stored.pages:,} pages read), search windows "
                f"{stored.windows_done} complete and {stored.windows_open} open, {stored.papers:,} papers, "
                f"{stored.researchers:,} researchers"
            )
        self.logger.debug("Coverage shown for %d companies.", len(coverage))
