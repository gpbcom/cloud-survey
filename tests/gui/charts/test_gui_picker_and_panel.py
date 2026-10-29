from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from PyQt6 import sip
from pytestqt.qtbot import QtBot

from conftest import build_software, seed_marketplace
from gui.charts.common.chart_labels import ChartLabels
from gui.charts.panels.chart_panel import ChartPanel
from gui.charts.panels.stored_chart_controller import StoredChartController
from gui.charts.picker.axis_picker import AxisPicker
from gui.charts.sections.chart_state_store import ChartStateStore
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.cloud.enums import CloudProvider, DateSource, SoftwareCategory
from models.storage.enums import DatasetKind
from models.storage.pages.item_query import ItemQuery
from models.trends.chart_axes import ChartAxes
from models.trends.enums import ChartKind, ChartMetric, ChartPreset, ChartScope, SeriesGrouping
from models.trends.metric_point import MetricPoint
from models.trends.metric_series import MetricSeries
from models.trends.trend_result import TrendResult
from storage.storage import Storage


@pytest.fixture
def picker(qtbot: QtBot) -> AxisPicker:
    widget = AxisPicker(ChartLabels(Theme()), ChartScope.MARKETPLACE)
    qtbot.addWidget(widget)
    widget.resize(1200, 60)
    return widget


class TestAxisPicker:
    def test_it_starts_with_the_default_ready_made_chart(self, picker: AxisPicker) -> None:
        assert picker.axes().preset is ChartPreset.NEW_LISTINGS_BY_BLOC
        assert list(picker.kind_bar.buttons) == ["line", "area", "heatmap", "mix"]
        assert (picker.y_box.value(), picker.x_box.value(), picker.by_box.value()) == ("added", "quarter", "bloc")

    def test_a_user_change_is_repaired_and_reported_once(self, qtbot: QtBot, picker: AxisPicker) -> None:
        with qtbot.waitSignals([picker.axes_changed]) as blocker:
            picker.by_box.setCurrentIndex(picker.by_box.findData(SeriesGrouping.DELIVERY.value))

        axes = blocker.all_signals_and_args[0].args[0]
        assert isinstance(axes, ChartAxes)
        assert axes.series_by is SeriesGrouping.DELIVERY
        assert axes.preset is None
        share = picker.x_box.options.item(picker.x_box.findData(ChartMetric.SHARE.value))
        assert share is not None
        assert not share.isEnabled()
        assert share.toolTip() == "Not known per value of this grouping"

    def test_the_matrix_kinds_relabel_the_boxes(self, qtbot: QtBot, picker: AxisPicker) -> None:
        with qtbot.waitSignal(picker.axes_changed):
            picker.kind_bar.buttons["heatmap"].click()

        assert picker.axes().chart is ChartKind.HEATMAP
        assert [picker.captions[name].text() for name in ("y", "x", "by")] == ["Rows", "Columns", "Cells"]
        assert picker.size_box.isHidden()

    def test_the_missing_datasets_block_their_options(self, picker: AxisPicker) -> None:
        chosen = picker.axes()

        picker.set_available(frozenset())
        assert picker.axes() == chosen
        picker.set_available(frozenset({DatasetKind.MARKETPLACE}))

        share = picker.x_box.options.item(picker.x_box.findData(ChartMetric.SHARE.value))
        assert share is not None
        assert share.toolTip().startswith("No market statistics yet")

    def test_every_series_is_shown_by_default_and_a_cap_can_be_chosen(self, picker: AxisPicker) -> None:
        picker.set_axes(ChartAxes(scope=ChartScope.MARKETPLACE))
        assert picker.menu.top() is None
        assert picker.menu.top_actions[None].isChecked()

        picker.menu.top_actions[12].trigger()

        assert picker.axes().top == 12
        picker.menu.top_actions[None].trigger()
        assert picker.axes().top is None

    def test_every_line_chart_offers_the_rate_of_change(self, qtbot: QtBot, picker: AxisPicker) -> None:
        picker.set_axes(ChartAxes(scope=ChartScope.MARKETPLACE))
        action = picker.menu.derivative_action
        assert action is not None
        assert action.isVisible()
        assert "change between two consecutive points" in action.toolTip()

        with qtbot.waitSignal(picker.axes_changed):
            action.trigger()

        assert picker.axes().derivative
        assert picker.options_button.text().endswith("\u2022")
        with qtbot.waitSignal(picker.axes_changed):
            picker.kind_bar.buttons["area"].click()
        assert not picker.axes().derivative
        assert not action.isVisible(), "an area chart has no lines to derive"

    def test_the_options_mark_and_the_responsive_rows(self, picker: AxisPicker) -> None:
        picker.set_axes(ChartAxes(scope=ChartScope.MARKETPLACE, top=20))
        assert not picker.options_button.text().endswith("\u2022")
        picker.set_axes(ChartAxes(scope=ChartScope.MARKETPLACE, forecast=True))

        assert picker.options_button.text().endswith("•")
        picker.show()
        picker.resize(600, 80)
        assert picker.wrapped
        picker.resize(1200, 60)
        assert not picker.wrapped


class TestChartPanel:
    @pytest.fixture
    def panel(self, qtbot: QtBot) -> ChartPanel:
        widget = ChartPanel(Theme(), ChartScope.CATALOGUE, "catalogue/trends", ChartStateStore())
        qtbot.addWidget(widget)
        widget.resize(1100, 500)
        return widget

    def test_a_ready_made_chart_is_shown_and_remembered(self, qtbot: QtBot, panel: ChartPanel) -> None:
        with qtbot.waitSignal(panel.heading_changed) as blocker:
            panel.apply_preset(ChartPreset.CATALOGUE_BLOCS)

        assert blocker.args[0] == "United States vs European Union vs China vs Russia"
        assert panel.stack.currentWidget() is panel.charts[ChartKind.AREA]
        assert panel.store.axes("catalogue/trends") == panel.axes()

    def test_results_are_drawn_unless_the_axes_changed(self, panel: ChartPanel) -> None:
        axes = panel.axes()
        result = TrendResult(
            series=[MetricSeries(key="scaleway", points=[MetricPoint(x=24290, y=3)])],
            notes=[],
            total_count=1,
        )

        panel.show_result(axes.model_copy(update={"y": ChartMetric.ADDED}), result)
        assert panel.chart().lines == []
        panel.show_result(axes, result)
        assert [label for _, label, _, _ in panel.chart().lines] == ["Scaleway"]
        assert "series,quarter,x,listed" in panel._export_data()

    def test_the_empty_and_error_states(self, panel: ChartPanel) -> None:
        panel.set_available(frozenset())
        panel.show_result(panel.axes(), TrendResult())

        assert panel.chart().message == "No catalogue stored yet: crawl the catalogues first"
        panel.show_error("connection refused")
        assert panel.chart().message.startswith("The chart data could not be read: connection refused")
        assert panel.error == "connection refused"


class TestStoredChartController:
    def test_requests_are_debounced_and_stale_results_dropped(self, qtbot: QtBot, offline_loop: StorageLoop) -> None:
        panel = ChartPanel(Theme(), ChartScope.CATALOGUE, "catalogue/trends", ChartStateStore())
        qtbot.addWidget(panel)
        controller = StoredChartController(panel, offline_loop, "synergy")
        with patch.object(offline_loop, "submit") as submit:
            controller.set_query(ItemQuery(search="kube"))
            controller.refresh()
            assert controller.timer.isActive()
            controller.timer.timeout.emit()
            controller._request()

        assert submit.call_count == 2
        assert controller.query.search == "kube"
        stale_done = submit.call_args_list[0].args[1]
        stale_done(TrendResult(series=[MetricSeries(key="aws", points=[MetricPoint(x=1, y=1)])]))
        assert panel.chart().lines == []
        assert panel.chart().loading

    def test_a_result_after_the_chart_was_closed_is_dropped(self, qtbot: QtBot, offline_loop: StorageLoop) -> None:
        panel = ChartPanel(Theme(), ChartScope.CATALOGUE, "catalogue/trends", ChartStateStore())
        controller = StoredChartController(panel, offline_loop, "synergy")
        with patch.object(offline_loop, "submit") as submit:
            controller._request()
        done = submit.call_args.args[1]

        panel.deleteLater()
        qtbot.waitUntil(lambda: sip.isdeleted(panel))
        done(TrendResult(series=[MetricSeries(key="aws", points=[MetricPoint(x=1, y=1)])]))

        assert not controller._is_current(controller.request)

    @pytest.mark.db
    async def test_a_round_trip_through_the_storage(
        self, qtbot: QtBot, storage: Storage, gui_loop: StorageLoop
    ) -> None:
        added = datetime(2025, 5, 2, tzinfo=UTC)
        software = build_software("Postgres", ["database"], [SoftwareCategory.DEVELOPER_TOOL])
        dated = software.model_copy(update={"added_at": added, "added_from": DateSource.WEBSITE})
        await seed_marketplace(storage, CloudProvider.CIVO, [dated])
        panel = ChartPanel(Theme(), ChartScope.MARKETPLACE, "marketplace/trends", ChartStateStore())
        qtbot.addWidget(panel)
        controller = StoredChartController(panel, gui_loop, "synergy")

        controller._request()

        qtbot.waitUntil(lambda: bool(panel.chart().lines), timeout=10_000)
        ((series, label, _, _),) = panel.chart().lines
        assert (label, series.points[0].y) == ("Other countries", 1)
