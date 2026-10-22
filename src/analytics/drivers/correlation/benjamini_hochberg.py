from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional

# Third Party Imports.
import numpy


class BenjaminiHochberg:
    """Adjust the p-values of tests run together for the false discovery rate (Benjamini-Hochberg).

    Attributes:
        logger (Logger): The adjustment logger.

    Notes:
        With `m` tests sorted by increasing p-value, the q-value of the `i`-th is the smallest `p(j) × m / j` over
        `j ≥ i`, capped at 1. A q-value is never below its p-value, and the order of the tests is kept.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the adjustment.

        Args:
            logger (Optional[Logger]): The adjustment logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def q_values(self, p_values: List[float]) -> List[float]:
        """Compute the q-values of p-values tested together.

        Args:
            p_values (List[float]): The p-values, from 0 to 1.

        Returns:
            List[float]: The q-value of each, in the same order.
        """
        if not p_values:
            return []
        p = numpy.clip(numpy.asarray(p_values, dtype=numpy.float64), 0.0, 1.0)
        count = len(p)
        order = numpy.argsort(p)
        scaled = p[order] * count / numpy.arange(1, count + 1)
        adjusted = numpy.minimum.accumulate(scaled[::-1])[::-1]
        q = numpy.empty(count, dtype=numpy.float64)
        q[order] = numpy.clip(numpy.maximum(adjusted, p[order]), 0.0, 1.0)
        self.logger.debug("Adjusted %d p-values (smallest q-value %.3g).", count, float(q.min()))
        return [float(value) for value in q]
