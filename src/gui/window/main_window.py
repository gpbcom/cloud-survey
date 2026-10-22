from __future__ import annotations

import logging

# Standard Library Imports.
from functools import partial
from logging import Logger, getLogger
from typing import ClassVar, Dict, FrozenSet, List, Optional

# Third Party Imports.
from PyQt6.QtCore import QItemSelectionModel, QModelIndex, Qt, QThread, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTableView,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from crawler.enums import CrawlSource
from crawler.runner import CatalogueRunner
from gui.analysis.analysis_view import AnalysisView
from gui.charts.sections.chart_state_store import ChartStateStore
from gui.charts.sections.section.chart_section import ChartSection
from gui.correspondence.correspondence_view import CorrespondenceView
from gui.crawl_worker import CrawlWorker
from gui.editing.item_actions import ItemActions
from gui.layout.flow_layout import FlowLayout
from gui.layout.folding_dock import FoldingDock
from gui.layout.folding_splitter import FoldingSplitter
from gui.layout.panes.section_stack import SectionStack
from gui.layout.panes.side_pane import SidePane
from gui.log_bridge.qt_log_handler import QtLogHandler
from gui.marketplace.widgets.advanced_filters import AdvancedSoftwareFilters
from gui.marketplace.widgets.marketplace_view import MarketplaceView
from gui.product_model.product_row import ProductRow
from gui.product_model.product_table_model import ProductTableModel
from gui.selection.bulk.selection_actions import SelectionActions
from gui.selection.taxonomy.category_picker import CategoryPicker
from gui.statistics.view.statistics_view import StatisticsView
from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.manager.categories_manager import CategoriesManager
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from gui.widgets.compact_combo import CompactCombo
from gui.widgets.dashboard.dashboard import Dashboard
from gui.widgets.details.product_details import ProductDetails
from gui.widgets.log_panel import LogPanel
from gui.widgets.marketplace_menu import MarketplaceMenu
from gui.widgets.provider_sidebar import ProviderSidebar
from models.cloud.enums import CloudProvider, Country
from models.cloud.products.product import CloudProduct
from models.stats.market_statistics import MarketStatistics
from models.storage.dataset_stamp import DatasetStamp
from models.storage.enums import DatasetKind, ItemFilter, ItemSort
from models.storage.pages.item_query import ItemQuery
from storage.exception import StorageError


class MainWindow(QMainWindow):
    """Cloud catalogue explorer: browse the stored catalogues, marketplaces and statistics, and launch crawls.

    Attributes:
        TITLE (ClassVar[str]): The window title.
        STATISTICS_SOURCE (ClassVar[str]): The market statistics source shown in the statistics view.
        POLL_INTERVAL_MS (ClassVar[int]): How often the state of the stored datasets is read.
        SEARCH_DELAY_MS (ClassVar[int]): How long the search text must stay unchanged before it is searched.
        loop (StorageLoop): The storage thread of the GUI.
        runner (CatalogueRunner): The runner used by the crawls launched from the window, with its own storage.
        theme (Theme): The application theme.
        catalogues (Dict[CloudProvider, DatasetStamp]): The state of the stored catalogues.
        marketplaces (Dict[CloudProvider, DatasetStamp]): The state of the stored marketplaces.
        revisions (Dict[DatasetKind, Dict[str, int]]): The revision of each dataset when it was last shown.
        deleted (int): The number of stored products deleted from their website.
        provider (Optional[CloudProvider]): The only provider whose products are shown, `None` for all of them.
        country (Optional[Country]): The only country whose products are shown, `None` for all of them.
        crawl_thread (Optional[QThread]): The thread of the running crawl.
        crawl_worker (Optional[CrawlWorker]): The running crawl.
        crawl_source (CrawlSource): What the running (or last) crawl crawls.
        statistics (Optional[MarketStatistics]): The stored market statistics, `None` before the first crawl.
        storage_error (Optional[str]): Why the storage is unavailable, `None` while it answers.
        taxonomy (TaxonomyCache): The unified taxonomy and the names of the source labels, shared by the views.
        table_model (ProductTableModel): The products matching the filters, read page by page.
        store (ChartStateStore): The store of the chart states (expanded sections, chosen axes).
        available (Optional[FrozenSet[DatasetKind]]): The datasets holding data, `None` before the first read.
        product_actions (ItemActions[CloudProduct, ProductRow]): The create, edit and delete actions of the
            selected products (several rows at once, also in the context menu of the table).
        country_box (QComboBox): The country filter, with the number of listed products of each country.
        provider_box (QComboBox): The provider filter (the providers of the chosen country), following the sidebar.
        category_picker (CategoryPicker): The filter on the categories and domains of the unified taxonomy.
        selection_actions (SelectionActions[CloudProduct, ProductRow]): The bulk selection of the products (chosen
            by criteria, then shown, exported or deleted).
        selection_query (Optional[ItemQuery]): The bulk selection shown instead of the filters, `None` for none.
        select_button (QToolButton): Opens the bulk selection dialog.
        selection_button (QPushButton): Shown while the table shows a bulk selection: clears it.
        advanced (AdvancedSoftwareFilters): The filters on the other product fields (texts, catalogue category,
            dates), shown on request.
        more_button (QPushButton): Shows or hides the other filters, with the number of those set.
        table_section (ChartSection): The collapsible card of the product table.
        table_stack (SectionStack): Holds the product table card, folding when it is collapsed.
        details_pane (SidePane): Holds the product details, folding to a strip on request.
        log_dock (FoldingDock): The logs, folding to their title bar (or hidden, shown again from the View menu).
        view_menu (QMenu): Shows the logs and the details panels again, folded or hidden.
        taxonomy_menu (QMenu): Opens the Categories manager, or categorizes every item again.
        categories_manager (Optional[CategoriesManager]): The Categories manager, built when first opened.
        logs_button (QToolButton): Shows the logs again from the status bar, while they are folded or hidden.

    Notes:
        The window holds no dataset: every few seconds it reads the state of the stored datasets (`DatasetStamp`),
        and reads again the figures and the visible rows of those which changed (a running crawl writes its items
        every few seconds, they appear progressively).
    """

    TITLE: ClassVar[str] = "Cloud Catalogue Explorer"
    STATISTICS_SOURCE: ClassVar[str] = "synergy"
    POLL_INTERVAL_MS: ClassVar[int] = 2000
    SEARCH_DELAY_MS: ClassVar[int] = 300

    def __init__(
        self,
        loop: StorageLoop,
        runner: Optional[CatalogueRunner] = None,
        theme: Optional[Theme] = None,
        logger: Optional[Logger] = None,
        store: Optional[ChartStateStore] = None,
    ) -> None:
        """Build the window and read the stored datasets.

        Args:
            loop (StorageLoop): The storage thread of the GUI.
            runner (Optional[CatalogueRunner]): The runner of the crawls launched from the window.
            theme (Optional[Theme]): The application theme.
            logger (Optional[Logger]): The window logger.
            store (Optional[ChartStateStore]): The store of the chart states, remembered for the session by default.
        """
        super().__init__()
        self.loop = loop
        self.runner = runner if runner else CatalogueRunner()
        self.theme = theme if theme else Theme()
        self.logger = logger if logger else getLogger(__name__)
        self.catalogues: Dict[CloudProvider, DatasetStamp] = {}
        self.marketplaces: Dict[CloudProvider, DatasetStamp] = {}
        self.revisions: Dict[DatasetKind, Dict[str, int]] = {}
        self.deleted = 0
        self.provider: Optional[CloudProvider] = None
        self.country: Optional[Country] = None
        self.crawl_thread: Optional[QThread] = None
        self.crawl_worker: Optional[CrawlWorker] = None
        self.crawl_source = CrawlSource.CATALOGUE
        self.statistics: Optional[MarketStatistics] = None
        self.storage_error: Optional[str] = None
        self.store = store if store else ChartStateStore(logger=self.logger)
        self.available: Optional[FrozenSet[DatasetKind]] = None
        self.setWindowTitle(self.TITLE)
        self.resize(1440, 880)
        self.taxonomy = TaxonomyCache(loop, self.logger)
        self.table_model = ProductTableModel(self.theme, loop, taxonomy=self.taxonomy)
        self.log_handler = QtLogHandler()
        self._build_status_bar()
        self._build_toolbar()
        self._build_marketplace_menu()
        self._build_central()
        self._build_log_dock()
        self._build_view_menu()
        self.categories_manager: Optional[CategoriesManager] = None
        self._build_taxonomy_menu()
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(self.SEARCH_DELAY_MS)
        self.search_timer.timeout.connect(self._apply_filters)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(self.POLL_INTERVAL_MS)
        self.poll_timer.timeout.connect(self._poll)
        self.table_model.loaded.connect(lambda total: self._update_counts())
        self.table_model.failed.connect(self._on_storage_error_text)
        logging.getLogger().addHandler(self.log_handler)
        self.logger.info("%s started on %s.", self.TITLE, self.loop.storage.url)
        self.poll_timer.start()
        self._poll()

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_toolbar(self) -> None:
        """Build the toolbar actions."""
        toolbar = QToolBar("Actions")
        self.toolbar = toolbar
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.reload_action = QAction("⟳  Reload", self)
        self.reload_action.setShortcut(QKeySequence("F5"))
        self.reload_action.setToolTip("Read the stored catalogues, marketplaces and statistics again (F5)")
        self.crawl_selected_action = QAction("▶  Crawl selected", self)
        self.crawl_selected_action.setShortcut(QKeySequence("Ctrl+R"))
        self.crawl_selected_action.setToolTip(
            "Crawl the selected provider, the providers of the selected country, or every provider (Ctrl+R)"
        )
        self.crawl_all_action = QAction("⏩  Crawl all", self)
        self.crawl_all_action.setShortcut(QKeySequence("Ctrl+Shift+R"))
        self.crawl_all_action.setToolTip(f"Crawl the {len(CloudProvider)} providers, several at a time (Ctrl+Shift+R)")
        self.reload_action.triggered.connect(self.reload)
        self.crawl_selected_action.triggered.connect(self.crawl_selected)
        self.crawl_all_action.triggered.connect(self.crawl_all)
        for action in (self.reload_action, self.crawl_selected_action, self.crawl_all_action):
            toolbar.addAction(action)
        self.concurrency_box = QSpinBox()
        self.concurrency_box.setRange(1, len(CloudProvider))
        self.concurrency_box.setValue(self.runner.concurrency)
        self.concurrency_box.setPrefix("Parallel crawls: ")
        self.concurrency_box.setToolTip(
            "How many providers are crawled at the same time (each one opens its own browser when it needs one)"
        )
        self.concurrency_box.valueChanged.connect(self._on_concurrency_changed)
        toolbar.addWidget(self.concurrency_box)
        self.logger.debug("Toolbar built.")

    def _build_marketplace_menu(self) -> None:
        """Build the marketplace menu, in the menu bar and behind a toolbar button, to extract chosen marketplaces."""
        self.marketplace_menu = MarketplaceMenu(self.theme, self.runner.factory.marketplace_providers(), self)
        menu_bar = QMenuBar(self)
        menu_bar.addMenu(self.marketplace_menu)
        self.setMenuBar(menu_bar)
        self.marketplace_button = QToolButton()
        self.marketplace_button.setText("\U0001f6d2  Marketplaces")
        self.marketplace_button.setToolTip("Choose the marketplaces to extract the software from")
        self.marketplace_button.setMenu(self.marketplace_menu)
        self.marketplace_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.marketplace_button)
        self.marketplace_menu.extract_requested.connect(self._on_marketplaces_requested)
        self.logger.debug("Marketplace menu built.")

    def _build_country_box(self) -> None:
        """Build the country filter: "All countries", then each country with its flag."""
        self.country_box = CompactCombo(logger=self.logger)
        self.country_box.setToolTip("Show only the products of the providers of a country")
        self.country_box.addItem("All countries", "")
        for country in Country:
            flag = self.theme.flag_icon(country, 14)
            self.country_box.addItem(flag, self.theme.country_label(country), country.value)
        self.logger.debug("Country filter built: %d countries.", self.country_box.count() - 1)

    def _fill_provider_box(self) -> None:
        """Fill the provider filter with the providers of the chosen country, the chosen provider kept.

        Notes:
            Each provider shows its number of listed products.
        """
        providers = [provider for provider in CloudProvider if self.country in (None, provider.country)]
        listed = sum(stamp.size for provider, stamp in self.catalogues.items() if provider in providers)
        self.provider_box.blockSignals(True)
        self.provider_box.clear()
        self.provider_box.addItem(f"All providers  ({listed:,})", "")
        for provider in providers:
            stamp = self.catalogues.get(provider)
            label = self.theme.provider_label(provider)
            text = f"{label}  ({stamp.size:,})" if stamp is not None else label
            self.provider_box.addItem(self.theme.provider_icon(provider), text, provider.value)
        chosen = self.provider.value if self.provider is not None else ""
        self.provider_box.setCurrentIndex(max(self.provider_box.findData(chosen), 0))
        self.provider_box.blockSignals(False)
        self.logger.debug("Provider filter filled: %d providers.", len(providers))

    def _build_central(self) -> None:
        """Build the provider sidebar, the dashboard, the searchable and filterable product table and the details."""
        self.sidebar = ProviderSidebar(self.theme)
        self.dashboard = Dashboard(self.theme, self.loop, self.store, self.STATISTICS_SOURCE, self.logger)
        self._build_country_box()
        self.provider_box = CompactCombo(logger=self.logger)
        self.provider_box.setToolTip("Show only the products of a cloud provider (of the chosen country)")
        self._fill_provider_box()
        self.category_picker = CategoryPicker(self.taxonomy, self.logger)
        self.selection_query: Optional[ItemQuery] = None
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search products by name…   (Ctrl+F)")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMinimumWidth(220)
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.search_shortcut.activated.connect(self.search_box.setFocus)
        self.deleted_box = QCheckBox("Show deleted")
        self.deleted_box.setToolTip("Show the products which disappeared from their website, struck through")
        self.description_box = QCheckBox("In descriptions")
        self.description_box.setToolTip("Search the descriptions too (slower)")
        self.advanced = AdvancedSoftwareFilters(self.theme, self.logger, software_fields=False)
        self.advanced.setVisible(False)
        self.more_button = QPushButton("More filters")
        self.more_button.setCheckable(True)
        self.more_button.setToolTip("Filter on every other field: texts, catalogue category and dates")
        self.table = QTableView()
        header = QHeaderView(Qt.Orientation.Horizontal)
        header.setSectionsClickable(True)
        header.setStretchLastSection(True)
        vertical_header = QHeaderView(Qt.Orientation.Vertical)
        vertical_header.setVisible(False)
        self.table.setHorizontalHeader(header)
        self.table.setVerticalHeader(vertical_header)
        self.table.setModel(self.table_model)
        selection = QItemSelectionModel(self.table_model)
        self.table.setSelectionModel(selection)
        self.table_model.query = self.table_model.query.model_copy(update={"sort": ItemSort.NAME})
        header.setSortIndicator(ProductTableModel.NAME, Qt.SortOrder.AscendingOrder)
        header.setSortIndicatorShown(True)
        header.sortIndicatorChanged.connect(self.table_model.sort)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.setColumnWidth(ProductTableModel.PROVIDER, 190)
        self.table.setColumnWidth(ProductTableModel.COUNTRY, 150)
        self.table.setColumnWidth(ProductTableModel.NAME, 300)
        self.table.setColumnWidth(ProductTableModel.CATEGORIES, 220)
        self.table.setColumnWidth(ProductTableModel.LABELS, 200)
        self.table.setColumnWidth(ProductTableModel.DESCRIPTION, 420)
        self.table.setColumnWidth(ProductTableModel.ADDED, 100)
        self.details = ProductDetails(self.theme, taxonomy=self.taxonomy)
        self.details_pane = SidePane("catalogue/details", "Product details", self.details, self.store, self.logger)
        self.product_actions = ItemActions[CloudProduct, ProductRow](
            self.theme,
            self.table,
            self.table_model,
            self.loop,
            CloudProduct,
            lambda storage: storage.catalogues,
            list(CloudProvider),
            self,
            self.logger,
        )
        self.selection_actions = SelectionActions[CloudProduct, ProductRow](
            self.theme,
            self.table_model,
            self.loop,
            lambda storage: storage.catalogues,
            list(CloudProvider),
            self,
            logger=self.logger,
            taxonomy=self.taxonomy,
        )
        self.select_button = QToolButton()
        self.select_button.setDefaultAction(self.selection_actions.select_action)
        self.selection_button = QPushButton()
        self.selection_button.setToolTip("Clear the bulk selection: the table shows the filters again")
        self.selection_button.setVisible(False)
        products = QWidget()
        products_layout = QVBoxLayout(products)
        products_layout.setContentsMargins(0, 0, 0, 0)
        products_layout.setSpacing(10)
        filters = FlowLayout(gap=10, logger=self.logger)
        filters.addWidget(self.search_box)
        filters.addWidget(self.description_box)
        filters.addWidget(self.country_box)
        filters.addWidget(self.provider_box)
        filters.addWidget(self.category_picker)
        filters.addWidget(self.deleted_box)
        filters.addWidget(self.more_button)
        filters.addWidget(self.select_button)
        filters.addWidget(self.selection_button)
        for action in (
            self.product_actions.new_action,
            self.product_actions.edit_action,
            self.product_actions.delete_action,
        ):
            button = QToolButton()
            button.setDefaultAction(action)
            filters.addWidget(button)
        products_layout.addLayout(filters)
        products_layout.addWidget(self.advanced)
        self.table.setMinimumHeight(160)
        self.table_section = ChartSection(
            "catalogue/table", "Products", self.table, self.store, logger=self.logger, detachable=False
        )
        self.table_stack = SectionStack(scrollable=False, logger=self.logger)
        self.table_stack.add_section(self.table_section, 1)
        charts_and_table = FoldingSplitter(Qt.Orientation.Vertical, self.logger)
        charts_and_table.add_pane(self.dashboard, 1)
        charts_and_table.add_pane(self.table_stack, 1)
        charts_and_table.setSizes([440, 420])
        products_layout.addWidget(charts_and_table, 1)
        products_layout.addStretch(0)
        splitter = FoldingSplitter(Qt.Orientation.Horizontal, self.logger)
        splitter.setContentsMargins(10, 10, 10, 10)
        splitter.add_pane(self.sidebar)
        splitter.add_pane(products, 1)
        splitter.add_pane(self.details_pane)
        splitter.setSizes([270, 860, 330])
        self.marketplace_view = MarketplaceView(
            self.theme,
            self.runner.factory.marketplace_providers(),
            self.loop,
            store=self.store,
            statistics_source=self.STATISTICS_SOURCE,
            taxonomy=self.taxonomy,
        )
        self.tabs = QTabWidget()
        self.tabs.addTab(splitter, "Products")
        self.tabs.addTab(self.marketplace_view, "Marketplaces")
        self.statistics_view = StatisticsView(self.theme, store=self.store)
        self.tabs.addTab(self.statistics_view, "Statistics")
        self.analysis_view = AnalysisView(self.theme, self.loop, self.store, self.STATISTICS_SOURCE, self.logger)
        self.tabs.addTab(self.analysis_view, "Analysis")
        self.correspondence_view = CorrespondenceView(
            self.theme, self.loop, self.taxonomy, self.store, logger=self.logger
        )
        self.tabs.addTab(self.correspondence_view, "Correspondences")
        self.statistics_view.refresh_requested.connect(self.crawl_statistics)
        self.setCentralWidget(self.tabs)
        self.marketplace_view.copied.connect(
            lambda text: self.status_bar.showMessage("Software copied to the clipboard.", 4000)
        )
        for actions in (
            self.product_actions,
            self.marketplace_view.item_actions,
            self.selection_actions,
            self.marketplace_view.selection_actions,
        ):
            actions.changed.connect(self._on_items_changed)
            actions.failed.connect(self._on_items_failed)
        self.selection_actions.filter_requested.connect(self.apply_selection)
        self.selection_button.clicked.connect(self.clear_selection)
        self.provider_box.currentIndexChanged.connect(self._on_provider_selected)
        self.category_picker.changed.connect(self._apply_filters)
        self.sidebar.provider_changed.connect(self._on_provider_changed)
        self.sidebar.country_changed.connect(self._on_sidebar_country_changed)
        self.country_box.currentIndexChanged.connect(self._on_country_selected)
        self.search_box.textChanged.connect(self._on_search_changed)
        self.deleted_box.toggled.connect(self._on_show_deleted)
        self.description_box.toggled.connect(self._on_show_deleted)
        selection.currentRowChanged.connect(self._on_current_changed)
        self.details.copied.connect(lambda text: self.status_bar.showMessage("Product copied to the clipboard.", 4000))
        self.details.filter_requested.connect(self._on_detail_filter)
        self.advanced.changed.connect(self._on_advanced_changed)
        self.more_button.toggled.connect(self.advanced.setVisible)
        self.logger.debug("Products, marketplaces, statistics and analysis tabs built.")

    def _update_logs_button(self) -> None:
        """Offer to show the logs from the status bar while they are folded or hidden."""
        hidden = self.log_dock.isHidden()
        self.logs_button.setText("\u25b4 Logs")
        self.logs_button.setToolTip("Show the logs (Ctrl+L)")
        self.logs_button.setVisible(hidden or self.log_dock.is_folded())
        self.logger.debug("Logs %s.", "hidden" if hidden else "folded" if self.log_dock.is_folded() else "shown")

    def _reveal_logs(self) -> None:
        """Show the logs, unfolded, even after they were hidden."""
        self.logger.debug("Showing the logs.")
        self.log_dock.reveal()
        self._update_logs_button()

    def _build_log_dock(self) -> None:
        """Build the log panel, fed with the application logs, folding to its title bar."""
        self.log_panel = LogPanel(self.theme)
        self.log_handler.signals.record_emitted.connect(self.log_panel.append_record)
        self.log_dock = FoldingDock("window/logs", "Logs", self.log_panel, self, self.store, self.logger)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.log_dock.fit_height()
        self.logs_button = QToolButton()
        self.logs_button.setObjectName("chartTool")
        self.logs_button.setAutoRaise(True)
        self.logs_button.clicked.connect(self._reveal_logs)
        self.status_bar.insertPermanentWidget(0, self.logs_button)
        self.log_dock.folded_changed.connect(lambda folded: self._update_logs_button())
        self.log_dock.visibilityChanged.connect(lambda visible: self._update_logs_button())
        self._update_logs_button()
        self.logger.debug("Log panel built.")

    def _build_view_menu(self) -> None:
        """Build the View menu: show the logs and the details panels again, and expand or collapse the tables."""
        self.view_menu = QMenu("&View", self)
        logs = self.view_menu.addAction("Show the logs")
        if logs is not None:
            logs.setShortcut(QKeySequence("Ctrl+L"))
            logs.triggered.connect(self._reveal_logs)
        fold_logs = self.view_menu.addAction("Fold the logs")
        if fold_logs is not None:
            fold_logs.triggered.connect(lambda: self.log_dock.set_folded(True))
        self.view_menu.addSeparator()
        details = self.view_menu.addAction("Show or hide the details panel")
        if details is not None:
            details.setShortcut(QKeySequence("Ctrl+D"))
            details.triggered.connect(self._toggle_details)
        menu_bar = self.menuBar()
        if menu_bar is not None:
            menu_bar.addMenu(self.view_menu)
        self.logger.debug("View menu built.")

    def _manager(self) -> CategoriesManager:
        """Get the Categories manager, building it the first time.

        Returns:
            CategoriesManager: The manager window.
        """
        if self.categories_manager is None:
            self.categories_manager = CategoriesManager(self.theme, self.loop, self.taxonomy, self.logger)
            self.categories_manager.edited.connect(self.reload)
        return self.categories_manager

    def _build_taxonomy_menu(self) -> None:
        """Build the taxonomy menu: the Categories manager (categories, source labels, unclassified items)."""
        self.taxonomy_menu = QMenu("&Taxonomy", self)
        manager = self.taxonomy_menu.addAction("Categories manager…")
        if manager is not None:
            manager.setShortcut(QKeySequence("Ctrl+Shift+T"))
            manager.triggered.connect(partial(self.open_categories_manager, 0))
        labels = self.taxonomy_menu.addAction("Source labels…")
        if labels is not None:
            labels.triggered.connect(partial(self.open_categories_manager, 1))
        unclassified = self.taxonomy_menu.addAction("Unclassified items…")
        if unclassified is not None:
            unclassified.triggered.connect(partial(self.open_categories_manager, 2))
        self.taxonomy_menu.addSeparator()
        recompute = self.taxonomy_menu.addAction("Recompute the categories")
        if recompute is not None:
            recompute.setToolTip("Categorize every stored item again with the current taxonomy and labels")
            recompute.triggered.connect(self.recompute_categories)
        self.taxonomy_menu.addSeparator()
        correspondences = self.taxonomy_menu.addAction("Service correspondences")
        if correspondences is not None:
            correspondences.setToolTip("Show the equivalent services of the providers side by side")
            correspondences.triggered.connect(lambda: self.tabs.setCurrentWidget(self.correspondence_view))
        match = self.taxonomy_menu.addAction("Match services with AI")
        if match is not None:
            match.setToolTip("Match the new or changed catalogue services with their equivalents (language model)")
            match.triggered.connect(self.correspondence_view.match)
        menu_bar = self.menuBar()
        if menu_bar is not None:
            menu_bar.addMenu(self.taxonomy_menu)
        self.logger.debug("Taxonomy menu built.")

    def _toggle_details(self) -> None:
        """Fold or unfold the details panel of the shown tab."""
        current = self.tabs.currentWidget()
        pane = self.marketplace_view.details_pane if current is self.marketplace_view else None
        if current is self.correspondence_view:
            pane = self.correspondence_view.details_pane
        pane = pane if pane is not None else self.details_pane
        pane.set_folded(not pane.is_folded())
        self.logger.debug("Details panel %s.", "folded" if pane.is_folded() else "unfolded")

    def _build_status_bar(self) -> None:
        """Build the status bar: shown products count and crawl progress."""
        self.count_label = QLabel()
        self.count_label.setObjectName("muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(180)
        self.progress.setVisible(False)
        self.status_bar = QStatusBar()
        self.status_bar.addPermanentWidget(self.progress)
        self.status_bar.addPermanentWidget(self.count_label)
        self.setStatusBar(self.status_bar)
        self.logger.debug("Status bar built.")

    def _update_counts(self) -> None:
        """Show how many products match the filters, out of the listed ones."""
        self.logger.debug("%d products match the filters (%d deleted stored).", self.table_model.total, self.deleted)
        listed = sum(stamp.size for stamp in self.catalogues.values())
        state = "included" if self.deleted_box.isChecked() else "hidden"
        suffix = f" ({self.deleted:,} deleted {state})" if self.deleted else ""
        self.count_label.setText(f"{self.table_model.total:,} of {listed:,} products shown{suffix}")

    def _update_country_box(self) -> None:
        """Show the number of listed products of each country and provider in the country and provider filters."""
        self.logger.debug("Country filter counts updated from %d catalogues.", len(self.catalogues))
        for index in range(1, self.country_box.count()):
            country = Country(self.country_box.itemData(index))
            total = sum(stamp.size for provider, stamp in self.catalogues.items() if provider.country is country)
            self.country_box.setItemText(index, f"{self.theme.country_label(country)}  ({total:,})")
        self._fill_provider_box()

    def _query(self) -> ItemQuery:
        """Build the query of the product filters, keeping the order of the table.

        Returns:
            ItemQuery: The products matching the search and the filters, or the bulk selection when one is shown.
        """
        if self.selection_query is not None:
            self.logger.debug("Showing the bulk selection of products instead of the filters.")
            order = {"sort": self.table_model.query.sort, "descending": self.table_model.query.descending}
            return self.selection_query.model_copy(update=order)
        self.logger.debug(
            "Product filters: provider %s, country %s, search %r.", self.provider, self.country, self.search_box.text()
        )
        if self.provider is not None:
            providers = [self.provider]
        elif self.country is not None:
            providers = [provider for provider in CloudProvider if provider.country is self.country]
        else:
            providers = []
        main = self.table_model.query.model_copy(
            update={
                "providers": providers,
                "search": self.search_box.text().strip() or None,
                "search_description": self.description_box.isChecked(),
                "include_deleted": self.deleted_box.isChecked(),
                "service_categories": self.category_picker.picked(),
            }
        )
        return self.advanced.apply(main)

    def _on_advanced_changed(self) -> None:
        """Show how many other filters are set, and search once they stop changing."""
        count = self.advanced.active_count()
        self.logger.debug("Advanced product filters changed: %d set.", count)
        self.more_button.setText(f"More filters ({count})" if count else "More filters")
        self.search_timer.start()

    def _on_detail_filter(self, name: str, value: str) -> None:
        """Filter the products on a chip clicked in the details panel (a catalogue category).

        Args:
            name (str): The `ItemFilter` value of the chip.
            value (str): The value filtered on.
        """
        if self.selection_query is not None:
            self.logger.warning("The products are not filtered on %r while a bulk selection is shown.", value)
            self.status_bar.showMessage("Clear the bulk selection to filter the products.", 4000)
            return
        item_filter = ItemFilter(name)
        if item_filter is ItemFilter.SERVICE_CATEGORIES:
            self.category_picker.set_picked([value])
            self.status_bar.showMessage(f"Products filtered on {self.taxonomy.path(value)}.", 4000)
            return
        if item_filter is ItemFilter.SOURCE_LABELS:
            self.advanced.source_label_box.pick(int(value), self.taxonomy)
            self.more_button.setChecked(True)
            return
        if self.advanced.pick(item_filter, value):
            self.more_button.setChecked(True)
            self.status_bar.showMessage(f"Products filtered on {value}.", 4000)
        else:
            self.logger.error("The products cannot be filtered on %s %r.", name, value)

    def _apply_filters(self) -> None:
        """Show only the products matching the search and the filters."""
        self.logger.debug("Applying the product filters.")
        self.search_timer.stop()
        self.table_model.set_query(self._query())
        self.dashboard.set_query(self._query())

    def _on_deleted_counted(self, every: int) -> None:
        """Keep the number of deleted products: every stored one minus the listed ones.

        Args:
            every (int): The number of stored products, the deleted ones included.
        """
        self.logger.debug("%d products stored, deleted ones included.", every)
        self.deleted = max(every - sum(stamp.size for stamp in self.catalogues.values()), 0)
        self._update_counts()

    def _on_storage_error_text(self, message: str) -> None:
        """Report that the storage does not answer, once until it answers again.

        Args:
            message (str): Why the storage is unavailable.
        """
        if self.storage_error != message:
            self.logger.warning("The storage is unavailable: %s", message)
        self.storage_error = message
        self.status_bar.showMessage(f"Database unavailable: {message}", self.POLL_INTERVAL_MS * 2)

    def _on_storage_error(self, error: StorageError) -> None:
        """Report that the storage does not answer.

        Args:
            error (StorageError): The error.
        """
        self.logger.debug("Storage error received: %s", error)
        self._on_storage_error_text(str(error))

    def _changed(self, kind: DatasetKind, stamps: Dict[str, DatasetStamp]) -> bool:
        """Tell whether the datasets of a kind changed since they were last shown, and remember their revisions.

        Args:
            kind (DatasetKind): What the datasets hold.
            stamps (Dict[str, DatasetStamp]): Their state, by dataset.

        Returns:
            bool: Whether a dataset appeared, disappeared or was written.
        """
        self.logger.debug("Checking %d stored %s datasets for changes.", len(stamps), kind.value)
        revisions = {dataset: stamp.revision for dataset, stamp in stamps.items()}
        changed = self.revisions.get(kind) != revisions
        self.revisions[kind] = revisions
        return changed

    def _show_catalogues(self, stamps: Dict[CloudProvider, DatasetStamp]) -> None:
        """Show the state of the stored catalogues, and read the products again.

        Args:
            stamps (Dict[CloudProvider, DatasetStamp]): The state of the stored catalogues.
        """
        self.logger.info("Showing %d stored catalogues.", len(stamps))
        first = DatasetKind.CATALOGUE not in self.revisions or not self.catalogues
        self.catalogues = {provider: stamps[provider] for provider in CloudProvider if provider in stamps}
        self.sidebar.update_catalogues(self.catalogues, {})
        self.dashboard.update_catalogues(self.catalogues, self.country)
        self._update_country_box()
        self.table_model.set_crawl_dates({provider: stamp.crawled_at for provider, stamp in self.catalogues.items()})
        if first:
            self.table_model.set_query(self._query())
        else:
            self.table_model.refresh()
        self.dashboard.set_query(self._query())
        self.loop.submit(
            lambda storage: storage.catalogues.count(ItemQuery(include_deleted=True)),
            self._on_deleted_counted,
            self._on_storage_error,
        )
        self.loop.submit(
            lambda storage: storage.catalogues.category_counts(ItemQuery()),
            self.category_picker.set_counts,
            self._on_storage_error,
        )
        self.loop.submit(
            lambda storage: storage.catalogues.label_counts(ItemQuery()),
            self.advanced.set_labels,
            self._on_storage_error,
        )
        self.taxonomy.load()

    def _update_available(self, by_kind: Dict[DatasetKind, Dict[str, DatasetStamp]]) -> None:
        """Tell the charts which datasets hold data, for their options and empty states.

        Args:
            by_kind (Dict[DatasetKind, Dict[str, DatasetStamp]]): The state of the stored datasets, by kind.
        """
        available = frozenset(kind for kind, stamps in by_kind.items() if any(stamp.size for stamp in stamps.values()))
        if available == self.available:
            return
        self.logger.info("Datasets holding data: %s.", ", ".join(sorted(kind.value for kind in available)) or "none")
        self.available = available
        self.dashboard.set_available(available)
        self.marketplace_view.set_available(available)
        self.analysis_view.set_available(available)

    def _on_stamps(self, stamps: List[DatasetStamp]) -> None:
        """Refresh the views of the datasets written since they were last shown (GUI thread).

        Args:
            stamps (List[DatasetStamp]): The state of every stored dataset.
        """
        if self.storage_error is not None:
            self.logger.info("The storage %s answers again.", self.loop.storage.url)
            self.storage_error = None
        by_kind: Dict[DatasetKind, Dict[str, DatasetStamp]] = {kind: {} for kind in DatasetKind}
        for stamp in stamps:
            by_kind[stamp.kind][stamp.dataset] = stamp
        first = not self.revisions
        self._update_available(by_kind)
        written = any(
            self.revisions.get(kind) != {name: stamp.revision for name, stamp in by_kind[kind].items()}
            for kind in DatasetKind
        )
        if written or first:
            self.analysis_view.refresh()
        if self._changed(DatasetKind.CATALOGUE, by_kind[DatasetKind.CATALOGUE]) or first:
            self.correspondence_view.refresh()
            catalogues = by_kind[DatasetKind.CATALOGUE]
            self._show_catalogues({CloudProvider(name): stamp for name, stamp in catalogues.items()})
            if first:
                count = len(self.catalogues)
                message = (
                    f"{count} catalogues stored in {self.loop.storage.url}."
                    if count
                    else "No catalogue yet: launch a crawl (Ctrl+R / Ctrl+Shift+R)."
                )
                self.logger.info(message)
                self.status_bar.showMessage(message, 8000)
        if self._changed(DatasetKind.MARKETPLACE, by_kind[DatasetKind.MARKETPLACE]) or first:
            self.marketplaces = {CloudProvider(name): stamp for name, stamp in by_kind[DatasetKind.MARKETPLACE].items()}
            self.marketplace_view.refresh(self.marketplaces)
            self.marketplace_menu.set_counts({provider: stamp.size for provider, stamp in self.marketplaces.items()})
        if self._changed(DatasetKind.STATISTICS, by_kind[DatasetKind.STATISTICS]) or first:
            self.loop.submit(
                lambda storage: storage.statistics.load(self.STATISTICS_SOURCE),
                self._on_statistics,
                self._on_storage_error,
            )

    def _on_statistics(self, statistics: Optional[MarketStatistics]) -> None:
        """Show the stored market statistics.

        Args:
            statistics (Optional[MarketStatistics]): The statistics, `None` when never crawled.
        """
        self.logger.info("Market statistics read: %d reports.", len(statistics.reports) if statistics else 0)
        self.statistics = statistics
        self.statistics_view.set_statistics(statistics)

    def _on_provider_changed(self, value: str) -> None:
        """Show only the products of the selected provider.

        Args:
            value (str): The selected provider value, empty for all of them.
        """
        self.logger.debug("Provider filter changed to %s.", value or "all providers")
        self.provider = CloudProvider(value) if value else None
        self._fill_provider_box()
        self._apply_filters()

    def _on_provider_selected(self, index: int) -> None:
        """Select the provider chosen in the provider filter in the sidebar, which filters the products.

        Args:
            index (int): The chosen entry of the provider filter.
        """
        value = self.provider_box.itemData(index)
        self.logger.debug("Provider filter entry %d chosen (%s).", index, value or "all providers")
        if value:
            self.sidebar.setCurrentItem(self.sidebar.provider_items[CloudProvider(value)])
        elif self.country is not None:
            self.sidebar.setCurrentItem(self.sidebar.country_items[self.country])
        else:
            self.sidebar.setCurrentItem(self.sidebar.all_item)

    def _apply_country(self, country: Optional[Country]) -> None:
        """Show only the products and the figures of the providers of a country.

        Args:
            country (Optional[Country]): The country, `None` for all of them.
        """
        self.logger.debug("Country filter changed to %s.", country.value if country else "all countries")
        self.country = country
        self.dashboard.update_catalogues(self.catalogues, country)
        self._fill_provider_box()
        self._apply_filters()

    def _on_sidebar_country_changed(self, value: str) -> None:
        """Filter on the country of the sidebar selection, and show it in the country filter.

        Args:
            value (str): The country code of the selection, empty for all of them.
        """
        self.logger.debug("Sidebar country changed to %s.", value or "all countries")
        index = max(self.country_box.findData(value), 0)
        self.country_box.blockSignals(True)
        self.country_box.setCurrentIndex(index)
        self.country_box.blockSignals(False)
        self._apply_country(Country(value) if value else None)

    def _on_country_selected(self, index: int) -> None:
        """Filter on the country chosen in the country filter, and select it in the sidebar if needed.

        Args:
            index (int): The chosen entry of the country filter.
        """
        self.logger.debug("Country filter entry %d chosen.", index)
        value = self.country_box.itemData(index)
        country = Country(value) if value else None
        self._apply_country(country)
        self.sidebar.select_country(country)

    def _set_filters_enabled(self, enabled: bool) -> None:
        """Enable the product filters, or disable them while a bulk selection is shown.

        Args:
            enabled (bool): Whether the filters can be used.
        """
        self.logger.debug("Product filters %s.", "enabled" if enabled else "disabled")
        for widget in (
            self.search_box,
            self.description_box,
            self.deleted_box,
            self.country_box,
            self.provider_box,
            self.category_picker,
            self.more_button,
            self.advanced,
        ):
            widget.setEnabled(enabled)

    def _on_show_deleted(self, shown: bool) -> None:
        """Show or hide the products deleted from their website (or search the descriptions or not).

        Args:
            shown (bool): Whether the box is checked.
        """
        self.logger.debug("Filter box toggled: %s.", shown)
        self._apply_filters()

    def _on_concurrency_changed(self, value: int) -> None:
        """Set how many providers the next crawls crawl at the same time.

        Args:
            value (int): The number of providers crawled at the same time.
        """
        self.runner.concurrency = value
        self.logger.info("The next crawls run %d providers at the same time.", value)

    def _on_search_changed(self, text: str) -> None:
        """Search the products once the text stops changing.

        Args:
            text (str): The searched text.
        """
        self.logger.debug("Search text changed to %r.", text)
        self.search_timer.start()

    def _on_current_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        """Show the details of the selected product.

        Args:
            current (QModelIndex): The selected index.
            previous (QModelIndex): The previously selected index.
        """
        self.logger.debug("Product row %d selected.", current.row())
        self.details.show_row(self.table_model.row_at(current))

    def _set_crawling(self, running: bool, message: str) -> None:
        """Switch the window between the crawling and idle states.

        Args:
            running (bool): Whether a crawl is running.
            message (str): The status message.
        """
        self.logger.debug("Window %s: %s", "crawling" if running else "idle", message)
        for action in (self.crawl_selected_action, self.crawl_all_action):
            action.setEnabled(not running)
        self.progress.setVisible(running)
        self.status_bar.showMessage(message)

    def _on_product_crawled(self, provider_value: str, count: int) -> None:
        """Show the crawl progress.

        Args:
            provider_value (str): The crawled provider value.
            count (int): The products (or software) crawled so far for this provider.
        """
        label = self.theme.provider_label(CloudProvider(provider_value))
        unit = "software" if self.crawl_source is CrawlSource.MARKETPLACE else "products"
        self.status_bar.showMessage(f"Crawling {label}: {count} {unit}…")

    def _poll(self) -> None:
        """Read the state of the stored datasets in the storage thread."""
        self.logger.debug("Polling the state of the stored datasets.")
        self.loop.submit(lambda storage: storage.datasets.stamps(), self._on_stamps, self._on_storage_error)

    def _on_items_changed(self, message: str) -> None:
        """Show items created, edited or deleted by hand: the changed datasets are read again.

        Args:
            message (str): What was done.
        """
        self.logger.info("Items changed by hand: %s", message)
        self.status_bar.showMessage(message, 6000)
        self._poll()

    def _on_items_failed(self, message: str) -> None:
        """Report an item action which failed (e.g. the provider is being crawled).

        Args:
            message (str): Why it failed.
        """
        self.logger.warning("An item action failed: %s", message)
        self.status_bar.showMessage(f"Not saved: {message}", 10000)
        QMessageBox.warning(self, "Not saved", message)

    def _on_crawl_succeeded(self, summary: str) -> None:
        """Show the written datasets after a successful crawl.

        Args:
            summary (str): The crawl summary.
        """
        self.logger.info("Crawl over: %s.", summary)
        self._poll()
        self.status_bar.showMessage(f"Crawl over: {summary}.", 10000)

    def _on_crawl_failed(self, message: str) -> None:
        """Report a failed crawl.

        Args:
            message (str): Why the crawl failed.
        """
        self.status_bar.showMessage(f"Crawl failed: {message}", 10000)
        QMessageBox.warning(self, "Crawl failed", f"{message}\n\nSee the logs panel for the details.")

    def _on_thread_finished(self, thread: QThread, worker: CrawlWorker) -> None:
        """Release the crawl thread and go back to the idle state.

        Args:
            thread (QThread): The finished crawl thread.
            worker (CrawlWorker): The finished crawl.
        """
        self.logger.debug("Crawl thread finished.")
        worker.deleteLater()
        thread.deleteLater()
        self.crawl_thread, self.crawl_worker = None, None
        self._set_crawling(False, self.status_bar.currentMessage())

    def _start_crawl(
        self,
        provider: Optional[CloudProvider],
        country: Optional[Country] = None,
        source: CrawlSource = CrawlSource.CATALOGUE,
        providers: Optional[List[CloudProvider]] = None,
    ) -> None:
        """Start a crawl in a background thread, unless one is running.

        Args:
            provider (Optional[CloudProvider]): The crawled provider, `None` for several of them.
            country (Optional[Country]): The country whose providers are crawled when no provider is given, `None`
                for every provider.
            source (CrawlSource): What is crawled, the catalogues (default), the marketplaces or the statistics.
            providers (Optional[List[CloudProvider]]): The crawled providers when no provider is given, `None` for
                every provider.
        """
        if self.crawl_thread is not None:
            self.logger.warning("A crawl is already running: the new one is ignored.")
            return
        match provider, providers, country:
            case CloudProvider(), _, _:
                label = self.theme.provider_label(provider)
            case None, list(), _:
                label = ", ".join(self.theme.provider_label(chosen) for chosen in providers)
            case None, None, Country():
                label = f"the {self.theme.country_label(country)} providers"
            case _:
                label = "every provider"
        if source is CrawlSource.MARKETPLACE:
            label = f"{label} (marketplaces)"
        elif source is CrawlSource.STATISTICS:
            label = "the market statistics (Synergy Research Group)"
        self.logger.info("Crawl of %s requested from the GUI.", label)
        thread = QThread(self)
        worker = CrawlWorker(self.runner, provider, country=country, source=source, providers=providers)
        self.crawl_source = source
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.product_crawled.connect(self._on_product_crawled)
        worker.succeeded.connect(self._on_crawl_succeeded)
        worker.failed.connect(self._on_crawl_failed)
        worker.stopped.connect(thread.quit)
        thread.finished.connect(lambda: self._on_thread_finished(thread, worker))
        self.crawl_thread, self.crawl_worker = thread, worker
        self._set_crawling(True, f"Crawling {label}… (the stealth browser window may open)")
        thread.start()

    def _on_marketplaces_requested(self, values: List[str]) -> None:
        """Extract the marketplaces chosen in the marketplace menu, and show the marketplace view.

        Args:
            values (List[str]): The values of the chosen marketplaces' cloud providers.
        """
        self.logger.info("Marketplaces requested from the menu: %s.", ", ".join(values))
        self.tabs.setCurrentWidget(self.marketplace_view)
        self._start_crawl(None, None, CrawlSource.MARKETPLACE, [CloudProvider(value) for value in values])

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_marketplace_tab(self) -> bool:
        """Tell whether the marketplace view is shown.

        Returns:
            bool: Whether the "Marketplaces" tab is the current one.
        """
        return self.tabs.currentWidget() is self.marketplace_view

    def apply_selection(self, query: ItemQuery) -> None:
        """Show a bulk selection of products in the table instead of the filters, until it is cleared.

        Args:
            query (ItemQuery): The chosen products.
        """
        self.logger.info("Showing a bulk selection of products.")
        self.selection_query = query
        self.selection_button.setText("Selection  \u2715")
        self.selection_button.setVisible(True)
        self._set_filters_enabled(False)
        self._apply_filters()

    def clear_selection(self) -> None:
        """Show the products of the filters again."""
        self.logger.info("Bulk selection of products cleared.")
        self.selection_query = None
        self.selection_button.setVisible(False)
        self._set_filters_enabled(True)
        self._apply_filters()

    def poll(self) -> None:
        """Read the state of the stored datasets, the changed ones being shown again."""
        self.logger.debug("Poll requested.")
        self._poll()

    def open_categories_manager(self, tab: int = 0) -> None:
        """Open the Categories manager on a tab.

        Args:
            tab (int): The tab shown: 0 categories, 1 source labels, 2 unclassified items.
        """
        self.logger.info("Categories manager opened (tab %d).", tab)
        self._manager().open_on(tab)

    def recompute_categories(self) -> None:
        """Categorize every stored item again with the current taxonomy and labels."""
        self.logger.info("Every item is categorized again from the Taxonomy menu.")
        self._manager().recompute()

    def reload(self) -> None:
        """Read every stored dataset again, changed or not."""
        self.logger.info("Reloading the catalogues, the marketplaces and the statistics.")
        self.revisions.clear()
        self._poll()

    def crawl_statistics(self) -> None:
        """Crawl the cloud market statistics (Synergy Research Group) again."""
        self.logger.info("Crawl of the market statistics requested.")
        self._start_crawl(None, None, CrawlSource.STATISTICS)

    def crawl_selected(self) -> None:
        """Crawl the provider or the country selected in the current tab, every provider when none is."""
        self.logger.debug("Crawl of the selection requested.")
        if self.tabs.currentWidget() is self.statistics_view:
            self.crawl_statistics()
            return
        if self.is_marketplace_tab():
            provider = self.marketplace_view.selected_provider()
            country = None if provider else self.marketplace_view.selected_country()
            self._start_crawl(provider, country, CrawlSource.MARKETPLACE)
            return
        provider = self.sidebar.selected_provider()
        self._start_crawl(provider, None if provider else self.sidebar.selected_country())

    def crawl_all(self) -> None:
        """Crawl every provider catalogue, or every marketplace on the marketplace tab, several at a time."""
        self.logger.debug("Crawl of every provider requested.")
        if self.tabs.currentWidget() is self.statistics_view:
            self.crawl_statistics()
            return
        self._start_crawl(None, None, CrawlSource.MARKETPLACE if self.is_marketplace_tab() else CrawlSource.CATALOGUE)

    def is_crawling(self) -> bool:
        """Tell whether a crawl is running.

        Returns:
            bool: Whether a crawl is running.
        """
        return self.crawl_thread is not None

    def closeEvent(self, event: Optional[QCloseEvent]) -> None:
        """Close the window, unless a crawl is running (Qt override).

        Args:
            event (Optional[QCloseEvent]): The close event.
        """
        if event is None:
            return
        if self.is_crawling():
            event.ignore()
            self.status_bar.showMessage("A crawl is running: close the window once it is over.", 8000)
            self.logger.warning("Closing refused: a crawl is running.")
            return
        self.poll_timer.stop()
        logging.getLogger().removeHandler(self.log_handler)
        self.loop.stop()
        self.logger.info("%s closed.", self.TITLE)
        event.accept()
