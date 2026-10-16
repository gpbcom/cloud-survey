from __future__ import annotations

# Standard Library Imports.
import logging
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QFileSystemWatcher, QItemSelectionModel, QModelIndex, Qt, QThread, QTimer, QUrl
from PyQt6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QProgressBar,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableView,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from catalogue.exception import CatalogueFileError
from catalogue.store import CatalogueStore
from crawler.runner import CatalogueRunner
from gui.crawl_worker import CrawlWorker
from gui.log_bridge.qt_log_handler import QtLogHandler
from gui.marketplace.marketplace_view import MarketplaceView
from gui.product_model.product_filter_model import ProductFilterModel
from gui.product_model.product_table_model import ProductTableModel
from gui.statistics.statistics_view import StatisticsView
from gui.theme import Theme
from gui.widgets.dashboard.dashboard import Dashboard
from gui.widgets.log_panel import LogPanel
from gui.widgets.marketplace_menu import MarketplaceMenu
from gui.widgets.product_details import ProductDetails
from gui.widgets.provider_sidebar import ProviderSidebar
from models.cloud.catalogue import CloudCatalogue
from models.cloud.enums import CloudProvider, Country
from models.cloud.marketplace import CloudMarketplace
from models.stats.market_statistics import MarketStatistics


class MainWindow(QMainWindow):
    """Cloud catalogue explorer: browse the crawled catalogues and launch crawls.

    Attributes:
        TITLE (ClassVar[str]): The window title.
        STATISTICS_SOURCE (ClassVar[str]): The market statistics source shown in the statistics view.
        RELOAD_DELAY_MS (ClassVar[int]): How long the output folder must stay unchanged before an automatic reload.
        POLL_INTERVAL_MS (ClassVar[int]): How often the output folder is checked when it cannot be watched.
        store (CatalogueStore): The store holding the catalogue files.
        runner (CatalogueRunner): The runner used by the crawls launched from the window.
        theme (Theme): The application theme.
        catalogues (Dict[CloudProvider, CloudCatalogue]): The loaded catalogues.
        errors (Dict[CloudProvider, str]): Why the unusable catalogue files could not be loaded.
        crawl_thread (Optional[QThread]): The thread of the running crawl.
        crawl_worker (Optional[CrawlWorker]): The running crawl.
        crawl_source (str): What the running (or last) crawl crawls, catalogues or marketplaces.
        marketplaces (Dict[CloudProvider, CloudMarketplace]): The loaded marketplaces.
        marketplace_errors (Dict[CloudProvider, str]): Why the unusable marketplace files could not be loaded.
        statistics (Optional[MarketStatistics]): The loaded market statistics, `None` before the first crawl.
        file_stamps (Dict[Path, Optional[Tuple[int, int]]]): The modification time and size of each output file
            when it was last read (`None` when missing), to read only the changed files again.
    """

    TITLE: ClassVar[str] = "Cloud Catalogue Explorer"
    STATISTICS_SOURCE: ClassVar[str] = "synergy"
    RELOAD_DELAY_MS: ClassVar[int] = 400
    POLL_INTERVAL_MS: ClassVar[int] = 2000

    def __init__(
        self,
        store: CatalogueStore,
        runner: Optional[CatalogueRunner] = None,
        theme: Optional[Theme] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Build the window and load the catalogues.

        Args:
            store (CatalogueStore): The store holding the catalogue files. Its folder is created when missing.
            runner (Optional[CatalogueRunner]): The runner of the crawls launched from the window.
            theme (Optional[Theme]): The application theme.
            logger (Optional[Logger]): The window logger.
        """
        super().__init__()
        self.store = store
        self.runner = runner if runner else CatalogueRunner(store=store)
        self.theme = theme if theme else Theme()
        self.logger = logger if logger else getLogger(__name__)
        self.catalogues: Dict[CloudProvider, CloudCatalogue] = {}
        self.errors: Dict[CloudProvider, str] = {}
        self.crawl_thread: Optional[QThread] = None
        self.crawl_worker: Optional[CrawlWorker] = None
        self.crawl_source = CrawlWorker.CATALOGUE
        self.marketplaces: Dict[CloudProvider, CloudMarketplace] = {}
        self.marketplace_errors: Dict[CloudProvider, str] = {}
        self.setWindowTitle(self.TITLE)
        self.resize(1440, 880)
        self.store.output_dir.mkdir(parents=True, exist_ok=True)
        self.runner.marketplace_store.output_dir.mkdir(parents=True, exist_ok=True)
        self.runner.statistics_store.output_dir.mkdir(parents=True, exist_ok=True)
        self.statistics: Optional[MarketStatistics] = None
        self.file_stamps: Dict[Path, Optional[Tuple[int, int]]] = {}
        self.table_model = ProductTableModel(self.theme)
        self.filter_model = ProductFilterModel(self.table_model)
        self.log_handler = QtLogHandler()
        self._build_status_bar()
        self._build_toolbar()
        self._build_marketplace_menu()
        self._build_central()
        self._build_log_dock()
        self.reload_timer = QTimer(self)
        self.reload_timer.setSingleShot(True)
        self.reload_timer.setInterval(self.RELOAD_DELAY_MS)
        self.reload_timer.timeout.connect(self._load_outputs)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._on_output_changed)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(self.POLL_INTERVAL_MS)
        self.poll_timer.timeout.connect(self._poll_output)
        self.output_snapshot = self._output_snapshot()
        self._watch_output()
        logging.getLogger().addHandler(self.log_handler)
        self.logger.info("%s started on %s.", self.TITLE, self.store.output_dir.resolve())
        self._load_outputs()

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
        self.reload_action.setToolTip("Reload the catalogue files (F5)")
        self.crawl_selected_action = QAction("▶  Crawl selected", self)
        self.crawl_selected_action.setShortcut(QKeySequence("Ctrl+R"))
        self.crawl_selected_action.setToolTip(
            "Crawl the selected provider, the providers of the selected country, or every provider (Ctrl+R)"
        )
        self.crawl_all_action = QAction("⏩  Crawl all", self)
        self.crawl_all_action.setShortcut(QKeySequence("Ctrl+Shift+R"))
        self.crawl_all_action.setToolTip(f"Crawl the {len(CloudProvider)} providers, several at a time (Ctrl+Shift+R)")
        self.open_folder_action = QAction("📂  Open output folder", self)
        self.open_folder_action.setToolTip(f"Open {self.store.output_dir.resolve()}")
        self.reload_action.triggered.connect(self.reload)
        self.crawl_selected_action.triggered.connect(self.crawl_selected)
        self.crawl_all_action.triggered.connect(self.crawl_all)
        self.open_folder_action.triggered.connect(self.open_output_folder)
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
        toolbar.addSeparator()
        toolbar.addAction(self.open_folder_action)

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

    def _build_country_box(self) -> None:
        """Build the country filter: "All countries", then each country with its flag."""
        self.country_box = QComboBox()
        self.country_box.setMinimumWidth(220)
        self.country_box.setToolTip("Show only the products of the providers of a country")
        self.country_box.addItem("All countries", "")
        for country in Country:
            flag = self.theme.flag_icon(country, 14)
            self.country_box.addItem(flag, self.theme.country_label(country), country.value)

    def _build_central(self) -> None:
        """Build the provider sidebar, the dashboard, the searchable and filterable product table and the details."""
        self.sidebar = ProviderSidebar(self.theme)
        self.dashboard = Dashboard(self.theme)
        self._build_country_box()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search products by name or description…   (Ctrl+F)")
        self.search_box.setClearButtonEnabled(True)
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.search_shortcut.activated.connect(self.search_box.setFocus)
        self.deleted_box = QCheckBox("Show deleted")
        self.deleted_box.setToolTip("Show the products which disappeared from their website, struck through")
        self.table = QTableView()
        header = QHeaderView(Qt.Orientation.Horizontal)
        header.setSectionsClickable(True)
        header.setStretchLastSection(True)
        vertical_header = QHeaderView(Qt.Orientation.Vertical)
        vertical_header.setVisible(False)
        self.table.setHorizontalHeader(header)
        self.table.setVerticalHeader(vertical_header)
        self.table.setModel(self.filter_model)
        selection = QItemSelectionModel(self.filter_model)
        self.table.setSelectionModel(selection)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(ProductTableModel.NAME, self.filter_model.sortOrder().AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.setColumnWidth(ProductTableModel.PROVIDER, 190)
        self.table.setColumnWidth(ProductTableModel.COUNTRY, 150)
        self.table.setColumnWidth(ProductTableModel.NAME, 300)
        self.table.setColumnWidth(ProductTableModel.DESCRIPTION, 420)
        self.table.setColumnWidth(ProductTableModel.ADDED, 100)
        self.details = ProductDetails(self.theme)
        products = QWidget()
        products_layout = QVBoxLayout(products)
        products_layout.setContentsMargins(0, 0, 0, 0)
        products_layout.setSpacing(10)
        filters = QHBoxLayout()
        filters.setSpacing(10)
        filters.addWidget(self.search_box, 1)
        filters.addWidget(self.country_box)
        filters.addWidget(self.deleted_box)
        products_layout.addWidget(self.dashboard)
        products_layout.addLayout(filters)
        products_layout.addWidget(self.table, 1)
        splitter = QSplitter()
        splitter.setContentsMargins(10, 10, 10, 10)
        for widget in (self.sidebar, products, self.details):
            splitter.addWidget(widget)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([270, 860, 330])
        self.marketplace_view = MarketplaceView(self.theme, self.runner.factory.marketplace_providers())
        self.tabs = QTabWidget()
        self.tabs.addTab(splitter, "Products")
        self.tabs.addTab(self.marketplace_view, "Marketplaces")
        self.statistics_view = StatisticsView(self.theme)
        self.tabs.addTab(self.statistics_view, "Statistics")
        self.statistics_view.refresh_requested.connect(self.crawl_statistics)
        self.setCentralWidget(self.tabs)
        self.marketplace_view.copied.connect(
            lambda text: self.status_bar.showMessage("Software copied to the clipboard.", 4000)
        )
        self.sidebar.provider_changed.connect(self._on_provider_changed)
        self.sidebar.country_changed.connect(self._on_sidebar_country_changed)
        self.country_box.currentIndexChanged.connect(self._on_country_selected)
        self.search_box.textChanged.connect(self._on_search_changed)
        self.deleted_box.toggled.connect(self._on_show_deleted)
        selection.currentRowChanged.connect(self._on_current_changed)
        self.details.copied.connect(lambda text: self.status_bar.showMessage("Product copied to the clipboard.", 4000))

    def _build_log_dock(self) -> None:
        """Build the log panel, fed with the application logs."""
        self.log_panel = LogPanel(self.theme)
        self.log_handler.signals.record_emitted.connect(self.log_panel.append_record)
        dock = QDockWidget("Logs", self)
        dock.setObjectName("logs")
        dock.setWidget(self.log_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [190], Qt.Orientation.Vertical)
        self.log_dock = dock

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

    def _update_counts(self) -> None:
        """Show how many products are shown out of the loaded ones."""
        shown, total = self.filter_model.rowCount(), self.table_model.rowCount()
        deleted = sum(1 for row in self.table_model.rows if row.product.is_deleted)
        state = "included" if self.filter_model.show_deleted else "hidden"
        suffix = f" ({deleted:,} deleted {state})" if deleted else ""
        self.count_label.setText(f"{shown:,} of {total - deleted:,} products shown{suffix}")

    def _update_country_box(self) -> None:
        """Show the number of products of each country in the country filter."""
        for index in range(1, self.country_box.count()):
            country = Country(self.country_box.itemData(index))
            loaded = [catalogue for provider, catalogue in self.catalogues.items() if provider.country is country]
            total = sum(catalogue.size for catalogue in loaded)
            self.country_box.setItemText(index, f"{self.theme.country_label(country)}  ({total:,})")

    def _changed(self, path: Path) -> bool:
        """Tell whether an output file changed (or appeared, or disappeared) since it was last read, and remember it.

        Args:
            path (Path): The output file.

        Returns:
            bool: Whether the file must be read again.
        """
        try:
            status = path.stat()
            stamp: Optional[Tuple[int, int]] = (status.st_mtime_ns, status.st_size)
        except OSError:
            stamp = None
        changed = path not in self.file_stamps or self.file_stamps[path] != stamp
        self.file_stamps[path] = stamp
        return changed

    def _load_catalogues(self) -> None:
        """Load the catalogue files changed since the last load and refresh the views. Unusable files are reported.

        Notes:
            A running crawl rewrites its catalogue file every few seconds: only that file is read again, so the
            products appear progressively.
        """
        reloaded = [provider for provider in CloudProvider if self._changed(self.store.path_for(provider))]
        if not reloaded:
            return
        catalogues, errors = dict(self.catalogues), dict(self.errors)
        for provider in reloaded:
            catalogues.pop(provider, None)
            errors.pop(provider, None)
            try:
                catalogue = self.store.load(provider)
            except CatalogueFileError as e:
                errors[provider] = e.reason
                continue
            if catalogue is not None:
                catalogues[provider] = catalogue
        catalogues = {provider: catalogues[provider] for provider in CloudProvider if provider in catalogues}
        self.catalogues, self.errors = catalogues, errors
        self.table_model.set_catalogues(catalogues)
        self.sidebar.update_catalogues(catalogues, errors)
        self.dashboard.update_catalogues(catalogues, self.filter_model.country)
        self._update_country_box()
        self.details.show_row(None)
        self._update_counts()
        if len(reloaded) < len(CloudProvider):
            self.logger.debug("Catalogue files reloaded: %s.", ", ".join(provider.value for provider in reloaded))
            return
        if errors:
            message = f"{len(catalogues)} catalogues loaded, {len(errors)} unusable files (see the logs)."
            self.logger.warning(message)
        elif catalogues:
            message = f"{len(catalogues)} catalogues loaded from {self.store.output_dir}."
            self.logger.info(message)
        else:
            message = "No catalogue yet: launch a crawl (Ctrl+R / Ctrl+Shift+R)."
            self.logger.info(message)
        self.status_bar.showMessage(message, 8000)

    def _load_marketplaces(self) -> None:
        """Load the marketplace files changed since the last load and refresh the marketplace view, progressively.

        Unusable files are reported, not fatal.
        """
        store = self.runner.marketplace_store
        reloaded = [provider for provider in CloudProvider if self._changed(store.path_for(provider))]
        if not reloaded:
            return
        marketplaces, errors = dict(self.marketplaces), dict(self.marketplace_errors)
        for provider in reloaded:
            marketplaces.pop(provider, None)
            errors.pop(provider, None)
            try:
                marketplace = store.load(provider)
            except CatalogueFileError as e:
                errors[provider] = e.reason
                continue
            if marketplace is not None:
                marketplaces[provider] = marketplace
        marketplaces = {provider: marketplaces[provider] for provider in CloudProvider if provider in marketplaces}
        self.marketplaces, self.marketplace_errors = marketplaces, errors
        self.marketplace_view.set_marketplaces(marketplaces)
        self.marketplace_menu.set_counts({provider: marketplace.size for provider, marketplace in marketplaces.items()})
        if len(reloaded) < len(CloudProvider):
            self.logger.debug("Marketplace files reloaded: %s.", ", ".join(provider.value for provider in reloaded))
        elif errors:
            self.logger.warning(
                "%d marketplaces loaded, %d unusable files (see the logs).", len(marketplaces), len(errors)
            )
        else:
            self.logger.info("%d marketplaces loaded.", len(marketplaces))

    def _load_statistics(self) -> None:
        """Load the market statistics file when it changed and refresh the view, reporting an unusable file."""
        if not self._changed(self.runner.statistics_store.path_for(self.STATISTICS_SOURCE)):
            return
        try:
            self.statistics = self.runner.statistics_store.load(self.STATISTICS_SOURCE)
        except CatalogueFileError as e:
            self.logger.warning("The market statistics file is unusable: %s", e.reason)
            self.statistics = None
        self.statistics_view.set_statistics(self.statistics)

    def _load_outputs(self) -> None:
        """Load the catalogue and marketplace files."""
        self._load_catalogues()
        self._load_marketplaces()
        self._load_statistics()

    def _on_output_changed(self, path: str) -> None:
        """Reload the catalogues once the output folder stops changing.

        Args:
            path (str): The changed folder.
        """
        self.logger.debug("Output folder %s changed: reload scheduled.", path)
        self.reload_timer.start()

    def _output_snapshot(self) -> Tuple[Tuple[str, int, int], ...]:
        """Describe the catalogue and marketplace files, to detect their changes without a file watcher.

        Returns:
            Tuple[Tuple[str, int, int], ...]: The path, modification time and size of each file.
        """
        folders = (
            self.store.output_dir,
            self.runner.marketplace_store.output_dir,
            self.runner.statistics_store.output_dir,
        )
        files = sorted(path for folder in folders for path in folder.glob("*.json"))
        return tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in files if path.is_file())

    def _poll_output(self) -> None:
        """Schedule a reload when the catalogue files changed since the previous check."""
        snapshot = self._output_snapshot()
        if snapshot != self.output_snapshot:
            self.output_snapshot = snapshot
            self._on_output_changed(str(self.store.output_dir))

    def _watch_output(self) -> None:
        """Watch the output folders, or check them periodically when they cannot be watched (e.g. inotify limits)."""
        folder = str(self.store.output_dir)
        marketplace_folder = str(self.runner.marketplace_store.output_dir)
        statistics_folder = str(self.runner.statistics_store.output_dir)
        watched = [self.watcher.addPath(path) for path in (folder, marketplace_folder, statistics_folder)]
        if all(watched):
            self.logger.debug("Watching %s, %s and %s for changes.", folder, marketplace_folder, statistics_folder)
            return
        self.logger.warning(
            "%s cannot be watched (system file watch limit reached?). It is checked every %d s instead.",
            folder,
            self.POLL_INTERVAL_MS // 1000,
        )
        self.poll_timer.start()

    def _on_provider_changed(self, value: str) -> None:
        """Show only the products of the selected provider.

        Args:
            value (str): The selected provider value, empty for all of them.
        """
        self.filter_model.set_provider(CloudProvider(value) if value else None)
        self._update_counts()

    def _apply_country(self, country: Optional[Country]) -> None:
        """Show only the products and the figures of the providers of a country.

        Args:
            country (Optional[Country]): The country, `None` for all of them.
        """
        self.logger.debug("Country filter changed to %s.", country.value if country else "all countries")
        self.filter_model.set_country(country)
        self.dashboard.update_catalogues(self.catalogues, country)
        self._update_counts()

    def _on_sidebar_country_changed(self, value: str) -> None:
        """Filter on the country of the sidebar selection, and show it in the country filter.

        Args:
            value (str): The country code of the selection, empty for all of them.
        """
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
        value = self.country_box.itemData(index)
        country = Country(value) if value else None
        self._apply_country(country)
        self.sidebar.select_country(country)

    def _on_show_deleted(self, shown: bool) -> None:
        """Show or hide the products deleted from their website.

        Args:
            shown (bool): Whether the deleted products are shown.
        """
        self.filter_model.set_show_deleted(shown)
        self._update_counts()

    def _on_concurrency_changed(self, value: int) -> None:
        """Set how many providers the next crawls crawl at the same time.

        Args:
            value (int): The number of providers crawled at the same time.
        """
        self.runner.concurrency = value
        self.logger.info("The next crawls run %d providers at the same time.", value)

    def _on_search_changed(self, text: str) -> None:
        """Show only the products matching the search.

        Args:
            text (str): The searched text.
        """
        self.filter_model.set_search(text)
        self._update_counts()

    def _on_current_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        """Show the details of the selected product.

        Args:
            current (QModelIndex): The selected index.
            previous (QModelIndex): The previously selected index.
        """
        self.details.show_row(self.filter_model.row_at(current))

    def _set_crawling(self, running: bool, message: str) -> None:
        """Switch the window between the crawling and idle states.

        Args:
            running (bool): Whether a crawl is running.
            message (str): The status message.
        """
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
        unit = "software" if self.crawl_source == CrawlWorker.MARKETPLACE else "products"
        self.status_bar.showMessage(f"Crawling {label}: {count} {unit}…")

    def _on_crawl_succeeded(self, summary: str) -> None:
        """Reload the catalogues after a successful crawl.

        Args:
            summary (str): The crawl summary.
        """
        self._load_outputs()
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
        worker.deleteLater()
        thread.deleteLater()
        self.crawl_thread, self.crawl_worker = None, None
        self._set_crawling(False, self.status_bar.currentMessage())

    def _start_crawl(
        self,
        provider: Optional[CloudProvider],
        country: Optional[Country] = None,
        source: str = CrawlWorker.CATALOGUE,
        providers: Optional[List[CloudProvider]] = None,
    ) -> None:
        """Start a crawl in a background thread, unless one is running.

        Args:
            provider (Optional[CloudProvider]): The crawled provider, `None` for several of them.
            country (Optional[Country]): The country whose providers are crawled when no provider is given, `None`
                for every provider.
            source (str): What is crawled, the catalogues (default) or the marketplaces.
            providers (Optional[List[CloudProvider]]): The crawled providers when no provider is given, `None` for
                every provider.
        """
        if self.crawl_thread is not None:
            self.logger.warning("A crawl is already running: the new one is ignored.")
            return
        if provider:
            label = self.theme.provider_label(provider)
        elif providers is not None:
            label = ", ".join(self.theme.provider_label(chosen) for chosen in providers)
        elif country:
            label = f"the {self.theme.country_label(country)} providers"
        else:
            label = "every provider"
        if source == CrawlWorker.MARKETPLACE:
            label = f"{label} (marketplaces)"
        elif source == CrawlWorker.STATISTICS:
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
        self.tabs.setCurrentWidget(self.marketplace_view)
        self._start_crawl(None, None, CrawlWorker.MARKETPLACE, [CloudProvider(value) for value in values])

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_marketplace_tab(self) -> bool:
        """Tell whether the marketplace view is shown.

        Returns:
            bool: Whether the "Marketplaces" tab is the current one.
        """
        return self.tabs.currentWidget() is self.marketplace_view

    def reload(self) -> None:
        """Reload every catalogue, marketplace and statistics file, changed or not."""
        self.logger.info("Reloading the catalogues and the marketplaces.")
        self.file_stamps.clear()
        self._load_outputs()

    def crawl_statistics(self) -> None:
        """Crawl the cloud market statistics (Synergy Research Group) again."""
        self._start_crawl(None, None, CrawlWorker.STATISTICS)

    def crawl_selected(self) -> None:
        """Crawl the provider or the country selected in the current tab, every provider when none is."""
        if self.tabs.currentWidget() is self.statistics_view:
            self.crawl_statistics()
            return
        if self.is_marketplace_tab():
            provider = self.marketplace_view.selected_provider()
            country = None if provider else self.marketplace_view.selected_country()
            self._start_crawl(provider, country, CrawlWorker.MARKETPLACE)
            return
        provider = self.sidebar.selected_provider()
        self._start_crawl(provider, None if provider else self.sidebar.selected_country())

    def crawl_all(self) -> None:
        """Crawl every provider catalogue, or every marketplace on the marketplace tab, several at a time."""
        if self.tabs.currentWidget() is self.statistics_view:
            self.crawl_statistics()
            return
        self._start_crawl(None, None, CrawlWorker.MARKETPLACE if self.is_marketplace_tab() else CrawlWorker.CATALOGUE)

    def open_output_folder(self) -> None:
        """Open the output folder in the file manager."""
        folder = self.store.output_dir.resolve()
        self.logger.debug("Opening the output folder %s.", folder)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self.logger.warning("The output folder %s cannot be opened.", folder)
            self.status_bar.showMessage(f"Cannot open {folder}.", 6000)

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
        logging.getLogger().removeHandler(self.log_handler)
        self.logger.info("%s closed.", self.TITLE)
        event.accept()
