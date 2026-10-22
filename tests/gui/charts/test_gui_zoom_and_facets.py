from __future__ import annotations

from typing import List, Tuple

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QWidget
from pytestqt.qtbot import QtBot

from gui.charts.base.metric_chart import ChartLine, MetricChart
from gui.charts.common.chart_labels import ChartLabels
from gui.charts.panels.chart_panel import ChartPanel
from gui.charts.picker.axis_picker import AxisPicker
from gui.charts.plots.facets.facet_grid import FacetGrid
from gui.charts.plots.matrix.heatmap_chart import HeatmapChart
from gui.charts.plots.matrix.mix_bar_chart import MixBarChart
from gui.charts.plots.series.metric_line_chart import MetricLineChart
from gui.charts.plots.series.stacked_area_chart import StackedAreaChart
from gui.charts.sections.chart_state_store import ChartStateStore
from gui.marketplace.widgets.domain_bar_chart import DomainBarChart
from gui.statistics.charts.market_size_chart import MarketSizeChart
from gui.theme import Theme
from models.trends.chart_axes import ChartAxes
from models.trends.enums import (
    ChartKind,
    ChartPreset,
    ChartScope,
    MatrixCell,
    OptionBlock,
    SeriesGrouping,
    ValueTransform,
)
from models.trends.matrix.metric_matrix import MetricMatrix
from models.trends.metric_point import MetricPoint
from models.trends.metric_series import MetricSeries
from models.trends.trend_result import TrendResult

CTRL = Qt.KeyboardModifier.ControlModifier
CTRL_SHIFT = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier


def line(key: str, label: str, points: List[Tuple[float, float]], facet: str = "") -> ChartLine:
    series = MetricSeries(key=key, facet=facet or None, points=[MetricPoint(x=x, y=y) for x, y in points])
    return series, label, QColor("#3366cc"), Qt.PenStyle.SolidLine


def wheel(widget: QWidget, position: QPointF, steps: int, modifiers: Qt.KeyboardModifier) -> None:
    event = QWheelEvent(
        position,
        widget.mapToGlobal(position),
        QPoint(0, 0),
        QPoint(0, 120 * steps),
        Qt.MouseButton.NoButton,
        modifiers,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, event)


def mouse(widget: QWidget, kind: QEvent.Type, position: QPointF) -> None:
    pressed = Qt.MouseButton.NoButton if kind is QEvent.Type.MouseButtonRelease else Qt.MouseButton.LeftButton
    event = QMouseEvent(
        kind, position, widget.mapToGlobal(position), Qt.MouseButton.LeftButton, pressed, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(widget, event)


def drag(widget: QWidget, start: QPointF, end: QPointF) -> None:
    mouse(widget, QEvent.Type.MouseButtonPress, start)
    mouse(widget, QEvent.Type.MouseMove, end)
    mouse(widget, QEvent.Type.MouseButtonRelease, end)


def time_axes() -> ChartAxes:
    return ChartAxes(scope=ChartScope.CATALOGUE)


@pytest.fixture
def chart(qtbot: QtBot) -> MetricLineChart:
    widget = MetricLineChart(Theme())
    qtbot.addWidget(widget)
    widget.resize(900, 360)
    widget.set_lines(time_axes(), [line("civo", "Civo", [(24288.0 + 3 * step, step * 10.0) for step in range(13)])])
    widget.grab()
    return widget


class TestSeriesZoom:
    def test_ctrl_wheel_zooms_the_time_axis_around_the_mouse(self, chart: MetricLineChart) -> None:
        center = chart.plot_area.center()
        full = chart.zoom.full_x
        assert full is not None

        wheel(chart, center, 2, CTRL)
        chart.grab()

        window = chart.zoom.x_window
        assert window is not None
        assert full[0] < window[0] < window[1] < full[1]
        assert chart.zoom.y_window is None, "the plain zoom keeps the y axis of a time chart"
        assert chart.zoom.frame is not None
        assert chart.zoom.frame.x_low == pytest.approx(window[0])

    def test_shift_zooms_the_y_axis_and_the_plain_wheel_scrolls(self, chart: MetricLineChart) -> None:
        wheel(chart, chart.plot_area.center(), 1, Qt.KeyboardModifier.NoModifier)
        assert not chart.zoom.is_zoomed(), "the plain wheel scrolls the page"

        wheel(chart, chart.plot_area.center(), 1, CTRL_SHIFT)

        assert chart.zoom.x_window is None
        assert chart.zoom.y_window is not None

    def test_a_dragged_rectangle_zooms_and_a_double_click_resets(self, chart: MetricLineChart) -> None:
        area = chart.plot_area
        start = QPointF(area.left() + area.width() * 0.25, area.top() + 20)
        end = QPointF(area.left() + area.width() * 0.5, area.bottom() - 20)

        drag(chart, start, end)

        frame = chart.zoom.frame
        window = chart.zoom.x_window
        assert frame is not None
        assert window is not None
        assert window[1] - window[0] == pytest.approx(frame.value_x(end.x()) - frame.value_x(start.x()), rel=0.02)
        mouse(chart, QEvent.Type.MouseButtonDblClick, area.center())
        assert not chart.zoom.is_zoomed()

    def test_escape_resets_and_a_tiny_drag_is_a_click(self, chart: MetricLineChart) -> None:
        center = chart.plot_area.center()
        drag(chart, center, QPointF(center.x() + 2, center.y()))
        assert not chart.zoom.is_zoomed()

        wheel(chart, center, 3, CTRL)
        QApplication.sendEvent(
            chart, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        )

        assert not chart.zoom.is_zoomed()

    def test_the_zoom_survives_new_data_but_not_new_axes(self, chart: MetricLineChart) -> None:
        wheel(chart, chart.plot_area.center(), 2, CTRL)
        lines = chart.lines

        chart.set_lines(time_axes(), lines)
        assert chart.zoom.is_zoomed()
        chart.set_lines(time_axes().model_copy(update={"chart": ChartKind.AREA}), lines)
        assert not chart.zoom.is_zoomed()


class TestOtherZooms:
    def test_the_heatmap_zooms_into_rows_and_columns(self, qtbot: QtBot) -> None:
        heatmap = HeatmapChart(Theme())
        qtbot.addWidget(heatmap)
        heatmap.resize(900, 500)
        names = [f"r{index}" for index in range(6)]
        matrix = MetricMatrix(
            rows=names, columns=names, cells={row: {column: 1.0 for column in names} for row in names}, total_rows=6
        )
        heatmap.set_matrix(
            ChartAxes(
                scope=ChartScope.MARKETPLACE,
                chart=ChartKind.HEATMAP,
                series_by=SeriesGrouping.PROVIDER,
                columns=SeriesGrouping.BLOC,
                cell=MatrixCell.LISTED,
            ),
            matrix,
        )
        heatmap.grab()
        area = heatmap._areas()[0]
        assert len(heatmap._cells(area)[0]) == 36

        drag(heatmap, area.topLeft() + QPointF(2, 2), QPointF(area.center().x(), area.center().y()))

        assert len(heatmap._cells(area)[0]) < 36

    def test_the_mix_zooms_along_the_shares(self, qtbot: QtBot) -> None:
        mix = MixBarChart(Theme())
        qtbot.addWidget(mix)
        mix.resize(900, 300)
        matrix = MetricMatrix(
            rows=["eu"], columns=["saas", "api"], cells={"eu": {"saas": 95.0, "api": 5.0}}, total_rows=1
        )
        mix.set_matrix(
            ChartAxes(
                scope=ChartScope.MARKETPLACE,
                chart=ChartKind.MIX,
                series_by=SeriesGrouping.BLOC,
                columns=SeriesGrouping.DELIVERY,
                cell=MatrixCell.ROW_SHARE,
            ),
            matrix,
        )
        mix.grab()
        before = {column: rect.width() for rect, _, column, _ in mix._segments(mix.plot_area)}

        wheel(mix, QPointF(mix.plot_area.right() - 5, mix.plot_area.top() + 10), 4, CTRL)

        after = {column: rect.width() for rect, _, column, _ in mix._segments(mix.plot_area)}
        assert after["api"] > before["api"], "the small share is easier to read"
        assert mix.zoom.y_window is None

    def test_the_bar_charts_zoom_their_values_from_zero(self, qtbot: QtBot) -> None:
        bars = DomainBarChart(Theme())
        qtbot.addWidget(bars)
        bars.set_bars([("CRM", 1000, "#000000"), ("ERP", 10, "#000000")])
        bars.resize(600, 80)
        bars.grab()

        wheel(bars, QPointF(bars.width() / 2, 10), 3, CTRL)

        window = bars.zoom.x_window
        assert window is not None
        assert window[0] == 0
        assert window[1] < 1000

    def test_the_market_size_chart_zooms_into_periods(self, qtbot: QtBot) -> None:
        sizes = MarketSizeChart(Theme())
        qtbot.addWidget(sizes)
        sizes.resize(800, 200)
        sizes.set_bars([(f"2024Q{index}", float(index), "USD", None) for index in range(1, 5)])
        sizes.grab()
        wide = sizes._window()[2]

        drag(sizes, QPointF(5, 20), QPointF(sizes.width() / 2, 40))

        low, high, slot = sizes._window()
        assert high - low < 4
        assert slot > wide


class TestFacetGrid:
    def test_one_compact_chart_per_facet_with_one_legend_and_a_shared_zoom(self, qtbot: QtBot) -> None:
        grid = FacetGrid(Theme())
        qtbot.addWidget(grid)
        grid.resize(1000, 600)
        axes = ChartAxes(scope=ChartScope.MARKETPLACE, chart=ChartKind.AREA, facet_by=SeriesGrouping.PROVIDER)
        points = [(24288.0, 1.0), (24291.0, 2.0), (24294.0, 3.0)]
        facets = [
            ("AWS", [line("crm", "CRM", points), line("erp", "ERP", points)]),
            ("Civo", [line("crm", "CRM", points)]),
            ("Azure", [line("cms", "CMS", points)]),
        ]

        grid.set_facets(axes, facets)
        for small in grid.charts:
            small.resize(400, 220)
            small.grab()

        assert [title.text() for title in grid.titles] == ["AWS", "Civo", "Azure"]
        assert all(small.compact and small.minimumHeight() == MetricChart.COMPACT_HEIGHT for small in grid.charts)
        assert grid.legend_layout.count() == 3, "CRM, ERP and CMS once each"
        assert grid.columns == 2
        first = grid.charts[0]
        wheel(first, first.plot_area.center(), 2, CTRL)
        assert all(small.zoom.x_window == first.zoom.x_window for small in grid.charts)
        grid.set_facets(axes, facets[:1])
        assert len(grid.charts) == 1
        grid.set_message("Nothing yet")
        assert grid.charts == []
        assert grid.message.text() == "Nothing yet"


class TestFacetedPanel:
    def test_the_domain_trends_show_one_chart_per_provider(self, qtbot: QtBot) -> None:
        panel = ChartPanel(Theme(), ChartScope.MARKETPLACE, "marketplace/trends", ChartStateStore())
        qtbot.addWidget(panel)
        panel.resize(1100, 600)
        panel.apply_preset(ChartPreset.DOMAIN_TRENDS_BY_PROVIDER)
        axes = panel.axes()
        points = [MetricPoint(x=24288.0, y=60.0), MetricPoint(x=24291.0, y=40.0)]
        result = TrendResult(
            series=[
                MetricSeries(key="compute", facet="amazon-web-services", points=points),
                MetricSeries(key="storage-services", facet="amazon-web-services", points=points),
                MetricSeries(key="compute", facet="civo", points=points),
            ],
            total_count=2,
        )

        assert panel.stack.currentWidget() is panel.facets
        with qtbot.waitSignal(panel.heading_changed) as heading:
            panel.show_result(axes, result)

        assert [title.text() for title in panel.facets.titles] == ["AWS", "Civo"]
        assert "2 charts per provider" in heading.args[1]
        assert "Civo · Compute" in panel._export_data()
        panel.show_error("refused")
        assert panel.facets.message.text().startswith("The chart data could not be read: refused")

    def test_the_picker_offers_the_facets_with_why_they_are_blocked(self, qtbot: QtBot) -> None:
        picker = AxisPicker(ChartLabels(Theme()), ChartScope.MARKETPLACE)
        qtbot.addWidget(picker)
        picker.set_axes(
            ChartAxes(scope=ChartScope.MARKETPLACE, chart=ChartKind.AREA, series_by=SeriesGrouping.CATEGORY)
        )

        box = picker.facet_box
        values = [box.itemData(index) for index in range(box.count())]
        assert values[0] == ""
        assert SeriesGrouping.PROVIDER.value in values
        index = box.findData(SeriesGrouping.PROVIDER.value)
        with qtbot.waitSignal(picker.axes_changed) as changed:
            box.setCurrentIndex(index)

        assert changed.args[0].facet_by is SeriesGrouping.PROVIDER
        blocked = box.itemData(box.findData(SeriesGrouping.CATEGORY.value), Qt.ItemDataRole.ToolTipRole)
        assert blocked == ChartLabels.BLOCK_LABELS[OptionBlock.SAME_AS_SERIES]


def test_a_single_quarter_is_drawn_as_a_stacked_column(qtbot: QtBot) -> None:
    area = StackedAreaChart(Theme())
    qtbot.addWidget(area)
    area.resize(600, 300)
    axes = ChartAxes(scope=ChartScope.MARKETPLACE, chart=ChartKind.AREA, transform=ValueTransform.SHARE_OF_TOTAL)
    area.set_lines(axes, [line("crm", "CRM", [(24323.0, 70.0)]), line("erp", "ERP", [(24323.0, 30.0)])])
    area.grab()
    frame = area.zoom.frame
    assert frame is not None

    band = area._band(frame, [(24323.0, 0.0, 70.0)])

    assert band.count() == 4
    assert band.boundingRect().width() == pytest.approx(StackedAreaChart.COLUMN_WIDTH)


class TestScrollAndWiden:
    def test_a_zoomed_chart_scrolls_with_the_wheel_keeping_its_span(self, chart: MetricLineChart) -> None:
        center = chart.plot_area.center()
        wheel(chart, center, 3, CTRL)
        chart.grab()
        before = chart.zoom.x_window
        assert before is not None

        wheel(chart, center, -2, Qt.KeyboardModifier.NoModifier)

        after = chart.zoom.x_window
        assert after is not None
        assert after[0] > before[0], "scrolled towards the later quarters"
        assert after[1] - after[0] == pytest.approx(before[1] - before[0])

    def test_a_middle_button_drag_scrolls_a_zoomed_chart(self, chart: MetricLineChart) -> None:
        center = chart.plot_area.center()
        wheel(chart, center, 3, CTRL)
        chart.grab()
        before = chart.zoom.x_window
        assert before is not None
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            center,
            chart.mapToGlobal(center),
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.MiddleButton,
            Qt.KeyboardModifier.NoModifier,
        )
        target = QPointF(center.x() - 100, center.y())
        move = QMouseEvent(
            QEvent.Type.MouseMove,
            target,
            chart.mapToGlobal(target),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.MiddleButton,
            Qt.KeyboardModifier.NoModifier,
        )

        QApplication.sendEvent(chart, press)
        QApplication.sendEvent(chart, move)

        after = chart.zoom.x_window
        assert after is not None
        assert after[0] > before[0]

    def test_widen_makes_the_chart_wider_than_the_view_and_scroll(self, qtbot: QtBot) -> None:
        panel = ChartPanel(Theme(), ChartScope.CATALOGUE, "catalogue/trends", ChartStateStore())
        qtbot.addWidget(panel)
        panel.resize(1200, 600)
        panel.show()
        points = [MetricPoint(x=24288.0 + 3 * index, y=float(index)) for index in range(6)]
        panel.show_result(panel.axes(), TrendResult(series=[MetricSeries(key="civo", points=points)], total_count=1))

        panel.set_wide(True)

        viewport = panel.chart_area.viewport()
        assert viewport is not None
        assert panel.stack.minimumWidth() >= viewport.width() * ChartPanel.WIDE_FACTOR - 1
        qtbot.waitUntil(lambda: (bar := panel.chart_area.horizontalScrollBar()) is not None and bar.maximum() > 0)
        panel.set_wide(False)
        assert panel.stack.minimumWidth() == 0

    def test_widen_makes_the_small_charts_larger(self, qtbot: QtBot) -> None:
        grid = FacetGrid(Theme())
        qtbot.addWidget(grid)
        grid.resize(1400, 600)
        axes = ChartAxes(scope=ChartScope.MARKETPLACE, chart=ChartKind.AREA, facet_by=SeriesGrouping.PROVIDER)
        points = [(24288.0, 1.0), (24291.0, 2.0)]
        grid.set_facets(axes, [(name, [line("crm", "CRM", points)]) for name in ("A", "B", "C", "D")])
        narrow = grid.columns

        grid.set_wide(True)

        assert grid.columns < narrow


class TestZoomButtonsAndSpace:
    def test_the_zoom_buttons_zoom_the_shown_chart_and_reset_it(self, qtbot: QtBot) -> None:
        panel = ChartPanel(Theme(), ChartScope.CATALOGUE, "catalogue/trends", ChartStateStore())
        qtbot.addWidget(panel)
        panel.resize(1200, 600)
        panel.show()
        points = [MetricPoint(x=24288.0 + 3 * index, y=float(index)) for index in range(12)]
        panel.show_result(panel.axes(), TrendResult(series=[MetricSeries(key="civo", points=points)], total_count=1))
        panel.chart().grab()
        zoom_in, zoom_out, reset = panel.zoom_buttons

        zoom_in.click()
        window = panel.chart().zoom.x_window
        assert window is not None
        zoom_out.click()
        wider = panel.chart().zoom.x_window
        assert wider is None or wider[1] - wider[0] > window[1] - window[0]
        zoom_in.click()
        reset.click()
        assert not panel.chart().zoom.is_zoomed()

    def test_the_small_charts_share_the_whole_width(self, qtbot: QtBot) -> None:
        grid = FacetGrid(Theme())
        qtbot.addWidget(grid)
        grid.resize(1400, 600)
        grid.show()
        axes = ChartAxes(scope=ChartScope.MARKETPLACE, chart=ChartKind.AREA, facet_by=SeriesGrouping.PROVIDER)
        points = [(24288.0, 1.0), (24291.0, 2.0)]
        grid.set_facets(axes, [(name, [line("crm", "CRM", points)]) for name in ("A", "B", "C", "D")])
        assert grid.columns == 3

        grid.resize(1000, 600)
        qtbot.waitUntil(lambda: grid.columns == 2, timeout=2000)
        qtbot.waitUntil(lambda: grid.cards[1].geometry().right() >= grid.width() - 20, timeout=2000)
        grid.set_facets(axes, [("A", [line("crm", "CRM", points)])])
        qtbot.waitUntil(lambda: grid.cards[0].width() >= grid.width() - 20, timeout=2000)
        assert grid.columns == 1, "a single chart takes the whole width"
