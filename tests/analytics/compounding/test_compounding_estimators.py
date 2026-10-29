from __future__ import annotations

from typing import Tuple

import numpy
import pytest
from numpy.typing import NDArray

from analytics.compounding.estimators.curves.growth_curves import GrowthCurves
from analytics.compounding.estimators.curves.heaps_fitter import HeapsFitter
from analytics.compounding.estimators.curves.ordinary_least_squares import OrdinaryLeastSquares
from analytics.compounding.estimators.logit_estimator import LogitEstimator
from analytics.compounding.estimators.roc_scorer import RocScorer
from models.cloud.enums import CloudProvider


def synthetic_logit(rows: int, seed: int) -> Tuple[NDArray[numpy.float64], NDArray[numpy.float64]]:
    generator = numpy.random.default_rng(seed)
    x = generator.normal(size=(rows, 2))
    p = 1 / (1 + numpy.exp(-(-1.0 + 1.5 * x[:, 0] - 0.5 * x[:, 1])))
    y = (generator.random(rows) < p).astype(float)
    return x, y


def test_the_logit_recovers_known_coefficients() -> None:
    x, y = synthetic_logit(6000, 3)

    fit = LogitEstimator().fit(x, y)

    assert fit.converged
    assert fit.beta[0] == pytest.approx(1.5, abs=0.12)
    assert fit.beta[1] == pytest.approx(-0.5, abs=0.1)
    assert fit.intercept == pytest.approx(-1.0, abs=0.1)


def test_the_cluster_bootstrap_interval_covers_the_true_coefficient() -> None:
    x, y = synthetic_logit(3000, 5)
    clusters = numpy.arange(3000) // 15

    bounds = LogitEstimator().bootstrap(x, y, clusters, 60, 1)

    assert bounds[0][0] is not None
    assert bounds[0][1] is not None
    assert bounds[0][0] < 1.5 < bounds[0][1]


def test_a_logit_without_entries_does_not_converge() -> None:
    fit = LogitEstimator().fit(numpy.ones((5, 1)), numpy.zeros(5))

    assert not fit.converged


def test_the_auc_ranks_entries_above_non_entries() -> None:
    scorer = RocScorer()
    y = numpy.array([0.0, 0.0, 1.0, 1.0])

    assert scorer.auc(y, numpy.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert scorer.auc(y, numpy.array([0.9, 0.8, 0.2, 0.1])) == 0.0
    assert scorer.auc(numpy.zeros(3), numpy.zeros(3)) is None
    assert scorer.log_score(y, numpy.full(4, 0.5)) == pytest.approx(numpy.log(0.5))


def test_the_least_squares_interval_covers_the_slope() -> None:
    x = numpy.arange(30, dtype=float)
    y = 2.0 + 0.5 * x + numpy.random.default_rng(1).normal(scale=0.1, size=30)

    intercept, estimates, r2 = OrdinaryLeastSquares().fit(y, x.reshape(-1, 1), ["slope"]) or (0.0, [], 0.0)

    low, high = estimates[0].low, estimates[0].high
    assert low is not None
    assert high is not None
    assert low < 0.5 < high
    assert intercept == pytest.approx(2.0, abs=0.1)
    assert r2 > 0.99


def test_the_heaps_slope_is_recovered() -> None:
    points = [(float(size), float(3 * size**0.7)) for size in (5, 10, 20, 40, 80, 160)]

    fit = HeapsFitter(OrdinaryLeastSquares()).fit(CloudProvider.AWS, points)

    assert fit.slope is not None
    assert fit.slope.value == pytest.approx(0.7, abs=1e-6)


def test_the_heaps_law_needs_three_distinct_points() -> None:
    fit = HeapsFitter(OrdinaryLeastSquares()).fit(CloudProvider.AWS, [(5.0, 3.0), (5.0, 3.0), (6.0, 3.0)])

    assert fit.slope is None


def test_the_growth_curves_start_at_the_first_size_and_saturate() -> None:
    curves = GrowthCurves(10.0)
    t = numpy.array([0.0, 5.0, 200.0])

    assert curves.exponential(t, 2.0, 0.0)[1] == pytest.approx(20.0)
    assert curves.bass(t, 100.0, 0.03, 0.4)[0] == pytest.approx(10.0)
    assert curves.bass(t, 100.0, 0.03, 0.4)[2] == pytest.approx(110.0)
    assert curves.logistic(t, 50.0, 0.5, 5.0)[1] == pytest.approx(25.0)
