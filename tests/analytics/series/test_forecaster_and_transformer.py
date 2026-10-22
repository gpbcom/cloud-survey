from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pytest

from analytics.series.series_transformer import SeriesTransformer
from analytics.series.trend_forecaster import TrendForecaster
from models.trends.enums import ChartMetric, ValueTransform
from models.trends.metric_point import MetricPoint
from models.trends.metric_series import MetricSeries


def series(key: str, points: List[Tuple[float, float]], label: Optional[str] = None) -> MetricSeries:
    return MetricSeries(key=key, points=[MetricPoint(x=x, y=y, label=label) for x, y in points])


def values(found: List[MetricSeries]) -> Dict[str, List[Tuple[float, float]]]:
    return {one.key: [(point.x, round(point.y, 6)) for point in one.points] for one in found}


class TestTrendForecaster:
    def test_a_straight_line_is_projected_exactly(self) -> None:
        line = series("aws", [(x, 2 * x + 1) for x in (0, 3, 6, 9)])

        (projected,) = TrendForecaster().project([line], ChartMetric.ADDED)

        tail = [point for point in projected.points if point.projected]
        assert [(point.x, point.y) for point in tail] == [(12, 25), (15, 31), (18, 37), (21, 43)]
        assert projected.trend_pct == pytest.approx(12 * 2 / 19 * 100)

    def test_a_doubling_size_compounds(self) -> None:
        doubling = series("aws", [(x, 100 * 2 ** (x / 12)) for x in (0, 12, 24)])

        (projected,) = TrendForecaster().project([doubling], ChartMetric.LISTED)

        assert projected.points[3].y == pytest.approx(800)
        assert projected.trend_pct == pytest.approx(100)

    def test_short_series_are_not_projected_and_values_stay_in_bounds(self) -> None:
        short = series("aws", [(0, 10), (3, 20)])
        falling = series("gcp", [(0, 30), (3, 20), (6, 10)])

        kept, clamped = TrendForecaster().project([short, falling], ChartMetric.SHARE)

        assert kept == short
        assert [point.y for point in clamped.points if point.projected] == [0, 0, 0, 0]

    def test_every_series_shares_the_future_grid(self) -> None:
        early = series("a", [(0, 1), (3, 2), (6, 3)])
        late = series("b", [(3, 1), (6, 2), (9, 3)])

        projected = TrendForecaster().project([early, late], ChartMetric.ADDED)

        grids = [[point.x for point in one.points if point.projected] for one in projected]
        assert grids == [[12, 15, 18, 21], [12, 15, 18, 21]]


class TestSeriesTransformer:
    def test_align_carries_the_levels_and_zeroes_the_flows(self) -> None:
        first, second = series("a", [(0, 5), (6, 7)]), series("b", [(3, 2)])
        transformer = SeriesTransformer()

        assert values(transformer.align([first, second], ChartMetric.LISTED)) == {
            "a": [(0, 5), (3, 5), (6, 7)],
            "b": [(0, 0), (3, 2), (6, 2)],
        }
        assert values(transformer.align([first, second], ChartMetric.ADDED))["b"] == [(0, 0), (3, 2), (6, 0)]

    def test_share_of_total_indexed_yoy_and_rank(self) -> None:
        transformer = SeriesTransformer()
        first, second = series("a", [(0, 30), (12, 60)]), series("b", [(0, 10), (12, 60)])

        shares = transformer.transform([first, second], ValueTransform.SHARE_OF_TOTAL)
        ranks = transformer.transform([first, second], ValueTransform.RANK)

        assert values(shares) == {"a": [(0, 75), (12, 50)], "b": [(0, 25), (12, 50)]}
        assert values(transformer.transform([first], ValueTransform.INDEXED)) == {"a": [(0, 100), (12, 200)]}
        assert values(transformer.transform([first], ValueTransform.YOY)) == {"a": [(12, 100)]}
        assert values(ranks) == {"a": [(0, 1), (12, 1)], "b": [(0, 2), (12, 1)]}

    def test_pair_applies_a_market_wide_series_to_every_key(self) -> None:
        shares = [series("aws", [(5, 30), (8, 31)]), series("gcp", [(8, 12)])]
        market = [series("", [(5, 100), (8, 110)], label="2025Q2")]

        paired = SeriesTransformer().pair(market, shares)

        assert values(paired) == {"aws": [(100, 30), (110, 31)], "gcp": [(110, 12)]}

    def test_pair_compares_the_buckets(self) -> None:
        catalogue = [series("aws", [(24290, 10), (24293, 12)])]
        marketplace = [series("aws", [(24292.5, 100)])]

        paired = SeriesTransformer().pair(catalogue, marketplace, ChartMetric.QUARTER)

        assert values(paired) == {"aws": [(12, 100)]}
        assert paired[0].points[0].label == "2024Q2"

    def test_snapshot_positions_one_bubble_per_key(self) -> None:
        xs = [series("aws", [(24290, 30), (24293, 31)]), series("gcp", [(24290, 10)])]
        ys = [series("aws", [(24290, 100), (24293, 120)]), series("gcp", [(24290, 50)])]
        sizes = [series("aws", [(24293, 7)])]

        bubbles, as_of = SeriesTransformer().snapshot(xs, ys, sizes, ChartMetric.QUARTER)

        assert [(one.key, one.points[0].x, one.points[0].y, one.points[0].size) for one in bubbles] == [
            ("aws", 31, 120, 7)
        ]
        assert as_of == 24293

    def test_top_keeps_the_largest_and_merges_the_rest(self) -> None:
        transformer = SeriesTransformer()
        found = [series("a", [(0, 1)]), series("b", [(0, 5)]), series("c", [(0, 3)]), series("", [(0, 9)])]
        weights = transformer.weights(found)

        kept = transformer.top(found, 1, weights)
        merged = transformer.top(found, 2, weights, merge=True)

        assert [one.key for one in kept] == ["", "b"]
        assert values(merged) == {"": [(0, 9)], "b": [(0, 5)], "c": [(0, 3)], "*": [(0, 1)]}

    def test_top_without_count_keeps_every_series(self) -> None:
        transformer = SeriesTransformer()
        found = [series("a", [(0, 1)]), series("b", [(0, 5)]), series("c", [(0, 3)])]

        kept = transformer.top(found, None, transformer.weights(found), merge=True)

        assert [one.key for one in kept] == ["b", "c", "a"]

    def test_combine_sums_the_providers_of_a_bloc(self) -> None:
        found = [series("aws", [(0, 2), (3, 4)]), series("gcp", [(3, 1)]), series("ovh-cloud", [(0, 1)])]

        combined = SeriesTransformer().combine(found, {"aws": "us", "gcp": "us", "ovh-cloud": "eu"}, ChartMetric.LISTED)

        assert values(combined) == {"us": [(0, 2), (3, 5)], "eu": [(0, 1), (3, 1)]}

    def test_extend_carries_the_last_level_to_now(self) -> None:
        (extended,) = SeriesTransformer().extend([series("aws", [(0, 2)])], 9)

        assert values([extended]) == {"aws": [(0, 2), (9, 2)]}
