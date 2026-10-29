from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QHelpEvent, QPainter, QPaintEvent, QPen, QPolygonF
from PyQt6.QtWidgets import QToolTip, QWidget

# First Party Imports.
from gui.theme import Theme

type DriverBar = Tuple[str, float, Optional[float], Optional[float], str, str, Optional[float]]


class DriverBarChart(QWidget):
    """Ranked horizontal bars of the driver analysis: a value per criterion, its interval and an optional marker.

    Attributes:
        ROW_HEIGHT (ClassVar[int]): The height of a row, in pixels.
        LABEL_WIDTH (ClassVar[int]): The width of the criterion names.
        VALUE_WIDTH (ClassVar[int]): The width of the values written right of the bars.
        theme (Theme): The application theme.
        bars (List[DriverBar]): The label, value, interval low and high, colour, tooltip and marker of each bar.
        symmetric (bool): Whether the axis goes from -limit to +limit (correlations), else from 0 (importances).
        limit (float): The largest absolute value of the axis.
        message (str): What the chart says without bars.
        logger (Logger): The chart logger.

    Notes:
        The interval is drawn as a whisker across the bar, the marker (e.g. the partial correlation) as a diamond.
        Hovering a row shows its tooltip (the figures and how to read them).
    """

    ROW_HEIGHT: ClassVar[int] = 26
    LABEL_WIDTH: ClassVar[int] = 210
    VALUE_WIDTH: ClassVar[int] = 70

    def __init__(self, theme: Theme, symmetric: bool, logger: Optional[Logger] = None) -> None:
        """Build an empty chart.

        Args:
            theme (Theme): The application theme.
            symmetric (bool): Whether the axis is symmetric around zero.
            logger (Optional[Logger]): The chart logger.
        """
        super().__init__()
        self.theme = theme
        self.symmetric = symmetric
        self.logger = logger if logger else getLogger(__name__)
        self.bars: List[DriverBar] = []
        self.limit = 1.0
        self.message = "Run the analysis to see the criteria."
        self.setMouseTracking(True)
        self.setFixedHeight(self.ROW_HEIGHT * 3 + 8)

    ############################
    # Internal Helpers Methods #
    ############################

    def _plot(self) -> QRectF:
        """Get the area of the bars.

        Returns:
            QRectF: The area between the names and the values.
        """
        return QRectF(
            self.LABEL_WIDTH, 4, max(self.width() - self.LABEL_WIDTH - self.VALUE_WIDTH, 40), self.height() - 8
        )

    def _x(self, value: float) -> float:
        """Place a value on the axis.

        Args:
            value (float): The value.

        Returns:
            float: Its horizontal position, in pixels.
        """
        plot = self._plot()
        low = -self.limit if self.symmetric else 0.0
        ratio = (max(low, min(self.limit, value)) - low) / (self.limit - low) if self.limit > low else 0.0
        return plot.left() + ratio * plot.width()

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_bars(self, bars: List[DriverBar], limit: Optional[float] = None, message: str = "") -> None:
        """Show bars.

        Args:
            bars (List[DriverBar]): The bars, in their order.
            limit (Optional[float]): The largest absolute value of the axis, the largest value shown by default.
            message (str): What the chart says without bars.
        """
        self.bars = list(bars)
        values = [abs(value) for _, value, low, high, _, _, _ in bars for value in (value, low or 0.0, high or 0.0)]
        self.limit = limit if limit is not None else max([*values, 0.05])
        self.message = message or self.message
        self.setFixedHeight(self.ROW_HEIGHT * max(len(self.bars), 3) + 8)
        self.updateGeometry()
        self.update()
        self.logger.debug("Driver chart shows %d bars.", len(self.bars))
        if not self.bars:
            self.logger.warning("Driver chart without bars: it shows %r.", self.message)

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override): one row per bar.

        Returns:
            QSize: The preferred size.
        """
        return QSize(640, self.ROW_HEIGHT * max(len(self.bars), 3) + 8)

    def event(self, event: Optional[QEvent]) -> bool:
        """Show the tooltip of the hovered row (Qt override).

        Args:
            event (Optional[QEvent]): The event.

        Returns:
            bool: Whether the event was handled.
        """
        if event is not None and event.type() is QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            row = int((event.pos().y() - 4) // self.ROW_HEIGHT)
            if 0 <= row < len(self.bars):
                QToolTip.showText(event.globalPos(), self.bars[row][5], self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint the axis, the bars, their intervals and markers (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.bars:
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(
                QRectF(self.rect()).adjusted(12, 12, -12, 0),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
                self.message,
            )
            painter.end()
            return
        plot = self._plot()
        zero = self._x(0.0)
        painter.setPen(QPen(QColor(self.theme.BORDER), 1))
        painter.drawLine(QPointF(zero, plot.top()), QPointF(zero, plot.bottom()))
        for index, (label, value, low, high, color, _, marker) in enumerate(self.bars):
            top = 4 + index * self.ROW_HEIGHT
            middle = top + self.ROW_HEIGHT / 2
            painter.setPen(QColor(self.theme.TEXT))
            name = painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, self.LABEL_WIDTH - 12)
            painter.drawText(
                QRectF(0, top, self.LABEL_WIDTH - 8, self.ROW_HEIGHT),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                name,
            )
            end = self._x(value)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRectF(min(zero, end), top + 6, abs(end - zero), self.ROW_HEIGHT - 12), 3, 3)
            if low is not None and high is not None:
                painter.setPen(QPen(QColor(self.theme.TEXT), 1.4))
                painter.drawLine(QPointF(self._x(low), middle), QPointF(self._x(high), middle))
                for bound in (low, high):
                    painter.drawLine(QPointF(self._x(bound), middle - 4), QPointF(self._x(bound), middle + 4))
            if marker is not None:
                x = self._x(marker)
                painter.setPen(QPen(QColor(self.theme.WINDOW), 1))
                painter.setBrush(QColor(self.theme.WARNING))
                painter.drawPolygon(
                    QPolygonF(
                        [QPointF(x, middle - 5), QPointF(x + 5, middle), QPointF(x, middle + 5), QPointF(x - 5, middle)]
                    )
                )
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(
                QRectF(plot.right() + 6, top, self.VALUE_WIDTH - 6, self.ROW_HEIGHT),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{value:+.2f}" if self.symmetric else f"{value:.2f}",
            )
        painter.end()
