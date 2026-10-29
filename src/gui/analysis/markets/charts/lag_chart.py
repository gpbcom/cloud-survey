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
from models.markets.series.lag_correlation import LagCorrelation


class LagChart(QWidget):
    """The correlation of the share changes with a counterpart's (the stock returns by default), a bar per lag.

    Attributes:
        LEFT (ClassVar[int]): The width of the correlation axis.
        BOTTOM (ClassVar[int]): The height of the lag axis.
        TOP (ClassVar[int]): The margin above the plot.
        RIGHT (ClassVar[int]): The margin right of the plot.
        SIGNIFICANT (ClassVar[float]): The q-value below which a bar is drawn solid.
        RHO (ClassVar[str]): The Greek letter rho, naming the Spearman correlation.
        theme (Theme): The application theme.
        lags (List[LagCorrelation]): The correlations drawn.
        message (str): What the chart says without correlations.
        bars (List[Tuple[QRectF, LagCorrelation]]): The bars of the last paint, for the mouse.
        unit (str): The period of the lags, `months` or `quarters`.
        counterpart (str): What the share changes are correlated with, e.g. `the returns`.
        logger (Logger): The chart logger.

    Notes:
        A positive lag pairs a period's share change with the counterpart's change some periods later (does it
        follow the share?), a negative one with its change some periods before (does the share follow it?). A bar
        is solid when its q-value is below 5%, faded otherwise. Each bar has its 95% interval.
    """

    LEFT: ClassVar[int] = 48
    BOTTOM: ClassVar[int] = 40
    TOP: ClassVar[int] = 10
    RIGHT: ClassVar[int] = 16
    SIGNIFICANT: ClassVar[float] = 0.05
    RHO: ClassVar[str] = chr(0x03C1)

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build an empty chart.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The chart logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.lags: List[LagCorrelation] = []
        self.message = "Pick a company, then Correlate."
        self.bars: List[Tuple[QRectF, LagCorrelation]] = []
        self.unit = "months"
        self.counterpart = "the returns"
        self.setMouseTracking(True)
        self.setMinimumHeight(220)

    ############################
    # Internal Helpers Methods #
    ############################

    def _plot(self) -> QRectF:
        """Get the plot area.

        Returns:
            QRectF: The area right of the correlation axis, above the lag axis.
        """
        return QRectF(
            self.LEFT,
            self.TOP,
            max(self.width() - self.LEFT - self.RIGHT, 60),
            max(self.height() - self.TOP - self.BOTTOM, 60),
        )

    def _y(self, plot: QRectF, value: float) -> float:
        """Map a correlation to a pixel ordinate.

        Args:
            plot (QRectF): The plot area.
            value (float): The correlation, from -1 to 1.

        Returns:
            float: The ordinate.
        """
        return plot.center().y() - value * plot.height() / 2

    def _tooltip(self, lag: LagCorrelation) -> str:
        """Explain a bar.

        Args:
            lag (LagCorrelation): Its correlation.

        Returns:
            str: The rich text tooltip.
        """
        if lag.rho is None:
            return f"<qt>Lag {lag.lag:+d} {self.unit}: too few {self.unit} paired ({lag.months}).</qt>"
        direction = f"{self.counterpart} {'after' if lag.lag > 0 else 'before'} the share change"
        interval = f"[{lag.low:+.2f}, {lag.high:+.2f}]" if lag.low is not None and lag.high is not None else "-"
        q_value = f"{lag.q_value:.3g}" if lag.q_value is not None else "-"
        return (
            f"<qt><b>Lag {lag.lag:+d} {self.unit}</b> ({direction if lag.lag else 'same month'})<br>"
            f"Spearman {self.RHO} {lag.rho:+.3f}, 95% interval {interval}<br>"
            f"p {lag.p_value:.3g}, q {q_value}, {lag.months} {self.unit} paired</qt>"
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_lags(
        self, lags: List[LagCorrelation], message: str = "", unit: str = "months", counterpart: str = "the returns"
    ) -> None:
        """Draw correlations, or say why there are none.

        Args:
            lags (List[LagCorrelation]): The correlations, by lag.
            message (str): What to say when there are none.
            unit (str): The period of the lags, `months` or `quarters`.
            counterpart (str): What the share changes are correlated with.
        """
        self.lags = list(lags)
        self.unit = unit
        self.counterpart = counterpart
        self.message = message or self.message
        self.update()
        self.logger.debug("Lag chart: %d lags.", len(self.lags))

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override).

        Returns:
            QSize: The preferred size.
        """
        return QSize(800, 260)

    def event(self, event: Optional[QEvent]) -> bool:
        """Explain the hovered bar (Qt override).

        Args:
            event (Optional[QEvent]): The event.

        Returns:
            bool: Whether the event was handled.
        """
        if event is not None and event.type() is QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            position = QPointF(event.pos())
            hit = next((lag for box, lag in self.bars if box.adjusted(-2, 0, 2, 0).contains(position)), None)
            if hit is not None:
                QToolTip.showText(event.globalPos(), self._tooltip(hit), self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint the axes, the bars and their intervals (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.bars = []
        if not self.lags:
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(
                QRectF(self.rect()).adjusted(12, 24, -12, 0),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
                self.message,
            )
            painter.end()
            return
        plot = self._plot()
        painter.fillRect(plot, QColor(self.theme.SURFACE))
        for tick in (-1.0, -0.5, 0.0, 0.5, 1.0):
            y = self._y(plot, tick)
            painter.setPen(
                QPen(QColor(self.theme.BORDER), 1, Qt.PenStyle.SolidLine if tick == 0 else Qt.PenStyle.DotLine)
            )
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(
                QRectF(0, y - 9, self.LEFT - 6, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{tick:+.1f}",
            )
        slot = plot.width() / len(self.lags)
        for index, lag in enumerate(self.lags):
            x = plot.left() + slot * (index + 0.5)
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(
                QRectF(x - slot / 2, plot.bottom() + 2, slot, 16), Qt.AlignmentFlag.AlignHCenter, f"{lag.lag:+d}"
            )
            if lag.rho is None:
                continue
            zero, top = self._y(plot, 0.0), self._y(plot, lag.rho)
            box = QRectF(x - slot * 0.32, min(zero, top), slot * 0.64, max(abs(top - zero), 1.0))
            color = QColor(self.theme.DRIVER_POSITIVE if lag.rho >= 0 else self.theme.DRIVER_NEGATIVE)
            if lag.q_value is None or lag.q_value >= self.SIGNIFICANT:
                color.setAlpha(90)
            painter.fillRect(box, color)
            if lag.low is not None and lag.high is not None:
                painter.setPen(QPen(QColor(self.theme.TEXT), 1))
                low, high = self._y(plot, lag.low), self._y(plot, lag.high)
                painter.drawLine(QPointF(x, low), QPointF(x, high))
                painter.drawLine(QPointF(x - 3, low), QPointF(x + 3, low))
                painter.drawLine(QPointF(x - 3, high), QPointF(x + 3, high))
            self.bars.append((QRectF(x - slot / 2, plot.top(), slot, plot.height()), lag))
        painter.setPen(QColor(self.theme.TEXT_MUTED))
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 18, plot.width(), 18),
            Qt.AlignmentFlag.AlignHCenter,
            f"Lag in {self.unit} (positive: {self.counterpart} follow the share change)",
        )
        painter.end()
