from __future__ import annotations

# Standard Library Imports.
import itertools
import math
from logging import Logger, getLogger
from typing import ClassVar, Optional

# Third Party Imports.
import numpy
from numpy.typing import NDArray
from scipy import stats


class SpearmanCorrelation:
    """Compute rank correlations, plain or partial, and their p-values.

    Attributes:
        EXACT_LIMIT (ClassVar[int]): The most observations whose p-value is computed exactly, over every permutation.
        logger (Logger): The correlation logger.

    Notes:
        - The Spearman correlation is the Pearson correlation of the ranks (ties share their average rank). It is
          robust to the outliers and to the size gaps between the providers.
        - The partial correlation holds the controls constant: the ranks of both measures are regressed on the ranks
          of the controls, and the residuals are correlated.
        - The p-value comes from the t statistic `rho * sqrt(df / (1 - rho^2))` with `n - 2 - controls` degrees of
          freedom. Up to `EXACT_LIMIT` observations, where that approximation fails (3 providers perfectly ranked
          would get 0), the p-value is exact: the share of the orders of the target correlating at least as much.
    """

    EXACT_LIMIT: ClassVar[int] = 7

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the correlation.

        Args:
            logger (Optional[Logger]): The correlation logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _ranks(self, values: NDArray[numpy.float64]) -> NDArray[numpy.float64]:
        """Rank values, ties sharing their average rank.

        Args:
            values (NDArray[numpy.float64]): The values (one column, or one column per measure).

        Returns:
            NDArray[numpy.float64]: Their ranks, column by column.
        """
        return numpy.asarray(stats.rankdata(values, axis=0), dtype=numpy.float64)

    def _pearson(self, a: NDArray[numpy.float64], b: NDArray[numpy.float64]) -> Optional[float]:
        """Compute the Pearson correlation of two series.

        Args:
            a (NDArray[numpy.float64]): The first series.
            b (NDArray[numpy.float64]): The second series.

        Returns:
            Optional[float]: The correlation, `None` with fewer than 3 values or a constant series.
        """
        if len(a) < 3:
            return None
        da, db = a - a.mean(), b - b.mean()
        spread = math.sqrt(float(da @ da) * float(db @ db))
        if spread <= 1e-12:
            return None
        return max(-1.0, min(1.0, float(da @ db) / spread))

    def _residuals(self, values: NDArray[numpy.float64], controls: NDArray[numpy.float64]) -> NDArray[numpy.float64]:
        """Remove from a series what the controls explain linearly.

        Args:
            values (NDArray[numpy.float64]): The series.
            controls (NDArray[numpy.float64]): The controls, one column each.

        Returns:
            NDArray[numpy.float64]: The residuals of the regression of the series on the controls and a constant.
        """
        design = numpy.column_stack([numpy.ones(len(values)), controls])
        coefficients = numpy.linalg.lstsq(design, values, rcond=None)[0]
        return numpy.asarray(values - design @ coefficients, dtype=numpy.float64)

    def _exact_p_value(self, x: NDArray[numpy.float64], y: NDArray[numpy.float64], rho: float) -> float:
        """Compute the exact two-sided p-value of a correlation, over every order of the target.

        Args:
            x (NDArray[numpy.float64]): The criterion.
            y (NDArray[numpy.float64]): The target.
            rho (float): Their correlation.

        Returns:
            float: The share of the orders whose correlation is at least as strong.
        """
        ranks_x, ranks_y = self._ranks(x), self._ranks(y)
        hits = total = 0
        for order in itertools.permutations(range(len(y))):
            permuted = self._pearson(ranks_x, ranks_y[list(order)])
            total += 1
            hits += permuted is not None and abs(permuted) >= abs(rho) - 1e-12
        self.logger.debug("Exact p-value of rho %.3f: %d of %d permutations as extreme.", rho, hits, total)
        return hits / total if total else 1.0

    ############################
    # Publicly Exposed Methods #
    ############################

    def rho(self, x: NDArray[numpy.float64], y: NDArray[numpy.float64]) -> Optional[float]:
        """Compute the Spearman correlation of two complete series.

        Args:
            x (NDArray[numpy.float64]): The criterion.
            y (NDArray[numpy.float64]): The target.

        Returns:
            Optional[float]: The correlation, `None` with fewer than 3 values or a constant series.
        """
        return self._pearson(self._ranks(x), self._ranks(y))

    def partial(
        self, x: NDArray[numpy.float64], y: NDArray[numpy.float64], controls: NDArray[numpy.float64]
    ) -> Optional[float]:
        """Compute the Spearman correlation of two complete series once the controls are held constant.

        Args:
            x (NDArray[numpy.float64]): The criterion.
            y (NDArray[numpy.float64]): The target.
            controls (NDArray[numpy.float64]): The controls, one column each.

        Returns:
            Optional[float]: The partial correlation, `None` without enough values left.
        """
        if len(x) < controls.shape[1] + 3:
            self.logger.warning(
                "Too few observations (%d) for a partial correlation with %d controls.", len(x), controls.shape[1]
            )
            return None
        self.logger.debug("Partial correlation of %d observations with %d controls.", len(x), controls.shape[1])
        ranked = self._ranks(controls)
        return self._pearson(self._residuals(self._ranks(x), ranked), self._residuals(self._ranks(y), ranked))

    def p_value(self, rho: float, observations: int, controls: int = 0) -> float:
        """Compute the two-sided p-value of a correlation.

        Args:
            rho (float): The correlation.
            observations (int): The observations it is computed on.
            controls (int): The controls held constant.

        Returns:
            float: The p-value, 1 without degrees of freedom left.
        """
        freedom = observations - 2 - controls
        if freedom < 1:
            self.logger.warning(
                "No degree of freedom left (%d observations, %d controls): p-value 1.", observations, controls
            )
            return 1.0
        if abs(rho) >= 1.0:
            self.logger.debug("Perfect correlation over %d observations: p-value 0.", observations)
            return 0.0
        statistic = rho * math.sqrt(freedom / (1.0 - rho * rho))
        return min(1.0, max(0.0, float(2.0 * stats.t.sf(abs(statistic), freedom))))

    def significance(self, x: NDArray[numpy.float64], y: NDArray[numpy.float64], rho: float) -> float:
        """Compute the two-sided p-value of a correlation, exactly for few observations.

        Args:
            x (NDArray[numpy.float64]): The criterion.
            y (NDArray[numpy.float64]): The target.
            rho (float): Their correlation.

        Returns:
            float: The p-value.
        """
        if len(x) <= self.EXACT_LIMIT:
            self.logger.debug("%d observations: exact permutation p-value.", len(x))
            return self._exact_p_value(x, y, rho)
        return self.p_value(rho, len(x))
