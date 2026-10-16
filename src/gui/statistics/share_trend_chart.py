from __future__ import annotations

# Standard Library Imports.
import math
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QPointF, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QWidget

# First Party Imports.
from gui.theme import Theme

TrendSeries = Tuple[str, QColor, List[Optional[float]], Qt.PenStyle]


class ShareTrendChart(QWidget):
    """Line chart of the market shares over the periods, one line per player, with the methodology breaks marked.

    Attributes:
        MARGIN (ClassVar[int]): The margin around the plot, in pixels.
        AXIS_WIDTH (ClassVar[int]): The width of the y axis values, left of the plot, in pixels.
        LABEL_SPACING (ClassVar[int]): The smallest distance between two period labels, in pixels.
        LEGEND_WIDTH (ClassVar[int]): The width of the legend, in pixels.
        theme (Theme): The application theme.
        periods (List[str]): The periods of the x axis, in chronological order.
        series (List[TrendSeries]): The label, colour, value (or gap) per period and line style of each line.
        breaks (List[str]): The periods starting a methodology break, marked by a dashed line.
    """

    MARGIN: ClassVar[int] = 36
    AXIS_WIDTH: ClassVar[int] = 44
    LABEL_SPACING: ClassVar[int] = 64
    LEGEND_WIDTH: ClassVar[int] = 230

    def __init__(self, theme: Theme) -> None:
        """Build an empty chart.

        Args:
            theme (Theme): The application theme.
        """
        super().__init__()
        self.theme = theme
        self.periods: List[str] = []
        self.series: List[TrendSeries] = []
        self.breaks: List[str] = []
        self.setMinimumHeight(240)

    ############################
    # Internal Helpers Methods #
    ############################

    def _plot_area(self) -> QRect:
        """Get the area of the plot, inside the margins and left of the legend.

        Returns:
            QRect: The plot area.
        """
        return QRect(
            self.AXIS_WIDTH,
            self.MARGIN // 2,
            max(self.width() - self.AXIS_WIDTH - self.MARGIN - self.LEGEND_WIDTH, 1),
            max(self.height() - self.MARGIN - self.MARGIN // 2, 1),
        )

    def _point(self, area: QRect, index: int, value: float, highest: int) -> QPointF:
        """Get the position of a value.

        Args:
            area (QRect): The plot area.
            index (int): The period index.
            value (float): The share, in percent.
            highest (int): The share at the top of the y axis.

        Returns:
            QPointF: The position of the value.
        """
        step = area.width() / max(len(self.periods) - 1, 1)
        return QPointF(area.left() + index * step, area.bottom() - area.height() * value / highest)

    def _scale(self) -> Tuple[int, int]:
        """Get the y axis scale: round values, every 10% up to 50%, every 20% beyond.

        Returns:
            Tuple[int, int]: The share at the top of the y axis and the step between two grid lines.
        """
        highest = max((value for _, _, line, _ in self.series for value in line if value is not None), default=0.0)
        step = 10 if highest <= 50 else 20
        return max(step, math.ceil(highest / step) * step), step

    def _paint_axes(self, painter: QPainter, area: QRect, highest: int, step: int) -> None:
        """Paint the grid, the y axis values and the period labels, the latest period always labelled.

        Args:
            painter (QPainter): The painter.
            area (QRect): The plot area.
            highest (int): The share at the top of the y axis.
            step (int): The step between two grid lines.
        """
        painter.setPen(QPen(QColor(self.theme.BORDER), 1))
        for value in range(0, highest + 1, step):
            y = round(area.bottom() - area.height() * value / highest)
            painter.drawLine(area.left(), y, area.right(), y)
            painter.drawText(QRect(0, y - 8, self.AXIS_WIDTH - 6, 16), Qt.AlignmentFlag.AlignRight, f"{value}%")
        painter.setPen(QColor(self.theme.TEXT_MUTED))
        last_x: Optional[float] = None
        for index in reversed(range(len(self.periods))):
            x = self._point(area, index, 0, highest).x()
            if last_x is None or last_x - x >= self.LABEL_SPACING:
                box = QRect(round(x) - 30, area.bottom() + 4, 60, 16)
                painter.drawText(box, Qt.AlignmentFlag.AlignHCenter, self.periods[index])
                last_x = x

    def _paint_breaks(self, painter: QPainter, area: QRect, highest: int) -> None:
        """Paint a dashed vertical line at each methodology break.

        Args:
            painter (QPainter): The painter.
            area (QRect): The plot area.
            highest (int): The share at the top of the y axis.
        """
        pen = QPen(QColor(self.theme.LEVEL_COLORS[30]), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        for period in self.breaks:
            if period in self.periods:
                x = round(self._point(area, self.periods.index(period), 0, highest).x())
                painter.drawLine(x, area.top(), x, area.bottom())
                painter.drawText(QRect(x + 3, area.top(), 160, 16), Qt.AlignmentFlag.AlignLeft, "methodology change")

    def _paint_series(self, painter: QPainter, area: QRect, highest: int) -> None:
        """Paint one line (and its points) per series, joining the points over the periods without value.

        Args:
            painter (QPainter): The painter.
            area (QRect): The plot area.
            highest (int): The share at the top of the y axis.
        """
        for _, color, values, style in self.series:
            painter.setPen(QPen(color, 2, style))
            painter.setBrush(color)
            previous: Optional[QPointF] = None
            for index, value in enumerate(values):
                if value is None:
                    continue
                point = self._point(area, index, value, highest)
                if previous is not None:
                    painter.drawLine(previous, point)
                painter.drawEllipse(point, 3, 3)
                previous = point

    def _paint_legend(self, painter: QPainter) -> None:
        """Paint the legend: a line sample, in the colour and style of the series, and its label.

        Args:
            painter (QPainter): The painter.
        """
        left = self.width() - self.LEGEND_WIDTH + 12
        for row, (label, color, _, style) in enumerate(self.series):
            top = self.MARGIN // 2 + row * 20
            painter.setPen(QPen(color, 3, style))
            painter.drawLine(left, top + 10, left + 14, top + 10)
            painter.setPen(QColor(self.theme.TEXT))
            painter.drawText(QRect(left + 20, top, self.LEGEND_WIDTH - 32, 20), Qt.AlignmentFlag.AlignVCenter, label)

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_series(self, periods: List[str], series: List[TrendSeries], breaks: List[str]) -> None:
        """Show new lines.

        Args:
            periods (List[str]): The periods of the x axis, in chronological order.
            series (List[TrendSeries]): The label, colour, value (or gap) per period and line style of each line.
            breaks (List[str]): The periods starting a methodology break.
        """
        self.periods, self.series, self.breaks = periods, series, breaks
        self.update()

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override).

        Returns:
            QSize: The preferred size.
        """
        return QSize(720, 260)

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint the axes, the breaks, the lines and the legend (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = self._plot_area()
        highest, step = self._scale()
        if not self.periods:
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No period selected")
            painter.end()
            return
        self._paint_axes(painter, area, highest, step)
        self._paint_breaks(painter, area, highest)
        self._paint_series(painter, area, highest)
        self._paint_legend(painter)
        painter.end()
