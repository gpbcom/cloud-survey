from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence

# Third Party Imports.
import numpy
from numpy.typing import NDArray


class FixedEffectsDemeaner:
    """Remove the provider and quarter effects from panel observations (the within transformation).

    Attributes:
        ITERATIONS (ClassVar[int]): The most alternating passes.
        TOLERANCE (ClassVar[float]): The largest change of a pass at which the passes stop.
        logger (Logger): The demeaner logger.

    Notes:
        Each pass subtracts the mean of every provider, then of every quarter. On an unbalanced panel (providers
        measured over different quarters) the passes converge to the two-way fixed effects residuals, as many as the
        groups need.
    """

    ITERATIONS: ClassVar[int] = 200
    TOLERANCE: ClassVar[float] = 1e-10

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the demeaner.

        Args:
            logger (Optional[Logger]): The demeaner logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _subtract_means(self, values: NDArray[numpy.float64], codes: NDArray[numpy.intp]) -> NDArray[numpy.float64]:
        """Subtract the mean of each group, column by column.

        Args:
            values (NDArray[numpy.float64]): The observations, one column per variable.
            codes (NDArray[numpy.intp]): The group of each observation, numbered from 0.

        Returns:
            NDArray[numpy.float64]: The observations minus their group mean.
        """
        groups = int(codes.max()) + 1
        sums = numpy.zeros((groups, values.shape[1]), dtype=numpy.float64)
        numpy.add.at(sums, codes, values)
        counts = numpy.bincount(codes, minlength=groups).astype(numpy.float64)
        return numpy.asarray(values - (sums / counts[:, None])[codes], dtype=numpy.float64)

    ############################
    # Publicly Exposed Methods #
    ############################

    def codes(self, labels: Sequence[str]) -> NDArray[numpy.intp]:
        """Number the groups of the observations.

        Args:
            labels (Sequence[str]): The group of each observation (a provider, a quarter).

        Returns:
            NDArray[numpy.intp]: The number of the group of each observation.
        """
        numbers = {label: index for index, label in enumerate(dict.fromkeys(labels))}
        return numpy.asarray([numbers[label] for label in labels], dtype=numpy.intp)

    def demean(self, values: NDArray[numpy.float64], groupings: List[NDArray[numpy.intp]]) -> NDArray[numpy.float64]:
        """Remove the effects of every grouping.

        Args:
            values (NDArray[numpy.float64]): The complete observations, one column per variable.
            groupings (List[NDArray[numpy.intp]]): The group numbers of each grouping (the providers, the quarters).

        Returns:
            NDArray[numpy.float64]: The observations without the effects.
        """
        if not len(values) or not groupings:
            return values
        current = values
        for iteration in range(self.ITERATIONS):
            previous = current
            for codes in groupings:
                current = self._subtract_means(current, codes)
            if float(numpy.abs(current - previous).max(initial=0.0)) < self.TOLERANCE:
                self.logger.debug("Fixed effects removed in %d passes.", iteration + 1)
                return current
        self.logger.warning("The fixed effects did not converge in %d passes.", self.ITERATIONS)
        return current
