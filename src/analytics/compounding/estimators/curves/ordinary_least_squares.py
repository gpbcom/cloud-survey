from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# Third Party Imports.
import numpy
from numpy.typing import NDArray
from scipy.stats import t as student

# First Party Imports.
from models.compounding.results.fits.estimate import Estimate


class OrdinaryLeastSquares:
    """Fit a least-squares line or plane, with Student intervals.

    Attributes:
        logger (Logger): The estimator logger.

    Notes:
        The intervals assume independent residuals. Yearly series are autocorrelated, so they are optimistic: the
        results document says so.
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

    def fit(
        self, y: NDArray[numpy.float64], x: NDArray[numpy.float64], names: List[str]
    ) -> Optional[Tuple[float, List[Estimate], float]]:
        """Fit the target on the covariates with an intercept.

        Args:
            y (NDArray[numpy.float64]): The target.
            x (NDArray[numpy.float64]): The covariates, one column each, without intercept.
            names (List[str]): The name of each covariate.

        Returns:
            Optional[Tuple[float, List[Estimate], float]]: The intercept, the coefficients with their 95% intervals
                and the share of the variance explained, `None` without degrees of freedom.
        """
        design = numpy.column_stack([numpy.ones(y.size), x])
        freedom = y.size - design.shape[1]
        if freedom < 1:
            self.logger.debug("No least-squares fit of %d points on %d covariates.", y.size, len(names))
            return None
        beta, *_ = numpy.linalg.lstsq(design, y, rcond=None)
        residuals = y - design @ beta
        variance = float(residuals @ residuals) / freedom
        try:
            covariance = variance * numpy.linalg.inv(design.T @ design)
        except numpy.linalg.LinAlgError:
            self.logger.warning("The least-squares covariates are collinear.")
            return None
        quantile = float(student.ppf(0.975, freedom))
        errors = numpy.sqrt(numpy.clip(numpy.diag(covariance), 0.0, None))
        estimates = [
            Estimate(
                name=name,
                value=float(beta[column + 1]),
                low=float(beta[column + 1] - quantile * errors[column + 1]) if errors[column + 1] > 0 else None,
                high=float(beta[column + 1] + quantile * errors[column + 1]) if errors[column + 1] > 0 else None,
            )
            for column, name in enumerate(names)
        ]
        total = float(numpy.sum((y - numpy.mean(y)) ** 2))
        r2 = 1 - float(residuals @ residuals) / total if total > 0 else 0.0
        return float(beta[0]), estimates, r2
