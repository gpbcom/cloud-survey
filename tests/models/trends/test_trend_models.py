from __future__ import annotations

from typing import Optional, Tuple

import pytest
from pydantic import ValidationError

from analytics.series.axis_rules import AxisRules
from analytics.series.chart_presets import ChartPresets
from models.cloud.enums import CloudProvider, Country, GeoBloc, MarketPlayer
from models.trends.chart_axes import ChartAxes
from models.trends.enums import (
    ChartKind,
    ChartMetric,
    ChartPreset,
    ChartScope,
    ForecastMethod,
    MatrixCell,
    MetricKind,
    MetricUnit,
    SeriesGrouping,
    ValueTransform,
)
from models.trends.metric_series import MetricSeries


class TestBlocs:
    def test_every_country_provider_and_player_has_a_bloc(self) -> None:
        assert {country.bloc for country in Country} == set(GeoBloc)
        assert all(isinstance(provider.bloc, GeoBloc) for provider in CloudProvider)
        assert all(isinstance(player.bloc, GeoBloc) for player in MarketPlayer)

    @pytest.mark.parametrize(
        ("provider", "bloc"),
        [
            (CloudProvider.AWS, GeoBloc.UNITED_STATES),
            (CloudProvider.OVH, GeoBloc.EUROPEAN_UNION),
            (CloudProvider.ALIBABA, GeoBloc.CHINA),
            (CloudProvider.CIVO, GeoBloc.OTHER),
            (CloudProvider.EXOSCALE, GeoBloc.OTHER),
        ],
    )
    def test_provider_blocs(self, provider: CloudProvider, bloc: GeoBloc) -> None:
        assert provider.bloc is bloc

    def test_player_blocs(self) -> None:
        assert MarketPlayer.BIG_THREE.bloc is GeoBloc.UNITED_STATES
        assert MarketPlayer.SAP.bloc is GeoBloc.EUROPEAN_UNION
        assert MarketPlayer.OTHERS.bloc is GeoBloc.OTHER


class TestChartMetrics:
    def test_time_metrics_have_a_date_unit(self) -> None:
        for metric in ChartMetric:
            assert (metric.kind is MetricKind.TIME) == (metric.unit is MetricUnit.DATE)

    @pytest.mark.parametrize(
        ("metric", "unit", "bounds", "method"),
        [
            (ChartMetric.SHARE, MetricUnit.PERCENT, (0.0, 100.0), ForecastMethod.LINEAR),
            (ChartMetric.GROWTH, MetricUnit.PERCENT, (None, None), ForecastMethod.LINEAR),
            (ChartMetric.REVENUE, MetricUnit.BILLIONS, (0.0, None), ForecastMethod.LOG_LINEAR),
            (ChartMetric.LISTED, MetricUnit.COUNT, (0.0, None), ForecastMethod.LOG_LINEAR),
            (ChartMetric.ADDED, MetricUnit.COUNT, (0.0, None), ForecastMethod.LINEAR),
        ],
    )
    def test_units_bounds_and_forecast_methods(
        self,
        metric: ChartMetric,
        unit: MetricUnit,
        bounds: Tuple[Optional[float], Optional[float]],
        method: ForecastMethod,
    ) -> None:
        assert (metric.unit, metric.bounds, metric.forecast_method) == (unit, bounds, method)

    def test_flows_stocks_and_sources(self) -> None:
        assert not ChartMetric.ADDED.stock
        assert (ChartMetric.LISTED.stock, ChartMetric.LISTED.additive, ChartMetric.LISTED.from_crawls) == (True,) * 3
        assert not ChartMetric.PUBLISHERS.additive
        assert ChartMetric.SHARE.player_scoped
        assert not ChartMetric.MARKET_SIZE.player_scoped
        assert ChartMetric.CATALOGUE_SIZE.source is not None
        assert ChartMetric.ADDED.source is None

    def test_transform_and_cell_units(self) -> None:
        assert ValueTransform.RAW.unit is None
        assert ValueTransform.RANK.unit is MetricUnit.RANK
        assert MatrixCell.OVERLAP.unit is MetricUnit.PERCENT
        assert MatrixCell.OVERLAP.publisher_pairs
        assert ChartKind.HEATMAP.is_matrix
        assert not ChartKind.BUBBLE.is_matrix


class TestChartModels:
    def test_axes_are_frozen_and_bounded(self) -> None:
        axes = ChartAxes(scope=ChartScope.CATALOGUE)

        with pytest.raises(ValidationError):
            axes.top = 3  # type: ignore[misc]
        with pytest.raises(ValidationError):
            ChartAxes(scope=ChartScope.CATALOGUE, top=50)

    def test_saved_type_axes_are_read_with_their_replacements(self) -> None:
        axes = ChartAxes.model_validate(
            {
                "scope": "marketplace",
                "series_by": "type",
                "facet_by": "type",
                "columns": "type",
                "preset": "type-mix-by-provider",
            }
        )

        assert (axes.series_by, axes.facet_by, axes.columns) == (
            SeriesGrouping.CATEGORY,
            SeriesGrouping.CATEGORY,
            SeriesGrouping.CATEGORY,
        )
        assert axes.preset is ChartPreset.DOMAIN_TRENDS_BY_PROVIDER
        assert ChartAxes.model_validate({"scope": "marketplace", "series_by": "provider"}).series_by is (
            SeriesGrouping.PROVIDER
        )
        with pytest.raises(ValidationError):
            ChartAxes.model_validate({"scope": "marketplace", "preset": "nowhere"})

    def test_series_currency_is_checked(self) -> None:
        with pytest.raises(ValidationError):
            MetricSeries(key="aws", currency="GBP")

    @pytest.mark.parametrize("preset", list(ChartPreset))
    def test_every_preset_is_valid(self, preset: ChartPreset) -> None:
        axes = ChartPresets().axes(preset)

        assert AxisRules().is_valid(axes)
        assert axes.preset is preset

    @pytest.mark.parametrize("scope", list(ChartScope))
    def test_every_scope_has_a_default_preset(self, scope: ChartScope) -> None:
        presets = ChartPresets()

        assert presets.default(scope).scope is scope
        assert presets.DEFAULTS[scope] in presets.for_scope(scope)
