from __future__ import annotations

# Standard Library Imports.
import math
from logging import Logger, getLogger
from typing import Optional

# Third Party Imports.
import numpy
from numpy.typing import NDArray
from scipy import stats

# First Party Imports.
from analytics.drivers.regression.ols_fit import OlsFit


class OlsEstimator:
    """Fit the standardized target on the standardized criteria by ordinary least squares.

    Attributes:
        logger (Logger): The estimator logger.

    Notes:
        - Every variable is centred and divided by its standard deviation, so a coefficient reads "standard deviations
          of the target per standard deviation of the criterion" and the coefficients are comparable.
        - The leave-one-out R² comes from the PRESS residuals `e / (1 - h)` (`h` the leverage), without refitting.
        - `absorbed` counts the degrees of freedom already spent elsewhere (the fixed effects of a panel).
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the estimator.

        Args:
            logger (Optional[Logger]): The estimator logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def standardize(self, values: NDArray[numpy.float64]) -> NDArray[numpy.float64]:
        """Centre values and divide them by their standard deviation, column by column.

        Args:
            values (NDArray[numpy.float64]): The values (one column, or one column per variable).

        Returns:
            NDArray[numpy.float64]: The standardized values, 0 for a constant column.
        """
        centred = values - values.mean(axis=0)
        spread = values.std(axis=0, ddof=1) if len(values) > 1 else numpy.zeros_like(values[:1])
        return numpy.asarray(numpy.divide(centred, spread, out=numpy.zeros_like(centred), where=spread > 1e-12))

    def fit(self, y: NDArray[numpy.float64], x: NDArray[numpy.float64], absorbed: int = 0) -> OlsFit:
        """Fit complete observations.

        Args:
            y (NDArray[numpy.float64]): The target of each observation.
            x (NDArray[numpy.float64]): The criteria of each observation, one column each.
            absorbed (int): The degrees of freedom already spent (fixed effects).

        Returns:
            OlsFit: The coefficients, their intervals and p-values, the R² and the leave-one-out R².
        """
        observations, count = x.shape
        ys, xs = self.standardize(y), self.standardize(x)
        gram = numpy.linalg.pinv(xs.T @ xs)
        beta = gram @ xs.T @ ys
        residuals = ys - xs @ beta
        total = float(ys @ ys)
        r2 = 1.0 - float(residuals @ residuals) / total if total > 1e-12 else 0.0
        freedom = observations - count - 1 - absorbed
        nan = numpy.full(count, numpy.nan)
        low, high, p_values = nan.copy(), nan.copy(), nan.copy()
        if freedom >= 1:
            variance = float(residuals @ residuals) / freedom
            errors = numpy.sqrt(numpy.clip(numpy.diag(gram) * variance, 0.0, None))
            margin = float(stats.t.ppf(0.975, freedom)) * errors
            low, high = beta - margin, beta + margin
            statistics = numpy.divide(beta, errors, out=numpy.full(count, numpy.nan), where=errors > 1e-12)
            p_values = numpy.clip(2.0 * stats.t.sf(numpy.abs(statistics), freedom), 0.0, 1.0)
        leverage = numpy.einsum("ij,jk,ik->i", xs, gram, xs) + 1.0 / observations
        loo_r2: Optional[float] = None
        if total > 1e-12 and bool((leverage < 1.0 - 1e-9).all()):
            press = float(((residuals / (1.0 - leverage)) ** 2).sum())
            loo_r2 = 1.0 - press / total
        with numpy.errstate(divide="ignore", invalid="ignore"):
            correlation = numpy.corrcoef(xs, rowvar=False) if count > 1 else numpy.ones((1, 1))
        vif = numpy.diag(numpy.linalg.pinv(numpy.atleast_2d(numpy.nan_to_num(correlation))))
        self.logger.debug(
            "OLS of %d observations on %d criteria: R2 %.3f, LOO R2 %s.",
            observations,
            count,
            r2,
            "n/a" if loo_r2 is None else f"{loo_r2:.3f}",
        )
        return OlsFit(
            beta=numpy.asarray(beta, dtype=numpy.float64),
            low=numpy.asarray(low, dtype=numpy.float64),
            high=numpy.asarray(high, dtype=numpy.float64),
            p_values=numpy.asarray(p_values, dtype=numpy.float64),
            r2=max(0.0, min(1.0, r2)) if math.isfinite(r2) else 0.0,
            loo_r2=loo_r2,
            vif=numpy.asarray(vif, dtype=numpy.float64),
            observations=observations,
            freedom=freedom,
        )
