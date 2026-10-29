from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Optional

# Third Party Imports.
import numpy
from numpy.typing import NDArray


class GrowthCurves:
    """The growth curves of a catalogue size, as functions of the years since the first year fitted.

    Attributes:
        start (float): The catalogue size the first year fitted.
        logger (Logger): The curves logger.

    Notes:
        - Exponential (6.6): launches `a + b N`, so `N = start e^(b t) + a (e^(b t) - 1) / b`.
        - Logistic: `N = K / (1 + e^(-r (t - m)))`.
        - Bass (6.7): `N = start + M F(t)`, `F = (1 - e^(-(p + q) t)) / (1 + (q / p) e^(-(p + q) t))`.
    """

    def __init__(self, start: float, logger: Optional[Logger] = None) -> None:
        """Initialize the curves.

        Args:
            start (float): The catalogue size the first year fitted.
            logger (Optional[Logger]): The curves logger.
        """
        self.start = start
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def exponential(self, t: NDArray[numpy.float64], a: float, b: float) -> NDArray[numpy.float64]:
        """Compute the catalogue size of a launch rate linear in the size.

        Args:
            t (NDArray[numpy.float64]): The years since the first year fitted.
            a (float): The launches per year of an empty catalogue.
            b (float): The launches per year per product held.

        Returns:
            NDArray[numpy.float64]: The size of each year.
        """
        growth = numpy.expm1(b * t) / b if abs(b) > 1e-9 else t
        return self.start * numpy.exp(b * t) + a * growth

    def logistic(self, t: NDArray[numpy.float64], ceiling: float, rate: float, middle: float) -> NDArray[numpy.float64]:
        """Compute the catalogue size of a logistic curve.

        Args:
            t (NDArray[numpy.float64]): The years since the first year fitted.
            ceiling (float): The size it tends to.
            rate (float): The growth rate.
            middle (float): The year of the inflection, since the first year fitted.

        Returns:
            NDArray[numpy.float64]: The size of each year.
        """
        return ceiling / (1 + numpy.exp(-rate * (t - middle)))

    def bass(
        self, t: NDArray[numpy.float64], potential: float, steady: float, imitation: float
    ) -> NDArray[numpy.float64]:
        """Compute the catalogue size of a Bass curve.

        Args:
            t (NDArray[numpy.float64]): The years since the first year fitted.
            potential (float): The launches still to come the first year fitted (M).
            steady (float): The steady launch coefficient (p).
            imitation (float): The self-reinforcing launch coefficient (q).

        Returns:
            NDArray[numpy.float64]: The size of each year.
        """
        decay = numpy.exp(-(steady + imitation) * t)
        return self.start + potential * (1 - decay) / (1 + (imitation / steady) * decay)
