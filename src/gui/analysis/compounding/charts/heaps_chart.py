from __future__ import annotations

# Standard Library Imports.
import math
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QHelpEvent, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QToolTip, QWidget

# First Party Imports.
from gui.charts.base.chart_zoom import ChartZoom
from gui.charts.base.plot_frame import PlotFrame
from gui.theme import Theme
from models.cloud.enums import CloudProvider

type HeapsSeries = Tuple[CloudProvider, List[Tuple[float, float]], Optional[float], Optional[float]]


class HeapsChart(QWidget):
    """Heaps' law: each provider's distinct categories against its catalogue size, both on logarithmic axes.

    Attributes:
        MARGIN (ClassVar[int]): The space left around the plot for the axes.
        RADIUS (ClassVar[float]): The radius of a dot.
        theme (Theme): The application theme.
        series (List[HeapsSeries]): The provider, the yearly points (size, categories) and the fitted slope and
            intercept (of the logarithms) of each provider.
        message (str): What the chart says without points.
        zoom (ChartZoom): The zoom of both axes.
        logger (Logger): The chart logger.

    Notes:
        A dot per provider and year, coloured by provider, and the fitted line of each provider. Hovering a dot shows
        its figures, Ctrl + wheel or a drag zooms, a double-click resets.
    """

    MARGIN: ClassVar[int] = 64
    RADIUS: ClassVar[float] = 4.0

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build an empty chart.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The chart logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.series: List[HeapsSeries] = []
        self.message = "Run the analysis to see Heaps' law."
        self.zoom = ChartZoom(self, wheel_y=True, logger=self.logger)
        self.zoom.changed.connect(self.update)
        self.setMouseTracking(True)
        self.setMinimumHeight(300)

    ############################
    # Internal Helpers Methods #
    ############################

    def _points(self) -> List[Tuple[CloudProvider, float, float]]:
        """Get every positive point.

        Returns:
            List[Tuple[CloudProvider, float, float]]: The provider, size and categories of each point.
        """
        return [(provider, x, y) for provider, points, _, _ in self.series for x, y in points if x > 0 and y > 0]

    def _frame(self) -> PlotFrame:
        """Map the values to the pixels, through the zoom.

        Returns:
            PlotFrame: The frame of the plot.
        """
        points = self._points()
        xs = [x for _, x, _ in points]
        ys = [y for _, _, y in points]
        full_x = (min(xs) / 1.2, max(xs) * 1.2)
        full_y = (min(ys) / 1.2, max(ys) * 1.2)
        area = QRectF(
            self.MARGIN, 12, max(self.width() - self.MARGIN - 16, 40), max(self.height() - self.MARGIN - 12, 40)
        )
        frame = PlotFrame(
            area, self.zoom.x_range(*full_x, log=True), self.zoom.y_range(*full_y, log=True), log_x=True, log_y=True
        )
        self.zoom.set_frame(frame, full_x, full_y)
        return frame

    def _nearest(self, position: QPointF) -> Optional[Tuple[CloudProvider, float, float]]:
        """Find the dot under the mouse.

        Args:
            position (QPointF): The mouse position.

        Returns:
            Optional[Tuple[CloudProvider, float, float]]: The nearest dot within a few pixels, if any.
        """
        frame = self.zoom.frame
        if frame is None:
            return None
        best: Optional[Tuple[CloudProvider, float, float]] = None
        reach = (self.RADIUS + 4) ** 2
        for point in self._points():
            where = frame.map(point[1], point[2])
            distance = (where.x() - position.x()) ** 2 + (where.y() - position.y()) ** 2
            if distance <= reach:
                best, reach = point, distance
        return best

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_series(self, series: List[HeapsSeries], message: str = "", key: str = "") -> None:
        """Show the points and the fitted lines.

        Args:
            series (List[HeapsSeries]): The provider, points, slope and intercept of each provider.
            message (str): What the chart says without points.
            key (str): What the chart shows: the zoom is kept while it stays the same.
        """
        self.series = list(series)
        self.message = message or self.message
        self.zoom.follow(key)
        self.update()
        self.logger.debug("Heaps chart shows %d providers.", len(self.series))
        if not self._points():
            self.logger.warning("Heaps chart without points: it shows %r.", self.message)

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override).

        Returns:
            QSize: The preferred size.
        """
        return QSize(720, 360)

    def event(self, event: Optional[QEvent]) -> bool:
        """Show the tooltip of the hovered dot (Qt override).

        Args:
            event (Optional[QEvent]): The event.

        Returns:
            bool: Whether the event was handled.
        """
        if event is not None and event.type() is QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            point = self._nearest(QPointF(event.pos()))
            if point is None:
                QToolTip.hideText()
            else:
                QToolTip.showText(
                    event.globalPos(),
                    f"<b>{self.theme.provider_label(point[0])}</b><br>Products: {point[1]:,.0f}"
                    f"<br>Categories: {point[2]:,.0f}",
                    self,
                )
            return True
        return super().event(event)

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint the axes, the fitted lines and the dots (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._points():
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(
                QRectF(self.rect()).adjusted(12, 24, -12, 0),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
                self.message,
            )
            painter.end()
            return
        frame = self._frame()
        area = frame.area
        painter.setPen(QPen(QColor(self.theme.BORDER), 1))
        painter.drawRect(area)
        painter.setPen(QColor(self.theme.TEXT_MUTED))
        painter.drawText(
            QRectF(area.left(), area.bottom() + 22, area.width(), 18),
            Qt.AlignmentFlag.AlignCenter,
            "Products offered (log)",
        )
        for value, alignment in (
            (frame.x_low, Qt.AlignmentFlag.AlignLeft),
            (frame.x_high, Qt.AlignmentFlag.AlignRight),
        ):
            painter.drawText(QRectF(area.left(), area.bottom() + 4, area.width(), 18), alignment, f"{value:,.0f}")
        for value, top in ((frame.y_high, area.top()), (frame.y_low, area.bottom() - 16)):
            painter.drawText(QRectF(6, top, self.MARGIN - 10, 16), Qt.AlignmentFlag.AlignRight, f"{value:,.0f}")
        painter.save()
        painter.translate(12, area.center().y())
        painter.rotate(-90)
        painter.drawText(
            QRectF(-area.height() / 2, -10, area.height(), 20),
            Qt.AlignmentFlag.AlignCenter,
            "Distinct categories (log)",
        )
        painter.restore()
        painter.setClipRect(area)
        for provider, points, slope, intercept in self.series:
            color = self.theme.provider_color(provider)
            xs = [x for x, y in points if x > 0 and y > 0]
            if slope is not None and intercept is not None and xs:
                painter.setPen(QPen(color, 1.5, Qt.PenStyle.DashLine))
                low, high = min(xs), max(xs)
                painter.drawLine(
                    frame.map(low, math.exp(intercept + slope * math.log(low))),
                    frame.map(high, math.exp(intercept + slope * math.log(high))),
                )
            painter.setPen(QPen(QColor(self.theme.WINDOW), 1))
            painter.setBrush(color)
            for x, y in points:
                if x > 0 and y > 0:
                    painter.drawEllipse(frame.map(x, y), self.RADIUS, self.RADIUS)
        painter.setClipping(False)
        self.zoom.paint(painter)
        painter.end()
