from __future__ import annotations

# Standard Library Imports.
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

type CoefficientRow = Tuple[str, float, Optional[float], Optional[float], str, str]


class CoefficientChart(QWidget):
    """Horizontal coefficients with their 95% intervals, one row each, around zero.

    Attributes:
        ROW_HEIGHT (ClassVar[int]): The height of a row, in pixels.
        LABEL_WIDTH (ClassVar[int]): The width of the row names.
        VALUE_WIDTH (ClassVar[int]): The width of the values written right of the plot.
        theme (Theme): The application theme.
        rows (List[CoefficientRow]): The name, value, interval low and high, colour and tooltip of each row.
        zero (bool): Whether the axis always shows zero (coefficients), else it starts at the lowest value.
        message (str): What the chart says without rows.
        zoom (ChartZoom): The zoom of the value axis.
        logger (Logger): The chart logger.

    Notes:
        The value is a dot, its interval a whisker, and zero a vertical line. Ctrl + wheel or a drag zooms the value
        axis, a double-click resets it. Hovering a row shows its tooltip.
    """

    ROW_HEIGHT: ClassVar[int] = 26
    LABEL_WIDTH: ClassVar[int] = 220
    VALUE_WIDTH: ClassVar[int] = 200

    def __init__(self, theme: Theme, zero: bool = True, logger: Optional[Logger] = None) -> None:
        """Build an empty chart.

        Args:
            theme (Theme): The application theme.
            zero (bool): Whether the axis always shows zero.
            logger (Optional[Logger]): The chart logger.
        """
        super().__init__()
        self.theme = theme
        self.zero = zero
        self.logger = logger if logger else getLogger(__name__)
        self.rows: List[CoefficientRow] = []
        self.message = "Run the analysis to see the coefficients."
        self.zoom = ChartZoom(self, zoom_y=False, logger=self.logger)
        self.zoom.changed.connect(self.update)
        self.setMouseTracking(True)
        self.setFixedHeight(self.ROW_HEIGHT * 3 + 30)

    ############################
    # Internal Helpers Methods #
    ############################

    def _full(self) -> Tuple[float, float]:
        """Get the full range of the value axis, padded.

        Returns:
            Tuple[float, float]: The lowest and highest value shown.
        """
        values = [
            value for _, center, low, high, _, _ in self.rows for value in (center, low, high) if value is not None
        ]
        if self.zero:
            values.append(0.0)
        low, high = min(values), max(values)
        pad = (high - low) * 0.08 or 0.5
        return low - pad, high + pad

    def _frame(self) -> PlotFrame:
        """Map the values to the pixels, through the zoom.

        Returns:
            PlotFrame: The frame of the plot.
        """
        area = QRectF(
            self.LABEL_WIDTH, 4, max(self.width() - self.LABEL_WIDTH - self.VALUE_WIDTH, 40), self.height() - 26
        )
        full = self._full()
        frame = PlotFrame(area, self.zoom.x_range(*full), (0.0, float(max(len(self.rows), 1))), invert_y=True)
        self.zoom.set_frame(frame, full, None)
        return frame

    def _figure(self, value: Optional[float]) -> str:
        """Write a value.

        Args:
            value (Optional[float]): The value.

        Returns:
            str: Three significant digits, a dash when unknown.
        """
        return "-" if value is None else f"{value:+.3g}"

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_rows(self, rows: List[CoefficientRow], message: str = "", key: str = "") -> None:
        """Show coefficients.

        Args:
            rows (List[CoefficientRow]): The name, value, interval, colour and tooltip of each row.
            message (str): What the chart says without rows.
            key (str): What the chart shows: the zoom is kept while it stays the same.
        """
        self.rows = list(rows)
        self.message = message or self.message
        self.setFixedHeight(self.ROW_HEIGHT * max(len(self.rows), 3) + 30)
        self.zoom.follow(key)
        self.update()
        self.logger.debug("Coefficient chart shows %d rows.", len(self.rows))
        if not self.rows:
            self.logger.warning("Coefficient chart without rows: it shows %r.", self.message)

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override).

        Returns:
            QSize: The preferred size.
        """
        return QSize(720, self.height())

    def event(self, event: Optional[QEvent]) -> bool:
        """Show the tooltip of the hovered row (Qt override).

        Args:
            event (Optional[QEvent]): The event.

        Returns:
            bool: Whether the event was handled.
        """
        if event is not None and event.type() is QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            row = int((event.pos().y() - 4) // self.ROW_HEIGHT)
            if self.rows and 0 <= row < len(self.rows):
                QToolTip.showText(event.globalPos(), self.rows[row][5], self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint zero, the intervals and the values (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.rows:
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(
                QRectF(self.rect()).adjusted(12, 12, -12, 0),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
                self.message,
            )
            painter.end()
            return
        frame = self._frame()
        area = frame.area
        painter.setPen(QPen(QColor(self.theme.BORDER), 1))
        painter.drawRect(area)
        if frame.x_low <= 0 <= frame.x_high:
            painter.setPen(QPen(QColor(self.theme.TEXT_MUTED), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(frame.map_x(0.0), area.top()), QPointF(frame.map_x(0.0), area.bottom()))
        painter.setPen(QColor(self.theme.TEXT_MUTED))
        for value, alignment in (
            (frame.x_low, Qt.AlignmentFlag.AlignLeft),
            (frame.x_high, Qt.AlignmentFlag.AlignRight),
        ):
            painter.drawText(QRectF(area.left(), area.bottom() + 4, area.width(), 18), alignment, f"{value:.3g}")
        painter.setClipRect(QRectF(0, 0, self.width(), self.height()))
        for index, (label, value, low, high, color, _) in enumerate(self.rows):
            middle = area.top() + (index + 0.5) * self.ROW_HEIGHT
            painter.setPen(QColor(self.theme.TEXT))
            painter.drawText(
                QRectF(8, middle - self.ROW_HEIGHT / 2, self.LABEL_WIDTH - 16, self.ROW_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, self.LABEL_WIDTH - 16),
            )
            painter.save()
            painter.setClipRect(area)
            if low is not None and high is not None:
                painter.setPen(QPen(QColor(color), 2))
                painter.drawLine(QPointF(frame.map_x(low), middle), QPointF(frame.map_x(high), middle))
                for bound in (low, high):
                    painter.drawLine(QPointF(frame.map_x(bound), middle - 5), QPointF(frame.map_x(bound), middle + 5))
            painter.setPen(QPen(QColor(self.theme.WINDOW), 1))
            painter.setBrush(QColor(color))
            painter.drawEllipse(QPointF(frame.map_x(value), middle), 5.0, 5.0)
            painter.restore()
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(
                QRectF(area.right() + 8, middle - self.ROW_HEIGHT / 2, self.VALUE_WIDTH - 8, self.ROW_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                self._figure(value)
                if low is None or high is None
                else f"{self._figure(value)} [{self._figure(low)}, {self._figure(high)}]",
            )
        self.zoom.paint(painter)
        painter.end()
