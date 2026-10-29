from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, Optional

# Third Party Imports.
import numpy
from numpy.typing import NDArray

# First Party Imports.
from analytics.compounding.data.risk_set import RiskSet
from analytics.compounding.data.risk_set_builder import RiskSetBuilder
from analytics.compounding.estimators.logit_estimator import LogitEstimator
from models.cloud.enums import CloudProvider
from models.compounding.results.scores.placebo_result import PlaceboResult


class PlaceboTest:
    """Refit the foundation hazard with random foundation sets of the same sizes.

    Attributes:
        builder (RiskSetBuilder): The risk set builder (it recomputes the foundation columns).
        estimator (LogitEstimator): The logit estimator.
        logger (Logger): The test logger.

    Notes:
        - Each random set draws, for every dependent category, as many categories as its real set, uniformly among
          the other categories kept. The rows and the controls are unchanged.
        - The p-value is the share of random sets whose foundation coefficient is at least the real one, counting the
          real set itself: (1 + at least as large) / (1 + draws).
    """

    def __init__(self, builder: RiskSetBuilder, estimator: LogitEstimator, logger: Optional[Logger] = None) -> None:
        """Initialize the test.

        Args:
            builder (RiskSetBuilder): The risk set builder.
            estimator (LogitEstimator): The logit estimator.
            logger (Optional[Logger]): The test logger.
        """
        self.builder = builder
        self.estimator = estimator
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def run(
        self,
        risk_set: RiskSet,
        sets: Dict[CloudProvider, Dict[int, NDArray[numpy.intp]]],
        categories: int,
        real: float,
        lag: int,
        draws: int,
        seed: int,
        provider: Optional[CloudProvider],
    ) -> PlaceboResult:
        """Run the placebo test of a hazard fit.

        Args:
            risk_set (RiskSet): The hazard risk set fitted.
            sets (Dict[CloudProvider, Dict[int, NDArray[numpy.intp]]]): The real foundation columns.
            categories (int): The number of categories kept.
            real (float): The foundation coefficient of the real fit.
            lag (int): The years the foundations must have been held.
            draws (int): The random sets.
            seed (int): The seed of the draws.
            provider (Optional[CloudProvider]): The provider fitted, `None` for the pooled fit.

        Returns:
            PlaceboResult: The coefficients of the random sets and the p-value.
        """
        generator = numpy.random.default_rng(seed)
        found = []
        for _ in range(draws):
            random_sets: Dict[CloudProvider, Dict[int, NDArray[numpy.intp]]] = {}
            for owner, columns in sets.items():
                random_sets[owner] = {}
                for column, foundations in columns.items():
                    pool = numpy.delete(numpy.arange(categories), column)
                    random_sets[owner][column] = generator.choice(pool, size=len(foundations), replace=False)
            fit = self.estimator.fit(self.builder.refill(risk_set, random_sets, lag).x, risk_set.y)
            if fit.converged:
                found.append(float(fit.beta[0]))
        p_value = (1 + sum(1 for draw in found if draw >= real)) / (1 + len(found)) if found else None
        self.logger.info("Placebo of %s: %d random sets, p = %s.", provider or "the pooled fit", len(found), p_value)
        return PlaceboResult(provider=provider, real=real, draws=found, p_value=p_value)
