from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import QItemSelectionModel, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.manager.label_table_model import LabelTableModel
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from models.taxonomy.enums import LabelStatus, Language
from models.taxonomy.labels.label_details import LabelDetails
from storage.exception import StorageError
from storage.storage import Storage


class LabelsEditor(QWidget):
    """The source labels tab of the Categories manager: translate, link, merge and sort out the labels.

    Attributes:
        ANY (ClassVar[str]): The label of the "any value" entry of the filters.
        edited (pyqtSignal): Emitted once an edit is written and its items categorized again.
        message (pyqtSignal): Emitted with what happened, for the status line of the manager.
        theme (Theme): The application theme.
        loop (StorageLoop): The storage thread of the GUI.
        cache (TaxonomyCache): The taxonomy, naming the nodes.
        model (LabelTableModel): The labels shown.
        table (QTableView): The table of the labels.
        status_box, language_box, provider_box (QComboBox): The filters.
        find_box (QLineEdit): Finds the labels containing a text.
        name_box (QLineEdit): The English name of the selected label.
        node_box (QComboBox): The category (or domain) to link or unlink.
        merge_box (QComboBox): The label to merge the selected one into, with completion.
        buttons (List[QPushButton]): The action buttons, enabled with a selected label.
        logger (Logger): The editor logger.

    Notes:
        - Every edit is made by a person: the rules, the seed and the language model never overwrite it.
        - The items of the edited labels (and of their aliases) are categorized again in the same storage job.
    """

    ANY: ClassVar[str] = "Any"

    edited = pyqtSignal()
    message = pyqtSignal(str)

    def __init__(self, theme: Theme, loop: StorageLoop, cache: TaxonomyCache, logger: Optional[Logger] = None) -> None:
        """Build the tab, empty until `load`.

        Args:
            theme (Theme): The application theme.
            loop (StorageLoop): The storage thread of the GUI.
            cache (TaxonomyCache): The taxonomy, naming the nodes.
            logger (Optional[Logger]): The editor logger.
        """
        super().__init__()
        self.theme = theme
        self.loop = loop
        self.cache = cache
        self.logger = logger if logger else getLogger(__name__)
        self.model = LabelTableModel(theme, cache, self.logger)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionModel(QItemSelectionModel(self.model))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(True)
        self.status_box, self.language_box, self.provider_box = QComboBox(), QComboBox(), QComboBox()
        self.status_box.addItem(self.ANY, None)
        for status in LabelStatus:
            self.status_box.addItem(status.value.capitalize(), status.value)
        self.language_box.addItem(self.ANY, None)
        for language in Language:
            self.language_box.addItem(TaxonomyCache.LANGUAGE_NAMES[language.value], language.value)
        self.provider_box.addItem(self.ANY, None)
        self.find_box = QLineEdit()
        self.find_box.setPlaceholderText("Find a label…")
        self.find_box.setClearButtonEnabled(True)
        self.name_box = QLineEdit()
        self.name_box.setPlaceholderText("English name")
        self.node_box = QComboBox()
        self.merge_box = QComboBox()
        self.merge_box.setEditable(True)
        self.merge_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.buttons: List[QPushButton] = []
        self._build_layout()
        self._fill_nodes()
        for box in (self.status_box, self.language_box, self.provider_box):
            box.currentIndexChanged.connect(self._apply_filter)
        self.find_box.textChanged.connect(self._apply_filter)
        selection = self.table.selectionModel()
        if selection is not None:
            selection.selectionChanged.connect(self._on_selection_changed)
        self.cache.changed.connect(self._fill_nodes)
        self._on_selection_changed()
        self.logger.debug("Labels editor built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _load(self) -> None:
        """Read the labels again."""
        self.logger.debug("Reading the labels for the editor.")
        self.loop.submit(lambda storage: storage.labels.list(), self._on_labels, self._on_error)

    def _button(self, text: str, tooltip: str) -> QPushButton:
        """Build an action button, enabled with a selected label.

        Args:
            text (str): Its text.
            tooltip (str): What it does.

        Returns:
            QPushButton: The button.
        """
        button = QPushButton(text)
        button.setToolTip(tooltip)
        self.buttons.append(button)
        return button

    def _fill_nodes(self) -> None:
        """Offer the domains and categories to link, keeping the choice."""
        chosen = self.node_box.currentData()
        self.node_box.blockSignals(True)
        self.node_box.clear()
        taxonomy = self.cache.taxonomy
        for domain in taxonomy.domains():
            self.node_box.addItem(f"{domain.name_en} (whole domain)", domain.slug)
            for node in taxonomy.children(domain.slug):
                if not node.hidden:
                    self.node_box.addItem(self.cache.path(node.slug), node.slug)
        self.node_box.setCurrentIndex(max(self.node_box.findData(chosen), 0))
        self.node_box.blockSignals(False)
        self.logger.debug("%d taxonomy nodes offered to link.", self.node_box.count())

    def _fill_labels(self, labels: List[LabelDetails]) -> None:
        """Offer the labels to merge into, and the datasets to filter on.

        Args:
            labels (List[LabelDetails]): Every label read.
        """
        self.merge_box.blockSignals(True)
        self.merge_box.clear()
        for label in sorted(labels, key=lambda label: label.display_name().casefold()):
            if label.canonical_id is None:
                suffix = "" if label.display_name() == label.text else f" ({label.text})"
                self.merge_box.addItem(f"{label.display_name()}{suffix}", label.id)
        completer = QCompleter([self.merge_box.itemText(row) for row in range(self.merge_box.count())], self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.merge_box.setCompleter(completer)
        self.merge_box.setEditText("")
        self.merge_box.blockSignals(False)
        chosen = self.provider_box.currentData()
        self.provider_box.blockSignals(True)
        self.provider_box.clear()
        self.provider_box.addItem(self.ANY, None)
        for dataset in sorted({seen for label in labels for seen in label.providers}):
            self.provider_box.addItem(dataset.replace(":", " · "), dataset)
        self.provider_box.setCurrentIndex(max(self.provider_box.findData(chosen), 0))
        self.provider_box.blockSignals(False)

    def _apply_filter(self) -> None:
        """Show the labels matching the filters."""
        status, language = self.status_box.currentData(), self.language_box.currentData()
        self.model.set_filter(
            LabelStatus(status) if status else None,
            Language(language) if language else None,
            self.provider_box.currentData(),
            self.find_box.text(),
        )
        self.message.emit(f"{self.model.rowCount():,} of {len(self.model.labels):,} labels shown.")

    def _selected(self) -> List[LabelDetails]:
        """Get the selected labels.

        Returns:
            List[LabelDetails]: The labels of the selected rows, in their order.
        """
        selection = self.table.selectionModel()
        rows = sorted({index.row() for index in selection.selectedRows()}) if selection is not None else []
        return [label for row in rows if (label := self.model.label(row)) is not None]

    def _on_selection_changed(self) -> None:
        """Show the English name of the selected label, and enable the actions."""
        selected = self._selected()
        for button in self.buttons:
            button.setEnabled(bool(selected))
        self.name_box.setText(selected[0].name_en or "" if len(selected) == 1 else "")
        self.name_box.setEnabled(len(selected) == 1)

    def _on_labels(self, labels: List[LabelDetails]) -> None:
        """Show the labels read.

        Args:
            labels (List[LabelDetails]): Every stored label.
        """
        self.logger.debug("%d labels read for the editor.", len(labels))
        self.model.set_labels(labels)
        self._fill_labels(labels)
        self._apply_filter()

    def _on_error(self, error: StorageError) -> None:
        """Report an edit or a read which failed.

        Args:
            error (StorageError): The error.
        """
        self.logger.warning("A label edit failed: %s", error)
        self.message.emit(f"The labels cannot be changed: {error}")

    def _on_done(self, changed: int) -> None:
        """Read the labels again once an edit is written, and tell the manager.

        Args:
            changed (int): The number of items categorized again.
        """
        self.logger.info("Label edit written: %d items categorized again.", changed)
        self.message.emit(f"Saved: {changed:,} items categorized again.")
        self._load()
        self.edited.emit()

    async def _rename_job(self, storage: Storage, label_id: int, name: str) -> int:
        """Rename a label, then categorize its items again (storage thread).

        Args:
            storage (Storage): The open storage.
            label_id (int): The label.
            name (str): Its English name.

        Returns:
            int: The number of items categorized again.
        """
        return await storage.recategorize(label_ids=await storage.labels.update(label_id, name))

    async def _link_job(self, storage: Storage, label_ids: Sequence[int], slug: str, linked: bool) -> int:
        """Link labels to a node, or unlink them, then categorize their items again (storage thread).

        Args:
            storage (Storage): The open storage.
            label_ids (Sequence[int]): The labels.
            slug (str): The node.
            linked (bool): Whether they tell the node.

        Returns:
            int: The number of items categorized again.
        """
        affected: List[int] = []
        for label_id in label_ids:
            affected += await storage.labels.link(label_id, slug, linked)
        return await storage.recategorize(label_ids=sorted(set(affected)))

    async def _merge_job(self, storage: Storage, label_ids: Sequence[int], canonical_id: Optional[int]) -> int:
        """Merge labels into another one, or undo their merges, then categorize their items again (storage thread).

        Args:
            storage (Storage): The open storage.
            label_ids (Sequence[int]): The labels.
            canonical_id (Optional[int]): The label they are merged into, `None` to undo the merges.

        Returns:
            int: The number of items categorized again.
        """
        affected: List[int] = []
        for label_id in label_ids:
            if label_id != canonical_id:
                affected += await storage.labels.merge(label_id, canonical_id)
        return await storage.recategorize(label_ids=sorted(set(affected)))

    async def _status_job(self, storage: Storage, label_ids: Sequence[int], status: LabelStatus) -> int:
        """Set the status of labels, then categorize their items again (storage thread).

        Args:
            storage (Storage): The open storage.
            label_ids (Sequence[int]): The labels.
            status (LabelStatus): Their status.

        Returns:
            int: The number of items categorized again.
        """
        return await storage.recategorize(label_ids=await storage.labels.set_status(label_ids, status))

    def _on_rename(self) -> None:
        """Write the English name of the selected label."""
        selected = self._selected()
        if len(selected) != 1:
            return
        label_id, name = selected[0].id, self.name_box.text()
        self.message.emit("Saving the English name…")
        self.loop.submit(lambda storage: self._rename_job(storage, label_id, name), self._on_done, self._on_error)

    def _on_link(self, linked: bool) -> None:
        """Link the selected labels to the chosen node, or unlink them.

        Args:
            linked (bool): Whether they tell the node.
        """
        ids, slug = [label.id for label in self._selected()], self.node_box.currentData()
        if not ids or not slug:
            return
        self.message.emit("Saving the links…")
        self.loop.submit(lambda storage: self._link_job(storage, ids, str(slug), linked), self._on_done, self._on_error)

    def _on_merge(self, merged: bool) -> None:
        """Merge the selected labels into the chosen one, or undo their merges.

        Args:
            merged (bool): Whether they are merged (`False`: unmerged).
        """
        ids = [label.id for label in self._selected()]
        index = self.merge_box.findText(self.merge_box.currentText())
        canonical = self.merge_box.itemData(index) if merged and index >= 0 else None
        if not ids or (merged and canonical is None):
            self.message.emit("Choose the label to merge into." if ids else "")
            return
        target = int(canonical) if canonical is not None else None
        self.message.emit("Saving the merge…")
        self.loop.submit(lambda storage: self._merge_job(storage, ids, target), self._on_done, self._on_error)

    def _on_status(self, status: LabelStatus) -> None:
        """Set the status of the selected labels.

        Args:
            status (LabelStatus): Their status.
        """
        ids = [label.id for label in self._selected()]
        if not ids:
            return
        self.message.emit(f"Marking {len(ids)} labels as {status.value}…")
        self.loop.submit(lambda storage: self._status_job(storage, ids, status), self._on_done, self._on_error)

    def _build_layout(self) -> None:
        """Lay the filters and the table out on the left, the actions on the right."""
        filters = QHBoxLayout()
        for caption, widget in (
            ("Status", self.status_box),
            ("Language", self.language_box),
            ("Seen in", self.provider_box),
        ):
            filters.addWidget(QLabel(caption))
            filters.addWidget(widget)
        filters.addWidget(self.find_box, 1)
        rename = self._button("Rename", "Set the English name: the label joins the labels of the same name")
        link = self._button("Link", "File the items of the label under this category (or domain)")
        unlink = self._button("Unlink", "Never file the items of the label under it, whatever the rules")
        merge = self._button("Merge", "Make the label an alias of another one: its items count as the other's")
        unmerge = self._button("Unmerge", "Undo the merge of the label")
        noise = self._button("Noise", "The label is not a category (a tab, a vendor, 'Other'): it files nothing")
        reviewed = self._button("Reviewed", "The translation and the links are checked")
        pending = self._button("Pending", "The label waits for its translation")
        rename.clicked.connect(self._on_rename)
        link.clicked.connect(lambda: self._on_link(True))
        unlink.clicked.connect(lambda: self._on_link(False))
        merge.clicked.connect(lambda: self._on_merge(True))
        unmerge.clicked.connect(lambda: self._on_merge(False))
        noise.clicked.connect(lambda: self._on_status(LabelStatus.NOISE))
        reviewed.clicked.connect(lambda: self._on_status(LabelStatus.REVIEWED))
        pending.clicked.connect(lambda: self._on_status(LabelStatus.PENDING))
        form = QFormLayout()
        name_row = QHBoxLayout()
        name_row.addWidget(self.name_box, 1)
        name_row.addWidget(rename)
        node_row = QHBoxLayout()
        node_row.addWidget(link)
        node_row.addWidget(unlink)
        merge_row = QHBoxLayout()
        merge_row.addWidget(merge)
        merge_row.addWidget(unmerge)
        status_row = QHBoxLayout()
        for button in (noise, reviewed, pending):
            status_row.addWidget(button)
        form.addRow("English name", name_row)
        form.addRow("Category", self.node_box)
        form.addRow("", node_row)
        form.addRow("Merge into", self.merge_box)
        form.addRow("", merge_row)
        form.addRow("Mark as", status_row)
        actions = QGroupBox("Selected label")
        actions.setLayout(form)
        actions.setMinimumWidth(360)
        left = QVBoxLayout()
        left.addLayout(filters)
        left.addWidget(self.table, 1)
        layout = QHBoxLayout(self)
        layout.addLayout(left, 1)
        layout.addWidget(actions, 0, Qt.AlignmentFlag.AlignTop)
        self.logger.debug("Labels editor laid out.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def load(self) -> None:
        """Read the labels again."""
        self._load()
