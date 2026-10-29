from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# Third Party Imports.
import numpy

# First Party Imports.
from analytics.compounding.estimators.curves.ordinary_least_squares import OrdinaryLeastSquares
from models.cloud.enums import CloudProvider
from models.compounding.results.fits.heaps_fit import HeapsFit


class HeapsFitter:
    """Fit Heaps' law (6.8): the distinct categories against the catalogue size, in logarithms.

    Attributes:
        least_squares (OrdinaryLeastSquares): The least-squares estimator.
        logger (Logger): The fitter logger.

    Notes:
        A year repeating the size and the categories of the year before adds no information and is dropped.
    """

    def __init__(self, least_squares: OrdinaryLeastSquares, logger: Optional[Logger] = None) -> None:
        """Initialize the fitter.

        Args:
            least_squares (OrdinaryLeastSquares): The least-squares estimator.
            logger (Optional[Logger]): The fitter logger.
        """
        self.least_squares = least_squares
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def fit(self, provider: CloudProvider, points: List[Tuple[float, float]]) -> HeapsFit:
        """Fit a provider's Heaps' law.

        Args:
            provider (CloudProvider): The provider.
            points (List[Tuple[float, float]]): The catalogue size and the distinct categories of each year.

        Returns:
            HeapsFit: The slope and its interval, none with fewer than three distinct points.
        """
        kept: List[Tuple[float, float]] = []
        for point in points:
            if point[0] >= 1 and point[1] >= 1 and (not kept or kept[-1] != point):
                kept.append(point)
        if len(kept) < 3:
            self.logger.debug("Too few points for the Heaps' law of %s.", provider.value)
            return HeapsFit(provider=provider, points=points)
        sizes = numpy.log([size for size, _ in kept])
        categories = numpy.log([count for _, count in kept])
        fitted = self.least_squares.fit(categories, sizes.reshape(-1, 1), ["slope"])
        if fitted is None:
            return HeapsFit(provider=provider, points=points)
        intercept, estimates, r2 = fitted
        self.logger.debug("Heaps' law of %s: slope %.2f.", provider.value, estimates[0].value)
        return HeapsFit(provider=provider, slope=estimates[0], intercept=intercept, r2=r2, points=points)
