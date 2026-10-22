from __future__ import annotations

from decimal import Decimal

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTabWidget, QVBoxLayout

# First Party Imports.
from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.manager.labels_editor import LabelsEditor
from gui.taxonomy.manager.taxonomy_editor import TaxonomyEditor
from gui.taxonomy.manager.unclassified_panel import UnclassifiedPanel
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from llm.exception import LLMConfigurationFileError, LLMError
from llm.settings_loader import LLMSettingsLoader
from llm.tasks.item_classifier import ItemClassifier
from llm.tasks.label_translator import LabelTranslator
from models.configuration.llm.enums import LLMTask
from models.configuration.llm.llm_settings import LLMSettings
from storage.exception import StorageError
from storage.storage import Storage


class CategoriesManager(QDialog):
    """The window editing the unified taxonomy and the source labels, and sorting out the unclassified items.

    Attributes:
        MINIMUM_SIZE (ClassVar[Tuple[int, int]]): The smallest size of the window, in pixels.
        edited (pyqtSignal): Emitted once an edit is written (the views read the categories again).
        loop (StorageLoop): The storage thread of the GUI.
        cache (TaxonomyCache): The taxonomy shared with the views.
        taxonomy_editor (TaxonomyEditor): The categories tab.
        labels_editor (LabelsEditor): The source labels tab.
        unclassified_panel (UnclassifiedPanel): The unclassified items tab.
        tabs (QTabWidget): The three tabs.
        status_label (QLabel): What happened last.
        recompute_button (QPushButton): Categorizes every stored item again.
        llm_settings (LLMSettings): The language model settings (`conf/llm.yaml`).
        translate_button (QPushButton): Translates the pending labels with the language model (shown when configured).
        classify_button (QPushButton): Categorizes the unclassified items with the language model (shown when
            configured).
        cost_label (QLabel): What the language model calls spent, of the budget.
        logger (Logger): The manager logger.

    Notes:
        - The window is not modal: the views stay usable while it is open, and follow its edits.
        - Every edit is written by the storage thread, then the items it concerns are categorized again in the same
          job: the tables, pickers and charts read them at their next refresh.
        - The language model actions are shown only when a model of the task has its API key. They stop at the budget
          ceiling (the work done so far is kept).
    """

    MINIMUM_SIZE: ClassVar[Tuple[int, int]] = (1100, 640)

    edited = pyqtSignal()

    def __init__(
        self,
        theme: Theme,
        loop: StorageLoop,
        cache: TaxonomyCache,
        logger: Optional[Logger] = None,
        llm_settings: Optional[LLMSettings] = None,
    ) -> None:
        """Build the window, read when shown.

        Args:
            theme (Theme): The application theme.
            loop (StorageLoop): The storage thread of the GUI.
            cache (TaxonomyCache): The taxonomy shared with the views.
            logger (Optional[Logger]): The manager logger.
            llm_settings (Optional[LLMSettings]): The language model settings, read from `conf/llm.yaml` by default.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        if llm_settings is None:
            try:
                llm_settings = LLMSettingsLoader(self.logger).load()
            except LLMConfigurationFileError as e:
                self.logger.warning("The language model settings cannot be read, no model is offered: %s", e)
                llm_settings = LLMSettings()
        self.llm_settings = llm_settings
        self.loop = loop
        self.cache = cache
        self.setWindowTitle("Categories manager")
        self.setMinimumSize(*self.MINIMUM_SIZE)
        self.taxonomy_editor = TaxonomyEditor(theme, loop, cache, self.logger)
        self.labels_editor = LabelsEditor(theme, loop, cache, self.logger)
        self.unclassified_panel = UnclassifiedPanel(theme, loop, cache, self.logger)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.taxonomy_editor, "Categories")
        self.tabs.addTab(self.labels_editor, "Source labels")
        self.tabs.addTab(self.unclassified_panel, "Unclassified")
        self.status_label = QLabel()
        self.status_label.setObjectName("muted")
        self.recompute_button = QPushButton("Recompute every item")
        self.recompute_button.setToolTip(
            "Categorize every stored product and software again with the current taxonomy and labels"
        )
        self.translate_button = QPushButton("Translate pending labels")
        self.translate_button.setToolTip("Translate the pending labels and link them to the taxonomy (language model)")
        self.translate_button.setVisible(llm_settings.is_configured(LLMTask.LABEL_TRANSLATION))
        self.classify_button = QPushButton("Classify unclassified items")
        self.classify_button.setToolTip("File the items left under Other under categories (language model)")
        self.classify_button.setVisible(llm_settings.is_configured(LLMTask.ITEM_CLASSIFICATION))
        self.cost_label = QLabel()
        self.cost_label.setObjectName("muted")
        self.cost_label.setVisible(self.translate_button.isVisible() or self.classify_button.isVisible())
        close = QPushButton("Close")
        footer = QHBoxLayout()
        footer.addWidget(self.status_label, 1)
        footer.addWidget(self.cost_label)
        footer.addWidget(self.translate_button)
        footer.addWidget(self.classify_button)
        footer.addWidget(self.recompute_button)
        footer.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(footer)
        for tab in (self.taxonomy_editor, self.labels_editor, self.unclassified_panel):
            tab.message.connect(self.status_label.setText)
            tab.edited.connect(self._on_edited)
        self.recompute_button.clicked.connect(self.recompute)
        self.translate_button.clicked.connect(self.translate)
        self.classify_button.clicked.connect(self.classify)
        close.clicked.connect(self.close)
        self.logger.debug("Categories manager built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _on_spent(self, spent: Decimal) -> None:
        """Show what the language model calls spent.

        Args:
            spent (Decimal): The cost of the recorded calls.
        """
        budget = self.llm_settings.llm_budget
        self.cost_label.setText(f"Language model: {spent:.2f} of {budget.ceiling:.2f} {budget.currency}")

    def _on_cost_error(self, error: StorageError) -> None:
        """Leave the spending unknown when it cannot be read.

        Args:
            error (StorageError): The error.
        """
        self.logger.warning("The language model spending cannot be read: %s", error)
        self.cost_label.setText("Language model: spending unknown")

    async def _spent_job(self, storage: Storage) -> Decimal:
        """Read what the language model calls spent (storage thread).

        Args:
            storage (Storage): The open storage.

        Returns:
            Decimal: The cost of the recorded calls.
        """
        return await storage.llm_usage.spent(self.llm_settings.llm_budget.currency)

    def _refresh_cost(self) -> None:
        """Read the language model spending again, when a model is offered."""
        if self.translate_button.isHidden() and self.classify_button.isHidden():
            return
        self.loop.submit(self._spent_job, self._on_spent, self._on_cost_error)

    def _load(self) -> None:
        """Read the taxonomy, the labels and the unclassified items."""
        self.logger.debug("Reading the Categories manager.")
        self.status_label.setText("Reading the categories…")
        self.taxonomy_editor.load()
        self.labels_editor.load()
        self.unclassified_panel.load()
        self._refresh_cost()

    def _on_edited(self) -> None:
        """Read every tab and the shared taxonomy again after an edit, and tell the views."""
        self.logger.debug("An edit of the Categories manager is written.")
        self.cache.load()
        self.unclassified_panel.load()
        self.edited.emit()

    def _on_recomputed(self, changed: int) -> None:
        """Report the end of a full recomputation.

        Args:
            changed (int): The number of items whose categorization changed.
        """
        self.recompute_button.setEnabled(True)
        self.status_label.setText(f"Every item categorized again: {changed:,} changed.")
        self.logger.info("Every item categorized again from the manager: %d changed.", changed)
        self._load()
        self.edited.emit()

    def _on_error(self, error: StorageError) -> None:
        """Report a full recomputation which failed.

        Args:
            error (StorageError): The error.
        """
        self.recompute_button.setEnabled(True)
        self.status_label.setText(f"The items cannot be categorized again: {error}")
        self.logger.warning("The items cannot be categorized again: %s", error)

    async def _recompute_job(self, storage: Storage) -> int:
        """Categorize every stored item again (storage thread).

        Args:
            storage (Storage): The open storage.

        Returns:
            int: The number of items whose categorization changed.
        """
        return await storage.recategorize()

    async def _translate_job(self, storage: Storage) -> str:
        """Translate the pending labels with the language model (storage thread).

        Args:
            storage (Storage): The open storage.

        Returns:
            str: What happened, for the status line.
        """
        try:
            translated = await LabelTranslator(storage, self.llm_settings, logger=self.logger).run()
        except LLMError as e:
            self.logger.warning("The label translation stopped: %s", e)
            return f"The label translation stopped: {e}"
        return f"{translated:,} labels translated by the language model."

    async def _classify_job(self, storage: Storage) -> str:
        """Categorize the unclassified items with the language model (storage thread).

        Args:
            storage (Storage): The open storage.

        Returns:
            str: What happened, for the status line.
        """
        try:
            classified = await ItemClassifier(storage, self.llm_settings, logger=self.logger).run()
        except LLMError as e:
            self.logger.warning("The item classification stopped: %s", e)
            return f"The item classification stopped: {e}"
        return f"{classified:,} items categorized by the language model."

    def _on_model_done(self, message: str) -> None:
        """Report a language model action, and read everything again.

        Args:
            message (str): What happened.
        """
        self.translate_button.setEnabled(True)
        self.classify_button.setEnabled(True)
        self.status_label.setText(message)
        self.logger.info("Language model action over: %s", message)
        self.cache.load()
        self._load()
        self.edited.emit()

    def _on_model_error(self, error: StorageError) -> None:
        """Report a language model action which failed on the storage.

        Args:
            error (StorageError): The error.
        """
        self.translate_button.setEnabled(True)
        self.classify_button.setEnabled(True)
        self.status_label.setText(f"The language model action failed: {error}")
        self.logger.warning("A language model action failed: %s", error)

    ############################
    # Publicly Exposed Methods #
    ############################
    def recompute(self) -> None:
        """Categorize every stored item again (e.g. after editing many labels)."""
        self.logger.info("Every item is categorized again from the manager.")
        self.recompute_button.setEnabled(False)
        self.status_label.setText("Categorizing every item again… (a few minutes for 100,000 items)")
        self.loop.submit(self._recompute_job, self._on_recomputed, self._on_error)

    def open_on(self, tab: int = 0) -> None:
        """Show the window on a tab, reading it.

        Args:
            tab (int): The tab shown: 0 categories, 1 source labels, 2 unclassified items.
        """
        self.tabs.setCurrentIndex(tab)
        self._load()
        self.show()
        self.raise_()
        self.activateWindow()

    def load(self) -> None:
        """Read the taxonomy, the labels and the unclassified items."""
        self._load()

    def translate(self) -> None:
        """Translate the pending labels with the language model."""
        self.logger.info("Translation of the pending labels requested.")
        self.translate_button.setEnabled(False)
        self.status_label.setText("Translating the pending labels…")
        self.loop.submit(self._translate_job, self._on_model_done, self._on_model_error)

    def classify(self) -> None:
        """Categorize the unclassified items with the language model."""
        self.logger.info("Classification of the unclassified items requested.")
        self.classify_button.setEnabled(False)
        self.status_label.setText("Categorizing the unclassified items…")
        self.loop.submit(self._classify_job, self._on_model_done, self._on_model_error)
