from __future__ import annotations

# Standard Library Imports.
import math
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple


class NiceScale:
    """Choose readable axis bounds and grid steps: 1, 2, 2.5 or 5 times a power of ten.

    Attributes:
        STEPS (ClassVar[Tuple[float, ...]]): The multiples of a power of ten a step may be.
        logger (Logger): The scale logger.
    """

    STEPS: ClassVar[Tuple[float, ...]] = (1.0, 2.0, 2.5, 5.0, 10.0)

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the scale.

        Args:
            logger (Optional[Logger]): The scale logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def linear(self, low: float, high: float, target: int = 5, include_zero: bool = True) -> Tuple[float, float, float]:
        """Get the bounds and step of a linear axis.

        Args:
            low (float): The lowest value shown.
            high (float): The highest value shown.
            target (int): The number of grid steps wished.
            include_zero (bool): Whether the axis starts (or ends) at zero.

        Returns:
            Tuple[float, float, float]: The axis low and high bounds (multiples of the step) and the step, e.g.
                `(0, 40, 10)` for values up to 32.
        """
        if include_zero:
            low, high = min(low, 0.0), max(high, 0.0)
        if high <= low:
            low, high = (low - 1, high + 1) if not include_zero or low != 0 else (0.0, 1.0)
        raw = (high - low) / max(target, 1)
        magnitude = 10 ** math.floor(math.log10(raw))
        step = next(multiple * magnitude for multiple in self.STEPS if multiple * magnitude >= raw - 1e-12)
        return math.floor(low / step + 1e-9) * step, math.ceil(high / step - 1e-9) * step, step

    def ticks(self, low: float, high: float, step: float) -> List[float]:
        """List the grid values of a linear axis.

        Args:
            low (float): The axis low bound.
            high (float): The axis high bound.
            step (float): The step between two grid values.

        Returns:
            List[float]: The grid values, from low to high.
        """
        count = round((high - low) / step) if step > 0 else 0
        return [round(low + index * step, 10) for index in range(count + 1)]

    def log(self, low: float, high: float) -> Tuple[float, float, List[float]]:
        """Get the bounds and grid values of a logarithmic axis: the powers of ten around the values.

        Args:
            low (float): The lowest value shown (positive).
            high (float): The highest value shown (positive).

        Returns:
            Tuple[float, float, List[float]]: The axis low and high bounds and the powers of ten between them.
        """
        low, high = max(low, 1e-9), max(high, low * 10)
        first, last = math.floor(math.log10(low)), math.ceil(math.log10(high))
        last = max(last, first + 1)
        return 10.0**first, 10.0**last, [10.0**exponent for exponent in range(first, last + 1)]
