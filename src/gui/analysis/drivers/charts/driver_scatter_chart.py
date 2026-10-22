from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QHelpEvent, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QToolTip, QWidget

# First Party Imports.
from gui.theme import Theme
from models.cloud.enums import CloudProvider

type DriverPoint = Tuple[CloudProvider, str, float, float]


class DriverScatterChart(QWidget):
    """The target against a criterion, a dot per observation coloured by its provider, with the least-squares line.

    Attributes:
        MARGIN (ClassVar[int]): The space left around the plot for the axes and their names.
        TITLE_HEIGHT (ClassVar[int]): The height of the title above the plot, when there is one.
        RADIUS (ClassVar[float]): The radius of a dot.
        theme (Theme): The application theme.
        points (List[DriverPoint]): The provider, quarter, criterion and target of each dot (transformed values).
        x_label (str): The name of the criterion.
        y_label (str): The name of the target.
        message (str): What the chart says without dots.
        x_color (QColor): The colour of the criterion axis title (its role).
        y_color (QColor): The colour of the target axis title (its role).
        title (str): The title above the plot (the criterion and its weight), none by default.
        y_range (Optional[Tuple[float, float]]): The target axis shared with the other charts, its own by default.
        logger (Logger): The chart logger.

    Notes:
        The values are those of the analysis: the logarithms of the counts and the amounts, the shares as they are,
        or their yearly changes in a panel. Hovering a dot shows its provider, quarter and values.
    """

    MARGIN: ClassVar[int] = 64
    TITLE_HEIGHT: ClassVar[int] = 22
    RADIUS: ClassVar[float] = 5.0

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build an empty chart.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The chart logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.points: List[DriverPoint] = []
        self.x_label, self.y_label = "", ""
        self.x_color = self.y_color = QColor(theme.TEXT_MUTED)
        self.title = ""
        self.y_range: Optional[Tuple[float, float]] = None
        self.message = "Run the analysis to see the target against each criterion."
        self.setMouseTracking(True)
        self.setMinimumHeight(220)

    ############################
    # Internal Helpers Methods #
    ############################

    def _figure(self, value: float) -> str:
        """Write a value of an axis or a tooltip, readable on both scales.

        Args:
            value (float): The value (a logarithm, a share, a raw count or amount, a change).

        Returns:
            str: Thousands separated from 1,000 on, else 3 significant digits.
        """
        return f"{value:,.0f}" if abs(value) >= 1000 else f"{value:.3g}"

    def _compact(self, value: float) -> str:
        """Write an axis bound in a few characters.

        Args:
            value (float): The bound.

        Returns:
            str: `79.3k` or `1.2M` for the large values, else 3 significant digits.
        """
        for limit, suffix in ((1e9, "G"), (1e6, "M"), (1e3, "k")):
            if abs(value) >= limit:
                return f"{value / limit:.3g}{suffix}"
        return f"{value:.3g}"

    def _plot(self) -> QRectF:
        """Get the area of the dots.

        Returns:
            QRectF: The widget without its margins.
        """
        top = 12 + (self.TITLE_HEIGHT if self.title else 0)
        return QRectF(
            self.MARGIN, top, max(self.width() - self.MARGIN - 16, 40), max(self.height() - self.MARGIN - top, 40)
        )

    def _bounds(self) -> Tuple[float, float, float, float]:
        """Get the ranges of both axes, padded.

        Returns:
            Tuple[float, float, float, float]: The smallest and largest criterion, then target.
        """
        xs = [x for _, _, x, _ in self.points]
        ys = [y for _, _, _, y in self.points]
        x_pad = (max(xs) - min(xs)) * 0.06 or 0.5
        y_pad = (max(ys) - min(ys)) * 0.06 or 0.5
        x_low = max(min(xs) - x_pad, 0.0) if min(xs) > 0 else min(xs) - x_pad
        if self.y_range is not None:
            return x_low, max(xs) + x_pad, self.y_range[0], self.y_range[1]
        y_low = max(min(ys) - y_pad, 0.0) if min(ys) > 0 else min(ys) - y_pad
        return x_low, max(xs) + x_pad, y_low, max(ys) + y_pad

    def _place(self, x: float, y: float) -> QPointF:
        """Place a value pair on the plot.

        Args:
            x (float): The criterion.
            y (float): The target.

        Returns:
            QPointF: Its position, in pixels.
        """
        plot = self._plot()
        x_low, x_high, y_low, y_high = self._bounds()
        return QPointF(
            plot.left() + (x - x_low) / (x_high - x_low) * plot.width(),
            plot.bottom() - (y - y_low) / (y_high - y_low) * plot.height(),
        )

    def _line(self) -> Optional[Tuple[float, float]]:
        """Fit the least-squares line of the dots.

        Returns:
            Optional[Tuple[float, float]]: Its slope and intercept, `None` with fewer than 2 distinct criteria.
        """
        count = len(self.points)
        mean_x = sum(x for _, _, x, _ in self.points) / count
        mean_y = sum(y for _, _, _, y in self.points) / count
        spread = sum((x - mean_x) ** 2 for _, _, x, _ in self.points)
        if spread <= 1e-12:
            return None
        slope = sum((x - mean_x) * (y - mean_y) for _, _, x, y in self.points) / spread
        return slope, mean_y - slope * mean_x

    def _nearest(self, position: QPointF) -> Optional[DriverPoint]:
        """Find the dot under the mouse.

        Args:
            position (QPointF): The mouse position.

        Returns:
            Optional[DriverPoint]: The nearest dot within a few pixels, if any.
        """
        best: Optional[DriverPoint] = None
        reach = (self.RADIUS + 4) ** 2
        for point in self.points:
            where = self._place(point[2], point[3])
            distance = (where.x() - position.x()) ** 2 + (where.y() - position.y()) ** 2
            if distance <= reach:
                best, reach = point, distance
        return best

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_points(
        self,
        points: List[DriverPoint],
        x_label: str,
        y_label: str,
        message: str = "",
        x_color: Optional[QColor] = None,
        y_color: Optional[QColor] = None,
        title: str = "",
        y_range: Optional[Tuple[float, float]] = None,
    ) -> None:
        """Show dots.

        Args:
            points (List[DriverPoint]): The provider, quarter, criterion and target of each dot.
            x_label (str): The name of the criterion.
            y_label (str): The name of the target.
            message (str): What the chart says without dots.
            x_color (Optional[QColor]): The colour of the criterion axis title, muted by default.
            y_color (Optional[QColor]): The colour of the target axis title, muted by default.
            title (str): The title above the plot, none by default.
            y_range (Optional[Tuple[float, float]]): The target axis shared with the other charts, its own by default.
        """
        self.points = list(points)
        self.title, self.y_range = title, y_range
        self.x_label, self.y_label = x_label, y_label
        self.x_color = QColor(x_color) if x_color else QColor(self.theme.TEXT_MUTED)
        self.y_color = QColor(y_color) if y_color else QColor(self.theme.TEXT_MUTED)
        self.message = message or self.message
        self.update()
        self.logger.debug("Driver scatter shows %d dots.", len(self.points))

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override).

        Returns:
            QSize: The preferred size.
        """
        return QSize(640, 320)

    def event(self, event: Optional[QEvent]) -> bool:
        """Show the tooltip of the hovered dot (Qt override).

        Args:
            event (Optional[QEvent]): The event.

        Returns:
            bool: Whether the event was handled.
        """
        if event is not None and event.type() is QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            point = self._nearest(QPointF(event.pos())) if self.points else None
            if point is None:
                QToolTip.hideText()
            else:
                provider, period, x, y = point
                QToolTip.showText(
                    event.globalPos(),
                    f"<b>{self.theme.provider_label(provider)}</b> ({period})<br>"
                    f"{self.x_label}: {self._figure(x)}<br>{self.y_label}: {self._figure(y)}",
                    self,
                )
            return True
        return super().event(event)

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint the axes, the line and the dots (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.title:
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(self.x_color)
            title = painter.fontMetrics().elidedText(self.title, Qt.TextElideMode.ElideRight, self.width() - 16)
            painter.drawText(QRectF(8, 4, self.width() - 16, self.TITLE_HEIGHT), Qt.AlignmentFlag.AlignVCenter, title)
            font.setBold(False)
            painter.setFont(font)
        if not self.points:
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(
                QRectF(self.rect()).adjusted(12, 24 + (self.TITLE_HEIGHT if self.title else 0), -12, 0),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
                self.message,
            )
            painter.end()
            return
        plot = self._plot()
        painter.setPen(QPen(QColor(self.theme.BORDER), 1))
        painter.drawRect(plot)
        x_low, x_high, y_low, y_high = self._bounds()
        painter.setPen(self.x_color)
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 4, plot.width(), 18), Qt.AlignmentFlag.AlignCenter, self.x_label
        )
        painter.setPen(QColor(self.theme.TEXT_MUTED))
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 4, 80, 18), Qt.AlignmentFlag.AlignLeft, self._compact(x_low)
        )
        painter.drawText(
            QRectF(plot.right() - 80, plot.bottom() + 4, 80, 18), Qt.AlignmentFlag.AlignRight, self._compact(x_high)
        )
        for value, top in ((y_high, plot.top()), (y_low, plot.bottom() - 16)):
            painter.drawText(
                QRectF(22, top, self.MARGIN - 26, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._compact(value),
            )
        painter.save()
        painter.translate(12, plot.center().y())
        painter.rotate(-90)
        painter.setPen(self.y_color)
        painter.drawText(QRectF(-plot.height() / 2, -10, plot.height(), 20), Qt.AlignmentFlag.AlignCenter, self.y_label)
        painter.restore()
        painter.setClipRect(plot.adjusted(-self.RADIUS, -self.RADIUS, self.RADIUS, self.RADIUS))
        line = self._line()
        if line is not None:
            slope, intercept = line
            painter.setPen(QPen(QColor(self.theme.ACCENT), 1.5, Qt.PenStyle.DashLine))
            painter.drawLine(
                self._place(x_low, slope * x_low + intercept), self._place(x_high, slope * x_high + intercept)
            )
        for provider, _, x, y in self.points:
            painter.setPen(QPen(QColor(self.theme.WINDOW), 1))
            painter.setBrush(self.theme.provider_color(provider))
            painter.drawEllipse(self._place(x, y), self.RADIUS, self.RADIUS)
        painter.end()
