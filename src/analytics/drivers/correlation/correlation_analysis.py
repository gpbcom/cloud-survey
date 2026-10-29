from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
import numpy
from numpy.typing import NDArray

# First Party Imports.
from analytics.drivers.correlation.benjamini_hochberg import BenjaminiHochberg
from analytics.drivers.correlation.spearman_correlation import SpearmanCorrelation
from analytics.drivers.matrix.cluster_resampler import ClusterResampler
from analytics.drivers.matrix.driver_matrix import DriverMatrix
from models.drivers.enums import DriverWarningKind
from models.drivers.results.correlation_cell import CorrelationCell
from models.drivers.results.driver_warning import DriverWarning


class CorrelationAnalysis:
    """Correlate each criterion with the target: Spearman, bootstrap interval, q-value and partial correlation.

    Attributes:
        MIN_PROVIDERS (ClassVar[int]): The fewest providers a bootstrap interval is drawn from (fewer give a
            degenerate interval).
        spearman (SpearmanCorrelation): The rank correlations.
        adjustment (BenjaminiHochberg): The false discovery rate adjustment of the criteria tested together.
        resampler (ClusterResampler): The bootstrap resamples.
        logger (Logger): The analysis logger.

    Notes:
        Each criterion uses every observation holding both it and the target (pairwise complete), so a criterion
        measured for few providers does not shrink the others. A criterion with fewer than 3 such observations, or
        constant over them, is reported in the warnings and left out.
    """

    MIN_PROVIDERS: ClassVar[int] = 3

    def __init__(
        self,
        spearman: Optional[SpearmanCorrelation] = None,
        adjustment: Optional[BenjaminiHochberg] = None,
        resampler: Optional[ClusterResampler] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the analysis.

        Args:
            spearman (Optional[SpearmanCorrelation]): The rank correlations.
            adjustment (Optional[BenjaminiHochberg]): The false discovery rate adjustment.
            resampler (Optional[ClusterResampler]): The bootstrap resamples.
            logger (Optional[Logger]): The analysis logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.spearman = spearman if spearman else SpearmanCorrelation(self.logger)
        self.adjustment = adjustment if adjustment else BenjaminiHochberg(self.logger)
        self.resampler = resampler if resampler else ClusterResampler(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _interval(
        self, x: NDArray[numpy.float64], y: NDArray[numpy.float64], samples: List[NDArray[numpy.intp]]
    ) -> Tuple[Optional[float], Optional[float]]:
        """Get the 95% bootstrap interval of a correlation.

        Args:
            x (NDArray[numpy.float64]): The criterion, complete.
            y (NDArray[numpy.float64]): The target, complete.
            samples (List[NDArray[numpy.intp]]): The resamples of the observations.

        Returns:
            Tuple[Optional[float], Optional[float]]: The 2.5% and 97.5% percentiles, `None` without enough resamples.
        """
        draws = [rho for rows in samples if (rho := self.spearman.rho(x[rows], y[rows])) is not None]
        if len(draws) < 20:
            self.logger.warning(
                "Only %d of %d bootstrap draws give a correlation: no interval.", len(draws), len(samples)
            )
            return None, None
        low, high = numpy.percentile(draws, [2.5, 97.5])
        self.logger.debug("Bootstrap interval from %d draws: %.3f to %.3f.", len(draws), low, high)
        return float(low), float(high)

    ############################
    # Publicly Exposed Methods #
    ############################

    def analyse(
        self, matrix: DriverMatrix, bootstrap: int, seed: int
    ) -> Tuple[List[CorrelationCell], List[DriverWarning]]:
        """Correlate each criterion with the target.

        Args:
            matrix (DriverMatrix): The observations.
            bootstrap (int): The bootstrap resamples (0 for no interval).
            seed (int): The seed of the resampling.

        Returns:
            Tuple[List[CorrelationCell], List[DriverWarning]]: The correlations, the strongest first, and the
                warnings.
        """
        warnings: List[DriverWarning] = []
        found: List[Tuple[int, float, Optional[float], Optional[float], float, Optional[float], int]] = []
        finite_y = numpy.isfinite(matrix.y)
        finite_z = numpy.isfinite(matrix.z).all(axis=1)
        for column, criterion in enumerate(matrix.criteria):
            rows = numpy.flatnonzero(finite_y & numpy.isfinite(matrix.x[:, column]))
            x, y = matrix.x[rows, column], matrix.y[rows]
            rho = self.spearman.rho(x, y)
            if rho is None:
                self.logger.warning(
                    "%s cannot be correlated with %s (%d observations).", criterion, matrix.target, len(rows)
                )
                warnings.append(
                    DriverWarning(
                        kind=DriverWarningKind.UNCORRELATABLE,
                        message=f"{criterion.value}: fewer than 3 observations with the target, or constant.",
                        subjects=[criterion],
                    )
                )
                continue
            providers = [matrix.providers[row] for row in rows]
            draws = bootstrap if len(set(providers)) >= self.MIN_PROVIDERS else 0
            samples = self.resampler.samples(providers, draws, seed)
            low, high = self._interval(x, y, samples)
            partial: Optional[float] = None
            if matrix.controls:
                kept = numpy.flatnonzero(finite_y & numpy.isfinite(matrix.x[:, column]) & finite_z)
                partial = self.spearman.partial(matrix.x[kept, column], matrix.y[kept], matrix.z[kept])
            found.append((column, rho, low, high, self.spearman.significance(x, y, rho), partial, len(rows)))
        q_values = self.adjustment.q_values([p_value for _, _, _, _, p_value, _, _ in found])
        cells = [
            CorrelationCell(
                criterion=matrix.criteria[column],
                rho=rho,
                low=low,
                high=high,
                p_value=p_value,
                q_value=q_value,
                partial=partial,
                observations=observations,
            )
            for (column, rho, low, high, p_value, partial, observations), q_value in zip(found, q_values, strict=True)
        ]
        cells.sort(key=lambda cell: -abs(cell.rho))
        self.logger.info("Correlated %d criteria with %s.", len(cells), matrix.target)
        return cells, warnings
