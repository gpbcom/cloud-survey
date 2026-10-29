from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional

# Third Party Imports.
import numpy
from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QHelpEvent, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QToolTip, QWidget

# First Party Imports.
from gui.charts.base.chart_zoom import ChartZoom
from gui.charts.base.plot_frame import PlotFrame
from gui.theme import Theme


class PlaceboChart(QWidget):
    """The histogram of the placebo foundation coefficients, with the real coefficient marked.

    Attributes:
        BINS (ClassVar[int]): The bars of the histogram.
        MARGIN (ClassVar[int]): The space left around the plot for the axes.
        theme (Theme): The application theme.
        draws (List[float]): The coefficients of the random foundation sets.
        real (Optional[float]): The coefficient of the real foundation sets.
        p_value (Optional[float]): The share of random sets doing at least as well.
        message (str): What the chart says without draws.
        zoom (ChartZoom): The zoom of the value axis.
        logger (Logger): The chart logger.

    Notes:
        The real coefficient far right of the bars means the real foundations beat chance. Ctrl + wheel or a drag
        zooms, a double-click resets.
    """

    BINS: ClassVar[int] = 30
    MARGIN: ClassVar[int] = 48

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build an empty chart.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The chart logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.draws: List[float] = []
        self.real: Optional[float] = None
        self.p_value: Optional[float] = None
        self.message = "Run the analysis to see the placebo test."
        self.zoom = ChartZoom(self, zoom_y=False, anchor_low=False, logger=self.logger)
        self.zoom.changed.connect(self.update)
        self.setMouseTracking(True)
        self.setMinimumHeight(240)

    ############################
    # Internal Helpers Methods #
    ############################

    def _frame(self, top: float) -> PlotFrame:
        """Map the values to the pixels, through the zoom.

        Args:
            top (float): The tallest bar.

        Returns:
            PlotFrame: The frame of the plot.
        """
        values = [*self.draws, *([self.real] if self.real is not None else [])]
        low, high = min(values), max(values)
        pad = (high - low) * 0.06 or 0.5
        full = (low - pad, high + pad)
        area = QRectF(self.MARGIN, 24, max(self.width() - self.MARGIN - 16, 40), max(self.height() - 56, 40))
        frame = PlotFrame(area, self.zoom.x_range(*full), (0.0, top * 1.1))
        self.zoom.set_frame(frame, full, None)
        return frame

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_test(
        self, draws: List[float], real: Optional[float], p_value: Optional[float], message: str = "", key: str = ""
    ) -> None:
        """Show a placebo test.

        Args:
            draws (List[float]): The coefficients of the random sets.
            real (Optional[float]): The real coefficient.
            p_value (Optional[float]): The share of random sets doing at least as well.
            message (str): What the chart says without draws.
            key (str): What the chart shows: the zoom is kept while it stays the same.
        """
        self.draws, self.real, self.p_value = list(draws), real, p_value
        self.message = message or self.message
        self.zoom.follow(key)
        self.update()
        self.logger.debug("Placebo chart shows %d draws.", len(self.draws))
        if not self.draws:
            self.logger.warning("Placebo chart without draws: it shows %r.", self.message)

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override).

        Returns:
            QSize: The preferred size.
        """
        return QSize(720, 280)

    def event(self, event: Optional[QEvent]) -> bool:
        """Show what the chart tells (Qt override).

        Args:
            event (Optional[QEvent]): The event.

        Returns:
            bool: Whether the event was handled.
        """
        if event is not None and event.type() is QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            if self.draws and self.real is not None:
                QToolTip.showText(
                    event.globalPos(),
                    f"Real coefficient: {self.real:+.3g}<br>Random sets: {len(self.draws)}<br>"
                    f"At least as large: p = {self.p_value:.3f}"
                    if self.p_value is not None
                    else "",
                    self,
                )
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint the bars and the real coefficient (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.draws:
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(
                QRectF(self.rect()).adjusted(12, 24, -12, 0),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
                self.message,
            )
            painter.end()
            return
        values = [*self.draws, *([self.real] if self.real is not None else [])]
        counts, edges = numpy.histogram(self.draws, bins=self.BINS, range=(min(values), max(values)))
        frame = self._frame(float(max(int(counts.max()), 1)))
        area = frame.area
        painter.setPen(QPen(QColor(self.theme.BORDER), 1))
        painter.drawRect(area)
        painter.setPen(QColor(self.theme.TEXT_MUTED))
        for value, alignment in (
            (frame.x_low, Qt.AlignmentFlag.AlignLeft),
            (frame.x_high, Qt.AlignmentFlag.AlignRight),
        ):
            painter.drawText(QRectF(area.left(), area.bottom() + 4, area.width(), 18), alignment, f"{value:+.3g}")
        if self.p_value is not None:
            painter.drawText(
                QRectF(area.left(), 4, area.width(), 18), Qt.AlignmentFlag.AlignLeft, f"Placebo p = {self.p_value:.3f}"
            )
        painter.setClipRect(area)
        painter.setPen(QPen(QColor(self.theme.WINDOW), 1))
        painter.setBrush(QColor(self.theme.TEXT_MUTED))
        for count, left, right in zip(counts, edges[:-1], edges[1:], strict=True):
            top = frame.map(float(left), float(count))
            bottom = frame.map(float(right), 0.0)
            painter.drawRect(QRectF(top, bottom))
        if self.real is not None:
            painter.setPen(QPen(QColor(self.theme.ACCENT), 2.5))
            x = frame.map_x(self.real)
            painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
        painter.setClipping(False)
        self.zoom.paint(painter)
        painter.end()
