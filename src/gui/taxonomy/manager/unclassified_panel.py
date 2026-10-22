from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from pydantic import JsonValue
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from gui.selection.taxonomy.category_tree import CategoryTree
from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.storage.enums import DatasetKind, ItemField
from models.storage.pages.item_query import ItemQuery
from models.taxonomy.facets.unclassified_count import UnclassifiedCount
from storage.exception import StorageError
from storage.storage import Storage


class UnclassifiedPanel(QWidget):
    """The unclassified tab of the Categories manager: the share of items nothing categorized, and their list.

    Attributes:
        ITEM_LIMIT (ClassVar[int]): The largest number of unclassified items listed for a dataset.
        COUNT_HEADERS (ClassVar[List[str]]): The columns of the shares.
        edited (pyqtSignal): Emitted once categories were assigned by hand.
        message (pyqtSignal): Emitted with what happened, for the status line of the manager.
        theme (Theme): The application theme.
        loop (StorageLoop): The storage thread of the GUI.
        cache (TaxonomyCache): The taxonomy offered when assigning categories.
        counts_table (QTableWidget): The listed and unclassified items of each dataset, the largest share first.
        items_table (QTableWidget): The unclassified items of the selected dataset.
        assign_button (QPushButton): Assigns categories to the selected items (pinned: set by hand).
        counts (List[UnclassifiedCount]): The counts shown.
        item_ids (List[int]): The identifiers of the listed items, by row.
        logger (Logger): The panel logger.

    Notes:
        The categories assigned here are set by hand: the crawls and the rules never change them.
    """

    ITEM_LIMIT: ClassVar[int] = 1000
    COUNT_HEADERS: ClassVar[List[str]] = ["Dataset", "Provider", "Listed", "Unclassified", "Share"]

    edited = pyqtSignal()
    message = pyqtSignal(str)

    def __init__(self, theme: Theme, loop: StorageLoop, cache: TaxonomyCache, logger: Optional[Logger] = None) -> None:
        """Build the tab, empty until `load`.

        Args:
            theme (Theme): The application theme.
            loop (StorageLoop): The storage thread of the GUI.
            cache (TaxonomyCache): The taxonomy offered when assigning categories.
            logger (Optional[Logger]): The panel logger.
        """
        super().__init__()
        self.theme = theme
        self.loop = loop
        self.cache = cache
        self.logger = logger if logger else getLogger(__name__)
        self.counts: List[UnclassifiedCount] = []
        self.item_ids: List[int] = []
        self.counts_table = QTableWidget(0, len(self.COUNT_HEADERS))
        self.counts_table.setHorizontalHeaderLabels(self.COUNT_HEADERS)
        self.items_table = QTableWidget(0, 2)
        self.items_table.setHorizontalHeaderLabels(["Item", "Description"])
        for table in (self.counts_table, self.items_table):
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setAlternatingRowColors(True)
            header = table.horizontalHeader()
            if header is not None:
                header.setStretchLastSection(True)
        self.counts_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.items_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.items_table.setColumnWidth(0, 280)
        self.assign_button = QPushButton("Assign categories…")
        self.assign_button.setToolTip("File the selected items under categories chosen by hand")
        self.assign_button.setEnabled(False)
        layout = QHBoxLayout(self)
        left, right = QVBoxLayout(), QVBoxLayout()
        left.addWidget(QLabel("Items filed under Other, by dataset"))
        left.addWidget(self.counts_table, 1)
        right.addWidget(QLabel("Unclassified items of the selected dataset"))
        right.addWidget(self.items_table, 1)
        right.addWidget(self.assign_button, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(left, 2)
        layout.addLayout(right, 3)
        self.counts_table.itemSelectionChanged.connect(self._on_dataset_selected)
        self.items_table.itemSelectionChanged.connect(self._on_items_selected)
        self.assign_button.clicked.connect(self._on_assign)
        self.logger.debug("Unclassified panel built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _load(self) -> None:
        """Count the unclassified items of every dataset again."""
        self.logger.debug("Counting the unclassified items.")
        self.loop.submit(self._counts_job, self._on_counts, self._on_error)

    def _dataset(self) -> Optional[UnclassifiedCount]:
        """Get the selected dataset.

        Returns:
            Optional[UnclassifiedCount]: Its counts, `None` without selection.
        """
        rows = {index.row() for index in self.counts_table.selectedIndexes()}
        row = min(rows) if rows else -1
        return self.counts[row] if 0 <= row < len(self.counts) else None

    def _on_counts(self, counts: List[UnclassifiedCount]) -> None:
        """Show the counts of every dataset.

        Args:
            counts (List[UnclassifiedCount]): The counts, the largest share first.
        """
        self.counts = counts
        self.counts_table.setRowCount(len(counts))
        for row, count in enumerate(counts):
            cells = [
                count.kind.value.capitalize(),
                self.theme.provider_label(count.provider),
                f"{count.total:,}",
                f"{count.unclassified:,}",
                f"{count.share():.1f} %",
            ]
            for column, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if column >= 2:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.counts_table.setItem(row, column, cell)
        unclassified = sum(count.unclassified for count in counts)
        total = sum(count.total for count in counts)
        share = unclassified / total * 100 if total else 0.0
        self.message.emit(f"{unclassified:,} of {total:,} listed items unclassified ({share:.1f} %).")
        self.logger.debug("Unclassified counts of %d datasets shown.", len(counts))

    def _on_error(self, error: StorageError) -> None:
        """Report a read or an assignment which failed.

        Args:
            error (StorageError): The error.
        """
        self.logger.warning("The unclassified items cannot be read or changed: %s", error)
        self.message.emit(f"The unclassified items cannot be read or changed: {error}")

    def _on_assigned(self, changed: int) -> None:
        """Read everything again once categories were assigned.

        Args:
            changed (int): The number of items changed.
        """
        self.logger.info("Categories assigned by hand to %d items.", changed)
        self.message.emit(f"Categories assigned to {changed:,} items.")
        self._load()
        self.edited.emit()

    async def _counts_job(self, storage: Storage) -> List[UnclassifiedCount]:
        """Count the unclassified items of every dataset (storage thread).

        Args:
            storage (Storage): The open storage.

        Returns:
            List[UnclassifiedCount]: The counts, the largest share first.
        """
        counts = [*await storage.catalogues.unclassified(), *await storage.marketplaces.unclassified()]
        return sorted(counts, key=lambda count: (-count.share(), count.kind.value, count.provider.value))

    async def _items_job(
        self, storage: Storage, kind: DatasetKind, provider: CloudProvider
    ) -> List[Tuple[int, str, str]]:
        """Read the unclassified items of a dataset (storage thread).

        Args:
            storage (Storage): The open storage.
            kind (DatasetKind): The kind of the dataset.
            provider (CloudProvider): Its provider.

        Returns:
            List[Tuple[int, str, str]]: The identifier, name and description of each item, by name.
        """
        query = ItemQuery(providers=[provider], service_categories=["other"], limit=self.ITEM_LIMIT, with_total=False)
        if kind is DatasetKind.CATALOGUE:
            products = await storage.catalogues.list(query)
            return sorted(
                ((stored.id, *stored.item.name_and_description()) for stored in products.items), key=lambda one: one[1]
            )
        software = await storage.marketplaces.list(query)
        return sorted(
            ((stored.id, *stored.item.name_and_description()) for stored in software.items), key=lambda one: one[1]
        )

    async def _assign_job(self, storage: Storage, kind: DatasetKind, item_ids: List[int], slugs: List[str]) -> int:
        """File items under categories set by hand (storage thread).

        Args:
            storage (Storage): The open storage.
            kind (DatasetKind): The kind of the items.
            item_ids (List[int]): The items.
            slugs (List[str]): Their categories.

        Returns:
            int: The number of items changed.
        """
        categories: List[JsonValue] = [*slugs]
        repository = storage.catalogues if kind is DatasetKind.CATALOGUE else storage.marketplaces
        return await repository.update_many(item_ids, {ItemField.SERVICE_CATEGORIES: categories})

    def _on_items_selected(self) -> None:
        """Enable the assignment while items are selected."""
        self.assign_button.setEnabled(bool(self.items_table.selectedIndexes()))

    def _on_items(self, items: List[Tuple[int, str, str]]) -> None:
        """Show the unclassified items of the selected dataset.

        Args:
            items (List[Tuple[int, str, str]]): The identifier, name and description of each item.
        """
        self.item_ids = [item_id for item_id, _, _ in items]
        self.items_table.setRowCount(len(items))
        for row, (_, name, description) in enumerate(items):
            self.items_table.setItem(row, 0, QTableWidgetItem(name))
            described = QTableWidgetItem(description)
            described.setToolTip(description)
            self.items_table.setItem(row, 1, described)
        self._on_items_selected()

    def _on_dataset_selected(self) -> None:
        """List the unclassified items of the selected dataset."""
        dataset = self._dataset()
        if dataset is None:
            self._on_items([])
            return
        kind, provider = dataset.kind, dataset.provider
        self.loop.submit(lambda storage: self._items_job(storage, kind, provider), self._on_items, self._on_error)

    def _pick_categories(self) -> List[str]:
        """Ask for the categories to assign.

        Returns:
            List[str]: The checked categories, empty when the dialog is cancelled.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("Assign categories")
        tree = CategoryTree(self.cache, self.logger)
        tree.setMinimumHeight(420)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("The items are filed under the checked categories (set by hand)."))
        layout.addWidget(tree, 1)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return []
        return tree.checked()

    def _on_assign(self) -> None:
        """Assign categories chosen by hand to the selected items."""
        dataset = self._dataset()
        rows = sorted({index.row() for index in self.items_table.selectedIndexes()})
        ids = [self.item_ids[row] for row in rows if row < len(self.item_ids)]
        if dataset is None or not ids:
            return
        slugs = self._pick_categories()
        if not slugs:
            self.message.emit("No category chosen: nothing assigned.")
            return
        kind = dataset.kind
        self.message.emit(f"Assigning {len(slugs)} categories to {len(ids)} items…")
        self.loop.submit(lambda storage: self._assign_job(storage, kind, ids, slugs), self._on_assigned, self._on_error)

    ############################
    # Publicly Exposed Methods #
    ############################

    def load(self) -> None:
        """Count the unclassified items of every dataset again."""
        self._load()
