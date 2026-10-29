from __future__ import annotations

# Standard Library Imports.
import math
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
import numpy
from numpy.typing import NDArray

# First Party Imports.
from analytics.drivers.matrix.cluster_resampler import ClusterResampler
from analytics.drivers.regression.ols_estimator import OlsEstimator
from analytics.drivers.regression.ols_fit import OlsFit
from analytics.drivers.regression.shapley_decomposition import ShapleyDecomposition
from models.cloud.enums import CloudProvider
from models.drivers.enums import DriverWarningKind, ProviderMetric
from models.drivers.results.driver_coefficient import DriverCoefficient
from models.drivers.results.driver_warning import DriverWarning

type RegressionOutcome = Tuple[Optional[OlsFit], List[DriverCoefficient], List[DriverWarning]]


class DriverRegression:
    """Regress the target on the criteria and rank the criteria by their share of the explained variance.

    Attributes:
        COLLINEAR_VIF (ClassVar[float]): The variance inflation factor above which a criterion is called collinear.
        CRITERIA_PER_OBSERVATIONS (ClassVar[int]): The observations a criterion needs for a stable fit (about 10).
        MAX_IMPORTANCE_DRAWS (ClassVar[int]): The bootstrap resamples of the importances beyond 6 criteria.
        estimator (OlsEstimator): The least-squares fit.
        shapley (ShapleyDecomposition): The split of the R².
        resampler (ClusterResampler): The bootstrap resamples.
        logger (Logger): The regression logger.

    Notes:
        - The regression needs at least 3 observations more than criteria, else it is skipped with a warning (the
          correlations still answer).
        - Beyond `ShapleyDecomposition.MAX_CRITERIA` criteria, only those most correlated with the target are kept.
        - The interval of an importance comes from a bootstrap a provider at a time, like the correlations.
    """

    COLLINEAR_VIF: ClassVar[float] = 10.0
    CRITERIA_PER_OBSERVATIONS: ClassVar[int] = 10
    MAX_IMPORTANCE_DRAWS: ClassVar[int] = 200

    def __init__(
        self,
        estimator: Optional[OlsEstimator] = None,
        shapley: Optional[ShapleyDecomposition] = None,
        resampler: Optional[ClusterResampler] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the regression.

        Args:
            estimator (Optional[OlsEstimator]): The least-squares fit.
            shapley (Optional[ShapleyDecomposition]): The split of the R².
            resampler (Optional[ClusterResampler]): The bootstrap resamples.
            logger (Optional[Logger]): The regression logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.estimator = estimator if estimator else OlsEstimator(self.logger)
        self.shapley = shapley if shapley else ShapleyDecomposition(self.logger)
        self.resampler = resampler if resampler else ClusterResampler(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _strongest(self, y: NDArray[numpy.float64], x: NDArray[numpy.float64]) -> List[int]:
        """Keep the criteria most correlated with the target, at most what the decomposition handles.

        Args:
            y (NDArray[numpy.float64]): The target.
            x (NDArray[numpy.float64]): The criteria, one column each.

        Returns:
            List[int]: The columns kept, in their order.
        """
        limit = self.shapley.MAX_CRITERIA
        if x.shape[1] <= limit:
            self.logger.debug("%d criteria within the limit of %d: all kept for the importances.", x.shape[1], limit)
            return list(range(x.shape[1]))
        self.logger.warning(
            "%d criteria exceed the limit of %d: only the most correlated ones get an importance.", x.shape[1], limit
        )
        with numpy.errstate(divide="ignore", invalid="ignore"):
            correlations = numpy.atleast_2d(numpy.corrcoef(numpy.column_stack([y, x]), rowvar=False))
        strength = numpy.nan_to_num(numpy.abs(correlations[0, 1:]))
        return sorted(int(column) for column in numpy.argsort(-strength)[:limit])

    def _intervals(
        self,
        y: NDArray[numpy.float64],
        x: NDArray[numpy.float64],
        providers: List[CloudProvider],
        bootstrap: int,
        seed: int,
    ) -> Tuple[NDArray[numpy.float64], NDArray[numpy.float64]]:
        """Get the 95% bootstrap intervals of the importances.

        Args:
            y (NDArray[numpy.float64]): The target.
            x (NDArray[numpy.float64]): The criteria, one column each.
            providers (List[CloudProvider]): The provider of each observation.
            bootstrap (int): The resamples asked.
            seed (int): The seed of the resampling.

        Returns:
            Tuple[NDArray[numpy.float64], NDArray[numpy.float64]]: The 2.5% and 97.5% percentiles (`NaN` without
                enough resamples).
        """
        count = x.shape[1]
        draws = bootstrap if count <= 6 else min(bootstrap, self.MAX_IMPORTANCE_DRAWS)
        found = [
            self.shapley.importances(y[rows], x[rows])
            for rows in self.resampler.samples(providers, draws, seed)
            if len(set(rows.tolist())) >= count + 2
        ]
        if len(found) < 20:
            self.logger.warning(
                "Only %d of %d importance draws hold enough providers: no importance interval.", len(found), draws
            )
            return numpy.full(count, numpy.nan), numpy.full(count, numpy.nan)
        low, high = numpy.percentile(numpy.vstack(found), [2.5, 97.5], axis=0)
        self.logger.debug("Importance intervals of %d criteria from %d draws.", count, len(found))
        return numpy.asarray(low, dtype=numpy.float64), numpy.asarray(high, dtype=numpy.float64)

    ############################
    # Publicly Exposed Methods #
    ############################

    def regress(
        self,
        y: NDArray[numpy.float64],
        x: NDArray[numpy.float64],
        criteria: List[ProviderMetric],
        providers: List[CloudProvider],
        bootstrap: int,
        seed: int,
        absorbed: int = 0,
    ) -> RegressionOutcome:
        """Regress complete observations and rank the criteria.

        Args:
            y (NDArray[numpy.float64]): The target of each observation.
            x (NDArray[numpy.float64]): The criteria of each observation, one column each.
            criteria (List[ProviderMetric]): The criterion of each column.
            providers (List[CloudProvider]): The provider of each observation.
            bootstrap (int): The bootstrap resamples (0 for no interval).
            seed (int): The seed of the resampling.
            absorbed (int): The degrees of freedom already spent (fixed effects).

        Returns:
            RegressionOutcome: The fit (`None` when skipped), the coefficients (the most important criterion first)
                and the warnings.
        """
        warnings: List[DriverWarning] = []
        observations = len(y)
        varying = [
            column for column in range(x.shape[1]) if observations > 1 and float(numpy.std(x[:, column])) > 1e-12
        ]
        if len(varying) < x.shape[1]:
            constant = [criteria[column] for column in range(x.shape[1]) if column not in varying]
            self.logger.warning("%d criteria are constant over the observations.", len(constant))
            warnings.append(
                DriverWarning(
                    kind=DriverWarningKind.CONSTANT,
                    message="Constant over the observations, left out of the regression: "
                    + ", ".join(criterion.value for criterion in constant)
                    + ".",
                    subjects=constant,
                )
            )
            criteria, x = [criteria[column] for column in varying], x[:, varying]
        if not criteria:
            return None, [], warnings
        columns = self._strongest(y, x)
        if len(columns) < len(criteria):
            left_out = [criteria[column] for column in range(len(criteria)) if column not in columns]
            self.logger.warning("Only the %d strongest criteria are regressed.", len(columns))
            warnings.append(
                DriverWarning(
                    kind=DriverWarningKind.TOO_MANY_CRITERIA,
                    message=f"Only the {len(columns)} criteria most correlated with the target are regressed, not: "
                    + ", ".join(criterion.value for criterion in left_out)
                    + ".",
                    subjects=left_out,
                )
            )
        kept = [criteria[column] for column in columns]
        x = x[:, columns]
        if observations < len(kept) + 3 + absorbed:
            self.logger.warning(
                "%d observations cannot fit %d criteria: the regression is skipped.", observations, len(kept)
            )
            warnings.append(
                DriverWarning(
                    kind=DriverWarningKind.REGRESSION_SKIPPED,
                    message=f"{observations} observations cannot fit {len(kept)} criteria: the regression is "
                    "skipped, only the correlations answer.",
                    subjects=kept,
                )
            )
            return None, [], warnings
        if observations < self.CRITERIA_PER_OBSERVATIONS * len(kept):
            warnings.append(
                DriverWarning(
                    kind=DriverWarningKind.UNSTABLE,
                    message=f"{observations} observations for {len(kept)} criteria: about "
                    f"{self.CRITERIA_PER_OBSERVATIONS} per criterion are needed for stable coefficients.",
                    subjects=kept,
                )
            )
        fit = self.estimator.fit(y, x, absorbed)
        collinear = [criterion for criterion, vif in zip(kept, fit.vif, strict=True) if vif > self.COLLINEAR_VIF]
        if collinear:
            warnings.append(
                DriverWarning(
                    kind=DriverWarningKind.COLLINEAR,
                    message="Collinear criteria (they move together): "
                    + ", ".join(criterion.value for criterion in collinear)
                    + ".",
                    subjects=collinear,
                )
            )
        shares = self.shapley.importances(y, x)
        lows, highs = self._intervals(y, x, providers, bootstrap, seed)
        coefficients = [
            DriverCoefficient(
                criterion=criterion,
                beta=float(fit.beta[index]),
                low=float(fit.low[index]) if math.isfinite(fit.low[index]) else None,
                high=float(fit.high[index]) if math.isfinite(fit.high[index]) else None,
                p_value=float(fit.p_values[index]) if math.isfinite(fit.p_values[index]) else None,
                importance=float(shares[index]),
                importance_low=float(lows[index]) if math.isfinite(lows[index]) else None,
                importance_high=float(highs[index]) if math.isfinite(highs[index]) else None,
            )
            for index, criterion in enumerate(kept)
        ]
        coefficients.sort(key=lambda coefficient: -coefficient.importance)
        self.logger.info("Regressed %d observations on %d criteria: R2 %.3f.", observations, len(kept), fit.r2)
        return fit, coefficients, warnings
