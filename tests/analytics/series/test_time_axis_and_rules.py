from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Callable

import pytest

from analytics.series.axis_rules import AxisRules
from analytics.series.chart_presets import ChartPresets
from analytics.series.time_axis import TimeAxis
from models.cloud.enums import MarketPlayer
from models.stats.market_report import MarketReport
from models.storage.enums import DatasetKind
from models.trends.chart_axes import ChartAxes
from models.trends.enums import (
    ChartKind,
    ChartMetric,
    ChartPreset,
    ChartScope,
    MatrixCell,
    OptionBlock,
    SeriesGrouping,
    ValueTransform,
)


class TestTimeAxis:
    def test_periods_and_buckets_line_up_on_their_last_month(self, make_report: Callable[..., MarketReport]) -> None:
        time = TimeAxis()
        june = time.month(2025, 6)

        assert time.period(make_report("2025Q2", [(MarketPlayer.AMAZON, 30)])) == june
        assert time.period(make_report("2025H1", [(MarketPlayer.AMAZON, 30)])) == june
        assert time.bucket(time.ordinal(date(2025, 4, 12)), ChartMetric.QUARTER) == june
        assert time.bucket(june, ChartMetric.MONTH) == june
        assert time.bucket(june, ChartMetric.YEAR) == time.month(2025, 12)
        assert time.bucket_of_start(date(2025, 4, 1), ChartMetric.QUARTER) == june

    def test_dates_keep_the_elapsed_fraction_of_the_month(self) -> None:
        time = TimeAxis()

        assert time.ordinal(date(2026, 3, 1)) == time.month(2026, 3)
        assert time.ordinal(datetime(2026, 3, 16, 12, tzinfo=UTC)) == pytest.approx(time.month(2026, 3) + 15.5 / 31)

    @pytest.mark.parametrize(
        ("metric", "label"),
        [
            (ChartMetric.YEAR, "2026"),
            (ChartMetric.QUARTER, "2026Q2"),
            (ChartMetric.PERIOD, "2026Q2"),
            (ChartMetric.MONTH, "2026-05"),
            (ChartMetric.PUBLISHED, "01 May 2026"),
        ],
    )
    def test_labels(self, metric: ChartMetric, label: str) -> None:
        assert TimeAxis().label(metric, TimeAxis().month(2026, 5)) == label


class TestAxisRules:
    def test_the_y_axis_never_repeats_the_x_axis(self) -> None:
        axes = ChartAxes(scope=ChartScope.CATALOGUE, x=ChartMetric.LISTED, y=ChartMetric.ADDED)

        assert dict(AxisRules().y_options(axes))[ChartMetric.LISTED] is OptionBlock.SAME_AS_X

    def test_a_crawl_date_axis_needs_crawl_metrics_by_provider(self) -> None:
        rules = AxisRules()
        axes = ChartAxes(scope=ChartScope.MARKETPLACE, x=ChartMetric.CRAWL_DATE, y=ChartMetric.ADDED)

        assert dict(rules.y_options(axes))[ChartMetric.PUBLISHERS] is OptionBlock.NOT_FROM_CRAWLS
        assert dict(rules.groupings(axes))[SeriesGrouping.CATEGORY] is OptionBlock.NOT_PER_GROUPING

    def test_the_market_share_is_not_known_per_delivery(self) -> None:
        axes = ChartAxes(scope=ChartScope.MARKETPLACE, series_by=SeriesGrouping.DELIVERY)

        assert dict(AxisRules().x_options(axes))[ChartMetric.SHARE] is OptionBlock.NOT_PER_GROUPING
        assert dict(AxisRules().y_options(axes))[ChartMetric.UPDATED] is OptionBlock.NOT_PER_GROUPING

    def test_areas_need_time_and_additive_values(self) -> None:
        axes = ChartAxes(scope=ChartScope.STATISTICS, chart=ChartKind.AREA, x=ChartMetric.PERIOD)

        assert dict(AxisRules().y_options(axes))[ChartMetric.GROWTH] is OptionBlock.NOT_ADDITIVE
        assert dict(AxisRules().x_options(axes))[ChartMetric.SHARE] is OptionBlock.NEEDS_TIME_AXIS

    def test_missing_datasets_block_their_metrics(self) -> None:
        axes = ChartAxes(scope=ChartScope.ANALYSIS, chart=ChartKind.BUBBLE, x=ChartMetric.SHARE)
        available = frozenset({DatasetKind.CATALOGUE})

        options = dict(AxisRules().y_options(axes, available))

        assert options[ChartMetric.MARKETPLACE_SIZE] is OptionBlock.NO_MARKETPLACES
        assert options[ChartMetric.CATALOGUE_SIZE] is None

    def test_transforms_and_forecast_need_time(self) -> None:
        rules = AxisRules()
        numeric = ChartAxes(scope=ChartScope.STATISTICS, x=ChartMetric.SHARE, y=ChartMetric.REVENUE)
        published = ChartAxes(scope=ChartScope.STATISTICS, x=ChartMetric.PUBLISHED, y=ChartMetric.GROWTH)

        assert dict(rules.transforms(numeric))[ValueTransform.RANK] is OptionBlock.NEEDS_TIME_AXIS
        assert dict(rules.transforms(published))[ValueTransform.YOY] is OptionBlock.NEEDS_CALENDAR_AXIS
        assert dict(rules.transforms(published))[ValueTransform.SHARE_OF_TOTAL] is OptionBlock.NOT_ADDITIVE
        assert rules.forecastable(numeric) is OptionBlock.NEEDS_TIME_AXIS
        assert rules.forecastable(published) is None

    def test_the_publisher_pairs_need_providers(self) -> None:
        axes = ChartAxes(scope=ChartScope.MARKETPLACE, chart=ChartKind.HEATMAP, cell=MatrixCell.OVERLAP)

        assert dict(AxisRules().groupings(axes))[SeriesGrouping.BLOC] is OptionBlock.NEEDS_PROVIDERS
        assert dict(AxisRules().column_options(axes))[SeriesGrouping.PROVIDER] is None

    def test_repair_keeps_valid_choices_and_replaces_the_others(self) -> None:
        rules = AxisRules()
        valid = ChartAxes(scope=ChartScope.CATALOGUE, x=ChartMetric.YEAR, y=ChartMetric.ADDED, forecast=True)
        invalid = ChartAxes(
            scope=ChartScope.CATALOGUE,
            chart=ChartKind.BUBBLE,
            x=ChartMetric.SHARE,
            y=ChartMetric.SHARE,
            series_by=SeriesGrouping.DELIVERY,
            transform=ValueTransform.YOY,
            forecast=True,
            log_scale=True,
        )

        repaired = rules.repair(invalid)

        assert rules.repair(valid) == valid
        assert repaired.chart is ChartKind.LINE
        assert repaired.series_by is SeriesGrouping.PROVIDER
        assert repaired.y is ChartMetric.LISTED
        assert repaired.transform is ValueTransform.RAW
        assert (repaired.forecast, repaired.log_scale) == (False, False)
        assert rules.is_valid(repaired)

    def test_repair_sets_the_bubble_size_and_the_matrix_columns(self) -> None:
        rules = AxisRules()
        bubble = ChartAxes(
            scope=ChartScope.ANALYSIS, chart=ChartKind.BUBBLE, x=ChartMetric.SHARE, y=ChartMetric.PUBLISHERS
        )
        mix = ChartAxes(
            scope=ChartScope.MARKETPLACE,
            chart=ChartKind.MIX,
            series_by=SeriesGrouping.CATEGORY,
            columns=SeriesGrouping.CATEGORY,
        )

        assert rules.repair(bubble).size is ChartMetric.MARKETPLACE_SIZE
        assert rules.repair(mix).cell is MatrixCell.ROW_SHARE
        assert rules.repair(mix).columns is SeriesGrouping.PROVIDER


class TestFacetRules:
    def test_the_facets_split_counted_items_over_calendar_buckets(self) -> None:
        rules = AxisRules()
        axes = ChartAxes(scope=ChartScope.MARKETPLACE, chart=ChartKind.AREA, series_by=SeriesGrouping.CATEGORY)

        options = dict(rules.facet_options(axes))

        assert options[None] is None
        assert options[SeriesGrouping.PROVIDER] is None
        assert options[SeriesGrouping.CATEGORY] is OptionBlock.SAME_AS_SERIES
        assert dict(rules.facet_options(ChartAxes(scope=ChartScope.STATISTICS))) == {None: None}

    def test_the_facets_need_lines_or_areas_of_counted_items_over_buckets(self) -> None:
        rules = AxisRules()
        marketplace = ChartAxes(scope=ChartScope.MARKETPLACE, series_by=SeriesGrouping.CATEGORY)

        bubble = marketplace.model_copy(update={"chart": ChartKind.BUBBLE})
        crawls = marketplace.model_copy(update={"x": ChartMetric.CRAWL_DATE})
        updated = marketplace.model_copy(update={"y": ChartMetric.UPDATED})
        analysis = ChartAxes(scope=ChartScope.ANALYSIS, y=ChartMetric.SHARE)

        assert dict(rules.facet_options(bubble))[SeriesGrouping.PROVIDER] is OptionBlock.NEEDS_TIME_AXIS
        assert dict(rules.facet_options(crawls))[SeriesGrouping.PROVIDER] is OptionBlock.NEEDS_CALENDAR_AXIS
        assert dict(rules.facet_options(updated))[SeriesGrouping.PROVIDER] is OptionBlock.NOT_PER_GROUPING
        assert dict(rules.facet_options(analysis))[SeriesGrouping.BLOC] is OptionBlock.NOT_PER_GROUPING

    def test_repair_keeps_a_valid_facet_and_drops_the_others(self) -> None:
        rules = AxisRules()
        faceted = ChartAxes(
            scope=ChartScope.MARKETPLACE,
            chart=ChartKind.AREA,
            series_by=SeriesGrouping.CATEGORY,
            facet_by=SeriesGrouping.PROVIDER,
        )

        assert rules.repair(faceted) == faceted
        assert rules.repair(faceted.model_copy(update={"chart": ChartKind.HEATMAP})).facet_by is None
        assert rules.repair(faceted.model_copy(update={"facet_by": SeriesGrouping.CATEGORY})).facet_by is None
        assert rules.repair(faceted.model_copy(update={"x": ChartMetric.CRAWL_DATE})).facet_by is None


class TestAudienceRules:
    def test_the_audience_groups_the_software_and_the_products(self) -> None:
        rules = AxisRules()
        marketplace = ChartAxes(scope=ChartScope.MARKETPLACE, chart=ChartKind.AREA)
        catalogue = ChartAxes(scope=ChartScope.CATALOGUE, chart=ChartKind.AREA)
        mix = ChartAxes(scope=ChartScope.MARKETPLACE, chart=ChartKind.MIX, cell=MatrixCell.ROW_SHARE)

        assert dict(rules.groupings(marketplace))[SeriesGrouping.AUDIENCE] is None
        assert dict(rules.groupings(catalogue))[SeriesGrouping.AUDIENCE] is None
        assert dict(rules.facet_options(catalogue))[SeriesGrouping.AUDIENCE] is None
        assert SeriesGrouping.DELIVERY not in dict(rules.groupings(catalogue))
        assert dict(rules.column_options(mix))[SeriesGrouping.AUDIENCE] is None
        assert dict(rules.facet_options(marketplace))[SeriesGrouping.AUDIENCE] is None

    @pytest.mark.parametrize(
        "preset", [ChartPreset.AUDIENCE_TRENDS, ChartPreset.AUDIENCE_MIX_BY_PROVIDER, ChartPreset.AUDIENCE_BY_PROVIDER]
    )
    def test_the_audience_presets_are_valid(self, preset: ChartPreset) -> None:
        axes = ChartPresets().axes(preset)

        assert AxisRules().is_valid(axes)
        assert SeriesGrouping.AUDIENCE in (axes.series_by, axes.columns)
