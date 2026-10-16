from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QFileSystemWatcher
from PyQt6.QtGui import QCloseEvent
from pytestqt.qtbot import QtBot

from catalogue.store import CatalogueStore
from crawler.exception import CrawlerError
from crawler.factory import CrawlerFactory
from crawler.runner import CatalogueRunner, ProductCallback, ReportCallback, SoftwareCallback
from gui.crawl_worker import CrawlWorker
from gui.log_bridge.qt_log_handler import QtLogHandler
from gui.main_window import MainWindow
from gui.theme import Theme
from models.cloud.catalogue import CloudCatalogue
from models.cloud.enums import CloudProvider, Country, MarketPlayer, SoftwareCategory, SoftwareType
from models.cloud.marketplace import CloudMarketplace
from models.cloud.marketplace_software import MarketplaceSoftware
from models.cloud.product import CloudProduct
from models.stats.market_report import MarketReport
from models.stats.market_statistics import MarketStatistics

MakeCatalogue = Callable[[CloudProvider, List[str]], CloudCatalogue]


class FakeRunner(CatalogueRunner):
    """Runner writing pre-defined catalogues to the store, without crawling."""

    def __init__(
        self,
        store: CatalogueStore,
        make_catalogue: MakeCatalogue,
        error: Optional[Exception] = None,
        gate: Optional[threading.Event] = None,
    ) -> None:
        super().__init__(store=store)
        self.make_catalogue = make_catalogue
        self.error = error
        self.gate = gate

    async def run(self, target: Union[CloudProvider, str], on_product: Optional[ProductCallback] = None) -> Path:
        provider = CloudProvider(target)
        while self.gate is not None and not self.gate.is_set():
            await asyncio.sleep(0.01)
        if self.error:
            raise self.error
        if on_product:
            on_product(provider, CloudProduct(name="Fresh product", description="Just crawled"))
        return self.store.save(self.make_catalogue(provider, ["Fresh product"]))

    async def run_all(
        self, on_product: Optional[ProductCallback] = None, providers: Optional[List[CloudProvider]] = None
    ) -> Dict[CloudProvider, Path]:
        targets = list(CloudProvider) if providers is None else providers
        return {provider: await self.run(provider, on_product) for provider in targets}


@pytest.fixture
def store(tmp_path: Path, make_catalogue: MakeCatalogue) -> CatalogueStore:
    store = CatalogueStore(tmp_path / "output")
    store.save(make_catalogue(CloudProvider.AWS, ["Amazon EC2", "Amazon S3"]))
    store.save(make_catalogue(CloudProvider.SCALEWAY, ["Kubernetes Kapsule"]))
    return store


def _idle(window: MainWindow) -> Callable[[], bool]:
    return lambda: not window.is_crawling()


@pytest.fixture
def make_window(
    qtbot: QtBot, isolated_logging: None
) -> Iterator[Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow]]:
    windows: List[MainWindow] = []

    def build(store: CatalogueStore, runner: Optional[CatalogueRunner] = None) -> MainWindow:
        window = MainWindow(store, runner=runner, theme=Theme())
        qtbot.addWidget(window)
        windows.append(window)
        return window

    yield build
    for window in windows:
        qtbot.waitUntil(_idle(window), timeout=5000)
        window.close()


@pytest.fixture
def window(
    make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow], store: CatalogueStore
) -> MainWindow:
    return make_window(store, None)


class TestLoading:
    def test_loads_the_catalogues(self, window: MainWindow) -> None:
        assert window.windowTitle() == "Cloud Catalogue Explorer"
        assert set(window.catalogues) == {CloudProvider.AWS, CloudProvider.SCALEWAY}
        assert window.table_model.rowCount() == 3
        assert window.count_label.text() == "3 of 3 products shown"
        assert window.dashboard.providers_card.value_label.text() == "2 / 28"
        assert window.country_box.count() == 1 + len(Country)
        assert window.country_box.itemText(1) == "United States  (2)"
        assert window.country_box.itemText(2) == "France  (1)"
        assert not window.country_box.itemIcon(1).isNull()
        assert window.status_bar.currentMessage().startswith("2 catalogues loaded from")
        assert window.sidebar.provider_items[CloudProvider.AZURE].text() == "Microsoft Azure\nNot crawled yet"

    def test_unusable_files_are_reported(
        self, make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow], store: CatalogueStore
    ) -> None:
        store.path_for(CloudProvider.OVH).write_text("{not json", encoding="utf-8")

        window = make_window(store, None)

        assert window.errors == {CloudProvider.OVH: "the file is not valid JSON"}
        assert window.status_bar.currentMessage() == "2 catalogues loaded, 1 unusable files (see the logs)."
        assert "Unusable" in window.sidebar.provider_items[CloudProvider.OVH].text()

    def test_empty_output_folder_is_created(
        self, make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow], tmp_path: Path
    ) -> None:
        store = CatalogueStore(tmp_path / "missing" / "output")

        window = make_window(store, None)

        assert store.output_dir.is_dir()
        assert window.status_bar.currentMessage() == "No catalogue yet: launch a crawl (Ctrl+R / Ctrl+Shift+R)."
        assert isinstance(window.runner, CatalogueRunner)
        assert window.runner.store is store

    def test_logs_are_shown_in_the_log_panel(self, window: MainWindow) -> None:
        assert any(isinstance(handler, QtLogHandler) for handler in logging.getLogger().handlers)
        logging.getLogger("tests").warning("Visible in the GUI")

        assert "Visible in the GUI" in window.log_panel.view.toPlainText()

    def test_reload_action(self, window: MainWindow, store: CatalogueStore, make_catalogue: MakeCatalogue) -> None:
        store.save(make_catalogue(CloudProvider.GCP, ["Cloud Run"]))

        window.reload_action.trigger()

        assert window.table_model.rowCount() == 4

    def test_output_changes_reload_automatically(
        self, window: MainWindow, store: CatalogueStore, make_catalogue: MakeCatalogue, qtbot: QtBot
    ) -> None:
        store.save(make_catalogue(CloudProvider.AZURE, ["Azure Functions", "Azure SQL"]))

        qtbot.waitUntil(lambda: window.table_model.rowCount() == 5, timeout=5000)


class FailingWatcher(QFileSystemWatcher):
    """File watcher which cannot watch anything, as when the system watch limit is reached."""

    def addPath(self, path: Optional[str]) -> bool:  # noqa: N802 (Qt override)
        return False


class WorkingWatcher(QFileSystemWatcher):
    """File watcher which always succeeds, whatever the system watch limits."""

    def addPath(self, path: Optional[str]) -> bool:  # noqa: N802 (Qt override)
        return True


class TestWatching:
    def test_watched_output_is_not_polled(
        self,
        make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow],
        store: CatalogueStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("gui.main_window.QFileSystemWatcher", WorkingWatcher)

        window = make_window(store, None)

        assert not window.poll_timer.isActive()

    def test_unwatchable_output_is_polled(
        self,
        make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow],
        store: CatalogueStore,
        make_catalogue: MakeCatalogue,
        monkeypatch: pytest.MonkeyPatch,
        qtbot: QtBot,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setattr("gui.main_window.QFileSystemWatcher", FailingWatcher)

        window = make_window(store, None)
        window.poll_timer.setInterval(50)
        store.save(make_catalogue(CloudProvider.GCP, ["Cloud Run", "Cloud SQL"]))

        assert window.poll_timer.isActive()
        assert any("cannot be watched" in message for message in caplog.messages)
        qtbot.waitUntil(lambda: window.table_model.rowCount() == 5, timeout=5000)

    def test_unchanged_output_is_not_reloaded(self, window: MainWindow) -> None:
        window._poll_output()

        assert not window.reload_timer.isActive()


class TestBrowsing:
    def test_search_and_provider_filter(self, window: MainWindow) -> None:
        window.search_box.setText("amazon")
        assert window.count_label.text() == "2 of 3 products shown"

        window.sidebar.setCurrentItem(window.sidebar.provider_items[CloudProvider.SCALEWAY])
        assert window.count_label.text() == "0 of 3 products shown"

        window.search_box.clear()
        assert window.count_label.text() == "1 of 3 products shown"

    def test_country_filter(self, window: MainWindow) -> None:
        window.country_box.setCurrentIndex(window.country_box.findData(Country.FRANCE.value))

        assert window.count_label.text() == "1 of 3 products shown"
        assert window.sidebar.currentItem() is window.sidebar.country_items[Country.FRANCE]
        assert window.dashboard.providers_card.value_label.text() == "1 / 2"

        window.country_box.setCurrentIndex(0)

        assert window.count_label.text() == "3 of 3 products shown"
        assert window.sidebar.currentItem() is window.sidebar.all_item
        assert window.dashboard.providers_card.value_label.text() == "2 / 28"

    def test_sidebar_country_header_sets_the_country_filter(self, window: MainWindow) -> None:
        window.sidebar.setCurrentItem(window.sidebar.country_items[Country.UNITED_STATES])

        assert window.country_box.currentData() == "us"
        assert window.count_label.text() == "2 of 3 products shown"
        assert window.filter_model.provider is None

    def test_selected_provider_sets_its_country(self, window: MainWindow) -> None:
        window.sidebar.setCurrentItem(window.sidebar.provider_items[CloudProvider.SCALEWAY])

        assert window.country_box.currentData() == "fr"
        assert window.count_label.text() == "1 of 3 products shown"

    def test_other_country_replaces_the_selected_provider(self, window: MainWindow) -> None:
        window.sidebar.setCurrentItem(window.sidebar.provider_items[CloudProvider.SCALEWAY])

        window.country_box.setCurrentIndex(window.country_box.findData(Country.UNITED_STATES.value))

        assert window.sidebar.currentItem() is window.sidebar.country_items[Country.UNITED_STATES]
        assert (window.filter_model.provider, window.filter_model.country) == (None, Country.UNITED_STATES)
        assert window.count_label.text() == "2 of 3 products shown"

    def test_all_countries_keeps_the_selected_provider(self, window: MainWindow) -> None:
        window.sidebar.setCurrentItem(window.sidebar.provider_items[CloudProvider.SCALEWAY])

        window.country_box.setCurrentIndex(0)

        assert window.sidebar.selected_provider() is CloudProvider.SCALEWAY
        assert window.count_label.text() == "1 of 3 products shown"

    def test_selection_shows_the_details(self, window: MainWindow) -> None:
        window.search_box.setText("kapsule")

        window.table.selectRow(0)

        assert window.details.name_label.text() == "Kubernetes Kapsule"
        window.details.copy_button.click()
        assert window.status_bar.currentMessage() == "Product copied to the clipboard."

    def test_open_output_folder(self, window: MainWindow) -> None:
        with patch("gui.main_window.QDesktopServices.openUrl", return_value=True) as open_url:
            window.open_folder_action.trigger()

        assert open_url.call_args.args[0].toLocalFile() == str(window.store.output_dir.resolve())

    def test_output_folder_cannot_be_opened(self, window: MainWindow) -> None:
        with patch("gui.main_window.QDesktopServices.openUrl", return_value=False):
            window.open_output_folder()

        assert window.status_bar.currentMessage().startswith("Cannot open ")


class TestCrawling:
    def test_crawl_selected_provider(
        self,
        make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow],
        store: CatalogueStore,
        make_catalogue: MakeCatalogue,
        qtbot: QtBot,
    ) -> None:
        window = make_window(store, FakeRunner(store, make_catalogue))
        window.sidebar.setCurrentItem(window.sidebar.provider_items[CloudProvider.GCP])

        window.crawl_selected_action.trigger()

        assert window.is_crawling()
        assert not window.crawl_selected_action.isEnabled()
        assert window.status_bar.currentMessage().startswith("Crawling Google Cloud Platform")
        qtbot.waitUntil(lambda: not window.is_crawling(), timeout=5000)
        assert window.crawl_selected_action.isEnabled()
        assert CloudProvider.GCP in window.catalogues
        assert window.status_bar.currentMessage().startswith("Crawl over: 1 google-cloud-platform products written")

    def test_crawl_selected_country(
        self,
        make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow],
        store: CatalogueStore,
        make_catalogue: MakeCatalogue,
        qtbot: QtBot,
    ) -> None:
        window = make_window(store, FakeRunner(store, make_catalogue))
        window.sidebar.setCurrentItem(window.sidebar.country_items[Country.SWITZERLAND])

        window.crawl_selected_action.trigger()

        assert window.status_bar.currentMessage().startswith("Crawling the Switzerland providers")
        qtbot.waitUntil(lambda: not window.is_crawling(), timeout=5000)
        assert {CloudProvider.EXOSCALE, CloudProvider.INFOMANIAK} <= set(window.catalogues)
        assert CloudProvider.GCP not in window.catalogues
        assert window.status_bar.currentMessage() == "Crawl over: 2 catalogues updated."

    def test_crawl_all(
        self,
        make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow],
        store: CatalogueStore,
        make_catalogue: MakeCatalogue,
        qtbot: QtBot,
    ) -> None:
        window = make_window(store, FakeRunner(store, make_catalogue))

        window.crawl_all_action.trigger()

        qtbot.waitUntil(lambda: not window.is_crawling(), timeout=5000)
        assert len(window.catalogues) == len(CloudProvider)
        assert window.status_bar.currentMessage() == "Crawl over: 28 catalogues updated."

    def test_progress_message(self, window: MainWindow) -> None:
        window._on_product_crawled("scaleway", 3)

        assert window.status_bar.currentMessage() == "Crawling Scaleway: 3 products…"

    def test_failed_crawl_is_reported(
        self,
        make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow],
        store: CatalogueStore,
        make_catalogue: MakeCatalogue,
        qtbot: QtBot,
    ) -> None:
        window = make_window(store, FakeRunner(store, make_catalogue, error=CrawlerError("blocked")))

        with patch("gui.main_window.QMessageBox.warning") as warning:
            window.crawl_all()
            qtbot.waitUntil(lambda: not window.is_crawling(), timeout=5000)

        assert warning.call_args.args[1:] == ("Crawl failed", "blocked\n\nSee the logs panel for the details.")
        assert window.status_bar.currentMessage() == "Crawl failed: blocked"

    def test_one_crawl_at_a_time_and_no_closing_meanwhile(
        self,
        make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow],
        store: CatalogueStore,
        make_catalogue: MakeCatalogue,
        qtbot: QtBot,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        gate = threading.Event()
        window = make_window(store, FakeRunner(store, make_catalogue, gate=gate))
        window.crawl_selected()
        thread = window.crawl_thread

        window.crawl_all()
        event = QCloseEvent()
        window.closeEvent(event)

        assert window.crawl_thread is thread
        assert "A crawl is already running: the new one is ignored." in caplog.messages
        assert not event.isAccepted()
        assert window.status_bar.currentMessage() == "A crawl is running: close the window once it is over."
        gate.set()
        qtbot.waitUntil(lambda: not window.is_crawling(), timeout=5000)


class TestClosing:
    def test_close_detaches_the_log_panel(self, window: MainWindow) -> None:
        event = QCloseEvent()

        window.closeEvent(event)

        assert event.isAccepted()
        assert window.log_handler not in logging.getLogger().handlers

    def test_missing_event_is_ignored(self, window: MainWindow) -> None:
        window.closeEvent(None)

        assert window.log_handler in logging.getLogger().handlers


def test_runner_is_used_for_the_crawls(window: MainWindow) -> None:
    assert isinstance(window.runner, CatalogueRunner)
    assert window.runner.store is window.store
    assert isinstance(MagicMock(spec=MainWindow), MainWindow)


MakeMarketplace = Callable[[CloudProvider, List[MarketplaceSoftware]], CloudMarketplace]
MARKETPLACE_PROVIDERS = [CloudProvider.AWS, CloudProvider.CIVO]


class FakeMarketplaceRunner(FakeRunner):
    """Runner writing pre-defined marketplaces to the store, without crawling."""

    def __init__(
        self,
        store: CatalogueStore,
        make_catalogue: MakeCatalogue,
        make_marketplace: MakeMarketplace,
        make_software: Callable[..., MarketplaceSoftware],
    ) -> None:
        super().__init__(store, make_catalogue)
        self.make_marketplace = make_marketplace
        self.make_software = make_software
        self.factory = MagicMock(spec=CrawlerFactory)
        self.factory.marketplace_providers.return_value = MARKETPLACE_PROVIDERS

    async def run_marketplace(
        self, target: Union[CloudProvider, str], on_software: Optional[SoftwareCallback] = None
    ) -> Path:
        provider = CloudProvider(target)
        listing = self.make_software("Fresh app", [SoftwareType.CRM], [SoftwareCategory.END_USER_SOFTWARE])
        if on_software:
            on_software(provider, listing)
        return self.marketplace_store.save(self.make_marketplace(provider, [listing]))

    async def run_all_marketplaces(
        self, on_software: Optional[SoftwareCallback] = None, providers: Optional[List[CloudProvider]] = None
    ) -> Dict[CloudProvider, Path]:
        targets = MARKETPLACE_PROVIDERS if providers is None else providers
        return {provider: await self.run_marketplace(provider, on_software) for provider in targets}


class HalfWatcher(QFileSystemWatcher):
    """File watcher which can watch the first folder only."""

    def addPath(self, path: Optional[str]) -> bool:  # noqa: N802 (Qt override)
        return not path or not path.endswith("marketplaces")


class TestMarketplaces:
    @pytest.fixture
    def runner(
        self,
        store: CatalogueStore,
        make_catalogue: MakeCatalogue,
        make_marketplace: MakeMarketplace,
        make_software: Callable[..., MarketplaceSoftware],
    ) -> FakeMarketplaceRunner:
        runner = FakeMarketplaceRunner(store, make_catalogue, make_marketplace, make_software)
        listing = make_software("Datadog", [SoftwareType.MONITORING], [SoftwareCategory.DEVELOPER_TOOL])
        runner.marketplace_store.save(make_marketplace(CloudProvider.AWS, [listing]))
        return runner

    @pytest.fixture
    def marketplace_window(
        self,
        make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow],
        store: CatalogueStore,
        runner: FakeMarketplaceRunner,
    ) -> MainWindow:
        window = make_window(store, runner)
        window.tabs.setCurrentWidget(window.marketplace_view)
        return window

    def test_loads_the_marketplaces(self, marketplace_window: MainWindow) -> None:
        assert set(marketplace_window.marketplaces) == {CloudProvider.AWS}
        assert marketplace_window.marketplace_view.count_label.text() == "1 of 1 software shown"
        assert marketplace_window.tabs.tabText(1) == "Marketplaces"
        assert marketplace_window.is_marketplace_tab()

    def test_unusable_marketplace_files_are_reported(
        self,
        make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow],
        store: CatalogueStore,
        runner: FakeMarketplaceRunner,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        runner.marketplace_store.path_for(CloudProvider.CIVO).write_text("{", encoding="utf-8")

        window = make_window(store, runner)

        assert window.marketplace_errors == {CloudProvider.CIVO: "the file is not valid JSON"}
        assert "1 marketplaces loaded, 1 unusable files (see the logs)." in caplog.messages

    def test_crawl_the_selected_marketplace(self, marketplace_window: MainWindow, qtbot: QtBot) -> None:
        view = marketplace_window.marketplace_view
        view.provider_box.setCurrentIndex(view.provider_box.findData(CloudProvider.CIVO.value))

        marketplace_window.crawl_selected_action.trigger()

        assert marketplace_window.status_bar.currentMessage().startswith("Crawling Civo (marketplaces)")
        qtbot.waitUntil(lambda: not marketplace_window.is_crawling(), timeout=5000)
        assert CloudProvider.CIVO in marketplace_window.marketplaces
        assert marketplace_window.status_bar.currentMessage().startswith("Crawl over: 1 civo software written")

    def test_crawl_the_marketplaces_of_a_country(self, marketplace_window: MainWindow, qtbot: QtBot) -> None:
        view = marketplace_window.marketplace_view
        view.country_box.setCurrentIndex(view.country_box.findData(Country.UNITED_KINGDOM.value))

        marketplace_window.crawl_selected()

        qtbot.waitUntil(lambda: not marketplace_window.is_crawling(), timeout=5000)
        assert marketplace_window.status_bar.currentMessage() == "Crawl over: 1 marketplaces updated."

    def test_crawl_every_marketplace(self, marketplace_window: MainWindow, qtbot: QtBot) -> None:
        marketplace_window.crawl_all_action.trigger()

        qtbot.waitUntil(lambda: not marketplace_window.is_crawling(), timeout=5000)
        assert set(marketplace_window.marketplaces) == set(MARKETPLACE_PROVIDERS)
        assert marketplace_window.status_bar.currentMessage() == "Crawl over: 2 marketplaces updated."

    def test_progress_counts_software(self, marketplace_window: MainWindow) -> None:
        marketplace_window.crawl_source = CrawlWorker.MARKETPLACE

        marketplace_window._on_product_crawled("civo", 4)

        assert marketplace_window.status_bar.currentMessage() == "Crawling Civo: 4 software…"

    def test_marketplace_changes_are_detected(
        self, marketplace_window: MainWindow, runner: FakeMarketplaceRunner, qtbot: QtBot
    ) -> None:
        asyncio.run(runner.run_marketplace(CloudProvider.CIVO))

        marketplace_window._poll_output()

        assert marketplace_window.reload_timer.isActive()
        qtbot.waitUntil(lambda: CloudProvider.CIVO in marketplace_window.marketplaces, timeout=5000)

    def test_unwatchable_marketplace_folder_is_polled(
        self,
        make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow],
        store: CatalogueStore,
        runner: FakeMarketplaceRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("gui.main_window.QFileSystemWatcher", HalfWatcher)

        window = make_window(store, runner)

        assert window.poll_timer.isActive()

    def test_copied_software_is_reported(self, marketplace_window: MainWindow) -> None:
        marketplace_window.marketplace_view.copied.emit("Datadog")

        assert marketplace_window.status_bar.currentMessage() == "Software copied to the clipboard."


class TestMarketplaceMenu:
    @pytest.fixture
    def menu_window(
        self,
        make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow],
        store: CatalogueStore,
        make_catalogue: MakeCatalogue,
        make_marketplace: MakeMarketplace,
        make_software: Callable[..., MarketplaceSoftware],
    ) -> MainWindow:
        runner = FakeMarketplaceRunner(store, make_catalogue, make_marketplace, make_software)
        listing = make_software("Datadog", [SoftwareType.MONITORING], [SoftwareCategory.DEVELOPER_TOOL])
        runner.marketplace_store.save(make_marketplace(CloudProvider.AWS, [listing]))
        return make_window(store, runner)

    def test_menu_bar_and_toolbar_button(self, menu_window: MainWindow) -> None:
        menu_bar = menu_window.menuBar()
        assert menu_bar is not None
        assert menu_window.marketplace_menu.menuAction() in menu_bar.actions()
        assert menu_window.marketplace_button.menu() is menu_window.marketplace_menu
        assert list(menu_window.marketplace_menu.provider_actions) == MARKETPLACE_PROVIDERS

    def test_counts_follow_the_loaded_marketplaces(self, menu_window: MainWindow) -> None:
        actions = menu_window.marketplace_menu.provider_actions

        assert actions[CloudProvider.AWS].text() == "Amazon Web Services  (1)"
        assert actions[CloudProvider.CIVO].text() == "Civo"

    def test_extract_the_chosen_marketplaces(self, menu_window: MainWindow, qtbot: QtBot) -> None:
        menu_window.marketplace_menu.select([CloudProvider.CIVO])

        menu_window.marketplace_menu.extract_action.trigger()

        assert menu_window.is_marketplace_tab()
        assert menu_window.status_bar.currentMessage().startswith("Crawling Civo (marketplaces)")
        qtbot.waitUntil(lambda: not menu_window.is_crawling(), timeout=5000)
        assert menu_window.status_bar.currentMessage() == "Crawl over: 1 marketplaces updated."
        assert menu_window.marketplace_menu.provider_actions[CloudProvider.CIVO].text() == "Civo  (1)"


class FakeStatisticsRunner(FakeRunner):
    """Runner writing pre-defined market statistics, without crawling."""

    def __init__(self, store: CatalogueStore, make_catalogue: MakeCatalogue, statistics: MarketStatistics) -> None:
        super().__init__(store, make_catalogue)
        self.statistics = statistics

    async def run_statistics(self, name: str = "synergy", on_report: Optional[ReportCallback] = None) -> Path:
        return self.statistics_store.save(name, self.statistics)


class TestStatistics:
    @pytest.fixture
    def statistics(self, make_report: Callable[..., MarketReport]) -> MarketStatistics:
        report = make_report("2026Q2", [(MarketPlayer.AMAZON, 28), (MarketPlayer.MICROSOFT, 20)], market_size_bn=143.4)
        crawled_at = datetime(2026, 10, 16, tzinfo=UTC)
        return MarketStatistics(source="Synergy Research Group", crawled_at=crawled_at, reports=[report])

    @pytest.fixture
    def runner(
        self, store: CatalogueStore, make_catalogue: MakeCatalogue, statistics: MarketStatistics
    ) -> FakeStatisticsRunner:
        return FakeStatisticsRunner(store, make_catalogue, statistics)

    @pytest.fixture
    def statistics_window(
        self,
        make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow],
        store: CatalogueStore,
        runner: FakeStatisticsRunner,
    ) -> MainWindow:
        window = make_window(store, runner)
        window.tabs.setCurrentWidget(window.statistics_view)
        return window

    def test_no_statistics_yet(self, statistics_window: MainWindow) -> None:
        assert statistics_window.tabs.tabText(2) == "Statistics"
        assert statistics_window.statistics is None
        assert statistics_window.runner.statistics_store.output_dir.is_dir()

    def test_unusable_statistics_file_is_reported(
        self,
        make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow],
        store: CatalogueStore,
        runner: FakeStatisticsRunner,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        runner.statistics_store.output_dir.mkdir(parents=True)
        runner.statistics_store.path_for("synergy").write_text("{", encoding="utf-8")

        window = make_window(store, runner)

        assert window.statistics is None
        assert "The market statistics file is unusable: the file is not valid JSON" in caplog.messages

    @pytest.mark.parametrize("trigger", ["refresh", "selected", "all"])
    def test_crawl_the_statistics(
        self, statistics_window: MainWindow, statistics: MarketStatistics, qtbot: QtBot, trigger: str
    ) -> None:
        if trigger == "refresh":
            statistics_window.statistics_view.refresh_button.click()
        elif trigger == "selected":
            statistics_window.crawl_selected_action.trigger()
        else:
            statistics_window.crawl_all_action.trigger()

        assert statistics_window.status_bar.currentMessage().startswith(
            "Crawling the market statistics (Synergy Research Group)"
        )
        qtbot.waitUntil(lambda: not statistics_window.is_crawling(), timeout=5000)
        assert statistics_window.statistics == statistics
        assert statistics_window.statistics_view.panel.periods() == ["2026Q2"]
        assert statistics_window.status_bar.currentMessage().startswith("Crawl over: market statistics written to")


class TestProgressiveLoading:
    def test_only_changed_files_are_read_again(
        self, window: MainWindow, store: CatalogueStore, make_catalogue: MakeCatalogue
    ) -> None:
        in_progress = make_catalogue(CloudProvider.AWS, ["Amazon EC2"]).model_copy(update={"in_progress": True})
        store.save(in_progress)

        with patch.object(store, "load", wraps=store.load) as load:
            window._load_outputs()

        assert [call.args[0] for call in load.call_args_list] == [CloudProvider.AWS]
        assert window.catalogues[CloudProvider.AWS].in_progress
        assert window.sidebar.provider_items[CloudProvider.AWS].text().endswith(" · crawling…")
        assert set(window.catalogues) == {CloudProvider.AWS, CloudProvider.SCALEWAY}

    def test_unchanged_outputs_are_not_read_again(self, window: MainWindow, store: CatalogueStore) -> None:
        with patch.object(store, "load", wraps=store.load) as load:
            window._load_outputs()

        load.assert_not_called()

    def test_removed_file_is_unloaded(self, window: MainWindow, store: CatalogueStore) -> None:
        store.path_for(CloudProvider.SCALEWAY).unlink()

        window._load_outputs()

        assert set(window.catalogues) == {CloudProvider.AWS}

    def test_reload_reads_every_file(self, window: MainWindow, store: CatalogueStore) -> None:
        with patch.object(store, "load", wraps=store.load) as load:
            window.reload_action.trigger()

        assert load.call_count == len(CloudProvider)

    def test_unchanged_marketplace_rows_are_reused(
        self,
        make_window: Callable[[CatalogueStore, Optional[CatalogueRunner]], MainWindow],
        store: CatalogueStore,
        make_catalogue: MakeCatalogue,
        make_marketplace: MakeMarketplace,
        make_software: Callable[..., MarketplaceSoftware],
    ) -> None:
        runner = FakeMarketplaceRunner(store, make_catalogue, make_marketplace, make_software)
        listing = make_software("Datadog", [SoftwareType.MONITORING], [SoftwareCategory.DEVELOPER_TOOL])
        runner.marketplace_store.save(make_marketplace(CloudProvider.AWS, [listing]))
        window = make_window(store, runner)
        aws_rows = window.marketplace_view.table_model.provider_rows[CloudProvider.AWS][1]

        runner.marketplace_store.save(make_marketplace(CloudProvider.CIVO, [listing]))
        window._load_outputs()

        model = window.marketplace_view.table_model
        assert model.provider_rows[CloudProvider.AWS][1] is aws_rows
        assert [row.provider for row in model.rows] == [CloudProvider.AWS, CloudProvider.CIVO]
