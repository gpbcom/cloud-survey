from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable, Dict, List, Tuple

import pytest

from analytics.pipeline.chart_assembler import ChartAssembler
from analytics.pipeline.statistics_series import StatisticsSeries
from analytics.series.series_transformer import SeriesTransformer
from analytics.series.time_axis import TimeAxis
from models.cloud.enums import MarketPlayer, MarketRegion
from models.stats.market_report import MarketReport
from models.stats.market_statistics import MarketStatistics
from models.trends.chart_axes import ChartAxes
from models.trends.enums import (
    ChartKind,
    ChartMetric,
    ChartNote,
    ChartScope,
    OptionBlock,
    SeriesGrouping,
    ValueTransform,
)
from models.trends.metric_point import MetricPoint
from models.trends.metric_series import MetricSeries
from models.trends.trend_result import TrendResult

P = MarketPlayer
PLAYERS = [P.AMAZON, P.MICROSOFT, P.GOOGLE, P.OTHERS]


@pytest.fixture
def reports(make_report: Callable[..., MarketReport]) -> List[MarketReport]:
    return [
        make_report(
            "2024Q3", [(P.AMAZON, 31), (P.MICROSOFT, 20), (P.GOOGLE, 13)], market_size_bn=80, methodology_break=True
        ),
        make_report("2026Q2", [(P.AMAZON, 28), (P.MICROSOFT, 20), (P.GOOGLE, 15)], market_size_bn=140, growth_pct=40),
        make_report("2023Q2", [(P.AMAZON, 33), (P.MICROSOFT, 22), (P.GOOGLE, 11)], market_size_bn=60),
        make_report(
            "2025H1",
            [],
            region=MarketRegion.EUROPE,
            currency="EUR",
            market_size_bn=36,
            shares=[
                {"player": "big-three", "share_pct": 70},
                {"player": "european-providers", "share_pct": 15},
                {"player": "sap", "share_pct": 2, "part_of": "european-providers"},
            ],
        ),
    ]


def by_key(result: TrendResult) -> Dict[str, List[Tuple[float, float]]]:
    return {one.key: [(point.x, round(point.y, 6)) for point in one.points] for one in result.series}


class TestStatisticsSeries:
    def test_the_share_trend_of_today(self, reports: List[MarketReport]) -> None:
        worldwide = [report for report in reports if report.region is MarketRegion.WORLDWIDE]
        axes = ChartAxes(
            scope=ChartScope.STATISTICS, x=ChartMetric.PERIOD, y=ChartMetric.SHARE, series_by=SeriesGrouping.PLAYER
        )

        result = StatisticsSeries().build(worldwide, PLAYERS, axes)

        amazon = result.series[0]
        assert [one.key for one in result.series] == ["amazon", "microsoft", "google", "others"]
        assert [point.y for point in amazon.points] == [33, 31, 28]
        assert [point.label for point in amazon.points] == ["2023Q2", "2024Q3", "2026Q2"]
        assert result.breaks == [TimeAxis().month(2024, 9)]
        assert result.notes == [ChartNote.METHODOLOGY_BREAK]

    def test_the_blocs_sum_the_top_level_shares(self, reports: List[MarketReport]) -> None:
        europe = [report for report in reports if report.region is MarketRegion.EUROPE]
        axes = ChartAxes(
            scope=ChartScope.STATISTICS, x=ChartMetric.PERIOD, y=ChartMetric.SHARE, series_by=SeriesGrouping.BLOC
        )

        result = StatisticsSeries().build(europe, PLAYERS, axes)

        june = TimeAxis().month(2025, 6)
        assert by_key(result) == {"us": [(june, 70)], "eu": [(june, 15)], "other": [(june, 15)]}

    def test_the_revenue_and_the_mixed_currencies(self, reports: List[MarketReport]) -> None:
        axes = ChartAxes(
            scope=ChartScope.STATISTICS, x=ChartMetric.PERIOD, y=ChartMetric.REVENUE, series_by=SeriesGrouping.BLOC
        )

        result = StatisticsSeries().build(reports, PLAYERS, axes)

        assert result.series[0].points[0].y == pytest.approx((33 + 22 + 11) / 100 * 60)
        assert {one.currency for one in result.series} == {"USD", "EUR"}
        assert ChartNote.MIXED_CURRENCIES in result.notes

    def test_a_numeric_x_axis_pairs_the_market_with_each_player(self, reports: List[MarketReport]) -> None:
        worldwide = [report for report in reports if report.region is MarketRegion.WORLDWIDE]
        axes = ChartAxes(
            scope=ChartScope.STATISTICS, x=ChartMetric.MARKET_SIZE, y=ChartMetric.SHARE, series_by=SeriesGrouping.PLAYER
        )

        result = StatisticsSeries().build(worldwide, [P.AMAZON], axes)

        assert by_key(result) == {"amazon": [(60, 33), (80, 31), (140, 28)]}
        assert result.breaks == []

    def test_the_provider_series_of_the_worldwide_reports(self, reports: List[MarketReport]) -> None:
        statistics = MarketStatistics(source="synergy", crawled_at=datetime(2026, 7, 30, tzinfo=UTC), reports=reports)

        series = StatisticsSeries().provider_series(statistics, ChartMetric.SHARE, SeriesGrouping.PROVIDER)

        assert [one.key for one in series] == ["amazon-web-services", "microsoft-azure", "google-cloud-platform"]
        assert all(one.region is None for one in series)
        assert StatisticsSeries().provider_series(None, ChartMetric.SHARE, SeriesGrouping.PROVIDER) == []


def line(key: str, points: List[Tuple[float, float]]) -> MetricSeries:
    return MetricSeries(key=key, points=[MetricPoint(x=x, y=y) for x, y in points])


class TestChartAssembler:
    def test_the_forecast_runs_before_the_share_of_total(self) -> None:
        axes = ChartAxes(
            scope=ChartScope.CATALOGUE,
            chart=ChartKind.AREA,
            transform=ValueTransform.SHARE_OF_TOTAL,
            forecast=True,
        )
        raw = TrendResult(series=[line("us", [(0, 1), (3, 2), (6, 3)]), line("eu", [(0, 1), (3, 1), (6, 1)])])

        result = ChartAssembler().assemble(axes, raw)

        projected = [point for point in result.series[0].points if point.projected]
        assert len(projected) == 4
        assert all(
            sum(one.points[index].y for one in result.series) == pytest.approx(100)
            for index in range(len(result.series[0].points))
        )
        assert result.last_actual == 6
        assert ChartNote.FORECAST_METHOD in result.notes

    def test_the_largest_series_are_kept_by_their_raw_value(self) -> None:
        axes = ChartAxes(scope=ChartScope.CATALOGUE, transform=ValueTransform.RANK, top=1)
        raw = TrendResult(series=[line("small", [(0, 1)]), line("large", [(0, 9)]), line("empty", [])])

        result = ChartAssembler().assemble(axes, raw)

        assert [one.key for one in result.series] == ["large"]
        assert result.series[0].points[0].y == 1
        assert result.total_count == 2

    def test_a_numeric_axis_has_no_break_nor_forecast(self) -> None:
        axes = ChartAxes(scope=ChartScope.STATISTICS, x=ChartMetric.SHARE, y=ChartMetric.REVENUE, forecast=True)
        raw = TrendResult(series=[line("aws", [(30, 10), (31, 12), (32, 14)])], breaks=[3.0])

        result = ChartAssembler().assemble(axes, raw)

        assert result.breaks == []
        assert result.last_actual is None
        assert not any(point.projected for point in result.series[0].points)


def faceted(key: str, facet: str, points: List[Tuple[float, float]]) -> MetricSeries:
    return line(key, points).model_copy(update={"facet": facet})


class TestFacetAssembly:
    @pytest.fixture
    def axes(self) -> ChartAxes:
        return ChartAxes(
            scope=ChartScope.MARKETPLACE,
            chart=ChartKind.AREA,
            series_by=SeriesGrouping.CATEGORY,
            facet_by=SeriesGrouping.PROVIDER,
            transform=ValueTransform.SHARE_OF_TOTAL,
            top=2,
        )

    def test_each_facet_is_transformed_on_its_own_the_largest_first(self, axes: ChartAxes) -> None:
        raw = TrendResult(
            series=[
                faceted("crm", "civo", [(0, 1), (3, 1)]),
                faceted("erp", "civo", [(0, 1), (3, 3)]),
                faceted("crm", "aws", [(0, 10), (3, 30)]),
                faceted("erp", "aws", [(0, 10), (3, 10)]),
            ]
        )

        result = ChartAssembler().assemble(axes, raw)

        facets = list(dict.fromkeys(one.facet for one in result.series))
        assert facets == ["aws", "civo"], "the largest facet first"
        for facet in facets:
            mine = [one for one in result.series if one.facet == facet]
            assert all(sum(one.points[index].y for one in mine) == pytest.approx(100) for index in range(2))
        civo = {one.key: one.points[-1].y for one in result.series if one.facet == "civo"}
        assert civo == {"crm": pytest.approx(25), "erp": pytest.approx(75)}
        assert result.last_actual == 3

    def test_every_facet_keeps_the_same_largest_series(self, axes: ChartAxes) -> None:
        raw = TrendResult(
            series=[
                faceted("crm", "aws", [(0, 50)]),
                faceted("erp", "aws", [(0, 40)]),
                faceted("cms", "aws", [(0, 1)]),
                faceted("cms", "civo", [(0, 9)]),
                faceted("crm", "civo", [(0, 1)]),
                faceted("erp", "civo", [(0, 1)]),
            ]
        )

        result = ChartAssembler().assemble(axes, raw)

        for facet in ("aws", "civo"):
            keys = [one.key for one in result.series if one.facet == facet]
            assert keys[:2] == ["crm", "erp"], "kept by their weight over every facet"
            assert keys[2:] == [SeriesTransformer.OTHERS_KEY], "the others merged in each facet"
        assert result.total_count == 3


class TestDerivativeAssembly:
    def test_a_line_chart_draws_the_rate_of_change_of_its_transformed_values(self) -> None:
        axes = ChartAxes(scope=ChartScope.CATALOGUE, transform=ValueTransform.INDEXED, derivative=True)
        raw = TrendResult(series=[line("aws", [(0, 50), (12, 100), (24, 75)])])

        result = ChartAssembler().assemble(axes, raw)

        assert [(point.x, point.y) for point in result.series[0].points] == [(12, 100.0), (24, -50.0)]
        assert ChartNote.DERIVATIVE in result.notes

    def test_only_line_charts_keep_the_derivative(self) -> None:
        rules = ChartAssembler().rules
        area = ChartAxes(scope=ChartScope.CATALOGUE, chart=ChartKind.AREA, derivative=True)
        lines = ChartAxes(scope=ChartScope.CATALOGUE, derivative=True)

        assert rules.repair(area).derivative is False
        assert rules.repair(lines).derivative is True
        assert rules.derivable(area) is OptionBlock.NEEDS_LINE_CHART
