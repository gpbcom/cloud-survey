from __future__ import annotations

from typing import List

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QLineEdit, QMainWindow, QWidget
from pytestqt.qtbot import QtBot

from gui.charts.panels.chart_panel import ChartPanel
from gui.charts.plots.matrix.heatmap_chart import HeatmapChart
from gui.charts.plots.series.metric_line_chart import MetricLineChart
from gui.charts.sections.chart_state_store import ChartStateStore
from gui.charts.sections.section.chart_section import ChartSection
from gui.layout.fitted_scroll_area import FittedScrollArea
from gui.layout.flow_layout import FlowLayout
from gui.layout.folding_dock import FoldingDock
from gui.layout.folding_splitter import FoldingSplitter
from gui.layout.panes.section_stack import SectionStack
from gui.layout.panes.side_pane import SidePane
from gui.marketplace.widgets.domain_bar_chart import DomainBarChart
from gui.theme import Theme
from models.trends.chart_axes import ChartAxes
from models.trends.enums import ChartKind, ChartScope, MatrixCell, SeriesGrouping
from models.trends.matrix.metric_matrix import MetricMatrix
from models.trends.metric_point import MetricPoint
from models.trends.metric_series import MetricSeries


def body(height: int) -> QWidget:
    widget = QLabel("chart")
    widget.setMinimumHeight(height)
    return widget


class TestSectionStack:
    def test_the_expanded_sections_share_the_height(self, qtbot: QtBot) -> None:
        store = ChartStateStore()
        stack = SectionStack(scrollable=True)
        qtbot.addWidget(stack)
        small = stack.add_section(ChartSection("tab/small", "Small", body(60), store), 1)
        large = stack.add_section(ChartSection("tab/large", "Large", body(60), store), 3)
        stack.resize(600, 900)
        stack.show()
        qtbot.waitUntil(lambda: large.height() > 0)

        assert large.height() > 2 * small.height()
        assert stack.stacked_sections() == [small, large]
        small.set_expanded(False)
        qtbot.waitUntil(lambda: large.height() > 700)
        assert small.height() < 80

    def test_collapsing_every_section_folds_the_stack(self, qtbot: QtBot) -> None:
        store = ChartStateStore()
        stack = SectionStack(scrollable=False)
        qtbot.addWidget(stack)
        section = stack.add_section(ChartSection("tab/table", "Table", body(300), store), 1)

        with qtbot.waitSignal(stack.folded_changed) as blocker:
            section.set_expanded(False)

        assert blocker.args == [True]
        assert stack.is_folded()
        assert stack.maximumHeight() == stack.folded_extent() < 100
        section.set_expanded(True)
        assert not stack.is_folded()
        assert stack.maximumHeight() > 10_000

    def test_a_stack_built_collapsed_starts_folded(self) -> None:
        store = ChartStateStore()
        store.set_expanded("tab/table", False)
        stack = SectionStack(scrollable=False)

        stack.add_section(ChartSection("tab/table", "Table", body(300), store), 1)

        assert stack.is_folded()


class TestFoldingSplitter:
    def test_a_folded_pane_gives_its_height_and_takes_it_back(self, qtbot: QtBot) -> None:
        store = ChartStateStore()
        charts, table = SectionStack(scrollable=False), SectionStack(scrollable=False)
        charts.add_section(ChartSection("tab/charts", "Charts", body(100), store), 1)
        section = table.add_section(ChartSection("tab/table", "Table", body(100), store), 1)
        splitter = FoldingSplitter(Qt.Orientation.Vertical)
        qtbot.addWidget(splitter)
        splitter.add_pane(charts, 1)
        splitter.add_pane(table, 1)
        splitter.resize(500, 800)
        splitter.show()
        splitter.setSizes([400, 400])
        qtbot.waitUntil(lambda: table.height() > 300)

        section.set_expanded(False)
        qtbot.waitUntil(lambda: charts.height() > 650)
        assert table.height() < 100

        section.set_expanded(True)
        qtbot.waitUntil(lambda: table.height() > 300)
        assert abs(splitter.sizes()[0] - splitter.sizes()[1]) < 60


class TestSidePane:
    def test_the_pane_folds_to_a_strip_and_remembers_it(self, qtbot: QtBot) -> None:
        store = ChartStateStore()
        content = QLabel("details")
        pane = SidePane("tab/details", "Details", content, store)
        qtbot.addWidget(pane)
        pane.show()

        with qtbot.waitSignal(pane.folded_changed) as blocker:
            pane.toggle.click()

        assert blocker.args == [True]
        assert content.isHidden()
        assert pane.maximumWidth() == pane.folded_extent() < 60
        assert store.expanded("tab/details") is False
        assert SidePane("tab/details", "Details", QLabel(), store).is_folded()
        pane.toggle.click()
        assert content.isVisible()


class TestFoldingDock:
    @pytest.fixture
    def window(self, qtbot: QtBot) -> QMainWindow:
        window = QMainWindow()
        window.setCentralWidget(QLabel("central"))
        qtbot.addWidget(window)
        window.resize(800, 600)
        return window

    def test_the_dock_folds_to_its_title_and_is_revealed_again(self, qtbot: QtBot, window: QMainWindow) -> None:
        store = ChartStateStore()
        content = QLabel("logs")
        dock = FoldingDock("window/logs", "Logs", content, window, store)
        window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        dock.fit_height()
        window.show()

        dock.toggle.click()

        assert dock.is_folded()
        assert content.maximumHeight() == 0
        assert dock.width() > 600
        assert dock.maximumHeight() == dock.title_bar.sizeHint().height()
        assert store.expanded("window/logs") is False
        dock.close_button.click()
        assert dock.isHidden()
        dock.reveal()
        assert dock.isVisible()
        assert not dock.is_folded()
        assert content.maximumHeight() > 10_000


def series(key: str, count: int) -> MetricSeries:
    return MetricSeries(key=key, points=[MetricPoint(x=float(x), y=float(x + 1)) for x in range(count)])


class TestWidenedCharts:
    def test_the_chart_is_as_tall_as_its_legend(self, qtbot: QtBot) -> None:
        chart = MetricLineChart(Theme())
        qtbot.addWidget(chart)
        lines = [
            (series(f"p{index}", 3), f"Provider {index}", QColor("#fff"), Qt.PenStyle.SolidLine) for index in range(30)
        ]

        chart.set_lines(ChartAxes(scope=ChartScope.CATALOGUE), lines)

        assert chart.minimumHeight() >= 30 * 20
        assert chart.minimumWidth() == 0

    def test_a_widened_chart_shows_its_legend_in_full(self, qtbot: QtBot) -> None:
        chart = MetricLineChart(Theme())
        qtbot.addWidget(chart)
        label = "A provider whose name is far too long for the legend column"
        chart.set_lines(
            ChartAxes(scope=ChartScope.CATALOGUE), [(series("p", 40), label, QColor("#fff"), Qt.PenStyle.SolidLine)]
        )

        chart.set_wide(True)

        assert chart._legend_width() > MetricLineChart.LEGEND_WIDTH
        assert chart.minimumWidth() >= MetricLineChart.LEFT + 40 * MetricLineChart.WIDE_POINT_SPACING

    def test_a_widened_heatmap_fits_every_column_header(self, qtbot: QtBot) -> None:
        chart = HeatmapChart(Theme())
        qtbot.addWidget(chart)
        columns: List[str] = [f"column-{index}" for index in range(30)]
        axes = ChartAxes(
            scope=ChartScope.MARKETPLACE,
            chart=ChartKind.HEATMAP,
            series_by=SeriesGrouping.PROVIDER,
            columns=SeriesGrouping.CATEGORY,
            cell=MatrixCell.LISTED,
        )
        rows = [f"row-{index}" for index in range(25)]
        chart.set_matrix(axes, MetricMatrix(rows=rows, columns=columns, cells={rows[0]: {columns[0]: 3.0}}))
        fitted = chart.natural_width()

        chart.set_wide(True)

        assert chart.minimumWidth() == fitted >= 30 * HeatmapChart.VALUE_WIDTH
        assert chart.minimumHeight() >= 25 * HeatmapChart.ROW_HEIGHT

    def test_the_widen_tool_is_remembered_per_chart(self, qtbot: QtBot) -> None:
        store = ChartStateStore()
        panel = ChartPanel(Theme(), ChartScope.CATALOGUE, "catalogue/trends", store)
        qtbot.addWidget(panel)

        panel.wide_button.click()

        assert panel.chart().wide
        assert store.expanded("catalogue/trends/wide") is True
        assert ChartPanel(Theme(), ChartScope.CATALOGUE, "catalogue/trends", store).wide_button.isChecked()

    def test_the_heatmap_headers_tell_their_full_name(self, qtbot: QtBot) -> None:
        chart = HeatmapChart(Theme())
        qtbot.addWidget(chart)
        axes = ChartAxes(scope=ChartScope.MARKETPLACE, chart=ChartKind.HEATMAP, columns=SeriesGrouping.DELIVERY)
        chart.set_matrix(axes, MetricMatrix(rows=["amazon-web-services"], columns=["saas"], cells={}))
        chart.resize(900, 400)
        area, header = chart._areas()

        assert chart._tooltip(area.topLeft() + QPointF(-header / 2, 5)) == "AWS"
        assert chart._tooltip(area.topLeft() + QPointF(10, -10)) == "SaaS"


class TestFlowLayout:
    def test_the_items_wrap_when_the_width_runs_out(self, qtbot: QtBot) -> None:
        holder = QWidget()
        qtbot.addWidget(holder)
        flow = FlowLayout(holder, gap=10)
        buttons = [QLabel(f"Filter {index}") for index in range(6)]
        for button in buttons:
            button.setFixedSize(100, 30)
            flow.addWidget(button)

        assert flow.minimumSize().width() == 100
        assert flow.sizeHint().width() == 6 * 100 + 5 * 10
        assert flow.heightForWidth(700) == 30
        assert flow.heightForWidth(230) == 3 * 30 + 2 * 10
        holder.resize(230, 200)
        holder.show()
        qtbot.waitUntil(lambda: buttons[2].y() > 0)
        assert [button.y() for button in buttons[:3]] == [0, 0, 40]

    def test_an_expanding_item_takes_the_room_left_on_its_line(self, qtbot: QtBot) -> None:
        holder = QWidget()
        qtbot.addWidget(holder)
        flow = FlowLayout(holder, gap=10)
        search, fixed = QLineEdit(), QLabel("Fixed")
        fixed.setFixedSize(100, 30)
        search.setMinimumWidth(120)
        flow.addWidget(search)
        flow.addWidget(fixed)
        holder.resize(800, 100)
        holder.show()

        qtbot.waitUntil(lambda: search.width() > 600)
        assert fixed.x() + fixed.width() <= 800
        assert flow.count() == 2
        assert flow.itemAt(5) is None
        assert flow.takeAt(5) is None


class TestFittedScrollArea:
    def test_a_short_chart_keeps_its_height_and_a_tall_one_scrolls(self, qtbot: QtBot) -> None:
        chart = DomainBarChart(Theme())
        chart.set_bars([("CRM", 3, "#000000"), ("ERP", 2, "#000000")])
        area = FittedScrollArea(chart, 160)
        qtbot.addWidget(area)
        area.show()
        natural = chart.sizeHint().height()

        assert (area.minimumHeight(), area.maximumHeight()) == (natural, natural)
        chart.set_bars([(f"Type {number}", number, "#000000") for number in range(40)])
        qtbot.waitUntil(lambda: area.maximumHeight() == chart.sizeHint().height(), timeout=2000)
        assert area.minimumHeight() == 160, "below its scroll height a tall chart scrolls"


class TestStickingStack:
    def test_the_stack_is_as_tall_as_its_content_in_its_splitter(self, qtbot: QtBot) -> None:
        store = ChartStateStore()
        stack = SectionStack(scrollable=True)
        section = stack.add_section(ChartSection("test/short", "Short", body(120), store), 1)
        table = QLabel("table")
        table.setMinimumHeight(100)
        splitter = FoldingSplitter(Qt.Orientation.Vertical)
        splitter.add_pane(stack, 1)
        splitter.add_pane(table, 1)
        qtbot.addWidget(splitter)
        splitter.resize(800, 900)
        splitter.show()
        section.set_expanded(False)

        qtbot.waitUntil(lambda: splitter.sizes()[0] == stack._content_height(), timeout=2000)
        assert stack.maximumHeight() == stack._content_height()
        assert splitter.sizes()[1] > splitter.sizes()[0], "the table takes the rest"
