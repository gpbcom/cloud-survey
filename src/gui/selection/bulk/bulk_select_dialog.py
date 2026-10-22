from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Callable, ClassVar, Dict, List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

# First Party Imports.
from gui.marketplace.widgets.advanced_filters import AdvancedSoftwareFilters
from gui.selection.pickers.provider_tree import ProviderTree
from gui.selection.pickers.value_checklist import ValueChecklist
from gui.selection.taxonomy.category_tree import CategoryTree
from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from models.cloud.categorized_item import CategorizedItem
from models.cloud.enums import CloudProvider, DeliveryMethod, SoftwareCategory
from models.storage.enums import DeletedState, SelectionAction
from models.storage.pages.item_query import ItemQuery
from models.storage.pages.software_facets import SoftwareFacets
from models.taxonomy.labels.label_count import LabelCount
from storage.exception import StorageError
from storage.repositories.item_repository import ItemRepository
from storage.storage import Storage


class BulkSelectDialog[T: CategorizedItem](QDialog):
    """Choose stored items by criteria, counted live by the server, to show them, export them or delete them.

    Attributes:
        COUNT_DELAY_MS (ClassVar[int]): How long the criteria must stay unchanged before the items are counted.
        SEARCH_LENGTH (ClassVar[int]): The longest searched text.
        DELETED_LABELS (ClassVar[Dict[DeletedState, str]]): The label of each deletion state.
        theme (Theme): The application theme.
        loop (StorageLoop): The storage thread of the GUI.
        repository (Callable[[Storage], ItemRepository[T]]): Gets the repository of the items.
        base (ItemQuery): The query of the table the dialog was opened from (its order is kept).
        software (bool): Whether the items are marketplace software (with their audience and delivery).
        tree (ProviderTree): The chosen cloud providers, under their country.
        all_button, none_button (QPushButton): Check or uncheck every provider.
        search_box (QLineEdit): Text contained in the item name (and publisher).
        description_box (QCheckBox): Searches the descriptions too.
        deleted_box (QComboBox): The listed items, the deleted ones, or both.
        category_list, delivery_list (Optional[ValueChecklist]): The audiences and deliveries of the software
            (`None` for products), none checked meaning any.
        category_tree (Optional[CategoryTree]): The taxonomy categories of the items (`None` without a taxonomy),
            none checked meaning any.
        advanced (AdvancedSoftwareFilters): The filters on every other field.
        count_label (QLabel): How many items match.
        filter_button, export_button, delete_button (QPushButton): What is done with the matching items.
        count_timer (QTimer): Delays the count while the criteria change.
        generation (int): The number of counts requested, so that only the latest count is shown.
        count (Optional[int]): The number of matching items, `None` until counted.
        chosen (Optional[SelectionAction]): What to do with the items, `None` when the dialog is closed.
        logger (Logger): The dialog logger.

    Notes:
        The dialog starts from the main filters of the table
        (providers, search, deleted items, categories, and the
        audience and delivery of the software): the other
        filters start cleared. No item is read: the server counts
        them, and `query` describes them to the action chosen.
    """

    COUNT_DELAY_MS: ClassVar[int] = 250
    SEARCH_LENGTH: ClassVar[int] = 200
    DELETED_LABELS: ClassVar[Dict[DeletedState, str]] = {
        DeletedState.LISTED: "Listed items only",
        DeletedState.ALL: "Listed and deleted items",
        DeletedState.DELETED: "Deleted items only",
    }

    def __init__(
        self,
        theme: Theme,
        loop: StorageLoop,
        repository: Callable[[Storage], ItemRepository[T]],
        providers: Sequence[CloudProvider],
        base: ItemQuery,
        software: bool,
        logger: Optional[Logger] = None,
        taxonomy: Optional[TaxonomyCache] = None,
    ) -> None:
        """Build the dialog from the filters of a table, then count the matching items.

        Args:
            theme (Theme): The application theme.
            loop (StorageLoop): The storage thread of the GUI.
            repository (Callable[[Storage], ItemRepository[T]]): Gets the repository of the items.
            providers (Sequence[CloudProvider]): The cloud providers which can be chosen.
            base (ItemQuery): The query of the table.
            software (bool): Whether the items are marketplace software.
            logger (Optional[Logger]): The dialog logger.
            taxonomy (Optional[TaxonomyCache]): The taxonomy offering the categories, no category criterion when
                `None`.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.theme = theme
        self.loop = loop
        self.repository = repository
        self.base = base
        self.software = software
        self.generation = 0
        self.count: Optional[int] = None
        self.chosen: Optional[SelectionAction] = None
        self.setWindowTitle(f"Select {'software' if software else 'products'}")
        self.tree = ProviderTree(theme, providers, self.logger)
        self.all_button, self.none_button = QPushButton("All"), QPushButton("None")
        self.search_box = QLineEdit()
        self.search_box.setMaxLength(self.SEARCH_LENGTH)
        self.search_box.setPlaceholderText(f"Name{' or publisher' if software else ''} contains…")
        self.search_box.setClearButtonEnabled(True)
        self.description_box = QCheckBox("In descriptions")
        self.deleted_box = QComboBox()
        for state, label in self.DELETED_LABELS.items():
            self.deleted_box.addItem(label, state.value)
        self.category_list: Optional[ValueChecklist] = None
        self.delivery_list: Optional[ValueChecklist] = None
        if software:
            self.category_list = ValueChecklist(
                {value.value: theme.category_label(value) for value in SoftwareCategory}
            )
            self.delivery_list = ValueChecklist({value.value: theme.delivery_label(value) for value in DeliveryMethod})
        self.category_tree = CategoryTree(taxonomy, self.logger) if taxonomy is not None else None
        self.advanced = AdvancedSoftwareFilters(theme, self.logger, software_fields=software)
        self.count_label = QLabel()
        self.count_label.setObjectName("muted")
        self.filter_button = QPushButton("Show in the table")
        self.filter_button.setToolTip("Show only the matching items in the table, until the selection is cleared")
        self.export_button = QPushButton("Export…")
        self.export_button.setToolTip("Export the matching items to a CSV, JSON or JSON lines file")
        self.delete_button = QPushButton("Delete…")
        self.delete_button.setToolTip("Delete the matching items and their history, once confirmed")
        self.count_timer = QTimer(self)
        self.count_timer.setSingleShot(True)
        self.count_timer.setInterval(self.COUNT_DELAY_MS)
        self._build_layout()
        self._load(base)
        self._connect()
        self._request_count()
        self.logger.debug("Bulk selection dialog of %s built.", "software" if software else "products")

    ############################
    # Internal Helpers Methods #
    ############################

    def _checklists(self) -> Dict[str, ValueChecklist]:
        """Get the checklists of the software, by title.

        Returns:
            Dict[str, ValueChecklist]: The audience and delivery checklists, empty for products.
        """
        lists = {"Audience": self.category_list, "Delivery": self.delivery_list}
        return {title: checklist for title, checklist in lists.items() if checklist is not None}

    def _build_layout(self) -> None:
        """Lay the providers out on the left, the criteria on the right, then the count and the actions."""
        providers = QVBoxLayout()
        providers.addWidget(QLabel("Cloud providers"))
        providers.addWidget(self.tree, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(self.all_button)
        buttons.addWidget(self.none_button)
        providers.addLayout(buttons)
        form = QFormLayout()
        search = QHBoxLayout()
        search.addWidget(self.search_box, 1)
        search.addWidget(self.description_box)
        form.addRow("Search", search)
        form.addRow("Deleted items", self.deleted_box)
        lists = QHBoxLayout()
        for title, checklist in self._checklists().items():
            column = QVBoxLayout()
            column.addWidget(QLabel(title))
            column.addWidget(checklist)
            lists.addLayout(column)
        if self.category_tree is not None:
            column = QVBoxLayout()
            column.addWidget(QLabel("Categories"))
            column.addWidget(self.category_tree)
            lists.addLayout(column, 1)
        criteria = QVBoxLayout()
        criteria.addLayout(form)
        criteria.addLayout(lists)
        criteria.addWidget(self.advanced)
        criteria.addStretch(1)
        body = QHBoxLayout()
        body.addLayout(providers)
        body.addLayout(criteria, 1)
        actions = QHBoxLayout()
        actions.addWidget(self.count_label, 1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        for button in (self.filter_button, self.export_button, self.delete_button, close_button):
            actions.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addLayout(actions)
        self.logger.debug("Bulk selection dialog laid out.")

    def _load(self, base: ItemQuery) -> None:
        """Start from the main filters of the table.

        Args:
            base (ItemQuery): The query of the table.
        """
        self.tree.set_checked(base.providers or self.tree.providers)
        self.search_box.setText(base.search or "")
        self.description_box.setChecked(base.search_description)
        state = DeletedState.ALL if base.include_deleted else DeletedState.LISTED
        self.deleted_box.setCurrentIndex(self.deleted_box.findData(state.value))
        for checklist, values in (
            (self.category_list, [value.value for value in base.categories]),
            (self.delivery_list, [value.value for value in base.deliveries]),
        ):
            if checklist is not None:
                checklist.set_checked(values)
        if self.category_tree is not None:
            self.category_tree.set_picked(base.service_categories)
        self.logger.debug("Bulk selection started from the table filters (%d providers).", len(base.providers))

    def _on_criteria_changed(self) -> None:
        """Forget the count of the former criteria at once, then count again once they stop changing.

        Notes:
            A count still being read for the former criteria is ignored when it comes.
        """
        self.generation += 1
        self.count = None
        self.count_label.setText("Counting…")
        for button in (self.export_button, self.delete_button):
            button.setEnabled(False)
        self.count_timer.start()

    def _choose(self, action: SelectionAction) -> None:
        """Close the dialog with what to do with the matching items.

        Args:
            action (SelectionAction): The action.
        """
        if not self.tree.checked():
            self.logger.warning("No provider checked: nothing to %s.", action.value)
            self.count_label.setText("Check at least one cloud provider.")
            return
        if action is not SelectionAction.FILTER and not self.count:
            self.logger.warning("Nothing counted to %s yet (%s).", action.value, self.count)
            self.count_label.setText("Wait for the count of the matching items.")
            return
        self.logger.info("Bulk selection: %s (%s items).", action.value, self.count)
        self.chosen = action
        self.accept()

    def _connect(self) -> None:
        """Count the matching items again once a criterion changes, and bind the actions."""
        self.count_timer.timeout.connect(self._request_count)
        self.tree.changed.connect(self._on_criteria_changed)
        self.search_box.textChanged.connect(self._on_criteria_changed)
        self.description_box.toggled.connect(self._on_criteria_changed)
        self.deleted_box.currentIndexChanged.connect(self._on_criteria_changed)
        self.advanced.changed.connect(self._on_criteria_changed)
        for checklist in self._checklists().values():
            checklist.changed.connect(self._on_criteria_changed)
        if self.category_tree is not None:
            self.category_tree.changed.connect(self._on_criteria_changed)
        self.all_button.clicked.connect(lambda: self.tree.check_all(True))
        self.none_button.clicked.connect(lambda: self.tree.check_all(False))
        self.filter_button.clicked.connect(lambda: self._choose(SelectionAction.FILTER))
        self.export_button.clicked.connect(lambda: self._choose(SelectionAction.EXPORT))
        self.delete_button.clicked.connect(lambda: self._choose(SelectionAction.DELETE))
        self.logger.debug("Bulk selection criteria connected.")

    def _checked(self, title: str) -> Sequence[str]:
        """Get the checked values of a software checklist.

        Args:
            title (str): The checklist title.

        Returns:
            Sequence[str]: The checked values, none for products.
        """
        checklist = self._checklists().get(title)
        return checklist.checked() if checklist is not None else []

    def _query(self) -> ItemQuery:
        """Describe the matching items.

        Returns:
            ItemQuery: The criteria of the dialog, in the order of the table.
                No checked provider gives a query
                without providers: check `providers` before using it.
        """
        state = DeletedState(self.deleted_box.currentData())
        query = self.advanced.apply(
            self.base.model_copy(
                update={
                    "providers": self.tree.checked(),
                    "search": self.search_box.text().strip() or None,
                    "search_description": self.description_box.isChecked(),
                    "include_deleted": state is not DeletedState.LISTED,
                    "categories": [SoftwareCategory(value) for value in self._checked("Audience")],
                    "service_categories": self.category_tree.picked() if self.category_tree else [],
                    "deliveries": [DeliveryMethod(value) for value in self._checked("Delivery")],
                    "offset": 0,
                }
            )
        )
        if state is DeletedState.DELETED:
            query = query.model_copy(update={"deleted": query.deleted.model_copy(update={"known": True})})
        return query

    def _show_count(self, generation: int, count: int) -> None:
        """Show how many items match, unless the criteria changed meanwhile (GUI thread).

        Args:
            generation (int): The count request.
            count (int): The number of matching items.
        """
        if generation != self.generation:
            self.logger.debug("Stale count %d of request %d ignored.", count, generation)
            return
        self.count = count
        self.count_label.setText(f"{count:,} {'software' if self.software else 'products'} match")
        self.export_button.setEnabled(count > 0)
        self.delete_button.setEnabled(count > 0)
        self.export_button.setText(f"Export {count:,}…" if count else "Export…")
        self.delete_button.setText(f"Delete {count:,}…" if count else "Delete…")
        self.logger.debug("%d items match the bulk selection.", count)

    def _on_count_failed(self, error: StorageError) -> None:
        """Show that the items cannot be counted (GUI thread).

        Args:
            error (StorageError): The error.
        """
        self.logger.warning("The bulk selection cannot be counted: %s", error)
        self.count = None
        self.count_label.setText(f"Cannot count the items: {error}")

    def _request_count(self) -> None:
        """Count the matching items in the storage thread."""
        self._on_criteria_changed()
        self.count_timer.stop()
        generation, query = self.generation, self._query()
        if not query.providers:
            self.logger.debug("No provider checked: nothing matches.")
            self._show_count(generation, 0)
            return
        self.logger.debug("Counting the bulk selection (request %d).", generation)
        self.loop.submit(
            lambda storage: self.repository(storage).count(query),
            lambda count: self._show_count(generation, count),
            self._on_count_failed,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def query(self) -> ItemQuery:
        """Describe the matching items.

        Returns:
            ItemQuery: The criteria of the dialog, in the order of the table (no provider when none is checked).
        """
        return self._query()

    def set_pickers(self, facets: SoftwareFacets) -> None:
        """Fill the pickers of the other filters (publishers and categories) with their counts.

        Args:
            facets (SoftwareFacets): The counts of the listed software.
        """
        self.logger.debug("Filling the pickers of the bulk selection.")
        self.advanced.set_pickers(facets)

    def set_labels(self, counts: List[LabelCount]) -> None:
        """Fill the source label picker of the other filters with the labels of the listed items.

        Args:
            counts (List[LabelCount]): The labels of the listed items (see `ItemRepository.label_counts`).
        """
        self.logger.debug("Filling the source label picker of the bulk selection.")
        self.advanced.set_labels(counts)

    def choose(self, action: SelectionAction) -> None:
        """Close the dialog with what to do with the matching items, once they are counted.

        Args:
            action (SelectionAction): The action.
        """
        self._choose(action)
