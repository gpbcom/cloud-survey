from __future__ import annotations

from typing import List, Optional, Tuple

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QHelpEvent, QMouseEvent
from pytestqt.qtbot import QtBot

from gui.charts.base.metric_chart import ChartLine, MetricChart
from gui.charts.plots.matrix.heatmap_chart import HeatmapChart
from gui.charts.plots.matrix.mix_bar_chart import MixBarChart
from gui.charts.plots.series.metric_line_chart import MetricLineChart
from gui.charts.plots.series.positioning_chart import PositioningChart
from gui.charts.plots.series.stacked_area_chart import StackedAreaChart
from gui.theme import Theme
from models.trends.chart_axes import ChartAxes
from models.trends.enums import ChartKind, ChartMetric, ChartScope, MatrixCell, SeriesGrouping, ValueTransform
from models.trends.matrix.metric_matrix import MetricMatrix
from models.trends.metric_point import MetricPoint
from models.trends.metric_series import MetricSeries

AWS, AZURE = "amazon-web-services", "microsoft-azure"


def line(
    key: str, label: str, color: str, points: List[Tuple[float, float]], projected_from: Optional[float] = None
) -> ChartLine:
    series = MetricSeries(
        key=key,
        points=[MetricPoint(x=x, y=y, projected=projected_from is not None and x > projected_from) for x, y in points],
    )
    return series, label, QColor(color), Qt.PenStyle.SolidLine


def shown(chart: MetricChart, qtbot: QtBot) -> MetricChart:
    qtbot.addWidget(chart)
    chart.resize(900, 360)
    chart.grab()
    return chart


def help_event(chart: MetricChart, position: QPointF) -> Optional[str]:
    return chart._tooltip(position)


def release(chart: MetricChart, position: QPointF) -> None:
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        position,
        chart.mapToGlobal(position),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    chart.event(event)


class TestMetricLineChart:
    @pytest.fixture
    def chart(self, qtbot: QtBot) -> MetricLineChart:
        widget = MetricLineChart(Theme())
        axes = ChartAxes(scope=ChartScope.CATALOGUE, forecast=True)
        widget.set_lines(
            axes,
            [
                line(AWS, "AWS", "#ff9900", [(24290, 10), (24293, 12), (24296, 14), (24299, 16)], projected_from=24293),
                line(AZURE, "Azure", "#00a2ed", [(24290, 5), (24293, 6)]),
            ],
            breaks=[24293],
            last_actual=24293,
        )
        shown(widget, qtbot)
        return widget

    def test_legend_and_forecast_are_painted(self, chart: MetricLineChart) -> None:
        image = chart.grab().toImage()
        legend = image.pixelColor(chart.width() - MetricChart.LEGEND_WIDTH + 6, MetricChart.TOP + 10)

        assert legend == QColor("#ff9900")
        assert chart.legend.boxes[0][1] == "AWS"
        assert not chart.plot_area.isEmpty()

    def test_the_crosshair_tooltip_lists_every_series(self, chart: MetricLineChart) -> None:
        x = chart._frame(chart.plot_area)[0].map_x(24293)

        text = help_event(chart, QPointF(x, chart.plot_area.center().y()))

        assert text == "2024Q2\nAWS: 12\nAzure: 6"
        forecast = help_event(
            chart, QPointF(chart._frame(chart.plot_area)[0].map_x(24299), chart.plot_area.center().y())
        )
        assert forecast is not None
        assert "AWS: 16 (forecast)" in forecast

    def test_a_legend_click_hides_the_series(self, chart: MetricLineChart) -> None:
        box = chart.legend.boxes[1][0]

        release(chart, box.center())

        assert chart.hidden == {"Azure"}
        assert [label for _, label, _, _ in chart._visible()] == ["AWS"]
        release(chart, box.center())
        assert chart.hidden == set()

    def test_a_numeric_axis_and_a_rank_axis(self, qtbot: QtBot) -> None:
        chart = MetricLineChart(Theme())
        numeric = ChartAxes(scope=ChartScope.STATISTICS, x=ChartMetric.SHARE, y=ChartMetric.REVENUE)
        chart.set_lines(numeric, [line(AWS, "AWS", "#ff9900", [(31, 20), (28, 30), (33, 15)])])
        shown(chart, qtbot)

        frame = chart._frame(chart.plot_area)[0]
        assert frame.x_low <= 28
        assert frame.x_high >= 33
        assert "Market share: 28%" in (help_event(chart, frame.map(28, 30)) or "")

        rank = ChartAxes(scope=ChartScope.ANALYSIS, transform=ValueTransform.RANK)
        chart.set_lines(
            rank, [line(AWS, "AWS", "#ff9900", [(1, 1), (2, 2)]), line(AZURE, "Azure", "#00a2ed", [(1, 2), (2, 1)])]
        )
        chart.grab()
        frame, ticks, _ = chart._frame(chart.plot_area)
        assert chart.is_rank()
        assert frame.map_y(1) < frame.map_y(2)
        assert ticks[0] == 1

    def test_the_states(self, chart: MetricLineChart) -> None:
        chart.set_loading(True)
        chart.spin = MetricChart.SPIN_DELAY
        assert not chart.grab().isNull()
        assert chart.spin_timer.isActive()

        chart.set_message("No marketplace stored yet")

        assert (chart.lines, chart.loading, chart.message) == ([], False, "No marketplace stored yet")
        assert not chart.grab().isNull()

    def test_a_narrow_chart_puts_the_legend_below(self, chart: MetricLineChart) -> None:
        chart.resize(500, 400)
        chart.grab()

        assert chart.legend.boxes[0][0].top() > chart.plot_area.bottom()


class TestOtherCharts:
    def test_stacked_areas_and_their_tooltip(self, qtbot: QtBot) -> None:
        chart = StackedAreaChart(Theme())
        axes = ChartAxes(scope=ChartScope.CATALOGUE, chart=ChartKind.AREA, transform=ValueTransform.SHARE_OF_TOTAL)
        chart.set_lines(
            axes,
            [
                line("us", "United States", "#56B4E9", [(24290, 60), (24293, 55)]),
                line("eu", "European Union", "#F0E442", [(24290, 40), (24293, 45)]),
            ],
        )
        shown(chart, qtbot)

        frame = chart._frame(chart.plot_area, chart._stacks())[0]
        text = chart._tooltip(QPointF(frame.map_x(24293), chart.plot_area.center().y()))

        assert (frame.y_low, frame.y_high) == (0, 100)
        assert text == "2024Q2\nEuropean Union: 45%\nUnited States: 55%"

    def test_bubbles_are_coloured_and_listed_by_bloc(self, qtbot: QtBot) -> None:
        chart = PositioningChart(Theme())
        axes = ChartAxes(
            scope=ChartScope.ANALYSIS,
            chart=ChartKind.BUBBLE,
            x=ChartMetric.SHARE,
            y=ChartMetric.MARKETPLACE_SIZE,
            size=ChartMetric.CATALOGUE_SIZE,
        )
        bubbles = [
            (
                MetricSeries(key=key, points=[MetricPoint(x=x, y=y, size=size, label="2025Q2")]),
                label,
                QColor(color),
                Qt.PenStyle.SolidLine,
            )
            for key, label, color, x, y, size in (
                (AWS, "AWS", "#56B4E9", 30, 9000, 300),
                ("ovh-cloud", "OVHcloud", "#F0E442", 2, 500, 75),
            )
        ]
        chart.set_lines(axes, bubbles)
        shown(chart, qtbot)

        frame = chart._frame(chart.plot_area)[0]
        placed = chart._bubbles(frame)
        text = chart._tooltip(frame.map(30, 9000))

        assert [entry[0] for entry in chart._legend_entries()] == ["United States", "European Union"]
        assert placed[0][3] == PositioningChart.MAX_RADIUS
        assert placed[1][3] == pytest.approx(PositioningChart.MIN_RADIUS + 24 * 0.5)
        assert text == "AWS (2025Q2)\nMarket share: 30%\nMarketplace size: 9,000\nCatalogue size: 300"

    def test_the_heatmap_cells(self, qtbot: QtBot) -> None:
        chart = HeatmapChart(Theme())
        axes = ChartAxes(scope=ChartScope.MARKETPLACE, chart=ChartKind.HEATMAP, columns=SeriesGrouping.DELIVERY)
        chart.set_matrix(axes, MetricMatrix(rows=[AWS], columns=["saas", "container"], cells={AWS: {"saas": 12.0}}))
        shown(chart, qtbot)

        cells, largest = chart._cells(chart._areas()[0])

        assert largest == 12
        assert chart._tooltip(cells[1][0].center()) == "AWS × Container\nListed software: 0"
        assert chart._legend_entries() == []

    def test_the_mix_bars(self, qtbot: QtBot) -> None:
        chart = MixBarChart(Theme())
        axes = ChartAxes(
            scope=ChartScope.MARKETPLACE,
            chart=ChartKind.MIX,
            series_by=SeriesGrouping.BLOC,
            columns=SeriesGrouping.DELIVERY,
            cell=MatrixCell.ROW_SHARE,
        )
        chart.set_matrix(
            axes, MetricMatrix(rows=["eu"], columns=["saas", "api"], cells={"eu": {"saas": 75.0, "api": 25.0}})
        )
        shown(chart, qtbot)

        segments = chart._segments(chart.plot_area)

        assert segments[0][0].width() == pytest.approx(chart.plot_area.width() * 0.75)
        assert chart._tooltip(segments[1][0].center()) == "European Union · API\n25.0% of the row"
        assert [entry[0] for entry in chart._legend_entries()] == ["SaaS", "API"]
        assert chart.preferred_height() == MixBarChart.MIN_HEIGHT

    def test_the_qt_tooltip_event(self, qtbot: QtBot) -> None:
        chart = MetricLineChart(Theme())
        shown(chart, qtbot)

        event = QHelpEvent(QEvent.Type.ToolTip, QPoint(5, 5), QPoint(5, 5))

        assert chart.event(event)
