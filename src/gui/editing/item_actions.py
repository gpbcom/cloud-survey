from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Callable, ClassVar, Dict, List, Optional, Sequence, Tuple, Type

# Third Party Imports.
from pydantic import JsonValue
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QAbstractItemView, QDialog, QMessageBox, QTableView, QWidget

# First Party Imports.
from gui.editing.dialogs.bulk_edit_dialog import BulkEditDialog
from gui.editing.dialogs.item_editor_dialog import ItemEditorDialog
from gui.paging.identified_row import IdentifiedRow
from gui.paging.page.paged_table_model import PagedTableModel
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.cloud.categorized_item import CategorizedItem
from models.cloud.enums import CloudProvider
from models.storage.enums import ItemField
from models.storage.pages.item_query import ItemQuery
from models.storage.pages.stored_item import StoredItem
from storage.exception import StorageError
from storage.repositories.item_repository import ItemRepository
from storage.storage import Storage

RowRange = Tuple[int, int]


class ItemActions[T: CategorizedItem, R: IdentifiedRow](QObject):
    """The create, edit and delete actions of a table of stored items, on its selected rows (several at once).

    Attributes:
        DELETE_CONFIRMATION (ClassVar[str]): The question asked before deleting.
        changed (pyqtSignal): Emitted with a summary once items were created, changed or deleted.
        failed (pyqtSignal): Emitted with the reason when an action fails (e.g. the provider is being crawled).
        theme (Theme): The application theme.
        table (QTableView): The table of the items, its rows selected several at once.
        model (PagedTableModel[T, R]): The paged model of the table.
        loop (StorageLoop): The storage thread of the GUI.
        item_model (Type[T]): The model of the items.
        repository (Callable[[Storage], ItemRepository[T]]): Gets the repository of the items from the storage.
        providers (List[CloudProvider]): The cloud providers an item can be created for.
        parent_widget (QWidget): The widget the dialogs belong to.
        new_action, edit_action, delete_action (QAction): The actions, in the context menu of the table.
        logger (Logger): The actions logger.

    Notes:
        A selection may hold rows whose page is not read yet (e.g. a whole table selected): their identifiers are
        read from the storage with the query of the table (`ItemRepository.item_ids`), by ranges of rows.
        - **New** (Ctrl+N): a form creating an item by hand.
        - **Edit** (F2): the form of the item when one row is selected, the bulk edit form of the ticked fields else.
        - **Delete** (Del): removes the selected items, once confirmed.
        The table itself lists the items (page by page) and the details panel reads the current one.
    """

    DELETE_CONFIRMATION: ClassVar[str] = "Delete the {count:,} selected items and their history? This cannot be undone."

    changed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        theme: Theme,
        table: QTableView,
        model: PagedTableModel[T, R],
        loop: StorageLoop,
        item_model: Type[T],
        repository: Callable[[Storage], ItemRepository[T]],
        providers: Sequence[CloudProvider],
        parent_widget: QWidget,
        logger: Optional[Logger] = None,
    ) -> None:
        """Create the actions of a table.

        Args:
            theme (Theme): The application theme.
            table (QTableView): The table of the items.
            model (PagedTableModel[T, R]): The paged model of the table.
            loop (StorageLoop): The storage thread of the GUI.
            item_model (Type[T]): The model of the items.
            repository (Callable[[Storage], ItemRepository[T]]): Gets the repository of the items.
            providers (Sequence[CloudProvider]): The cloud providers an item can be created for.
            parent_widget (QWidget): The widget the dialogs and shortcuts belong to.
            logger (Optional[Logger]): The actions logger.
        """
        super().__init__(parent_widget)
        self.logger = logger if logger else getLogger(__name__)
        self.theme = theme
        self.table = table
        self.model = model
        self.loop = loop
        self.item_model = item_model
        self.repository = repository
        self.providers = list(providers)
        self.parent_widget = parent_widget
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.new_action = self._action("+  New…", "Ctrl+N", "Create an item by hand (Ctrl+N)", self.create)
        self.edit_action = self._action("✎  Edit…", "F2", "Edit the selected items (F2)", self.edit)
        self.delete_action = self._action("\U0001f5d1  Delete", "Del", "Delete the selected items (Del)", self.delete)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        for action in (self.new_action, self.edit_action, self.delete_action):
            self.table.addAction(action)
        selection = self.table.selectionModel()
        if selection is not None:
            selection.selectionChanged.connect(self._update_actions)
        self.model.modelReset.connect(self._update_actions)
        self._update_actions()
        self.logger.debug("Item actions of the %s table ready.", item_model.__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _action(self, text: str, shortcut: str, tip: str, slot: Callable[[], None]) -> QAction:
        """Build an action of the table, its shortcut active while the table (or its parent) has the focus.

        Args:
            text (str): The action text.
            shortcut (str): The keyboard shortcut.
            tip (str): The tooltip.
            slot (Callable[[], None]): What the action does.

        Returns:
            QAction: The action.
        """
        action = QAction(text, self.parent_widget)
        action.setShortcut(QKeySequence(shortcut))
        action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        action.setToolTip(tip)
        action.triggered.connect(slot)
        self.parent_widget.addAction(action)
        self.logger.debug("Action %r bound to %s.", text, shortcut)
        return action

    def _selected_rows(self) -> List[int]:
        """Get the selected rows of the table.

        Returns:
            List[int]: The row numbers, sorted.
        """
        selection = self.table.selectionModel()
        rows = sorted({index.row() for index in selection.selectedRows()}) if selection is not None else []
        self.logger.debug("%d rows selected.", len(rows))
        return rows

    def _update_actions(self) -> None:
        """Enable the actions which apply to the selection."""
        count = len(self._selected_rows())
        self.edit_action.setEnabled(count > 0)
        self.delete_action.setEnabled(count > 0)
        self.edit_action.setText("✎  Edit…" if count < 2 else f"✎  Edit {count:,}…")
        self.delete_action.setText("\U0001f5d1  Delete" if count < 2 else f"\U0001f5d1  Delete {count:,}")
        self.logger.debug("Actions updated for %d selected rows.", count)

    def _ranges(self, rows: Sequence[int]) -> List[RowRange]:
        """Group rows into ranges of consecutive rows.

        Args:
            rows (Sequence[int]): The sorted row numbers.

        Returns:
            List[RowRange]: The first row and the number of rows of each range.
        """
        ranges: List[RowRange] = []
        for row in rows:
            if ranges and ranges[-1][0] + ranges[-1][1] == row:
                ranges[-1] = (ranges[-1][0], ranges[-1][1] + 1)
            else:
                ranges.append((row, 1))
        self.logger.debug("%d rows grouped into %d ranges.", len(rows), len(ranges))
        return ranges

    async def _ids_of(self, storage: Storage, query: ItemQuery, ranges: Sequence[RowRange]) -> List[int]:
        """Read the identifiers of ranges of rows (storage thread).

        Args:
            storage (Storage): The open storage.
            query (ItemQuery): The query of the table.
            ranges (Sequence[RowRange]): The ranges of rows.

        Returns:
            List[int]: The identifiers of the rows, in their order.
        """
        repository = self.repository(storage)
        item_ids: List[int] = []
        for offset, count in ranges:
            item_ids += await repository.item_ids(query, offset, count)
        self.logger.debug("%d identifiers read for %d ranges.", len(item_ids), len(ranges))
        return item_ids

    def _resolve(self, rows: Sequence[int], on_ids: Callable[[List[int]], None]) -> None:
        """Get the identifiers of selected rows: from the kept pages, else from the storage.

        Args:
            rows (Sequence[int]): The selected rows.
            on_ids (Callable[[List[int]], None]): Called with the identifiers, in the GUI thread.
        """
        known = [self.model.loaded_id(row) for row in rows]
        if all(item_id is not None for item_id in known):
            self.logger.debug("The %d selected rows are kept: no read needed.", len(rows))
            on_ids([item_id for item_id in known if item_id is not None])
            return
        query, ranges = self.model.query, self._ranges(rows)
        self.logger.info("Reading the identifiers of %d selected rows (%d ranges).", len(rows), len(ranges))
        self.loop.submit(lambda storage: self._ids_of(storage, query, ranges), on_ids, self._on_error)

    def _open(self, dialog: QDialog) -> bool:
        """Show a dialog and wait for its answer.

        Args:
            dialog (QDialog): The dialog.

        Returns:
            bool: Whether it was accepted.
        """
        dialog.setParent(self.parent_widget, dialog.windowFlags())
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self.logger.debug("Dialog %r %s.", dialog.windowTitle(), "accepted" if accepted else "cancelled")
        return accepted

    def _confirm(self, count: int) -> bool:
        """Ask before deleting items.

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

    def _on_done(self, message: str) -> None:
        """Show the items as written, and tell the window (GUI thread).

        Args:
            message (str): What was done.
        """
        self.logger.info("%s", message)
        self.model.refresh()
        self.changed.emit(message)

    def _on_error(self, error: StorageError) -> None:
        """Report an action which failed (GUI thread).

        Args:
            error (StorageError): The error.
        """
        self.logger.warning("An item action failed: %s", error)
        self.failed.emit(str(error))

    def _on_created(self, stored: StoredItem[T]) -> None:
        """Report a created item.

        Args:
            stored (StoredItem[T]): The stored item.
        """
        self._on_done(f"Item {stored.id} created for {self.theme.provider_label(stored.provider)}.")

    def _on_saved(self, stored: Optional[StoredItem[T]]) -> None:
        """Report a saved item.

        Args:
            stored (Optional[StoredItem[T]]): The saved item, `None` when it was removed meanwhile.
        """
        if stored is None:
            self.logger.warning("The edited item no longer exists: it is not saved.")
            self.failed.emit("The edited item no longer exists: it is not saved.")
            self.model.refresh()
            return
        self._on_done(f"Item {stored.id} saved.")

    def _edit_one(self, stored: Optional[StoredItem[T]]) -> None:
        """Show the form of a stored item, then save it.

        Args:
            stored (Optional[StoredItem[T]]): The item, `None` when it was removed meanwhile.
        """
        if stored is None:
            self.logger.warning("The selected item no longer exists.")
            self.failed.emit("The selected item no longer exists.")
            return
        self.logger.debug("Showing the form of the item %d.", stored.id)
        dialog = ItemEditorDialog[T](self.theme, self.item_model, self.providers, stored.item, stored.provider)
        if not self._open(dialog) or dialog.result_item is None:
            self.logger.debug("The item %d is left unchanged.", stored.id)
            return
        item, item_id = dialog.result_item, stored.id
        self.logger.info("Saving the item %d.", item_id)
        self.loop.submit(
            lambda storage: self.repository(storage).update(item_id, item),
            self._on_saved,
            self._on_error,
        )

    def _edit_many(self, item_ids: List[int]) -> None:
        """Show the bulk edit form of selected items, then change them.

        Args:
            item_ids (List[int]): The identifiers of the selected items.
        """
        if len(item_ids) == 1:
            item_id = item_ids[0]
            self.logger.debug("Reading the item %d to edit it alone.", item_id)
            self.loop.submit(lambda storage: self.repository(storage).read(item_id), self._edit_one, self._on_error)
            return
        fields = [field for field in ItemField if field.value in self.item_model.model_fields]
        self.logger.debug("Showing the bulk edit form of %d items (%d fields).", len(item_ids), len(fields))
        dialog = BulkEditDialog(self.theme, fields, len(item_ids), self.logger)
        if not self._open(dialog):
            self.logger.debug("The bulk edit of %d items is cancelled.", len(item_ids))
            return
        changes: Dict[ItemField, JsonValue] = dialog.changes()
        self.logger.info("Changing %d fields of %d items.", len(changes), len(item_ids))
        self.loop.submit(
            lambda storage: self.repository(storage).update_many(item_ids, changes),
            lambda count: self._on_done(f"{count:,} items changed."),
            self._on_error,
        )

    def _delete_many(self, item_ids: List[int]) -> None:
        """Delete selected items, once confirmed.

        Args:
            item_ids (List[int]): The identifiers of the selected items.
        """
        if not self._confirm(len(item_ids)):
            self.logger.debug("The deletion of %d items is cancelled.", len(item_ids))
            return
        self.logger.info("Deleting %d items.", len(item_ids))
        self.loop.submit(
            lambda storage: self.repository(storage).delete_many(item_ids),
            lambda count: self._on_done(f"{count:,} items deleted."),
            self._on_error,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def create(self) -> None:
        """Show the form of a new item, then store it."""
        self.logger.debug("Creating an item by hand.")
        dialog = ItemEditorDialog[T](self.theme, self.item_model, self.providers, logger=self.logger)
        if not self._open(dialog) or dialog.result_item is None:
            return
        item, provider = dialog.result_item, dialog.provider()
        self.loop.submit(
            lambda storage: self.repository(storage).create(provider, item), self._on_created, self._on_error
        )

    def edit(self) -> None:
        """Edit the selected items: the form of one item, or the bulk edit form of several."""
        rows = self._selected_rows()
        if not rows:
            self.logger.debug("Nothing selected to edit.")
            return
        self.logger.info("Editing %d selected items.", len(rows))
        self._resolve(rows, self._edit_many)

    def delete(self) -> None:
        """Delete the selected items, once confirmed."""
        rows = self._selected_rows()
        if not rows:
            self.logger.debug("Nothing selected to delete.")
            return
        self.logger.info("Deleting %d selected items.", len(rows))
        self._resolve(rows, self._delete_many)
