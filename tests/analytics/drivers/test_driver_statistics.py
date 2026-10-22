from __future__ import annotations

from typing import List

import numpy
import pytest
from scipy import stats

from analytics.drivers.correlation.benjamini_hochberg import BenjaminiHochberg
from analytics.drivers.correlation.spearman_correlation import SpearmanCorrelation
from analytics.drivers.exception import InvalidQuarterError
from analytics.drivers.matrix.cluster_resampler import ClusterResampler
from analytics.drivers.matrix.quarter_calendar import QuarterCalendar
from analytics.drivers.panel.fixed_effects_demeaner import FixedEffectsDemeaner
from analytics.drivers.regression.ols_estimator import OlsEstimator
from analytics.drivers.regression.shapley_decomposition import ShapleyDecomposition
from models.cloud.enums import CloudProvider

PROVIDERS: List[CloudProvider] = list(CloudProvider)


class TestQuarterCalendar:
    def test_quarters_are_numbered_across_years(self) -> None:
        calendar = QuarterCalendar()

        assert calendar.shift("2025Q1", -1) == "2024Q4"
        assert calendar.shift("2024q3", 4) == "2025Q3"
        assert calendar.index("2025Q1") - calendar.index("2024Q1") == 4

    def test_a_malformed_quarter_is_refused(self) -> None:
        with pytest.raises(InvalidQuarterError):
            QuarterCalendar().index("2025-03")


class TestBenjaminiHochberg:
    def test_q_values_match_scipy(self) -> None:
        p_values = [0.001, 0.04, 0.03, 0.5, 0.012]

        q_values = BenjaminiHochberg().q_values(p_values)

        assert q_values == pytest.approx(list(stats.false_discovery_control(p_values)))
        assert all(q >= p for p, q in zip(p_values, q_values, strict=True))

    def test_no_p_value_gives_no_q_value(self) -> None:
        assert BenjaminiHochberg().q_values([]) == []


class TestSpearmanCorrelation:
    def test_a_monotone_relation_has_a_correlation_of_one(self) -> None:
        x = numpy.arange(1.0, 11.0)

        assert SpearmanCorrelation().rho(x, numpy.exp(x)) == pytest.approx(1.0)
        assert SpearmanCorrelation().rho(x, -(x**3)) == pytest.approx(-1.0)

    def test_it_matches_scipy_with_ties(self) -> None:
        x = numpy.array([1.0, 2.0, 2.0, 3.0, 5.0, 4.0, 7.0])
        y = numpy.array([2.0, 1.0, 4.0, 4.0, 3.0, 6.0, 5.0])

        expected = stats.spearmanr(x, y)

        assert SpearmanCorrelation().rho(x, y) == pytest.approx(expected.statistic)
        assert SpearmanCorrelation().p_value(float(expected.statistic), 7) == pytest.approx(expected.pvalue)

    def test_a_constant_or_short_series_has_no_correlation(self) -> None:
        assert SpearmanCorrelation().rho(numpy.ones(5), numpy.arange(5.0)) is None
        assert SpearmanCorrelation().rho(numpy.arange(2.0), numpy.arange(2.0)) is None

    def test_the_partial_correlation_removes_a_common_cause(self) -> None:
        generator = numpy.random.default_rng(1)
        size = generator.normal(size=200)
        x = size + 0.3 * generator.normal(size=200)
        y = size + 0.3 * generator.normal(size=200)
        spearman = SpearmanCorrelation()

        assert spearman.rho(x, y) == pytest.approx(0.9, abs=0.08)
        partial = spearman.partial(x, y, size[:, None])
        assert partial is not None
        assert abs(partial) < 0.2

    def test_few_observations_get_an_exact_p_value(self) -> None:
        x = numpy.array([1.0, 2.0, 3.0])
        spearman = SpearmanCorrelation()

        assert spearman.significance(x, x * 10, 1.0) == pytest.approx(2 / 6)
        assert spearman.significance(numpy.arange(9.0), numpy.arange(9.0), 1.0) == 0.0

    def test_no_degree_of_freedom_gives_a_p_value_of_one(self) -> None:
        assert SpearmanCorrelation().p_value(0.9, 3, controls=1) == 1.0


class TestClusterResampler:
    def test_resamples_draw_whole_providers_reproducibly(self) -> None:
        providers = [PROVIDERS[0]] * 3 + [PROVIDERS[1]] * 2
        resampler = ClusterResampler()

        first = resampler.samples(providers, 30, seed=3)
        second = resampler.samples(providers, 30, seed=3)

        assert all((a == b).all() for a, b in zip(first, second, strict=True))
        for rows in first:
            drawn = sorted(rows.tolist())
            assert drawn.count(0) == drawn.count(1) == drawn.count(2)
            assert drawn.count(3) == drawn.count(4)

    def test_no_resample_is_drawn_without_providers(self) -> None:
        assert ClusterResampler().samples([], 10, seed=1) == []


class TestOlsEstimator:
    def test_the_standardized_coefficients_and_the_leave_one_out_r2(self) -> None:
        generator = numpy.random.default_rng(2)
        x = generator.normal(size=(40, 2))
        y = 3.0 * x[:, 0] - 1.0 * x[:, 1] + 0.5 * generator.normal(size=40)
        estimator = OlsEstimator()

        fit = estimator.fit(y, x)

        xs, ys = estimator.standardize(x), estimator.standardize(y)
        assert fit.beta == pytest.approx(numpy.linalg.lstsq(xs, ys, rcond=None)[0])
        press = 0.0
        for left in range(40):
            kept = numpy.arange(40) != left
            design = numpy.column_stack([numpy.ones(39), x[kept]])
            coefficients = numpy.linalg.lstsq(design, y[kept], rcond=None)[0]
            press += float((y[left] - numpy.r_[1.0, x[left]] @ coefficients) ** 2)
        assert fit.loo_r2 == pytest.approx(1 - press / float(((y - y.mean()) ** 2).sum()))
        assert fit.loo_r2 is not None
        assert fit.r2 > fit.loo_r2 > 0.9
        assert fit.p_values[0] < 1e-10
        assert fit.low[0] < fit.beta[0] < fit.high[0]
        assert fit.freedom == 37

    def test_collinear_criteria_have_a_large_inflation_factor(self) -> None:
        generator = numpy.random.default_rng(4)
        base = generator.normal(size=50)
        x = numpy.column_stack([base, base + 0.01 * generator.normal(size=50), generator.normal(size=50)])

        fit = OlsEstimator().fit(base + generator.normal(size=50), x)

        assert fit.vif[0] > 100
        assert fit.vif[1] > 100
        assert fit.vif[2] < 2

    def test_no_interval_without_degrees_of_freedom(self) -> None:
        fit = OlsEstimator().fit(numpy.array([1.0, 2.0, 4.0]), numpy.array([[1.0], [2.0], [3.0]]), absorbed=1)

        assert fit.freedom == 0
        assert numpy.isnan(fit.p_values).all()


class TestShapleyDecomposition:
    def test_the_shares_sum_to_the_r2_and_rank_the_planted_driver_first(self) -> None:
        generator = numpy.random.default_rng(5)
        x = generator.normal(size=(60, 3))
        y = 2.0 * x[:, 1] + 0.5 * x[:, 0] + generator.normal(size=60)

        shares = ShapleyDecomposition().importances(y, x)

        assert shares.sum() == pytest.approx(OlsEstimator().fit(y, x).r2)
        assert list(numpy.argsort(-shares)) == [1, 0, 2]

    def test_two_copies_of_a_driver_share_it_equally(self) -> None:
        generator = numpy.random.default_rng(6)
        driver = generator.normal(size=80)
        x = numpy.column_stack([driver, driver, generator.normal(size=80)])

        shares = ShapleyDecomposition().importances(driver + 0.5 * generator.normal(size=80), x)

        assert shares[0] == pytest.approx(shares[1])
        assert shares[0] > 10 * shares[2]

    def test_one_criterion_carries_the_whole_r2(self) -> None:
        x = numpy.arange(10.0)[:, None]

        assert ShapleyDecomposition().importances(2 * x[:, 0] + 1, x) == pytest.approx([1.0])


class TestFixedEffectsDemeaner:
    def test_a_balanced_panel_loses_its_row_and_column_means(self) -> None:
        generator = numpy.random.default_rng(7)
        grid = generator.normal(size=(4, 5))
        demeaner = FixedEffectsDemeaner()
        providers = demeaner.codes([f"p{row}" for row in range(4) for _ in range(5)])
        periods = demeaner.codes([f"t{column}" for _ in range(4) for column in range(5)])

        within = demeaner.demean(grid.reshape(-1, 1), [providers, periods])

        expected = grid - grid.mean(axis=1, keepdims=True) - grid.mean(axis=0, keepdims=True) + grid.mean()
        assert within[:, 0] == pytest.approx(expected.reshape(-1))

    def test_groups_are_numbered_in_their_order(self) -> None:
        assert FixedEffectsDemeaner().codes(["b", "a", "b", "c"]).tolist() == [0, 1, 0, 2]
