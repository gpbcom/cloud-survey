from __future__ import annotations

from typing import Callable, List, Optional
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QScrollArea, QWidget
from pytestqt.qtbot import QtBot

from conftest import build_product, seed_catalogue, seed_marketplace
from crawler.runner import CatalogueRunner
from gui.analysis.analysis_view import AnalysisView
from gui.charts.sections.section.chart_section import ChartSection
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from gui.window.main_window import MainWindow
from models.cloud.enums import CloudProvider, Country, SoftwareCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.configuration.storage.storage_settings import StorageSettings
from models.storage.enums import DatasetKind
from models.trends.enums import ChartKind, ChartPreset, SeriesGrouping
from storage.storage import Storage


def scrolled(widget: QWidget) -> bool:
    parent: Optional[QWidget] = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QScrollArea):
            return True
        parent = parent.parentWidget()
    return False


class TestAnalysisView:
    def test_the_charts_are_collapsible_and_scroll(self, qtbot: QtBot, offline_loop: StorageLoop) -> None:
        view = AnalysisView(Theme(), offline_loop)
        qtbot.addWidget(view)

        assert [panel.axes().preset for panel in view.panels] == [preset for _, _, preset in AnalysisView.CHARTS]
        assert view.panels[-2].axes().facet_by is SeriesGrouping.PROVIDER, "the domain trends of each provider"
        assert view.panels[-1].axes().columns is SeriesGrouping.AUDIENCE, "the audience mix of each provider"
        assert view.panels[0].axes().chart is ChartKind.BUBBLE
        assert all(scrolled(section) for section in view.chart_sections)
        view.sections.collapse_button.click()
        assert not any(section.is_expanded() for section in view.chart_sections)

    def test_refresh_and_availability(self, qtbot: QtBot, offline_loop: StorageLoop) -> None:
        view = AnalysisView(Theme(), offline_loop)
        qtbot.addWidget(view)

        view.set_available(frozenset({DatasetKind.CATALOGUE}))
        view.refresh()

        assert all(controller.timer.isActive() for controller in view.controllers)
        assert view.panels[1].available == frozenset({DatasetKind.CATALOGUE})
        assert view.panels[0].axes().preset is ChartPreset.SHARE_VS_LISTINGS


@pytest.mark.db
class TestChartsInTheWindow:
    async def test_every_tab_scrolls_its_charts_and_follows_the_data(
        self,
        qtbot: QtBot,
        storage: Storage,
        gui_loop: StorageLoop,
        storage_settings: StorageSettings,
        make_software: Callable[..., MarketplaceSoftware],
        isolated_logging: None,
    ) -> None:
        await seed_catalogue(storage, CloudProvider.SCALEWAY, [build_product("Kubernetes Kapsule")])
        await seed_marketplace(
            storage,
            CloudProvider.CIVO,
            [make_software("Grafana", ["monitoring"], [SoftwareCategory.DEVELOPER_TOOL])],
        )
        runner = CatalogueRunner(storage=Storage(storage_settings), factory=MagicMock())
        window = MainWindow(gui_loop, runner=runner, theme=Theme())
        qtbot.addWidget(window)

        qtbot.waitUntil(lambda: window.available is not None, timeout=5000)

        tabs: List[str] = [window.tabs.tabText(index).replace("&&", "&") for index in range(window.tabs.count())]
        assert tabs == ["Products", "Marketplaces", "Statistics", "Analysis", "Correspondences", "Patents & Papers"]
        assert window.available == frozenset({DatasetKind.CATALOGUE, DatasetKind.MARKETPLACE})
        sections = window.findChildren(ChartSection)
        charts = [
            section
            for section in sections
            if not section.key.endswith("/table") and not section.key.startswith("correspondence/")
        ]
        assert len(charts) == 36
        assert all(scrolled(section) for section in charts)
        assert sorted(section.key for section in sections if section not in charts) == [
            "analysis/drivers/table",
            "analysis/leaders/table",
            "catalogue/table",
            "correspondence/controls",
            "correspondence/diagram",
            "marketplace/table",
        ]
        window.country_box.setCurrentIndex(window.country_box.findData(Country.FRANCE.value))
        controller = window.dashboard.controller
        assert controller is not None
        assert CloudProvider.SCALEWAY in controller.query.providers
        assert CloudProvider.AWS not in controller.query.providers
        qtbot.waitUntil(lambda: bool(window.dashboard.trends.chart().lines), timeout=10_000)
        window.close()
