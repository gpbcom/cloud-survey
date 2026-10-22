from __future__ import annotations

# Standard Library Imports.
import math
from typing import Tuple

# Third Party Imports.
from PyQt6.QtCore import QPointF, QRectF


class PlotFrame:
    """Map the values of a chart to the pixels of its plot area, linearly or logarithmically.

    Attributes:
        area (QRectF): The plot area.
        x_low (float): The x value at the left of the area.
        x_high (float): The x value at the right of the area.
        y_low (float): The y value at the bottom of the area (at the top when inverted).
        y_high (float): The y value at the top of the area (at the bottom when inverted).
        log_x (bool): Whether the x axis is logarithmic.
        log_y (bool): Whether the y axis is logarithmic.
        invert_y (bool): Whether the low y values are at the top (ranks).
    """

    def __init__(
        self,
        area: QRectF,
        x_range: Tuple[float, float],
        y_range: Tuple[float, float],
        log_x: bool = False,
        log_y: bool = False,
        invert_y: bool = False,
    ) -> None:
        """Initialize the frame.

        Args:
            area (QRectF): The plot area.
            x_range (Tuple[float, float]): The x values at the left and right of the area.
            y_range (Tuple[float, float]): The y values at the bottom and top of the area.
            log_x (bool): Whether the x axis is logarithmic.
            log_y (bool): Whether the y axis is logarithmic.
            invert_y (bool): Whether the low y values are at the top.
        """
        self.area = area
        self.x_low, self.x_high = x_range
        self.y_low, self.y_high = y_range
        self.log_x, self.log_y, self.invert_y = log_x, log_y, invert_y

    ############################
    # Internal Helpers Methods #
    ############################

    def _ratio(self, value: float, low: float, high: float, log: bool) -> float:  # noqa: E501
        """Place a value between two bounds.

        Args:
            value (float): The value.
            low (float): The low bound.
            high (float): The high bound.
            log (bool): Whether the scale is logarithmic.

        Returns:
            float: 0 at the low bound, 1 at the high bound (0.5 when the bounds are equal).
        """
        if log:
            value, low, high = (math.log10(max(number, 1e-12)) for number in (value, low, high))  # noqa: E501
        return (value - low) / (high - low) if high != low else 0.5

    def _unratio(self, ratio: float, low: float, high: float, log: bool) -> float:  # noqa: E501
        """Get the value at a place between two bounds (the inverse of `_ratio`).

        Args:
            ratio (float): 0 at the low bound, 1 at the high bound.
            low (float): The low bound.
            high (float): The high bound.
            log (bool): Whether the scale is logarithmic.

        Returns:
            float: The value.
        """
        if log:
            low_log, high_log = (math.log10(max(number, 1e-12)) for number in (low, high))  # noqa: E501
            return float(10 ** (low_log + ratio * (high_log - low_log)))
        return low + ratio * (high - low)

    ############################
    # Publicly Exposed Methods #
    ############################

    def map_x(self, x: float) -> float:
        """Get the horizontal pixel of an x value.

        Args:
            x (float): The x value.

        Returns:
            float: The pixel abscissa.
        """
        return self.area.left() + self.area.width() * self._ratio(x, self.x_low, self.x_high, self.log_x)  # noqa: E501

    def map_y(self, y: float) -> float:
        """Get the vertical pixel of a y value.

        Args:
            y (float): The y value.

        Returns:
            float: The pixel ordinate.
        """
        ratio = self._ratio(y, self.y_low, self.y_high, self.log_y)
        return self.area.bottom() - self.area.height() * (1 - ratio if self.invert_y else ratio)  # noqa: E501

    def map(self, x: float, y: float) -> QPointF:
        """Get the pixel of a point.

        Args:
            x (float): The x value.
            y (float): The y value.

        Returns:
            QPointF: The pixel.
        """
        return QPointF(self.map_x(x), self.map_y(y))

    def value_x(self, pixel: float) -> float:
        """Get the x value of a horizontal pixel (the inverse of `map_x`).

        Args:
            pixel (float): The pixel abscissa.

        Returns:
            float: The x value.
        """
        ratio = (pixel - self.area.left()) / self.area.width() if self.area.width() else 0.5  # noqa: E501
        return self._unratio(ratio, self.x_low, self.x_high, self.log_x)

    def value_y(self, pixel: float) -> float:
        """Get the y value of a vertical pixel (the inverse of `map_y`).

        Args:
            pixel (float): The pixel ordinate.

        Returns:
            float: The y value.
        """
        ratio = (self.area.bottom() - pixel) / self.area.height() if self.area.height() else 0.5  # noqa: E501
        return self._unratio(1 - ratio if self.invert_y else ratio, self.y_low, self.y_high, self.log_y)
