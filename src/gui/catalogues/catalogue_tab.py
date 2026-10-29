from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from pydantic import BaseModel, ValidationError
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from curated.exception import CuratedError
from gui.catalogues.rows.curated_row_model import CuratedRowModel, CuratedRowValues
from gui.catalogues.rows.row_editor_dialog import RowEditorDialog
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.curated.companies.company_identifier import CompanyIdentifier
from models.curated.companies.company_profile import CompanyProfile
from models.curated.enums import CuratedDataset, CuratedFile, IdentifierStatus
from models.curated.figures.reported_company_record import ReportedCompanyRecord
from models.curated.figures.reported_event_record import ReportedEventRecord
from models.curated.figures.reported_year_record import ReportedYearRecord
from models.curated.launches.product_launch import ProductLaunch
from models.curated.records.curated_bundle import CuratedBundle
from models.curated.records.curated_record import CuratedRecord
from storage.exception import StorageError
from storage.storage import Storage


class CatalogueTab(QWidget):
    """A tab of the Catalogues manager: the rows of one curated catalogue, section by section, edited in place.

    Attributes:
        SECTIONS (ClassVar[Dict[CuratedFile, List[Tuple[str, str, Optional[CuratedDataset]]]]]): The sections of
            each catalogue: their title, the list of the bundle holding their rows and, for the records, their
            dataset.
        MODELS (ClassVar[Dict[str, type[BaseModel]]]): The model of the rows of each list of the bundle.
        GROUPS (ClassVar[List[str]]): The fields a new row copies from the selected one (the rows of a company).
        edited (pyqtSignal): Emitted once an edit is written.
        message (pyqtSignal): Emitted with what happened, for the status line of the manager.
        file (CuratedFile): The catalogue edited.
        loop (StorageLoop): The storage thread of the GUI.
        part (Optional[CuratedBundle]): The stored rows of the catalogue, `None` until read.
        section_box (QComboBox): Picks the section shown.
        filter_edit (QLineEdit): Filters the rows by key, content or note.
        model (CuratedRowModel): The rows of the section shown.
        table (QTableView): Shows them.
        new_button, edit_button, delete_button (QPushButton): Create, change or remove a row.
        accept_button, reject_button (QPushButton): Confirm or reject the identifiers a resolver proposed.
        logger (Logger): The tab logger.

    Notes:
        - An edit is the rows the catalogue should hold: the storage thread assembles them into their catalogue and
          writes them only when it is valid (`storage.catalog_editor`), else the refusal is shown and nothing is
          written.
        - A row created or changed here is marked as changed by a person: a seed never writes over it. Accepting or
          rejecting a candidate identifier keeps its origin (the resolver) and marks it changed.
    """

    SECTIONS: ClassVar[Dict[CuratedFile, List[Tuple[str, str, Optional[CuratedDataset]]]]] = {
        CuratedFile.CHRONOLOGY: [
            ("As of", "records", CuratedDataset.CHRONOLOGY_AS_OF),
            ("Segments", "records", CuratedDataset.CHRONOLOGY_SEGMENTS),
            ("Companies", "records", CuratedDataset.CHRONOLOGY_COMPANIES),
            ("Reigns", "records", CuratedDataset.CHRONOLOGY_REIGNS),
            ("Events", "records", CuratedDataset.CHRONOLOGY_EVENTS),
        ],
        CuratedFile.MARKETS: [
            ("Segments", "records", CuratedDataset.MARKETS_SEGMENTS),
            ("Areas", "records", CuratedDataset.MARKETS_AREAS),
            ("Labels", "records", CuratedDataset.MARKETS_LABELS),
            ("Currencies", "records", CuratedDataset.MARKETS_CURRENCIES),
            ("Country currencies", "records", CuratedDataset.MARKETS_COUNTRY_CURRENCIES),
            ("Regions", "records", CuratedDataset.MARKETS_REGIONS),
            ("Listings", "records", CuratedDataset.MARKETS_LISTINGS),
            ("Valuations", "records", CuratedDataset.MARKETS_VALUATIONS),
            ("Press", "records", CuratedDataset.MARKETS_PRESS),
            ("Press names", "records", CuratedDataset.MARKETS_PRESS_NAMES),
            ("Manual shares", "records", CuratedDataset.MARKETS_MANUAL_SHARES),
        ],
        CuratedFile.COMPANIES: [("Companies", "profiles", None), ("Identifiers", "identifiers", None)],
        CuratedFile.FIGURES: [
            ("Companies", "figure_companies", None),
            ("Fiscal years", "figure_years", None),
            ("Events", "figure_events", None),
        ],
        CuratedFile.LAUNCHES: [
            ("Launches", "launches", None),
            ("Aliases", "records", CuratedDataset.LAUNCH_ALIASES),
        ],
    }
    MODELS: ClassVar[Dict[str, type[BaseModel]]] = {
        "records": CuratedRecord,
        "profiles": CompanyProfile,
        "identifiers": CompanyIdentifier,
        "figure_companies": ReportedCompanyRecord,
        "figure_years": ReportedYearRecord,
        "figure_events": ReportedEventRecord,
        "launches": ProductLaunch,
    }
    GROUPS: ClassVar[List[str]] = ["company", "kind", "crawler"]

    edited = pyqtSignal()
    message = pyqtSignal(str)

    def __init__(self, theme: Theme, loop: StorageLoop, file: CuratedFile, logger: Optional[Logger] = None) -> None:
        """Build the tab, read when shown.

        Args:
            theme (Theme): The application theme.
            loop (StorageLoop): The storage thread of the GUI.
            file (CuratedFile): The catalogue edited.
            logger (Optional[Logger]): The tab logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.file = file
        self.loop = loop
        self.part: Optional[CuratedBundle] = None
        self.section_box = QComboBox()
        for title, _, _ in self.SECTIONS[file]:
            self.section_box.addItem(title)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by key, content or note")
        self.filter_edit.setClearButtonEnabled(True)
        self.model = CuratedRowModel(theme, self.logger)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(CuratedRowModel.CONTENT, QHeaderView.ResizeMode.Stretch)
        self.new_button = QPushButton("New…")
        self.edit_button = QPushButton("Edit…")
        self.delete_button = QPushButton("Delete")
        self.accept_button = QPushButton("Accept")
        self.accept_button.setToolTip("Confirm the identifier a resolver proposed: the crawls use it")
        self.reject_button = QPushButton("Reject")
        self.reject_button.setToolTip("Reject the identifier a resolver proposed: it is never proposed again")
        self._build_layout()
        self.section_box.currentIndexChanged.connect(self._refresh)
        self.filter_edit.textChanged.connect(self._refresh)
        self.table.doubleClicked.connect(self.edit)
        self.new_button.clicked.connect(self.add_row)
        self.edit_button.clicked.connect(self.edit)
        self.delete_button.clicked.connect(self.delete)
        self.accept_button.clicked.connect(lambda: self.decide(IdentifierStatus.CONFIRMED))
        self.reject_button.clicked.connect(lambda: self.decide(IdentifierStatus.REJECTED))
        self._refresh()
        self.logger.debug("Catalogue tab of the %s built.", file.value)

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_layout(self) -> None:
        """Lay the section picker, the filter, the table and the buttons out."""
        top = QHBoxLayout()
        top.addWidget(self.section_box)
        top.addWidget(self.filter_edit, 1)
        buttons = QHBoxLayout()
        for button in (self.new_button, self.edit_button, self.delete_button, self.accept_button, self.reject_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addLayout(buttons)

    def _section(self) -> Tuple[str, str, Optional[CuratedDataset]]:
        """Get the section shown.

        Returns:
            Tuple[str, str, Optional[CuratedDataset]]: Its title, the list of the bundle holding its rows and their
                dataset.
        """
        return self.SECTIONS[self.file][max(self.section_box.currentIndex(), 0)]

    def _rows(self) -> List[CuratedRowValues]:
        """Get the rows of the section shown.

        Returns:
            List[CuratedRowValues]: Its rows, as stored, in their order.
        """
        if self.part is None:
            return []
        _, field, dataset = self._section()
        rows: List[CuratedRowValues] = self.part.model_dump(mode="json")[field]
        return [row for row in rows if dataset is None or row.get("dataset") == dataset.value]

    def _selected(self) -> Optional[int]:
        """Get the selected row.

        Returns:
            Optional[int]: Its index among the rows of the section, `None` without selection.
        """
        selection = self.table.selectionModel()
        rows = selection.selectedRows() if selection is not None else []
        return self.model.index_of(rows[0].row()) if rows else None

    def _refresh(self) -> None:
        """Show the rows of the section picked, filtered, and the buttons they allow."""
        self.model.set_rows(self._rows(), self.filter_edit.text())
        _, field, _ = self._section()
        self.accept_button.setVisible(field == "identifiers")
        self.reject_button.setVisible(field == "identifiers")
        for button in (self.new_button, self.edit_button, self.delete_button, self.accept_button, self.reject_button):
            button.setEnabled(self.part is not None)

    def _template(self) -> CuratedRowValues:
        """Get the values a new row of the section starts from.

        Returns:
            CuratedRowValues: The dataset of the section, the last rank plus one, and the company, kind or crawler of
                the selected row.
        """
        rows = self._rows()
        _, _, dataset = self._section()
        selected = self._selected()
        values: CuratedRowValues = {"position": max((int(str(row["position"])) for row in rows), default=-1) + 1}
        if dataset is not None:
            values["dataset"] = dataset.value
        if selected is not None:
            values.update({name: rows[selected][name] for name in self.GROUPS if name in rows[selected]})
        return values

    def _on_part(self, part: CuratedBundle) -> None:
        """Show the rows read.

        Args:
            part (CuratedBundle): The stored rows of the catalogue.
        """
        self.part = part
        self._refresh()
        self.logger.debug("Curated %s shown in the manager.", self.file.value)

    def _on_error(self, error: StorageError) -> None:
        """Report a read or a write which failed.

        Args:
            error (StorageError): The error.
        """
        self.logger.warning("The curated %s cannot be read or written: %s", self.file.value, error)
        self.message.emit(f"The {self.file.value} catalogue cannot be read or written: {error}")
        self._refresh()

    def _load(self) -> None:
        """Read the stored rows of the catalogue."""
        self.logger.debug("Reading the curated %s for the manager.", self.file.value)
        self.loop.submit(lambda storage: storage.catalog_editor.part(self.file), self._on_part, self._on_error)

    async def _save_job(self, storage: Storage, part: CuratedBundle) -> str:
        """Write an edit of the catalogue, once it is valid (storage thread).

        Args:
            storage (Storage): The open storage.
            part (CuratedBundle): The rows the catalogue should hold.

        Returns:
            str: What happened, for the status line.

        Raises:
            StorageError: If the rows cannot be read or written.
        """
        try:
            changes = await storage.catalog_editor.save(self.file, part)
        except CuratedError as e:
            self.logger.warning("The edit of the curated %s is refused: %s", self.file.value, e)
            return f"Refused, nothing was written: {e}"
        return f"{self.file.value.capitalize()}: {changes} rows written."

    def _on_saved(self, message: str) -> None:
        """Report a write, and read the catalogue again.

        Args:
            message (str): What happened.
        """
        self.message.emit(message)
        self.logger.info("Curated %s edit over: %s", self.file.value, message)
        self._load()
        if not message.startswith("Refused"):
            self.edited.emit()

    def _save(self, rows: List[CuratedRowValues]) -> None:
        """Write the rows of the section shown, those of the other sections kept.

        Args:
            rows (List[CuratedRowValues]): The rows the section should hold.
        """
        if self.part is None:
            self.logger.warning("The curated %s are not read yet: nothing is written.", self.file.value)
            return
        _, field, dataset = self._section()
        content = self.part.model_dump(mode="json")
        others = [row for row in content[field] if dataset is not None and row.get("dataset") != dataset.value]
        content[field] = [*others, *rows]
        try:
            part = CuratedBundle.model_validate(content)
        except ValidationError as e:
            self.logger.warning("The edit of the curated %s is invalid: %s", self.file.value, e)
            self.message.emit(f"Invalid edit, nothing was written: {e.error_count()} errors.")
            return
        self.message.emit(f"Writing the {self.file.value} catalogue…")
        self.loop.submit(lambda storage: self._save_job(storage, part), self._on_saved, self._on_error)

    ############################
    # Publicly Exposed Methods #
    ############################

    def load(self) -> None:
        """Read the stored rows of the catalogue."""
        self._load()

    def add_row(self) -> None:
        """Create a row of the section shown, from a form."""
        title, field, _ = self._section()
        dialog = RowEditorDialog(f"New row: {title}", self.MODELS[field], self._template(), self.logger)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_values is None:
            return
        self._save([*self._rows(), dialog.result_values])

    def edit(self) -> None:
        """Change the selected row, from a form."""
        selected = self._selected()
        if selected is None:
            self.message.emit("Select a row to edit.")
            return
        title, field, _ = self._section()
        rows = self._rows()
        dialog = RowEditorDialog(f"Edit: {title}", self.MODELS[field], rows[selected], self.logger)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_values is None:
            return
        rows[selected] = dialog.result_values
        self._save(rows)

    def delete(self) -> None:
        """Remove the selected row, once confirmed."""
        selected = self._selected()
        if selected is None:
            self.message.emit("Select a row to delete.")
            return
        rows = self._rows()
        answer = QMessageBox.question(self, "Delete the row", f"Delete {self.model.describe(rows[selected])}?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._save([row for index, row in enumerate(rows) if index != selected])

    def decide(self, status: IdentifierStatus) -> None:
        """Confirm or reject the selected identifier.

        Args:
            status (IdentifierStatus): Confirmed or rejected.
        """
        selected = self._selected()
        rows = self._rows()
        if selected is None or "status" not in rows[selected]:
            self.message.emit("Select an identifier to accept or reject.")
            return
        rows[selected] = {**rows[selected], "status": status.value, "edited": True}
        self._save(rows)
