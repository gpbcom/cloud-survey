from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator, Iterator
from functools import partial
from typing import Callable, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from pydantic import JsonValue
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QAbstractItemView, QApplication
from pytestqt.qtbot import QtBot

from conftest import CRAWLED_AT, build_product, build_report, seed_catalogue, seed_marketplace
from crawler.enums import CrawlSource
from crawler.exception import CrawlerError
from crawler.factory import CrawlerFactory
from crawler.runner import CatalogueRunner
from gui.layout.panes.section_stack import SectionStack
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from gui.window.main_window import MainWindow
from models.cloud.enums import CloudProvider, Country, MarketPlayer, SoftwareCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.configuration.storage.storage_settings import StorageSettings
from models.stats.market_statistics import MarketStatistics
from models.storage.pages.item_query import ItemQuery
from storage.storage import Storage

pytestmark = pytest.mark.db

MARKETPLACE_PROVIDERS = [CloudProvider.AWS, CloudProvider.CIVO]


class FakeCrawler:
    """Stand-in for a crawler, streaming one item, optionally after a gate opens or with an error."""

    source = "Synergy Research Group"

    def __init__(
        self, item: Dict[str, JsonValue], error: Optional[Exception] = None, gate: Optional[threading.Event] = None
    ) -> None:
        self.item = item
        self.error = error
        self.gate = gate

    async def stream(self) -> AsyncIterator[Dict[str, JsonValue]]:
        while self.gate is not None and not self.gate.is_set():
            await asyncio.sleep(0.01)
        if self.error:
            raise self.error
        yield self.item


def fake_factory(error: Optional[Exception] = None, gate: Optional[threading.Event] = None) -> MagicMock:
    factory = MagicMock(spec=CrawlerFactory)
    factory.marketplace_providers.return_value = MARKETPLACE_PROVIDERS
    factory.get.side_effect = lambda target: FakeCrawler(
        {"name": "Fresh product", "description": "Just crawled", "pricing_policy": []}, error, gate
    )
    factory.get_marketplace.side_effect = lambda target, classifier: FakeCrawler(
        {
            "name": "Fresh app",
            "description": "Just crawled",
            "url": f"https://market.example/{CloudProvider(target).value}/fresh",
            "categories": ["end-user-software"],
            "marketplace_categories": ["CRM"],
        }
    )
    factory.get_statistics.side_effect = lambda name: FakeCrawler(build_report("2026Q2", []).model_dump(mode="json"))
    return factory


async def seed(storage: Storage, make_software: Callable[..., MarketplaceSoftware]) -> None:
    await seed_catalogue(
        storage, CloudProvider.AWS, [build_product("Amazon EC2"), build_product("Amazon SimpleDB", deleted=True)]
    )
    await seed_catalogue(storage, CloudProvider.SCALEWAY, [build_product("Kubernetes Kapsule")])
    await seed_marketplace(
        storage,
        CloudProvider.CIVO,
        [make_software("Grafana", ["monitoring"], [SoftwareCategory.DEVELOPER_TOOL])],
    )


@pytest.fixture
def make_window(
    qtbot: QtBot, gui_loop: StorageLoop, storage_settings: StorageSettings, isolated_logging: None
) -> Iterator[Callable[[Optional[MagicMock]], MainWindow]]:
    windows: List[MainWindow] = []

    def build(factory: Optional[MagicMock] = None) -> MainWindow:
        runner = CatalogueRunner(storage=Storage(storage_settings), factory=factory or fake_factory(), save_interval=0)
        window = MainWindow(gui_loop, runner=runner, theme=Theme())
        qtbot.addWidget(window)
        windows.append(window)
        qtbot.waitUntil(lambda: bool(window.revisions), timeout=5000)
        return window

    yield build
    for window in windows:
        qtbot.waitUntil(partial(idle, window), timeout=10_000)
        window.close()


def idle(window: MainWindow) -> bool:
    return not window.is_crawling()


def shown(window: MainWindow, qtbot: QtBot, total: int) -> List[str]:
    qtbot.waitUntil(lambda: window.table_model.total == total, timeout=5000)
    qtbot.waitUntil(lambda: all(window.table_model.row(row) is not None for row in range(total)), timeout=5000)
    return [row.product.name for number in range(total) if (row := window.table_model.row(number)) is not None]


class TestLoading:
    async def test_shows_the_stored_datasets(
        self,
        storage: Storage,
        make_software: Callable[..., MarketplaceSoftware],
        make_window: Callable[[Optional[MagicMock]], MainWindow],
        qtbot: QtBot,
    ) -> None:
        await seed(storage, make_software)

        window = make_window(None)

        assert set(window.catalogues) == {CloudProvider.AWS, CloudProvider.SCALEWAY}
        assert shown(window, qtbot, 2) == ["Amazon EC2", "Kubernetes Kapsule"]
        qtbot.waitUntil(lambda: window.count_label.text() == "2 of 2 products shown (1 deleted hidden)")
        assert window.sidebar.all_item.text() == "All providers\n2 products · 2/32 crawled"
        assert window.country_box.itemText(window.country_box.findData(Country.FRANCE.value)) == "France  (1)"
        assert list(window.marketplaces) == [CloudProvider.CIVO]
        assert window.marketplace_menu.provider_actions[CloudProvider.CIVO].text() == "Civo  (1)"

    def test_an_empty_storage_invites_to_crawl(
        self, make_window: Callable[[Optional[MagicMock]], MainWindow], qtbot: QtBot
    ) -> None:
        window = make_window(None)

        assert window.status_bar.currentMessage() == "No catalogue yet: launch a crawl (Ctrl+R / Ctrl+Shift+R)."
        qtbot.waitUntil(lambda: window.count_label.text() == "0 of 0 products shown")

    def test_an_unavailable_storage_is_reported_and_retried(
        self, qtbot: QtBot, isolated_logging: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        loop = StorageLoop(Storage(StorageSettings(url="postgresql+asyncpg://u:p@127.0.0.1:9/nowhere")))
        window = MainWindow(loop, runner=CatalogueRunner(factory=fake_factory()), theme=Theme())
        qtbot.addWidget(window)

        qtbot.waitUntil(lambda: window.storage_error is not None, timeout=10_000)

        assert window.status_bar.currentMessage().startswith("Database unavailable: Cannot use the database")
        window.close()

    async def test_written_items_appear_at_the_next_poll(
        self, storage: Storage, make_window: Callable[[Optional[MagicMock]], MainWindow], qtbot: QtBot
    ) -> None:
        window = make_window(None)
        await seed_catalogue(storage, CloudProvider.CIVO, [build_product("Kubernetes")])

        window.poll()

        assert shown(window, qtbot, 1) == ["Kubernetes"]
        qtbot.waitUntil(lambda: CloudProvider.CIVO in window.catalogues)
        await storage.catalogues.create(CloudProvider.CIVO, build_product("Object Storage"))
        window.reload_action.trigger()
        assert shown(window, qtbot, 2) == ["Kubernetes", "Object Storage"]

    def test_logs_are_shown_in_the_log_panel(self, make_window: Callable[[Optional[MagicMock]], MainWindow]) -> None:
        window = make_window(None)

        window.logger.warning("Something to see.")

        assert "Something to see." in window.log_panel.view.toPlainText()


class TestBrowsing:
    @pytest.fixture
    async def window(
        self,
        storage: Storage,
        make_software: Callable[..., MarketplaceSoftware],
        make_window: Callable[[Optional[MagicMock]], MainWindow],
        qtbot: QtBot,
    ) -> MainWindow:
        await seed(storage, make_software)
        window = make_window(None)
        shown(window, qtbot, 2)
        return window

    def test_search(self, window: MainWindow, qtbot: QtBot) -> None:
        window.search_box.setText("kapsule")

        assert shown(window, qtbot, 1) == ["Kubernetes Kapsule"]
        window.search_box.setText("description")
        assert shown(window, qtbot, 0) == []
        window.description_box.setChecked(True)
        assert shown(window, qtbot, 2) == ["Amazon EC2", "Kubernetes Kapsule"]

    def test_provider_and_country_filters(self, window: MainWindow, qtbot: QtBot) -> None:
        window.sidebar.setCurrentItem(window.sidebar.provider_items[CloudProvider.AWS])
        assert shown(window, qtbot, 1) == ["Amazon EC2"]
        assert window.country_box.currentData() == Country.UNITED_STATES.value

        window.country_box.setCurrentIndex(window.country_box.findData(Country.FRANCE.value))
        assert shown(window, qtbot, 1) == ["Kubernetes Kapsule"]
        assert window.sidebar.selected_country() is Country.FRANCE
        assert window.dashboard.products_card.value_label.text() == "1"

        window.country_box.setCurrentIndex(0)
        assert shown(window, qtbot, 2) == ["Amazon EC2", "Kubernetes Kapsule"]

    def test_deleted_products_are_shown_on_request(self, window: MainWindow, qtbot: QtBot) -> None:
        window.deleted_box.setChecked(True)

        assert shown(window, qtbot, 3) == ["Amazon EC2", "Amazon SimpleDB", "Kubernetes Kapsule"]
        qtbot.waitUntil(lambda: window.count_label.text() == "3 of 2 products shown (1 deleted included)")

    def test_selection_shows_the_details(self, window: MainWindow) -> None:
        window.table.selectRow(0)

        assert window.details.name_label.text() == "Amazon EC2"

    def test_the_window_fits_common_screens_so_it_can_be_maximized(
        self, window: MainWindow, qapp: QApplication
    ) -> None:
        Theme().apply(qapp)
        for shown in (False, True):
            window.more_button.setChecked(shown)
            window.marketplace_view.more_button.setChecked(shown)
            for index in range(window.tabs.count()):
                window.tabs.setCurrentIndex(index)
                qapp.processEvents()
                hint = window.minimumSizeHint()
                assert hint.width() <= 1280, (window.tabs.tabText(index), shown, hint)
                assert hint.height() <= 820, (window.tabs.tabText(index), shown, hint)
        assert window.maximumWidth() > 10_000

    def test_the_panels_fold_and_the_logs_come_back(self, window: MainWindow) -> None:
        window.table_section.set_expanded(False)
        assert window.table_stack.is_folded()
        window.details_pane.toggle.click()
        assert window.details_pane.is_folded()
        window.log_dock.close_button.click()
        assert window.logs_button.isVisibleTo(window)

        window.logs_button.click()

        assert not window.log_dock.isHidden()
        assert not window.log_dock.is_folded()
        assert not window.logs_button.isVisibleTo(window)
        window.table_section.set_expanded(True)
        window.details_pane.toggle.click()

    def test_concurrency_box(self, window: MainWindow, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO, logger="gui.window.main_window")

        window.concurrency_box.setValue(7)

        assert window.runner.concurrency == 7
        assert "The next crawls run 7 providers at the same time." in caplog.messages


class TestEditing:
    @pytest.fixture
    async def window(
        self,
        storage: Storage,
        make_software: Callable[..., MarketplaceSoftware],
        make_window: Callable[[Optional[MagicMock]], MainWindow],
        qtbot: QtBot,
    ) -> MainWindow:
        await seed(storage, make_software)
        window = make_window(None)
        shown(window, qtbot, 2)
        return window

    def test_both_tables_select_several_rows_with_their_actions(self, window: MainWindow) -> None:
        for table, actions in (
            (window.table, window.product_actions),
            (window.marketplace_view.table, window.marketplace_view.item_actions),
        ):
            assert table.selectionMode() is QAbstractItemView.SelectionMode.ExtendedSelection
            assert table.actions() == [actions.new_action, actions.edit_action, actions.delete_action]
        assert (
            window.marketplace_view.delete_button.defaultAction() is window.marketplace_view.item_actions.delete_action
        )

    async def test_the_selected_products_are_deleted_from_the_window(
        self, window: MainWindow, storage: Storage, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window.table.selectAll()
        monkeypatch.setattr(window.product_actions, "_confirm", lambda count: True)

        window.product_actions.delete()

        qtbot.waitUntil(lambda: window.status_bar.currentMessage() == "2 items deleted.", timeout=5000)
        assert shown(window, qtbot, 0) == []
        assert (await storage.catalogues.list(ItemQuery())).total == 0

    def test_a_failed_action_is_warned(self, window: MainWindow) -> None:
        with patch("gui.window.main_window.QMessageBox.warning") as warning:
            window.product_actions.failed.emit("the civo catalogue is being crawled")

        warning.assert_called_once()
        assert window.status_bar.currentMessage() == "Not saved: the civo catalogue is being crawled"


class TestProviderFilterAndSelection:
    @pytest.fixture
    async def window(
        self,
        storage: Storage,
        make_software: Callable[..., MarketplaceSoftware],
        make_window: Callable[[Optional[MagicMock]], MainWindow],
        qtbot: QtBot,
    ) -> MainWindow:
        await seed(storage, make_software)
        window = make_window(None)
        shown(window, qtbot, 2)
        return window

    def test_the_provider_filter_follows_the_country_and_the_sidebar(self, window: MainWindow, qtbot: QtBot) -> None:
        assert window.provider_box.count() == len(CloudProvider) + 1
        assert window.provider_box.itemText(0) == "All providers  (2)"

        window.provider_box.setCurrentIndex(window.provider_box.findData(CloudProvider.SCALEWAY.value))

        assert shown(window, qtbot, 1) == ["Kubernetes Kapsule"]
        assert window.sidebar.selected_provider() is CloudProvider.SCALEWAY
        assert window.country_box.currentData() == Country.FRANCE.value
        assert all(
            CloudProvider(window.provider_box.itemData(index)).country is Country.FRANCE
            for index in range(1, window.provider_box.count())
        ), "the providers of the chosen country only"
        window.sidebar.setCurrentItem(window.sidebar.provider_items[CloudProvider.AWS])
        assert window.provider_box.currentData() == CloudProvider.AWS.value
        assert shown(window, qtbot, 1) == ["Amazon EC2"]
        window.provider_box.setCurrentIndex(0)
        assert window.sidebar.selected_provider() is None
        assert window.country_box.currentData() == Country.UNITED_STATES.value

    def test_a_bulk_selection_replaces_the_filters_until_cleared(self, window: MainWindow, qtbot: QtBot) -> None:
        assert window.select_button.defaultAction() is window.selection_actions.select_action
        assert window.selection_button.isHidden()

        window.selection_actions.filter_requested.emit(ItemQuery(providers=[CloudProvider.AWS], include_deleted=True))

        assert shown(window, qtbot, 2) == ["Amazon EC2", "Amazon SimpleDB"]
        assert not window.selection_button.isHidden()
        assert not window.search_box.isEnabled()
        assert not window.provider_box.isEnabled()
        window.selection_button.click()
        assert shown(window, qtbot, 2) == ["Amazon EC2", "Kubernetes Kapsule"]
        assert window.search_box.isEnabled()
        assert window.selection_query is None

    def test_the_marketplace_view_shows_a_bulk_selection(self, window: MainWindow, qtbot: QtBot) -> None:
        view = window.marketplace_view
        assert view.select_button.defaultAction() is view.selection_actions.select_action
        assert view.new_button.defaultAction() is view.item_actions.new_action

        view.selection_actions.filter_requested.emit(ItemQuery(providers=[CloudProvider.AWS]))

        qtbot.waitUntil(lambda: view.table_model.total == 0, timeout=5000)
        assert not view.search_box.isEnabled()
        view.clear_selection()
        qtbot.waitUntil(lambda: view.table_model.total == 1, timeout=5000)
        assert view.search_box.isEnabled()


class TestCrawling:
    def test_crawl_selected_provider(
        self, make_window: Callable[[Optional[MagicMock]], MainWindow], qtbot: QtBot
    ) -> None:
        window = make_window(None)
        window.sidebar.setCurrentItem(window.sidebar.provider_items[CloudProvider.GCP])

        window.crawl_selected_action.trigger()

        assert window.is_crawling()
        assert not window.crawl_selected_action.isEnabled()
        assert window.status_bar.currentMessage().startswith("Crawling Google Cloud Platform")
        qtbot.waitUntil(lambda: not window.is_crawling(), timeout=10_000)
        assert window.crawl_selected_action.isEnabled()
        assert window.status_bar.currentMessage() == (
            "Crawl over: 1 google-cloud-platform products written (0 added, 0 updated, 0 deleted)."
        )
        qtbot.waitUntil(lambda: CloudProvider.GCP in window.catalogues, timeout=5000)
        assert shown(window, qtbot, 1) == ["Fresh product"]

    def test_crawl_selected_country(
        self, make_window: Callable[[Optional[MagicMock]], MainWindow], qtbot: QtBot
    ) -> None:
        window = make_window(None)
        window.sidebar.setCurrentItem(window.sidebar.country_items[Country.SWITZERLAND])

        window.crawl_selected_action.trigger()

        assert window.status_bar.currentMessage().startswith("Crawling the Switzerland providers")
        qtbot.waitUntil(lambda: not window.is_crawling(), timeout=10_000)
        assert window.status_bar.currentMessage() == "Crawl over: 2 catalogues updated."
        qtbot.waitUntil(lambda: {CloudProvider.EXOSCALE, CloudProvider.INFOMANIAK} == set(window.catalogues))

    def test_progress_message(self, make_window: Callable[[Optional[MagicMock]], MainWindow]) -> None:
        window = make_window(None)

        window._on_product_crawled("scaleway", 3)

        assert window.status_bar.currentMessage() == "Crawling Scaleway: 3 products…"

    def test_failed_crawl_is_reported(
        self, make_window: Callable[[Optional[MagicMock]], MainWindow], qtbot: QtBot
    ) -> None:
        window = make_window(fake_factory(error=CrawlerError("blocked")))
        window.sidebar.setCurrentItem(window.sidebar.provider_items[CloudProvider.GCP])

        with patch("gui.window.main_window.QMessageBox.warning") as warning:
            window.crawl_selected()
            qtbot.waitUntil(lambda: not window.is_crawling(), timeout=10_000)

        assert warning.call_args.args[1:] == ("Crawl failed", "blocked\n\nSee the logs panel for the details.")
        assert window.status_bar.currentMessage() == "Crawl failed: blocked"

    def test_one_crawl_at_a_time_and_no_closing_meanwhile(
        self, make_window: Callable[[Optional[MagicMock]], MainWindow], qtbot: QtBot, caplog: pytest.LogCaptureFixture
    ) -> None:
        gate = threading.Event()
        window = make_window(fake_factory(gate=gate))
        window.sidebar.setCurrentItem(window.sidebar.provider_items[CloudProvider.GCP])
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
        qtbot.waitUntil(lambda: not window.is_crawling(), timeout=10_000)


class TestMarketplaces:
    async def test_marketplace_crawls_from_the_tab_and_the_menu(
        self,
        storage: Storage,
        make_software: Callable[..., MarketplaceSoftware],
        make_window: Callable[[Optional[MagicMock]], MainWindow],
        qtbot: QtBot,
    ) -> None:
        await seed(storage, make_software)
        window = make_window(None)
        window.tabs.setCurrentWidget(window.marketplace_view)
        view = window.marketplace_view
        view.provider_box.setCurrentIndex(view.provider_box.findData(CloudProvider.CIVO.value))

        window.crawl_selected()
        qtbot.waitUntil(lambda: not window.is_crawling(), timeout=10_000)
        assert window.crawl_source is CrawlSource.MARKETPLACE
        window._on_product_crawled("civo", 2)
        assert window.status_bar.currentMessage() == "Crawling Civo: 2 software…"

        window.marketplace_menu.extract_requested.emit([CloudProvider.AWS.value])
        qtbot.waitUntil(lambda: not window.is_crawling(), timeout=10_000)
        qtbot.waitUntil(lambda: set(window.marketplaces) == {CloudProvider.AWS, CloudProvider.CIVO}, timeout=5000)
        aws = window.marketplace_menu.provider_actions[CloudProvider.AWS]
        qtbot.waitUntil(lambda: aws.text() == "Amazon Web Services  (1)", timeout=5000)

    def test_copied_software_is_reported(self, make_window: Callable[[Optional[MagicMock]], MainWindow]) -> None:
        window = make_window(None)

        window.marketplace_view.copied.emit("Grafana")

        assert window.status_bar.currentMessage() == "Software copied to the clipboard."


class TestStatistics:
    async def test_statistics_are_shown_and_crawled(
        self, storage: Storage, make_window: Callable[[Optional[MagicMock]], MainWindow], qtbot: QtBot
    ) -> None:
        window = make_window(None)
        assert window.statistics is None
        await storage.statistics.replace(
            "synergy",
            MarketStatistics(
                source="Synergy Research Group",
                crawled_at=CRAWLED_AT,
                reports=[build_report("2026Q1", [(MarketPlayer.AMAZON, 30.0)])],
            ),
        )

        window.poll()
        qtbot.waitUntil(lambda: window.statistics is not None, timeout=5000)
        assert window.statistics is not None
        assert [report.period for report in window.statistics.reports] == ["2026Q1"]

        window.tabs.setCurrentWidget(window.statistics_view)
        window.crawl_all()
        qtbot.waitUntil(lambda: not window.is_crawling(), timeout=10_000)
        qtbot.waitUntil(lambda: window.statistics is not None and len(window.statistics.reports) == 1, timeout=5000)
        assert window.status_bar.currentMessage() == "Crawl over: 1 market reports written."


class TestClosing:
    def test_close_detaches_the_log_panel_and_stops_the_storage(
        self, make_window: Callable[[Optional[MagicMock]], MainWindow]
    ) -> None:
        window = make_window(None)
        event = QCloseEvent()

        window.closeEvent(event)

        assert event.isAccepted()
        assert window.log_handler not in logging.getLogger().handlers
        assert not window.loop.is_running

    def test_missing_event_is_ignored(self, make_window: Callable[[Optional[MagicMock]], MainWindow]) -> None:
        window = make_window(None)

        window.closeEvent(None)

        assert window.log_handler in logging.getLogger().handlers


@pytest.mark.parametrize("tab", [0, 1, 2, 3, 4])
def test_folded_sections_stick_to_the_top_of_their_view(
    make_window: Callable[[Optional[MagicMock]], MainWindow], qtbot: QtBot, tab: int
) -> None:
    window = make_window(None)
    window.resize(1500, 1100)
    window.show()
    window.tabs.setCurrentIndex(tab)
    view = window.tabs.widget(tab)
    assert view is not None
    stacks = view.findChildren(SectionStack)
    for stack in stacks:
        for section in stack.stacked_sections():
            section.set_expanded(False)

    def tops() -> List[int]:
        return sorted(stack.mapTo(view, stack.rect().topLeft()).y() for stack in stacks)

    qtbot.waitUntil(lambda: all(stack.is_folded() for stack in stacks))
    qtbot.waitUntil(lambda: tops()[0] <= 120)
    qtbot.wait(200)

    assert tops()[0] <= 120, "the first stack starts right below the filters, not in the middle of the view"
    assert all(stack.height() <= stack.folded_extent() + 1 for stack in stacks)


def test_the_taxonomy_menu_opens_the_categories_manager(
    make_window: Callable[[Optional[MagicMock]], MainWindow], qtbot: QtBot
) -> None:
    window = make_window(None)
    actions = [action.text() for action in window.taxonomy_menu.actions() if action.text()]

    window.open_categories_manager(2)

    assert actions == [
        "Categories manager…",
        "Source labels…",
        "Unclassified items…",
        "Recompute the categories",
        "Service correspondences",
        "Match services with AI",
    ]
    manager = window.categories_manager
    assert manager is not None
    assert manager.isVisible()
    assert manager.tabs.currentIndex() == 2
    assert window._manager() is manager, "the manager is built once"
    manager.close()
