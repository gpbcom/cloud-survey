from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QLabel
from pytestqt.qtbot import QtBot

from gui.charts.common.axis.axis_formatter import AxisFormatter
from gui.charts.common.axis.nice_scale import NiceScale
from gui.charts.common.chart_labels import ChartLabels
from gui.charts.panels.styling.chart_titles import ChartTitles
from gui.charts.sections.chart_state_store import ChartStateStore
from gui.charts.sections.section.chart_section import ChartSection
from gui.charts.sections.section.sections_toolbar import SectionsToolbar
from gui.theme import Theme
from models.cloud.enums import CloudProvider, GeoBloc, SoftwareAudience
from models.trends.chart_axes import ChartAxes
from models.trends.enums import (
    ChartKind,
    ChartMetric,
    ChartNote,
    ChartPreset,
    ChartScope,
    MetricUnit,
    SeriesGrouping,
    ValueTransform,
)
from models.trends.metric_point import MetricPoint
from models.trends.metric_series import MetricSeries
from models.trends.trend_result import TrendResult


class TestNiceScale:
    @pytest.mark.parametrize(
        ("low", "high", "expected"),
        [(0, 32, (0, 40, 10)), (0, 67, (0, 80, 20)), (-5, 12, (-5, 15, 5)), (0, 0, (0, 1, 0.2)), (3, 3, (0, 3, 1))],
    )
    def test_linear_bounds_and_step(self, low: float, high: float, expected: Tuple[float, float, float]) -> None:
        assert NiceScale().linear(low, high) == pytest.approx(expected)

    def test_ticks_and_log(self) -> None:
        scale = NiceScale()

        assert scale.ticks(0, 40, 10) == [0, 10, 20, 30, 40]
        assert scale.log(3, 4200) == (1, 10_000, [1, 10, 100, 1_000, 10_000])
        assert scale.linear(24290, 24310, include_zero=False)[0] >= 24280


class TestAxisFormatter:
    @pytest.mark.parametrize(
        ("unit", "value", "currency", "text"),
        [
            (MetricUnit.COUNT, 1234, None, "1,234"),
            (MetricUnit.COUNT, 12345, None, "12.3k"),
            (MetricUnit.COUNT, 2_500_000, None, "2.5M"),
            (MetricUnit.PERCENT, 28.0, None, "28%"),
            (MetricUnit.PERCENT, 12.25, None, "12.2%"),
            (MetricUnit.BILLIONS, 143.4, "USD", "$143.4bn"),
            (MetricUnit.BILLIONS, 36.0, "EUR", "€36bn"),
            (MetricUnit.RANK, 3.0, None, "#3"),
            (MetricUnit.INDEX, 112.0, None, "112"),
        ],
    )
    def test_values(self, unit: MetricUnit, value: float, currency: Optional[str], text: str) -> None:
        assert AxisFormatter().value(unit, value, currency) == text

    def test_x_labels(self) -> None:
        formatter = AxisFormatter()

        assert formatter.x_label(ChartMetric.PERIOD, 24305, "2025H1") == "2025H1"
        assert formatter.x_label(ChartMetric.QUARTER, 24305) == "2025Q2"
        assert formatter.x_label(ChartMetric.SHARE, 30, step=10) == "30%"


class TestChartLabels:
    def test_names_and_colours(self) -> None:
        labels = ChartLabels(Theme())

        assert labels.metric_label(ChartMetric.LISTED, ChartScope.CATALOGUE) == "Listed products"
        assert labels.metric_label(ChartMetric.ADDED, ChartScope.MARKETPLACE) == "Added software"
        assert labels.axis_title(ChartMetric.SHARE, ChartScope.STATISTICS) == "Market share (%)"
        assert labels.axis_title(ChartMetric.LISTED, ChartScope.CATALOGUE, ValueTransform.RANK) == (
            "Rank by listed products"
        )
        assert labels.series_label(SeriesGrouping.PROVIDER, CloudProvider.AWS.value) == "AWS"
        assert labels.series_label(SeriesGrouping.BLOC, "eu") == "European Union"
        assert labels.series_label(SeriesGrouping.CATEGORY, "unknown") == "unknown"
        assert labels.series_label(SeriesGrouping.DOMAIN, "data-analytics") == "Data Platforms & Analytics"
        assert labels.series_label(SeriesGrouping.DELIVERY, "*") == "Others"
        assert labels.series_label(SeriesGrouping.PLAYER, "") == "Market"
        assert labels.series_color(SeriesGrouping.BLOC, "cn") == QColor(Theme.BLOC_COLORS[GeoBloc.CHINA])
        assert labels.series_color(SeriesGrouping.PROVIDER, CloudProvider.AWS.value) == QColor("#ff9900")
        assert labels.bloc_of(SeriesGrouping.PROVIDER, CloudProvider.OVH.value) is GeoBloc.EUROPEAN_UNION
        assert labels.bloc_of(SeriesGrouping.CATEGORY, "crm") is None


class TestChartTitles:
    def test_titles_subtitles_and_footnotes(self) -> None:
        titles = ChartTitles(ChartLabels(Theme()))
        line = ChartAxes(scope=ChartScope.CATALOGUE, series_by=SeriesGrouping.BLOC, transform=ValueTransform.INDEXED)
        bubble = ChartAxes(
            scope=ChartScope.ANALYSIS,
            chart=ChartKind.BUBBLE,
            x=ChartMetric.SHARE,
            y=ChartMetric.PUBLISHERS,
            size=ChartMetric.CATALOGUE_SIZE,
        )
        heatmap = ChartAxes(scope=ChartScope.MARKETPLACE, chart=ChartKind.HEATMAP, columns=SeriesGrouping.CATEGORY)
        result = TrendResult(
            series=[MetricSeries(key="us", points=[MetricPoint(x=24308, y=1, projected=True)])], total_count=3
        )

        assert titles.title(line) == "Listed products by bloc"
        assert titles.subtitle(line, result) == "Quarterly · indexed (first = 100) · forecast to 2025Q3 · top 1 of 3"
        assert titles.title(bubble) == "Publishers vs market share, sized by catalogue size"
        assert "size: catalogue size" in titles.subtitle(bubble)
        assert titles.title(heatmap) == "Listed software: provider × category"
        assert titles.title(line.model_copy(update={"preset": ChartPreset.RANK_RACE})) == "Marketplace size rank race"
        assert titles.footnote([ChartNote.FORECAST_METHOD]).startswith("Forecast: least-squares")


class TestChartStateStore:
    def test_the_states_are_remembered_for_the_session(self) -> None:
        store = ChartStateStore()
        axes = ChartAxes(scope=ChartScope.CATALOGUE, y=ChartMetric.ADDED)

        store.set_expanded("catalogue/trends", False)
        store.set_axes("catalogue/trends", axes)

        assert store.expanded("catalogue/trends") is False
        assert store.expanded("catalogue/other") is True
        assert store.axes("catalogue/trends") == axes

    def test_the_states_persist_in_the_settings(self, tmp_path: Path) -> None:
        path = str(tmp_path / "charts.ini")
        axes = ChartAxes(scope=ChartScope.MARKETPLACE, chart=ChartKind.MIX)
        first = ChartStateStore(QSettings(path, QSettings.Format.IniFormat))
        first.set_expanded("marketplace/trends", False)
        first.set_axes("marketplace/trends", axes)
        assert first.settings is not None
        first.settings.sync()

        second = ChartStateStore(QSettings(path, QSettings.Format.IniFormat))

        assert second.expanded("marketplace/trends") is False
        assert second.axes("marketplace/trends") == axes

    def test_axes_saved_by_a_former_version_show_every_series(self, tmp_path: Path) -> None:
        settings = QSettings(str(tmp_path / "charts.ini"), QSettings.Format.IniFormat)
        capped = ChartAxes(scope=ChartScope.STATISTICS, top=20)
        settings.setValue("statistics/trends/axes", capped.model_dump_json())
        store = ChartStateStore(settings)

        assert store.axes("statistics/trends") == capped.model_copy(update={"top": None})
        store.set_axes("statistics/trends", capped)
        assert store.axes("statistics/trends") == capped

    def test_invalid_saved_axes_are_forgotten(self, tmp_path: Path) -> None:
        settings = QSettings(str(tmp_path / "charts.ini"), QSettings.Format.IniFormat)
        settings.setValue("analysis/rank/axes", '{"scope": "nowhere"}')

        assert ChartStateStore(settings).axes("analysis/rank") is None


class TestChartSections:
    def test_toggling_hides_the_chart_and_is_remembered(self, qtbot: QtBot) -> None:
        store = ChartStateStore()
        body = QLabel("chart")
        section = ChartSection("statistics/size", "Market size", body, store)
        qtbot.addWidget(section)
        section.show()

        with qtbot.waitSignal(section.toggled) as blocker:
            section.toggle.click()

        assert blocker.args == ["statistics/size", False]
        assert body.isHidden()
        assert store.expanded("statistics/size") is False
        restored = ChartSection("statistics/size", "Market size", QLabel(), store)
        qtbot.addWidget(restored)
        assert not restored.is_expanded()

    def test_heading_and_expand_all(self, qtbot: QtBot) -> None:
        store = ChartStateStore()
        toolbar = SectionsToolbar()
        sections = [toolbar.add(ChartSection(f"tab/{index}", "Chart", QLabel(), store)) for index in range(3)]
        for section in sections:
            qtbot.addWidget(section)
        qtbot.addWidget(toolbar)

        toolbar.collapse_button.click()
        assert [section.is_expanded() for section in sections] == [False, False, False]
        toolbar.expand_button.click()
        assert [section.is_expanded() for section in sections] == [True, True, True]

        sections[0].set_heading("Listed products by bloc", "Quarterly")
        assert sections[0].title() == "Listed products by bloc"
        assert sections[0].subtitle.text() == "Quarterly"


def test_the_audiences_have_their_own_labels_and_colours(qapp: QApplication) -> None:
    labels = ChartLabels(Theme())

    assert labels.series_label(SeriesGrouping.AUDIENCE, SoftwareAudience.BOTH.value) == "Both"
    assert labels.series_label(SeriesGrouping.AUDIENCE, "developer-tool") == "Developer tool only"
    colours = {labels.series_color(SeriesGrouping.AUDIENCE, audience.value).name() for audience in SoftwareAudience}
    assert len(colours) == 3
    assert labels.GROUPING_LABELS[SeriesGrouping.AUDIENCE] == "Audience"
