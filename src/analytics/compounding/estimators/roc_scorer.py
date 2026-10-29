from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Optional

# Third Party Imports.
import numpy
from numpy.typing import NDArray
from scipy.stats import rankdata


class RocScorer:
    """Score predicted entry probabilities against the entries observed.

    Attributes:
        logger (Logger): The scorer logger.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the scorer.

        Args:
            logger (Optional[Logger]): The scorer logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def auc(self, y: NDArray[numpy.float64], p: NDArray[numpy.float64]) -> Optional[float]:
        """Compute the area under the ROC curve (the chance an entry is ranked above a non-entry).

        Args:
            y (NDArray[numpy.float64]): The entries.
            p (NDArray[numpy.float64]): The predicted probabilities.

        Returns:
            Optional[float]: The area, `None` without entries or without non-entries.
        """
        positives = int(numpy.sum(y))
        negatives = int(y.size - positives)
        if positives == 0 or negatives == 0:
            self.logger.debug("No area under the ROC curve with %d entries and %d non-entries.", positives, negatives)
            return None
        ranks = rankdata(p)
        return float((numpy.sum(ranks[y == 1]) - positives * (positives + 1) / 2) / (positives * negatives))

    def log_score(self, y: NDArray[numpy.float64], p: NDArray[numpy.float64]) -> Optional[float]:
        """Compute the mean log-likelihood per row.

        Args:
            y (NDArray[numpy.float64]): The entries.
            p (NDArray[numpy.float64]): The predicted probabilities.

        Returns:
            Optional[float]: The mean log-likelihood, `None` without rows.
        """
        if y.size == 0:
            return None
        clipped = numpy.clip(p, 1e-12, 1 - 1e-12)
        return float(numpy.mean(y * numpy.log(clipped) + (1 - y) * numpy.log(1 - clipped)))
