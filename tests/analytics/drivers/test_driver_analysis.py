from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List

import numpy
import pytest

from analytics.drivers.catalog.metric_catalog_loader import MetricCatalogLoader
from analytics.drivers.driver_analysis import DriverAnalysis
from analytics.drivers.exception import MetricCatalogFileError
from analytics.drivers.matrix.driver_panel import DriverPanel
from analytics.drivers.matrix.quarter_calendar import QuarterCalendar
from analytics.drivers.panel.granger_test import GrangerTest
from models.cloud.enums import CloudProvider
from models.drivers.enums import DriverScope, DriverWarningKind, MetricSource, ProviderMetric
from models.drivers.metrics.metric_catalog import MetricCatalog
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from models.drivers.query.driver_query import DriverQuery

PROVIDERS: List[CloudProvider] = list(CloudProvider)
TARGET = ProviderMetric.MARKET_SHARE
DRIVER = ProviderMetric.AI_SHARE
NOISE = ProviderMetric.DATA_SHARE
SIZE = ProviderMetric.SECURITY_SHARE


@pytest.fixture(scope="module")
def catalog() -> MetricCatalog:
    return MetricCatalogLoader().load()


def measure(provider: CloudProvider, period: str, metric: ProviderMetric, value: float) -> ProviderMetricValue:
    return ProviderMetricValue(provider=provider, period=period, metric=metric, value=value)


def cross_section(seed: int, providers: int = 30) -> List[ProviderMetricValue]:
    """Plant a driver: the target follows `DRIVER`, `NOISE` is unrelated."""
    generator = numpy.random.default_rng(seed)
    values: List[ProviderMetricValue] = []
    for provider in PROVIDERS[:providers]:
        driver, noise = float(generator.normal()), float(generator.normal())
        values += [
            measure(provider, "2026Q2", DRIVER, driver),
            measure(provider, "2026Q2", NOISE, noise),
            measure(provider, "2026Q2", TARGET, 2.0 * driver + 0.4 * float(generator.normal())),
        ]
    return values


def panel(seed: int, lag: int, walk: bool = True) -> List[ProviderMetricValue]:
    """Plant a lagged driver: the yearly change of the target follows the change of `DRIVER` `lag` quarters before.

    A walking driver accumulates its shocks, otherwise each quarter draws a fresh one (no overlap between the
    yearly changes, so the target cannot predict the driver).
    """
    generator = numpy.random.default_rng(seed)
    calendar = QuarterCalendar()
    quarters = [calendar.period(calendar.index("2019Q1") + step) for step in range(28)]
    values: List[ProviderMetricValue] = []
    for provider in PROVIDERS[:12]:
        driver: Dict[int, float] = {}
        target: Dict[int, float] = {}
        noise = 0.0
        for step, quarter in enumerate(quarters):
            driver[step] = (driver.get(step - 1, 0.0) if walk else 0.0) + float(generator.normal())
            noise += float(generator.normal())
            if step < 4 + lag:
                target[step] = float(generator.normal())
            else:
                change = driver[step - lag] - driver[step - lag - 4]
                target[step] = target[step - 4] + 1.5 * change + 0.3 * float(generator.normal())
            values += [
                measure(provider, quarter, DRIVER, driver[step]),
                measure(provider, quarter, NOISE, noise),
                measure(provider, quarter, TARGET, target[step]),
            ]
    return values


class TestMetricCatalogLoader:
    def test_the_shipped_catalogue_loads(self, catalog: MetricCatalog) -> None:
        assert catalog.get(TARGET) is not None
        assert {definition.metric for definition in catalog.targets()} >= {TARGET, ProviderMetric.REVENUE}

    def test_a_missing_file_is_reported(self, tmp_path: Path) -> None:
        with pytest.raises(MetricCatalogFileError):
            MetricCatalogLoader().load(tmp_path / "missing.yaml")


class TestDriverPanel:
    def test_the_most_trusted_source_wins(self, catalog: MetricCatalog) -> None:
        provider = PROVIDERS[0]
        values = [
            measure(provider, "2025Q4", ProviderMetric.REVENUE, 10.0),
            ProviderMetricValue(
                provider=provider,
                period="2025Q4",
                metric=ProviderMetric.REVENUE,
                value=20.0,
                source=MetricSource.MANUAL,
            ),
            ProviderMetricValue(
                provider=provider,
                period="2025Q4",
                metric=ProviderMetric.REVENUE,
                value=30.0,
                source=MetricSource.DERIVED,
                fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ]

        levels = DriverPanel(catalog).levels(values, [ProviderMetric.REVENUE], [])

        assert levels[provider][ProviderMetric.REVENUE]["2025Q4"] == pytest.approx(math.log(20.0))

    def test_values_follow_the_scale_of_their_metric(self, catalog: MetricCatalog) -> None:
        driver_panel = DriverPanel(catalog)

        assert driver_panel.transform(ProviderMetric.PRODUCTS, 9.0) == pytest.approx(math.log(10.0))
        assert driver_panel.transform(ProviderMetric.REVENUE, 0.0) is None
        assert driver_panel.transform(ProviderMetric.PRODUCTS, -1.0) is None
        assert driver_panel.transform(ProviderMetric.AI_SHARE, 0.25) == 0.25

    def test_natural_values_invert_the_transform(self, catalog: MetricCatalog) -> None:
        driver_panel = DriverPanel(catalog)
        products = driver_panel.transform(ProviderMetric.PRODUCTS, 99.0)
        revenue = driver_panel.transform(ProviderMetric.REVENUE, 12.5)
        assert products is not None
        assert revenue is not None

        assert driver_panel.natural(ProviderMetric.PRODUCTS, products, DriverScope.CROSS_SECTION) == pytest.approx(99.0)
        assert driver_panel.natural(ProviderMetric.REVENUE, revenue, DriverScope.CROSS_SECTION) == pytest.approx(12.5)
        assert driver_panel.natural(ProviderMetric.AI_SHARE, 0.3, DriverScope.CROSS_SECTION) == 0.3
        assert driver_panel.natural(ProviderMetric.REVENUE, math.log(1.5), DriverScope.PANEL) == pytest.approx(50.0)
        assert driver_panel.natural(ProviderMetric.AI_SHARE, 0.02, DriverScope.PANEL) == 0.02
        assert driver_panel.natural(ProviderMetric.REVENUE, 1e6, DriverScope.CROSS_SECTION) is None

    def test_a_cross_section_takes_the_latest_complete_quarter(self, catalog: MetricCatalog) -> None:
        provider = PROVIDERS[0]
        values = [
            measure(provider, "2025Q1", TARGET, 0.1),
            measure(provider, "2025Q1", DRIVER, 0.2),
            measure(provider, "2025Q3", TARGET, 0.3),
        ]
        query = DriverQuery(target=TARGET, criteria=[DRIVER])

        matrix = DriverPanel(catalog).cross_section(query, values)

        assert matrix.periods == ["2025Q1"]
        assert matrix.y.tolist() == [0.1]

    def test_a_panel_uses_the_yearly_changes_with_the_lag(self, catalog: MetricCatalog) -> None:
        provider = PROVIDERS[0]
        values = [measure(provider, f"2024Q{q}", TARGET, float(q)) for q in range(1, 5)]
        values += [measure(provider, f"2025Q{q}", TARGET, float(q) * 3) for q in range(1, 5)]
        values += [
            measure(provider, f"{year}Q{q}", DRIVER, year + q / 10) for year in (2024, 2025) for q in (1, 2, 3, 4)
        ]
        query = DriverQuery(target=TARGET, criteria=[DRIVER], scope=DriverScope.PANEL, lag=1)

        matrix = DriverPanel(catalog).panel(query, values)

        assert matrix.periods == ["2025Q1", "2025Q2", "2025Q3", "2025Q4"]
        assert matrix.y.tolist() == [2.0, 4.0, 6.0, 8.0]
        assert numpy.isnan(matrix.x[0, 0])
        assert matrix.x[1:, 0] == pytest.approx([1.0, 1.0, 1.0])
        assert matrix.dropped == 1


class TestCrossSection:
    def test_the_planted_driver_is_found_and_predominant(self, catalog: MetricCatalog) -> None:
        query = DriverQuery(target=TARGET, criteria=[NOISE, DRIVER], bootstrap=200)

        result = DriverAnalysis(catalog).run(query, cross_section(seed=11))

        assert result.observations == result.providers == 30
        strongest, weakest = result.correlations
        assert strongest.criterion is DRIVER
        assert strongest.rho > 0.85
        assert strongest.q_value < 1e-6
        assert strongest.low is not None
        assert strongest.high is not None
        assert strongest.low < strongest.rho < strongest.high
        assert weakest.q_value > 0.05
        top = result.coefficients[0]
        assert top.criterion is DRIVER
        assert top.importance > 0.8
        assert top.importance_low is not None
        assert top.importance_low < top.importance
        assert result.r2 is not None
        assert result.loo_r2 is not None
        assert result.loo_r2 > 0.8
        assert sum(coefficient.importance for coefficient in result.coefficients) == pytest.approx(result.r2)

    def test_the_same_seed_gives_the_same_result(self, catalog: MetricCatalog) -> None:
        query = DriverQuery(target=TARGET, criteria=[NOISE, DRIVER], bootstrap=50)
        analysis = DriverAnalysis(catalog)

        assert analysis.run(query, cross_section(seed=3)) == analysis.run(query, cross_section(seed=3))

    def test_a_partial_correlation_is_given_with_controls(self, catalog: MetricCatalog) -> None:
        values = cross_section(seed=12) + [
            measure(provider, "2026Q2", SIZE, 1.0 + index) for index, provider in enumerate(PROVIDERS[:30])
        ]
        query = DriverQuery(target=TARGET, criteria=[DRIVER], controls=[SIZE], bootstrap=0)

        (cell,) = DriverAnalysis(catalog).run(query, values).correlations

        assert cell.partial is not None
        assert cell.partial > 0.8
        assert cell.low is None

    def test_three_providers_are_flagged_and_cannot_be_regressed(self, catalog: MetricCatalog) -> None:
        query = DriverQuery(target=TARGET, criteria=[NOISE, DRIVER], bootstrap=0)

        result = DriverAnalysis(catalog).run(query, cross_section(seed=1, providers=3))

        assert result.r2 is None
        assert result.coefficients == []
        kinds = {warning.kind for warning in result.warnings}
        assert {DriverWarningKind.FEW_PROVIDERS, DriverWarningKind.REGRESSION_SKIPPED} <= kinds
        assert any("Only 3 providers" in warning.message for warning in result.warnings)

    def test_a_missing_criterion_is_reported(self, catalog: MetricCatalog) -> None:
        query = DriverQuery(target=TARGET, criteria=[DRIVER, ProviderMetric.REGIONS], bootstrap=0)

        result = DriverAnalysis(catalog).run(query, cross_section(seed=2))

        assert [cell.criterion for cell in result.correlations] == [DRIVER]
        (missing,) = [warning for warning in result.warnings if warning.kind is DriverWarningKind.UNCORRELATABLE]
        assert missing.subjects == [ProviderMetric.REGIONS]
        assert missing.message.startswith("regions:")

    def test_a_criterion_of_few_providers_does_not_shrink_the_regression(self, catalog: MetricCatalog) -> None:
        values = cross_section(seed=6) + [measure(provider, "2026Q2", SIZE, 1.0) for provider in PROVIDERS[:5]]
        query = DriverQuery(target=TARGET, criteria=[DRIVER, SIZE], bootstrap=0)

        result = DriverAnalysis(catalog).run(query, values)

        assert result.observations == 30
        assert [coefficient.criterion for coefficient in result.coefficients] == [DRIVER]
        (left_out,) = [warning for warning in result.warnings if warning.kind is DriverWarningKind.LEFT_OUT]
        assert left_out.subjects == [SIZE]

    def test_the_scarcest_criteria_are_named(self, catalog: MetricCatalog) -> None:
        values = cross_section(seed=6) + [
            measure(provider, "2026Q2", SIZE, float(index)) for index, provider in enumerate(PROVIDERS[:10])
        ]
        query = DriverQuery(target=TARGET, criteria=[DRIVER, SIZE], bootstrap=0)

        result = DriverAnalysis(catalog).run(query, values)

        assert result.observations == 10
        (missing,) = [warning for warning in result.warnings if warning.kind is DriverWarningKind.MISSING_VALUES]
        assert f"measured least with the target: {SIZE.value} (10), {DRIVER.value} (30)" in missing.message
        assert missing.subjects == [SIZE, DRIVER]

    def test_a_constant_criterion_is_left_out_of_the_regression(self, catalog: MetricCatalog) -> None:
        values = cross_section(seed=7) + [
            measure(provider, "2026Q2", SIZE, 2.0 if index < 3 else 1.0)
            for index, provider in enumerate(PROVIDERS[:30])
        ]
        drop = {provider for provider in PROVIDERS[:3]}
        values = [value for value in values if value.provider not in drop or value.metric is SIZE]
        query = DriverQuery(target=TARGET, criteria=[DRIVER, SIZE], bootstrap=0)

        result = DriverAnalysis(catalog).run(query, values)

        assert [coefficient.criterion for coefficient in result.coefficients] == [DRIVER]
        assert any(
            warning.kind is DriverWarningKind.UNCORRELATABLE and warning.subjects == [SIZE]
            for warning in result.warnings
        )

    def test_no_interval_from_fewer_than_three_providers(self, catalog: MetricCatalog) -> None:
        query = DriverQuery(target=TARGET, criteria=[DRIVER], scope=DriverScope.PANEL, lag=1, bootstrap=100)
        values = [value for value in panel(seed=8, lag=1) if value.provider in PROVIDERS[:2]]

        (cell,) = DriverAnalysis(catalog).run(query, values).correlations

        assert cell.low is None
        assert cell.high is None

    def test_collinear_criteria_are_flagged(self, catalog: MetricCatalog) -> None:
        values = cross_section(seed=4)
        values += [
            measure(value.provider, value.period, SIZE, value.value * 1.001 + 1e-4 * index)
            for index, value in enumerate(values)
            if value.metric is DRIVER
        ]
        query = DriverQuery(target=TARGET, criteria=[DRIVER, SIZE], bootstrap=0)

        result = DriverAnalysis(catalog).run(query, values)

        (collinear,) = [warning for warning in result.warnings if warning.kind is DriverWarningKind.COLLINEAR]
        assert set(collinear.subjects) == {DRIVER, SIZE}


class TestPanel:
    def test_the_lagged_driver_is_found_and_leads_the_target(self, catalog: MetricCatalog) -> None:
        query = DriverQuery(target=TARGET, criteria=[NOISE, DRIVER], scope=DriverScope.PANEL, lag=2, bootstrap=100)

        result = DriverAnalysis(catalog).run(query, panel(seed=21, lag=2))

        top = result.coefficients[0]
        assert top.criterion is DRIVER
        assert top.beta > 0.8
        assert top.p_value is not None
        assert top.p_value < 1e-6
        assert top.granger_p is not None
        assert top.granger_p < 0.01
        assert result.coefficients[1].importance < 0.1
        assert result.providers == 12

    def test_granger_runs_without_a_regression(self, catalog: MetricCatalog) -> None:
        values = [value for value in panel(seed=24, lag=1) if value.provider is PROVIDERS[0]]
        query = DriverQuery(target=TARGET, criteria=[DRIVER], scope=DriverScope.PANEL, lag=1, bootstrap=0)

        result = DriverAnalysis(catalog).run(query, values)

        assert result.coefficients == []
        assert DriverWarningKind.SHORT_PANEL in {warning.kind for warning in result.warnings}
        (cell,) = result.correlations
        assert cell.granger_p is not None
        assert cell.granger_p < 0.01

    def test_the_coefficients_share_the_granger_of_their_criterion(self, catalog: MetricCatalog) -> None:
        query = DriverQuery(target=TARGET, criteria=[NOISE, DRIVER], scope=DriverScope.PANEL, lag=2, bootstrap=0)

        result = DriverAnalysis(catalog).run(query, panel(seed=25, lag=2))

        leads = {cell.criterion: cell.granger_p for cell in result.correlations}
        assert {coefficient.criterion: coefficient.granger_p for coefficient in result.coefficients} == leads
        assert all(value is not None for value in leads.values())

    def test_no_granger_on_the_latest_quarter(self, catalog: MetricCatalog) -> None:
        result = DriverAnalysis(catalog).run(
            DriverQuery(target=TARGET, criteria=[DRIVER], bootstrap=0), cross_section(seed=9)
        )

        assert [cell.granger_p for cell in result.correlations] == [None]

    def test_a_wrong_lag_explains_less(self, catalog: MetricCatalog) -> None:
        values = panel(seed=22, lag=2)
        analysis = DriverAnalysis(catalog)

        right = analysis.run(
            DriverQuery(target=TARGET, criteria=[DRIVER], scope=DriverScope.PANEL, lag=2, bootstrap=0), values
        )
        wrong = analysis.run(
            DriverQuery(target=TARGET, criteria=[DRIVER], scope=DriverScope.PANEL, lag=6, bootstrap=0), values
        )

        assert right.r2 is not None
        assert wrong.r2 is not None
        assert right.r2 > wrong.r2 + 0.3

    def test_one_quarter_of_history_is_not_a_panel(self, catalog: MetricCatalog) -> None:
        query = DriverQuery(target=TARGET, criteria=[DRIVER], scope=DriverScope.PANEL, bootstrap=0)

        result = DriverAnalysis(catalog).run(query, cross_section(seed=5))

        assert result.r2 is None
        assert DriverWarningKind.NOTHING_CORRELATED in {warning.kind for warning in result.warnings}


class TestGrangerTest:
    def test_the_driver_leads_far_more_than_it_follows(self, catalog: MetricCatalog) -> None:
        values = panel(seed=23, lag=1, walk=False)
        query = DriverQuery(target=TARGET, criteria=[DRIVER], scope=DriverScope.PANEL, lag=1)
        series = DriverPanel(catalog).panel(query, values).series
        granger = GrangerTest()

        forward = granger.p_value(series, TARGET, DRIVER, 1)
        backward = granger.p_value(series, DRIVER, TARGET, 1)

        assert forward is not None
        assert backward is not None
        assert forward < 1e-50 < 1e-4 < backward

    def test_too_short_a_history_gives_no_p_value(self) -> None:
        series = {PROVIDERS[0]: {TARGET: {"2025Q1": 1.0, "2025Q2": 2.0}, DRIVER: {"2025Q1": 1.0}}}

        assert GrangerTest().p_value(series, TARGET, DRIVER, 1) is None


class TestCommonCriteria:
    def test_a_market_context_is_flagged_and_correlated_only_over_time(self, catalog: MetricCatalog) -> None:
        values = panel(seed=11, lag=0)
        quarters = sorted({value.period for value in values})
        context = {quarter: float(index % 5) + 0.1 * index for index, quarter in enumerate(quarters)}
        values += [
            measure(provider, quarter, ProviderMetric.CONTEXT_DRAM_HHI, context[quarter])
            for provider in PROVIDERS[:12]
            for quarter in quarters
        ]
        criteria = [DRIVER, ProviderMetric.CONTEXT_DRAM_HHI]

        result = DriverAnalysis(catalog).run(
            DriverQuery(target=TARGET, criteria=criteria, scope=DriverScope.PANEL, bootstrap=0), values
        )
        latest = DriverAnalysis(catalog).run(DriverQuery(target=TARGET, criteria=criteria, bootstrap=0), values)

        common = [warning for warning in result.warnings if warning.kind is DriverWarningKind.COMMON_CRITERION]
        assert common
        assert common[0].subjects == [ProviderMetric.CONTEXT_DRAM_HHI]
        assert ProviderMetric.CONTEXT_DRAM_HHI in [cell.criterion for cell in result.correlations]
        assert ProviderMetric.CONTEXT_DRAM_HHI not in [cell.criterion for cell in latest.correlations]
        assert "latest quarter" in next(
            warning.message for warning in latest.warnings if warning.kind is DriverWarningKind.COMMON_CRITERION
        )
