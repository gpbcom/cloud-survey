from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import Awaitable, Callable, ClassVar, Dict, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox, QWidget

# First Party Imports.
from gui.paging.identified_row import IdentifiedRow
from gui.paging.page.paged_table_model import PagedTableModel
from gui.selection.bulk.bulk_select_dialog import BulkSelectDialog
from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from models.cloud.categorized_item import CategorizedItem
from models.cloud.enums import CloudProvider
from models.storage.enums import ExportFormat, SelectionAction
from models.storage.pages.item_query import ItemQuery
from models.storage.pages.software_facets import SoftwareFacets
from storage.exception import StorageError
from storage.exporter.item_exporter import ItemExporter
from storage.repositories.item_repository import ItemRepository
from storage.storage import Storage


class SelectionActions[T: CategorizedItem, R: IdentifiedRow](QObject):
    """The bulk selection of a table: choose items by criteria in a dialog, then show, export or delete them.

    Attributes:
        FILE_FILTERS (ClassVar[Dict[str, ExportFormat]]): The export file types, by file dialog filter.
        DELETE_CONFIRMATION (ClassVar[str]): The question asked before deleting.
        filter_requested (pyqtSignal): Emitted with the `ItemQuery` of the items the table must show.
        changed (pyqtSignal): Emitted with a summary once items were exported or deleted.
        failed (pyqtSignal): Emitted with the reason when an export or a deletion fails.
        theme (Theme): The application theme.
        model (PagedTableModel[T, R]): The paged model of the table.
        loop (StorageLoop): The storage thread of the GUI.
        repository (Callable[[Storage], ItemRepository[T]]): Gets the repository of the items.
        providers (List[CloudProvider]): The cloud providers which can be chosen.
        software (bool): Whether the items are marketplace software.
        pickers (Optional[Callable[[Storage], Awaitable[SoftwareFacets]]]): Reads the counts filling the pickers of
            the dialog (publishers and marketplace categories), `None` for products.
        parent_widget (QWidget): The widget the dialogs and the shortcut belong to.
        taxonomy (Optional[TaxonomyCache]): The taxonomy offering the categories in the dialog.
        select_action (QAction): Opens the bulk selection dialog (Ctrl+Shift+A).
        logger (Logger): The actions logger.

    Notes:
        Nothing is read in the GUI: the server counts the chosen items, streams them to the export file
        (`ItemExporter`), or deletes them (`ItemRepository.delete_matching`).
    """

    FILE_FILTERS: ClassVar[Dict[str, ExportFormat]] = {
        "CSV (*.csv)": ExportFormat.CSV,
        "JSON (*.json)": ExportFormat.JSON,
        "JSON lines (*.jsonl)": ExportFormat.JSON_LINES,
    }
    DELETE_CONFIRMATION: ClassVar[str] = "Delete the {count:,} chosen items and their history? This cannot be undone."

    filter_requested = pyqtSignal(object)
    changed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        theme: Theme,
        model: PagedTableModel[T, R],
        loop: StorageLoop,
        repository: Callable[[Storage], ItemRepository[T]],
        providers: Sequence[CloudProvider],
        parent_widget: QWidget,
        pickers: Optional[Callable[[Storage], Awaitable[SoftwareFacets]]] = None,
        logger: Optional[Logger] = None,
        taxonomy: Optional[TaxonomyCache] = None,
    ) -> None:
        """Create the bulk selection of a table.

        Args:
            theme (Theme): The application theme.
            model (PagedTableModel[T, R]): The paged model of the table.
            loop (StorageLoop): The storage thread of the GUI.
            repository (Callable[[Storage], ItemRepository[T]]): Gets the repository of the items.
            providers (Sequence[CloudProvider]): The cloud providers which can be chosen.
            parent_widget (QWidget): The widget the dialogs and the shortcut belong to.
            pickers (Optional[Callable[[Storage], Awaitable[SoftwareFacets]]]): Reads the counts of the software
                pickers, `None` for products.
            logger (Optional[Logger]): The actions logger.
            taxonomy (Optional[TaxonomyCache]): The taxonomy offering the categories in the dialog, none by default.
        """
        super().__init__(parent_widget)
        self.logger = logger if logger else getLogger(__name__)
        self.theme = theme
        self.model = model
        self.loop = loop
        self.repository = repository
        self.providers = list(providers)
        self.software = pickers is not None
        self.pickers = pickers
        self.parent_widget = parent_widget
        self.taxonomy = taxonomy
        self.select_action = QAction("☑  Select…", parent_widget)
        self.select_action.setShortcut(QKeySequence("Ctrl+Shift+A"))
        self.select_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.select_action.setToolTip("Choose items by criteria, to show, export or delete them (Ctrl+Shift+A)")
        self.select_action.triggered.connect(self.select)
        parent_widget.addAction(self.select_action)
        self.logger.debug("Bulk selection of the %s ready.", "software" if self.software else "products")

    ############################
    # Internal Helpers Methods #
    ############################

    def _open(self, dialog: QDialog) -> bool:
        """Show a dialog and wait for its answer.

        Args:
            dialog (QDialog): The dialog.

        Returns:
            bool: Whether it was accepted.
        """
        dialog.setParent(self.parent_widget, dialog.windowFlags())
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self.logger.debug("Dialog %r %s.", dialog.windowTitle(), "accepted" if accepted else "closed")
        return accepted

    def _confirm(self, count: int) -> bool:
        """Ask before deleting the chosen items.

        Args:
            count (int): The number of items.

        Returns:
            bool: Whether the deletion is confirmed.
        """
        answer = QMessageBox.question(
            self.parent_widget,
            "Delete items",
            self.DELETE_CONFIRMATION.format(count=count),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        confirmed = answer == QMessageBox.StandardButton.Yes
        self.logger.debug("Deletion of %d items %s.", count, "confirmed" if confirmed else "cancelled")
        return confirmed

    def _export_path(self, path: Path, file_filter: str) -> Path:
        """Give an export file the extension of its format when it has none of the known ones.

        Args:
            path (Path): The chosen file.
            file_filter (str): The chosen file type.

        Returns:
            Path: The file, ending with `.csv`, `.json` or `.jsonl`.
        """
        if path.suffix.lower().lstrip(".") in set(ExportFormat):
            return path.with_suffix(path.suffix.lower())
        format_ = self.FILE_FILTERS.get(file_filter, ExportFormat.CSV)
        self.logger.debug("Export file %s given the %s extension.", path, format_.value)
        return path.with_name(f"{path.name}.{format_.value}")

    def _save_path(self, count: int) -> Optional[Path]:
        """Ask where to export the chosen items.

        Args:
            count (int): The number of items.

        Returns:
            Optional[Path]: The export file, `None` when cancelled.
        """
        name, file_filter = QFileDialog.getSaveFileName(
            self.parent_widget,
            f"Export {count:,} items",
            f"{'software' if self.software else 'products'}.csv",
            ";;".join(self.FILE_FILTERS),
        )
        if not name:
            self.logger.debug("Export cancelled.")
            return None
        return self._export_path(Path(name), file_filter)

    def _on_done(self, message: str, refresh: bool) -> None:
        """Report what was done (GUI thread).

        Args:
            message (str): What was done.
            refresh (bool): Whether the table is read again (items were deleted).
        """
        self.logger.info("%s", message)
        if refresh:
            self.model.refresh()
        self.changed.emit(message)

    def _on_error(self, error: StorageError) -> None:
        """Report a failed export or deletion (GUI thread).

        Args:
            error (StorageError): The error.
        """
        self.logger.warning("A bulk action failed: %s", error)
        self.failed.emit(str(error))

    def _export(self, query: ItemQuery, count: int) -> None:
        """Export the chosen items to a file chosen by the user.

        Args:
            query (ItemQuery): The chosen items.
            count (int): Their number.
        """
        path = self._save_path(count)
        if path is None:
            return
        format_ = ExportFormat(path.suffix.lstrip("."))
        self.logger.info("Exporting %d items to %s.", count, path)
        self.loop.submit(
            lambda storage: ItemExporter(self.repository(storage), self.logger).export(query, path, format_),
            lambda written: self._on_done(f"{written:,} items exported to {path}.", False),
            self._on_error,
        )

    def _delete(self, query: ItemQuery, count: int) -> None:
        """Delete the chosen items, once confirmed.

        Args:
            query (ItemQuery): The chosen items.
            count (int): Their number.
        """
        if not self._confirm(count):
            return
        self.logger.info("Deleting %d chosen items.", count)
        self.loop.submit(
            lambda storage: self.repository(storage).delete_matching(query),
            lambda removed: self._on_done(f"{removed:,} items deleted.", True),
            self._on_error,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def select(self) -> None:
        """Open the bulk selection dialog from the filters of the table, then do what was chosen."""
        dialog = BulkSelectDialog[T](
            self.theme,
            self.loop,
            self.repository,
            self.providers,
            self.model.query,
            self.software,
            self.logger,
            self.taxonomy,
        )
        if self.pickers is not None:
            self.loop.submit(self.pickers, dialog.set_pickers, self._on_error)
        self.loop.submit(
            lambda storage: self.repository(storage).label_counts(ItemQuery()), dialog.set_labels, self._on_error
        )
        if not self._open(dialog) or dialog.chosen is None:
            return
        query, count = dialog.query(), dialog.count or 0
        match dialog.chosen:
            case SelectionAction.FILTER:
                self.logger.info("Showing the %d chosen items in the table.", count)
                self.filter_requested.emit(query)
            case SelectionAction.EXPORT:
                self._export(query, count)
            case SelectionAction.DELETE:
                self._delete(query, count)
