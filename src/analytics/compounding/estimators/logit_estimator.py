from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
import numpy
from numpy.typing import NDArray

# First Party Imports.
from analytics.compounding.estimators.logit_fit import LogitFit


class LogitEstimator:
    """Fit a logit of yearly entries by Newton iterations, with cluster bootstrap intervals.

    Attributes:
        PENALTY (ClassVar[float]): The ridge penalty on the standardized coefficients (it keeps the fit finite when an
            entry is perfectly predicted).
        ITERATIONS (ClassVar[int]): The most Newton iterations.
        TOLERANCE (ClassVar[float]): The largest change of a standardized coefficient at convergence.
        SEPARATION (ClassVar[float]): The standardized coefficient above which the fit is deemed separated.
        logger (Logger): The estimator logger.

    Notes:
        - The covariates are standardized for the iterations, and the coefficients returned in their own units.
        - The intervals are the 2.5 and 97.5 percentiles of the coefficients refitted on resampled clusters (the
          categories, so that the years of a category stay together). A resample that does not converge is dropped.
    """

    PENALTY: ClassVar[float] = 1e-3
    ITERATIONS: ClassVar[int] = 100
    TOLERANCE: ClassVar[float] = 1e-8
    SEPARATION: ClassVar[float] = 15.0

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the estimator.

        Args:
            logger (Optional[Logger]): The estimator logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _log_likelihood(
        self, design: NDArray[numpy.float64], y: NDArray[numpy.float64], beta: NDArray[numpy.float64]
    ) -> float:
        """Compute the log-likelihood of coefficients.

        Args:
            design (NDArray[numpy.float64]): The covariates with an intercept column.
            y (NDArray[numpy.float64]): The entries.
            beta (NDArray[numpy.float64]): The coefficients.

        Returns:
            float: The log-likelihood.
        """
        eta = design @ beta
        return float(numpy.sum(y * eta - numpy.logaddexp(0.0, eta)))

    def _newton(self, design: NDArray[numpy.float64], y: NDArray[numpy.float64]) -> Tuple[NDArray[numpy.float64], bool]:
        """Run the penalized Newton iterations.

        Args:
            design (NDArray[numpy.float64]): The standardized covariates with an intercept column.
            y (NDArray[numpy.float64]): The entries.

        Returns:
            Tuple[NDArray[numpy.float64], bool]: The coefficients and whether they converged.
        """
        width = design.shape[1]
        penalty = numpy.full(width, self.PENALTY)
        penalty[0] = 0.0
        beta = numpy.zeros(width)
        mean = float(numpy.clip(numpy.mean(y), 1e-6, 1 - 1e-6))
        beta[0] = numpy.log(mean / (1 - mean))
        for _ in range(self.ITERATIONS):
            p = 1.0 / (1.0 + numpy.exp(-(design @ beta)))
            gradient = design.T @ (y - p) - penalty * beta
            hessian = (design * (p * (1 - p))[:, None]).T @ design + numpy.diag(penalty)
            try:
                step = numpy.linalg.solve(hessian, gradient)
            except numpy.linalg.LinAlgError:
                return beta, False
            before = self._log_likelihood(design, y, beta) - 0.5 * float(numpy.sum(penalty * beta**2))
            scale = 1.0
            while scale > 1e-4:
                trial = beta + scale * step
                after = self._log_likelihood(design, y, trial) - 0.5 * float(numpy.sum(penalty * trial**2))
                if after >= before - 1e-12:
                    break
                scale /= 2
            beta = beta + scale * step
            if float(numpy.max(numpy.abs(scale * step))) < self.TOLERANCE:
                return beta, bool(numpy.all(numpy.abs(beta[1:]) < self.SEPARATION))
        return beta, False

    ############################
    # Publicly Exposed Methods #
    ############################

    def fit(self, x: NDArray[numpy.float64], y: NDArray[numpy.float64]) -> LogitFit:
        """Fit the logit.

        Args:
            x (NDArray[numpy.float64]): The covariates, one row per observation, without intercept.
            y (NDArray[numpy.float64]): The entries (0 or 1).

        Returns:
            LogitFit: The fit, not converged without entries, without non-entries or without rows.
        """
        width = x.shape[1]
        events = float(numpy.sum(y))
        if y.size == 0 or events == 0 or events == y.size:
            self.logger.warning("A logit cannot be fitted on %d rows with %d entries.", y.size, int(events))
            return LogitFit(intercept=0.0, beta=numpy.zeros(width), log_likelihood=0.0, converged=False)
        center = numpy.mean(x, axis=0)
        spread = numpy.std(x, axis=0)
        spread = numpy.where(spread > 1e-12, spread, 1.0)
        design = numpy.column_stack([numpy.ones(y.size), (x - center) / spread])
        standardized, converged = self._newton(design, y)
        beta = standardized[1:] / spread
        intercept = float(standardized[0] - numpy.sum(beta * center))
        log_likelihood = self._log_likelihood(design, y, standardized)
        if not converged:
            self.logger.warning("A logit on %d rows with %d entries did not converge.", y.size, int(events))
        return LogitFit(intercept=intercept, beta=beta, log_likelihood=log_likelihood, converged=converged)

    def predict(self, fit: LogitFit, x: NDArray[numpy.float64]) -> NDArray[numpy.float64]:
        """Predict the probability of an entry.

        Args:
            fit (LogitFit): The fit.
            x (NDArray[numpy.float64]): The covariates, in the columns of the fit.

        Returns:
            NDArray[numpy.float64]: The probability of each row.
        """
        return 1.0 / (1.0 + numpy.exp(-(fit.intercept + x @ fit.beta)))

    def bootstrap(
        self,
        x: NDArray[numpy.float64],
        y: NDArray[numpy.float64],
        clusters: NDArray[numpy.intp],
        draws: int,
        seed: int,
    ) -> List[Tuple[Optional[float], Optional[float]]]:
        """Compute the 95% interval of each coefficient by resampling clusters.

        Args:
            x (NDArray[numpy.float64]): The covariates.
            y (NDArray[numpy.float64]): The entries.
            clusters (NDArray[numpy.intp]): The cluster of each row.
            draws (int): The resamples.
            seed (int): The seed of the resampling.

        Returns:
            List[Tuple[Optional[float], Optional[float]]]: The bounds of each coefficient, `None` with fewer than 20
                converged resamples.
        """
        width = x.shape[1]
        if draws <= 0 or y.size == 0:
            return [(None, None)] * width
        names, rows = numpy.unique(clusters, return_inverse=True)
        members = [numpy.flatnonzero(rows == position) for position in range(len(names))]
        generator = numpy.random.default_rng(seed)
        found: List[NDArray[numpy.float64]] = []
        for _ in range(draws):
            picked = generator.integers(0, len(members), size=len(members))
            chosen = numpy.concatenate([members[position] for position in picked])
            refit = self.fit(x[chosen], y[chosen])
            if refit.converged:
                found.append(refit.beta)
        if len(found) < 20:
            self.logger.warning("Only %d of %d bootstrap resamples converged: no interval.", len(found), draws)
            return [(None, None)] * width
        matrix = numpy.array(found)
        low = numpy.percentile(matrix, 2.5, axis=0)
        high = numpy.percentile(matrix, 97.5, axis=0)
        self.logger.debug("%d of %d bootstrap resamples converged.", len(found), draws)
        return [(float(low[column]), float(high[column])) for column in range(width)]
