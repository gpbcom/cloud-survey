from __future__ import annotations

# Standard Library Imports.
import math
from logging import Logger, getLogger
from typing import ClassVar, List, Optional

# Third Party Imports.
import numpy
from numpy.typing import NDArray


class ShapleyDecomposition:
    """Split the R² of a regression between its criteria (the Shapley, or LMG, decomposition).

    Attributes:
        MAX_CRITERIA (ClassVar[int]): The most criteria decomposed (the subsets double with each one).
        logger (Logger): The decomposition logger.

    Notes:
        - The share of a criterion is the gain of R² it brings when it joins a model, averaged over every order in which
          the criteria can enter. The shares are never negative, are fair to correlated criteria, and sum to the R².
        - The R² of every subset comes from the correlation matrix (`r' R⁻¹ r`), without refitting.
    """

    MAX_CRITERIA: ClassVar[int] = 10

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the decomposition.

        Args:
            logger (Optional[Logger]): The decomposition logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _subset_r2(self, correlations: NDArray[numpy.float64], targets: NDArray[numpy.float64]) -> List[float]:
        """Compute the R² of every subset of the criteria.

        Args:
            correlations (NDArray[numpy.float64]): The correlations between the criteria.
            targets (NDArray[numpy.float64]): The correlation of each criterion with the target.

        Returns:
            List[float]: The R² of each subset, indexed by its bit mask (bit `j` for criterion `j`).
        """
        count = len(targets)
        r2 = [0.0] * (1 << count)
        for mask in range(1, 1 << count):
            members = [column for column in range(count) if mask >> column & 1]
            r = targets[members]
            r2[mask] = max(0.0, min(1.0, float(r @ numpy.linalg.pinv(correlations[numpy.ix_(members, members)]) @ r)))
        return r2

    ############################
    # Publicly Exposed Methods #
    ############################

    def importances(self, y: NDArray[numpy.float64], x: NDArray[numpy.float64]) -> NDArray[numpy.float64]:
        """Split the R² of complete observations between the criteria.

        Args:
            y (NDArray[numpy.float64]): The target of each observation.
            x (NDArray[numpy.float64]): The criteria of each observation, one column each (at most `MAX_CRITERIA`).

        Returns:
            NDArray[numpy.float64]: The share of the R² of each criterion (0 for a constant one).
        """
        count = x.shape[1]
        with numpy.errstate(divide="ignore", invalid="ignore"):
            matrix = numpy.nan_to_num(numpy.corrcoef(numpy.column_stack([y, x]), rowvar=False))
        matrix = numpy.atleast_2d(matrix)
        r2 = self._subset_r2(matrix[1:, 1:], matrix[0, 1:])
        weights = [
            math.factorial(size) * math.factorial(count - size - 1) / math.factorial(count) for size in range(count)
        ]
        shares = numpy.zeros(count, dtype=numpy.float64)
        for column in range(count):
            bit = 1 << column
            shares[column] = sum(
                weights[mask.bit_count()] * (r2[mask + bit] - r2[mask]) for mask in range(1 << count) if not mask & bit
            )
        self.logger.debug("Decomposed an R2 of %.3f between %d criteria.", r2[-1], count)
        return numpy.clip(shares, 0.0, None)
