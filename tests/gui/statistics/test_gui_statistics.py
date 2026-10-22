from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable, List

import pytest
from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QColor, QHelpEvent
from pytestqt.qtbot import QtBot

from analytics.series.time_axis import TimeAxis
from gui.statistics.charts.market_size_chart import MarketSizeChart, SizeBar
from gui.statistics.charts.share.share_bar import ShareBar
from gui.statistics.charts.share.share_bar_chart import ShareBarChart
from gui.statistics.view.perimeter_panel import PerimeterPanel
from gui.statistics.view.statistics_view import StatisticsView
from gui.theme import Theme
from models.cloud.enums import MarketPlayer, MarketRegion, MarketSegment
from models.stats.market_report import MarketReport
from models.stats.market_statistics import MarketStatistics

MakeReport = Callable[..., MarketReport]
P = MarketPlayer


@pytest.fixture
def reports(make_report: MakeReport) -> List[MarketReport]:
    return [
        make_report(
            "2024Q3", [(P.AMAZON, 31), (P.MICROSOFT, 20), (P.GOOGLE, 13)], market_size_bn=83.8, methodology_break=True
        ),
        make_report(
            "2026Q2",
            [(P.AMAZON, 28), (P.MICROSOFT, 20), (P.GOOGLE, 15)],
            market_size_bn=143.4,
            growth_pct=43,
            mentions=[{"name": "Oracle"}, {"name": "Alibaba", "rank": 4}, {"name": "CoreWeave"}],
            published="2026-07-30",
        ),
        make_report(
            "2023Q2",
            [(P.MICROSOFT, 22), (P.GOOGLE, 11)],
            shares=[
                {"player": "amazon", "share_pct": 33, "share_low_pct": 32, "share_high_pct": 34},
                {"player": "microsoft", "share_pct": 22},
                {"player": "google", "share_pct": 11},
            ],
            published="2023-08-03",
        ),
        make_report(
            "2025H1",
            [],
            region=MarketRegion.EUROPE,
            currency="EUR",
            market_size_bn=36,
            shares=[
                {"player": "big-three", "share_pct": 70},
                {"player": "european-providers", "share_pct": 15, "approximate": True},
                {"player": "sap", "share_pct": 2, "part_of": "european-providers"},
            ],
            mentions=[{"name": "OVHcloud"}, {"name": "Alibaba"}],
            published="2025-07-24",
        ),
        make_report("2026Q2", [(P.BIG_THREE, 67)], segment=MarketSegment.PUBLIC_IAAS_PAAS),
    ]


@pytest.fixture
def statistics(reports: List[MarketReport]) -> MarketStatistics:
    return MarketStatistics(
        source="Synergy Research Group", crawled_at=datetime(2026, 10, 16, tzinfo=UTC), reports=reports
    )


class TestShareBarChart:
    def test_bars(self, qtbot: QtBot) -> None:
        chart = ShareBarChart(Theme())
        qtbot.addWidget(chart)
        bars = [
            ShareBar("Amazon", 33, QColor("#ff9900"), low_pct=32, high_pct=34),
            ShareBar("European providers", 15, QColor("#2f6fde"), approximate=True),
            ShareBar("Others", 37, QColor("#6b7486"), computed=True),
        ]

        chart.set_groups([("Worldwide", bars)])
        chart.resize(chart.sizeHint())
        image = chart.grab().toImage()

        assert chart.sizeHint().height() == ShareBarChart.TITLE_HEIGHT + 3 * ShareBarChart.ROW_HEIGHT
        assert [chart._value_text(bar) for bar in bars] == ["32-34%", "~15%", "37%"]
        row = ShareBarChart.TITLE_HEIGHT + ShareBarChart.ROW_HEIGHT // 2 + 3
        assert image.pixelColor(ShareBarChart.LABEL_WIDTH + 4, row) == QColor("#ff9900")

    def test_empty_chart(self, qtbot: QtBot) -> None:
        chart = ShareBarChart(Theme())
        qtbot.addWidget(chart)
        chart.set_groups([])

        assert chart.sizeHint().height() == ShareBarChart.ROW_HEIGHT
        assert not chart.grab().isNull()


class TestMarketSizeChart:
    def test_bars_and_tooltips(self, qtbot: QtBot) -> None:
        chart = MarketSizeChart(Theme())
        qtbot.addWidget(chart)
        chart.resize(chart.sizeHint())

        chart.set_bars([("2026Q1", 128.6, "USD", None), ("2026Q2", 143.4, "USD", 43.0), ("2025H1", 36.0, "EUR", None)])
        image = chart.grab().toImage()

        assert chart.sizeHint().height() == 160
        assert chart._tooltip(1) == "2026Q2: $143.4 billion, +43% year on year"
        assert chart._tooltip(2) == "2025H1: €36 billion"
        slot = chart.width() // 3
        bottom = chart.height() - MarketSizeChart.CAPTION_HEIGHT - 5
        assert image.pixelColor(slot + slot // 2, bottom) == QColor(Theme.ACCENT)
        assert image.pixelColor(2 * slot + slot // 2, bottom) == QColor(Theme.ACCENT_ALT)
        assert chart._label_every(["2026Q2"], slot) == 1

    def test_narrow_bars_are_labelled_every_few_bars(self, qtbot: QtBot) -> None:
        chart = MarketSizeChart(Theme())
        qtbot.addWidget(chart)
        chart.resize(300, 160)

        bars: List[SizeBar] = [(f"2025Q{quarter}", 90.0 + quarter, "USD", None) for quarter in range(1, 5)]
        chart.set_bars(bars * 5)

        assert chart._label_every(["2025Q1", "$94"], 300 / 20) > 1
        assert not chart.grab().isNull()

    def test_tooltip_events(self, qtbot: QtBot) -> None:
        chart = MarketSizeChart(Theme())
        qtbot.addWidget(chart)
        chart.resize(300, 160)
        chart.set_bars([("2026Q2", 143.4, "USD", 43.0)])

        inside = QHelpEvent(QEvent.Type.ToolTip, QPoint(10, 50), QPoint(10, 50))
        outside = QHelpEvent(QEvent.Type.ToolTip, QPoint(-10, 50), QPoint(-10, 50))

        assert chart.event(inside)
        assert chart.event(outside)
        assert chart.event(QEvent(QEvent.Type.Leave)) in (True, False)


class TestPerimeterPanel:
    @pytest.fixture
    def panel(self, qtbot: QtBot, reports: List[MarketReport]) -> PerimeterPanel:
        widget = PerimeterPanel(Theme())
        qtbot.addWidget(widget)
        widget.set_reports(reports)
        return widget

    def test_defaults(self, panel: PerimeterPanel) -> None:
        assert panel.regions() == [MarketRegion.WORLDWIDE]
        assert panel.segments() == [MarketSegment.CLOUD_INFRASTRUCTURE]
        assert panel.players() == [P.AMAZON, P.MICROSOFT, P.GOOGLE, P.BIG_THREE, P.EUROPEAN_PROVIDERS, P.SAP, P.OTHERS]
        assert panel.periods() == ["2026Q2", "2025H1", "2024Q3", "2023Q2"]

    def test_disabled_without_data(self, qtbot: QtBot) -> None:
        panel = PerimeterPanel(Theme())
        qtbot.addWidget(panel)

        panel.set_reports([])

        assert (panel.regions(), panel.segments(), panel.players(), panel.periods()) == ([], [], [], [])

    def test_period_buttons_and_signals(self, panel: PerimeterPanel, qtbot: QtBot) -> None:
        with qtbot.waitSignal(panel.perimeter_changed):
            panel.latest_button.click()
        assert panel.periods() == ["2026Q2"]

        panel.all_button.click()
        assert len(panel.periods()) == 4

        with qtbot.waitSignal(panel.perimeter_changed):
            panel.player_boxes[P.GOOGLE].setChecked(False)
        assert P.GOOGLE not in panel.players()

    def test_reload_keeps_the_choices(self, panel: PerimeterPanel, reports: List[MarketReport]) -> None:
        panel.player_boxes[P.SAP].setChecked(False)
        panel.period_boxes["2023Q2"].setChecked(False)

        panel.set_reports(reports)

        assert P.SAP not in panel.players()
        assert "2023Q2" not in panel.periods()

    def test_reloads_keep_the_periods_at_the_top(self, panel: PerimeterPanel, reports: List[MarketReport]) -> None:
        for _ in range(3):
            panel.set_reports(reports)

        items = [panel.period_layout.itemAt(index) for index in range(panel.period_layout.count())]
        spacers = [index for index, item in enumerate(items) if item is not None and item.spacerItem()]
        assert spacers == [len(items) - 1], "one stretch, below the periods"


class TestStatisticsView:
    @pytest.fixture
    def view(self, qtbot: QtBot, statistics: MarketStatistics) -> StatisticsView:
        widget = StatisticsView(Theme())
        qtbot.addWidget(widget)
        widget.set_statistics(statistics)
        return widget

    def test_empty_state(self, qtbot: QtBot) -> None:
        view = StatisticsView(Theme())
        qtbot.addWidget(view)
        view.show()

        assert view.empty_label.isVisible()
        assert (view.share_chart.groups, view.source_label.text(), view.mentions_label.text()) == ([], "", "")
        with qtbot.waitSignal(view.refresh_requested):
            view.refresh_button.click()

    def test_latest_shares_with_the_computed_others(self, view: StatisticsView) -> None:
        ((title, bars),) = view.share_chart.groups

        assert title == "Worldwide · Cloud infrastructure services · 2026Q2"
        assert [(bar.label, bar.share_pct, bar.computed) for bar in bars] == [
            ("Amazon", 28, False),
            ("Microsoft", 20, False),
            ("Google", 15, False),
            ("Others (computed)", 37, True),
        ]

    def test_trend_size_mentions_and_source(self, view: StatisticsView) -> None:
        lines = {label: series for series, label, _, _ in view.trend_chart.lines}
        assert list(lines) == ["Others (computed)", "Amazon", "Microsoft", "Google"]
        assert [point.label for point in lines["Amazon"].points] == ["2023Q2", "2024Q3", "2026Q2"]
        assert [point.y for point in lines["Amazon"].points] == [33, 31, 28]
        assert view.trend_chart.breaks == [TimeAxis().month(2024, 9)]
        assert view.trend_section.title() == "Market share race"
        assert view.size_chart.bars == [("2024Q3", 83.8, "USD", None), ("2026Q2", 143.4, "USD", 43.0)]
        assert view.mentions_label.text() == "Not quantified by Synergy Research Group: 4. Alibaba, CoreWeave, Oracle."
        assert "srgresearch.com/articles/2026q2" in view.source_label.text()
        assert "(30 Jul 2026). Crawled on 16 Oct 2026." in view.source_label.text()

    def test_several_regions_and_segments(self, view: StatisticsView) -> None:
        view.panel.region_boxes[MarketRegion.EUROPE].setChecked(True)
        view.panel.segment_boxes[MarketSegment.PUBLIC_IAAS_PAAS].setChecked(True)

        titles = [title for title, _ in view.share_chart.groups]
        assert titles == [
            "Worldwide · Cloud infrastructure services · 2026Q2",
            "Worldwide · Public IaaS + PaaS · 2026Q2",
            "Europe · Cloud infrastructure services · 2025H1",
        ]
        europe = dict((bar.label, bar) for bar in view.share_chart.groups[2][1])
        assert (
            europe["European providers"].approximate,
            europe["SAP"].share_pct,
            europe["Others (computed)"].share_pct,
        ) == (
            True,
            2,
            15,
        )
        styles = {label: style for _, label, _, style in view.trend_chart.lines}
        assert styles["Amazon · WW · CIS"] == Qt.PenStyle.SolidLine
        assert styles["Big three · EU · CIS"] == Qt.PenStyle.DotLine
        assert ("2025H1 EU", 36.0, "EUR", None) in view.size_chart.bars
        assert view.mentions_label.text().endswith("4. Alibaba, CoreWeave, OVHcloud, Oracle.")

    def test_unchecking_everything(self, view: StatisticsView) -> None:
        for box in view.panel.player_boxes.values():
            box.setChecked(False)

        assert view.share_chart.groups == []
        assert view.trend_chart.lines == []

        view.panel.region_boxes[MarketRegion.WORLDWIDE].setChecked(False)
        assert (view.size_chart.bars, view.source_label.text(), view.mentions_label.text()) == ([], "", "")

    def test_no_statistics_after_some(self, view: StatisticsView) -> None:
        view.set_statistics(None)

        assert view.panel.periods() == []
        assert view.source_label.text() == ""

    def test_mentions_without_statistics_source(self, view: StatisticsView) -> None:
        groups = view._groups(view._selected_reports())
        view.statistics = None

        assert view._mentions(groups).startswith("Not quantified by the source: ")
