from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Set, Tuple

# Third Party Imports.
from pydantic import BaseModel
from PyQt6 import sip
from PyQt6.QtCore import QModelIndex, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSplitter,
    QStackedWidget,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from gui.paging.records.record_table_model import RecordTableModel
from gui.research.stored.record_details import RecordDetails
from gui.research.stored.record_layouts import RecordLayouts
from gui.storage_bridge.storage_loop import StorageLoop
from models.companies.stored.papers.stored_paper import StoredPaper
from models.companies.stored.patents.patent_file import PatentFile
from models.companies.stored.patents.stored_patent import StoredPatent
from models.storage.records.enums import RecordKind
from models.storage.records.record_query import RecordQuery
from storage.exception import StorageError


class StoredBrowser(QWidget):
    """The Stored data of the Patents & Papers tab: the patents, papers, people and windows stored, page by page.

    Attributes:
        KINDS (ClassVar[List[Tuple[RecordKind, str, str]]]): Each dataset, its label and its tooltip.
        DEBOUNCE_MS (ClassVar[int]): The pause after the last key typed before the filter applies.
        WIDE_PX (ClassVar[int]): The width of the columns of long texts.
        loop (StorageLoop): Runs the database reads off the GUI thread.
        layouts (RecordLayouts): The columns of each dataset.
        companies (List[str]): The companies shown, every one when empty.
        kind (RecordKind): The dataset shown.
        stale (Set[RecordKind]): The datasets to read again when they are shown.
        selected (Optional[str]): The record whose details are being read (a late answer for another is dropped).
        group (QButtonGroup): The dataset switch.
        filter_box (QLineEdit): The text looked for.
        timer (QTimer): Applies the filter once the typing pauses.
        count (QLabel): The records matching.
        pages (QStackedWidget): One table per dataset.
        views (Dict[RecordKind, QTableView]): The table of each dataset.
        models (Dict[RecordKind, RecordTableModel]): The records of each dataset.
        details (RecordDetails): Everything stored about the record selected.
        logger (Logger): The browser logger.

    Notes:
        - Only the dataset shown is read: the others are read when they are shown, if the companies, the text or
          the database changed meanwhile.
        - The tables are sorted in the database by a click on a column header (not every column can be sorted).
        - A double click opens the record's page: Google Patents, the DOI or OpenAlex.
    """

    KINDS: ClassVar[List[Tuple[RecordKind, str, str]]] = [
        (RecordKind.PATENTS, "Patents", "The publications found by the assignee searches, the selected one in full"),
        (RecordKind.PAPERS, "Papers", "The research papers of the companies' institutions, with their authors"),
        (RecordKind.RESEARCHERS, "Researchers", "The OpenAlex profiles of the companies' researchers"),
        (RecordKind.INVENTORS, "Inventors", "The inventor profiles derived from the stored patents"),
        (RecordKind.ASSIGNEES, "Assignees", "The assignee names of each company, derived from its stored patents"),
        (RecordKind.WINDOWS, "Search windows", "How far each assignee search went, window of priority dates by window"),
    ]
    DEBOUNCE_MS: ClassVar[int] = 300
    WIDE_PX: ClassVar[int] = 320

    def __init__(self, loop: StorageLoop, logger: Optional[Logger] = None) -> None:
        """Build the browser, empty until its companies are set.

        Args:
            loop (StorageLoop): Runs the database reads off the GUI thread.
            logger (Optional[Logger]): The browser logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.loop = loop
        self.layouts = RecordLayouts(self.logger)
        self.companies: List[str] = []
        self.kind = RecordKind.PATENTS
        self.stale: Set[RecordKind] = {kind for kind, _, _ in self.KINDS}
        self.selected: Optional[str] = None
        self.group = QButtonGroup(self)
        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText("Filter: title, name, publication, DOI…")
        self.filter_box.setClearButtonEnabled(True)
        self.filter_box.setToolTip("Text contained in the title, the name or the identifier, whatever the case")
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(self.DEBOUNCE_MS)
        self.count = QLabel("")
        self.pages = QStackedWidget()
        self.views: Dict[RecordKind, QTableView] = {}
        self.models: Dict[RecordKind, RecordTableModel] = {}
        self.details = RecordDetails(self.logger)
        for kind, _, _ in self.KINDS:
            self._add_table(kind)
        self._layout()
        self.timer.timeout.connect(self._apply_filter)
        self.filter_box.textChanged.connect(lambda _text: self.timer.start())
        self.group.idClicked.connect(lambda index: self.show_kind(self.KINDS[index][0]))
        self.logger.debug("Stored data browser built: %d datasets.", len(self.KINDS))

    ############################
    # Internal Helpers Methods #
    ############################

    def _query(self, kind: RecordKind) -> RecordQuery:
        """Build the query of a dataset: the companies and the text shown, its own order.

        Args:
            kind (RecordKind): The dataset.

        Returns:
            RecordQuery: The query.
        """
        current = self.models[kind].query
        return RecordQuery(
            companies=self.companies,
            text=self.filter_box.text(),
            sort=current.sort,
            descending=current.descending,
            limit=RecordTableModel.PAGE_SIZE,
        )

    def _load(self, kind: RecordKind) -> None:
        """Read a dataset from its start, with the companies and the text shown.

        Args:
            kind (RecordKind): The dataset.
        """
        self.logger.debug("Reading the stored %s of %d companies.", kind.value, len(self.companies))
        self.stale.discard(kind)
        self.count.setText("Reading…")
        self.models[kind].set_query(self._query(kind))

    def _apply_filter(self) -> None:
        """Apply the text typed: the dataset shown is read again, the others when shown."""
        self.logger.info("Stored data filtered by %r.", self.filter_box.text())
        self.stale.update(kind for kind, _, _ in self.KINDS)
        self._load(self.kind)

    def _on_loaded(self, kind: RecordKind, total: int) -> None:
        """Show the records matching (GUI thread).

        Args:
            kind (RecordKind): The dataset counted.
            total (int): The records matching.
        """
        if sip.isdeleted(self) or kind is not self.kind:
            return
        picked = len(self.companies)
        scope = "every company" if not picked else "1 company" if picked == 1 else f"{picked} companies"
        self.count.setText(f"{total:,} {kind.value} ({scope})")

    def _on_failed(self, kind: RecordKind, reason: str) -> None:
        """Show that a page cannot be read (GUI thread).

        Args:
            kind (RecordKind): The dataset.
            reason (str): The error.
        """
        if sip.isdeleted(self):
            return
        self.logger.warning("The stored %s cannot be read: %s", kind.value, reason)
        if kind is self.kind:
            self.count.setText(f"The {kind.value} cannot be read: {reason}")

    def _open(self, kind: RecordKind, index: QModelIndex) -> None:
        """Open the page of the record double-clicked.

        Args:
            kind (RecordKind): The dataset.
            index (QModelIndex): The cell.
        """
        link = self.models[kind].link_at(index)
        if link is None:
            self.logger.debug("The %s record double-clicked has no page.", kind.value)
            return
        self.logger.info("Opening %s.", link)
        QDesktopServices.openUrl(QUrl(link))

    def _on_patent(self, file: Optional[PatentFile], token: str) -> None:
        """Show the publication read (GUI thread).

        Args:
            file (Optional[PatentFile]): The publication, `None` when it is no longer stored.
            token (str): The record asked: dropped when another one is selected since.
        """
        if sip.isdeleted(self) or token != self.selected:
            return
        if file is None:
            self.details.show_message("This publication is no longer stored.")
            return
        self.details.show_patent(file)

    def _on_paper(self, paper: Optional[StoredPaper], token: str) -> None:
        """Show the paper read (GUI thread).

        Args:
            paper (Optional[StoredPaper]): The paper, `None` when it is no longer stored.
            token (str): The record asked: dropped when another one is selected since.
        """
        if sip.isdeleted(self) or token != self.selected:
            return
        if paper is None:
            self.details.show_message("This paper is no longer stored.")
            return
        self.details.show_paper(paper)

    def _on_detail_error(self, error: StorageError, token: str) -> None:
        """Report details which cannot be read (GUI thread).

        Args:
            error (StorageError): The error.
            token (str): The record asked.
        """
        if sip.isdeleted(self) or token != self.selected:
            return
        self.logger.error("The details of %s cannot be read: %s", token, error)
        self.details.show_message(f"The details cannot be read: {error}")

    def _on_current(self, kind: RecordKind, index: QModelIndex) -> None:
        """Show the details of the record selected, reading them for a patent or a paper.

        Args:
            kind (RecordKind): The dataset.
            index (QModelIndex): The row selected.
        """
        record: Optional[BaseModel] = self.models[kind].record_at(index)
        if record is None:
            self.selected = None
            self.details.clear()
            return
        match record:
            case StoredPatent():
                token = f"patent:{record.publication_number}"
                number = record.publication_number
                self.selected = token
                self.details.show_message(f"Reading {number}…")
                self.loop.submit(
                    lambda storage: storage.patents.read(number),
                    lambda file: self._on_patent(file, token),
                    lambda error: self._on_detail_error(error, token),
                )
            case StoredPaper():
                token = f"paper:{record.openalex_id}"
                work = record.openalex_id
                self.selected = token
                self.details.show_message(f"Reading {record.title or work}…")
                self.loop.submit(
                    lambda storage: storage.papers.read(work),
                    lambda paper: self._on_paper(paper, token),
                    lambda error: self._on_detail_error(error, token),
                )
            case _:
                self.selected = None
                headers = self.models[kind].layout.headers
                cells = self.layouts.cells(record)
                fields = [(title, cell) for (title, _), cell in zip(headers, cells, strict=False)]
                self.details.show_fields(cells[0] if cells else kind.value, fields, self.layouts.link(record))

    def _add_table(self, kind: RecordKind) -> None:
        """Build the table of a dataset, sorted by its first order (not read yet).

        Args:
            kind (RecordKind): The dataset.
        """
        layout = self.layouts.layout(kind)
        model = RecordTableModel(self.loop, layout, self.logger)
        model.query = RecordQuery(sort=layout.sorts[layout.default], limit=RecordTableModel.PAGE_SIZE)
        model.loaded.connect(lambda total, shown=kind: self._on_loaded(shown, total))
        model.failed.connect(lambda reason, shown=kind: self._on_failed(shown, reason))
        view = QTableView()
        view.setModel(model)
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setAlternatingRowColors(True)
        view.setWordWrap(False)
        vertical = view.verticalHeader()
        if vertical is not None:
            vertical.setVisible(False)
            vertical.setDefaultSectionSize(22)
        horizontal = view.horizontalHeader()
        if horizontal is not None:
            horizontal.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            horizontal.setDefaultSectionSize(110)
            horizontal.setStretchLastSection(True)
            horizontal.setSortIndicator(layout.default, Qt.SortOrder.DescendingOrder)
            for column in layout.wide:
                horizontal.resizeSection(column, self.WIDE_PX)
        view.setSortingEnabled(True)
        view.doubleClicked.connect(lambda index, shown=kind: self._open(shown, index))
        selection = view.selectionModel()
        if selection is not None:
            selection.currentRowChanged.connect(lambda current, _previous, shown=kind: self._on_current(shown, current))
        self.models[kind] = model
        self.views[kind] = view
        self.pages.addWidget(view)

    def _layout(self) -> None:
        """Lay the browser out: the dataset switch and the filter, then the table over the details."""
        tools = QHBoxLayout()
        tools.setSpacing(4)
        for index, (kind, label, tooltip) in enumerate(self.KINDS):
            button = QToolButton()
            button.setObjectName("segment")
            button.setText(label)
            button.setToolTip(tooltip)
            button.setCheckable(True)
            button.setChecked(kind is self.kind)
            self.group.addButton(button, index)
            tools.addWidget(button)
        tools.addSpacing(8)
        tools.addWidget(self.filter_box, 1)
        tools.addWidget(self.count)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.pages)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(tools)
        layout.addWidget(splitter, 1)

    ############################
    # Publicly Exposed Methods #
    ############################

    def show_kind(self, kind: RecordKind) -> None:
        """Show a dataset, read when the companies, the text or the database changed since it was shown.

        Args:
            kind (RecordKind): The dataset.
        """
        self.logger.info("Stored %s shown.", kind.value)
        self.kind = kind
        index = [shown for shown, _, _ in self.KINDS].index(kind)
        button = self.group.button(index)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        self.pages.setCurrentWidget(self.views[kind])
        self.selected = None
        self.details.clear()
        if kind in self.stale:
            self._load(kind)
        else:
            self._on_loaded(kind, self.models[kind].total)

    def set_companies(self, companies: Sequence[str]) -> None:
        """Show the records of other companies: the dataset shown is read again, the others when shown.

        Args:
            companies (Sequence[str]): The companies, every one when empty.
        """
        picked = list(companies)
        if picked == self.companies and self.kind not in self.stale:
            return
        self.logger.info("Stored data of %d companies.", len(picked))
        self.companies = picked
        self.stale.update(kind for kind, _, _ in self.KINDS)
        self._load(self.kind)

    def refresh(self) -> None:
        """Read the datasets again (a search wrote records): the one shown now, keeping its rows meanwhile."""
        self.logger.info("Stored data refreshed.")
        if self.kind in self.stale:
            self._load(self.kind)
        else:
            self.models[self.kind].refresh()
        self.stale.update(kind for kind, _, _ in self.KINDS if kind is not self.kind)

    def invalidate(self) -> None:
        """Mark every dataset to be read again when shown (records were written while the browser was hidden)."""
        self.logger.debug("Stored data marked stale.")
        self.stale.update(kind for kind, _, _ in self.KINDS)

    def model(self, kind: RecordKind) -> RecordTableModel:
        """Get the records of a dataset (tests).

        Args:
            kind (RecordKind): The dataset.

        Returns:
            RecordTableModel: Its table model.
        """
        return self.models[kind]
