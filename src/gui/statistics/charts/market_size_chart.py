from __future__ import annotations

# Standard Library Imports.
import math
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QEvent, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QHelpEvent, QPainter, QPaintEvent
from PyQt6.QtWidgets import QToolTip, QWidget

# First Party Imports.
from gui.charts.base.chart_zoom import ChartZoom
from gui.charts.base.plot_frame import PlotFrame
from gui.theme import Theme

SizeBar = Tuple[str, float, str, Optional[float]]


class MarketSizeChart(QWidget):
    """Vertical bar chart of the market size per period, the year-on-year growth in the tooltips.

    The amounts in euros are drawn in the secondary accent colour. When the bars are too narrow for their texts, only
    every n-th bar is labelled, counting from the latest one.

    Attributes:
        CAPTION_HEIGHT (ClassVar[int]): The height of the period captions, in pixels.
        theme (Theme): The application theme.
        bars (List[SizeBar]): The label, size in billions, currency and growth (if known) of each bar.
        zoom (ChartZoom): The zoom of the periods (Ctrl + wheel or a dragged rectangle, reset by a double-click).
    """

    CAPTION_HEIGHT: ClassVar[int] = 18

    def __init__(self, theme: Theme) -> None:
        """Build an empty chart.

        Args:
            theme (Theme): The application theme.
        """
        super().__init__()
        self.zoom = ChartZoom(self, zoom_y=False)
        self.theme = theme
        self.bars: List[SizeBar] = []
        self.setMinimumHeight(150)
        self.setMouseTracking(True)

    ############################
    # Internal Helpers Methods #
    ############################

    def _window(self) -> Tuple[float, float, float]:
        """Get the periods shown by the zoom and the width of a bar slot.

        Returns:
            Tuple[float, float, float]: The first and last bar positions shown (bar `i` spans `i` to `i + 1`) and the
                width of a slot, in pixels.
        """
        full = (0.0, float(max(len(self.bars), 1)))
        low, high = self.zoom.x_range(*full)
        frame = PlotFrame(QRectF(0, 0, self.width(), max(self.height() - self.CAPTION_HEIGHT, 1)), (low, high), (0, 1))
        self.zoom.set_frame(frame, full, None)
        return low, high, self.width() / max(high - low, 1e-6)

    def _bar_rect(self, index: int, size: float, highest: float) -> QRect:
        """Get the rectangle of a bar.

        Args:
            index (int): The bar index.
            size (float): The market size.
            highest (float): The largest market size.

        Returns:
            QRect: The bar rectangle.
        """
        low, _, slot = self._window()
        plot_height = max(self.height() - 2 * self.CAPTION_HEIGHT, 1)
        height = round(plot_height * size / highest)
        left = round((index - low) * slot + slot * 0.15)
        return QRect(left, self.height() - self.CAPTION_HEIGHT - height, max(round(slot * 0.7), 1), height)

    def _symbol(self, currency: str) -> str:
        """Get the symbol of a currency.

        Args:
            currency (str): The currency, `USD` or `EUR`.

        Returns:
            str: The currency symbol.
        """
        return "\u20ac" if currency == "EUR" else "$"

    def _label_every(self, texts: List[str], slot: float) -> int:
        """Get how often the bars can be labelled without overlapping texts.

        Args:
            texts (List[str]): The labels.
            slot (float): The width of a bar slot, in pixels.

        Returns:
            int: 1 to label every bar, n to label every n-th bar.
        """
        metrics = self.fontMetrics()
        widest = max((metrics.horizontalAdvance(text) for text in texts), default=0) + 8
        return max(1, math.ceil(widest / max(slot, 1.0)))

    def _tooltip(self, index: int) -> str:
        """Get the tooltip of a bar.

        Args:
            index (int): The bar index.

        Returns:
            str: The period, the size and the growth when known.
        """
        label, size, currency, growth = self.bars[index]
        text = f"{label}: {self._symbol(currency)}{size:g} billion"
        return text if growth is None else f"{text}, {growth:+g}% year on year"

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_bars(self, bars: List[SizeBar]) -> None:
        """Show new bars.

        Args:
            bars (List[SizeBar]): The label, size in billions, currency and growth (if known) of each bar.
        """
        self.bars = bars
        self.update()

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override).

        Returns:
            QSize: The preferred size.
        """
        return QSize(720, 160)

    def event(self, event: Optional[QEvent]) -> bool:
        """Show the tooltip of the hovered bar (Qt override).

        Args:
            event (Optional[QEvent]): The event.

        Returns:
            bool: Whether the event was handled.
        """
        if isinstance(event, QHelpEvent):
            low, _, slot = self._window()
            index = int(low + event.pos().x() / slot)
            if 0 <= index < len(self.bars):
                QToolTip.showText(event.globalPos(), self._tooltip(index), self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint one bar per period, its value above and its period below (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        low, high, slot = self._window()
        shown = range(max(math.floor(low), 0), min(math.ceil(high), len(self.bars)))
        highest = max((self.bars[index][1] for index in shown), default=0.0) or 1.0
        values = [f"{self._symbol(currency)}{size:g}" for _, size, currency, _ in self.bars]
        every = self._label_every([self.bars[index][0] for index in shown] + [values[index] for index in shown], slot)
        for index in shown:
            label, size, currency, _ = self.bars[index]
            rect = self._bar_rect(index, size, highest)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.theme.ACCENT_ALT if currency == "EUR" else self.theme.ACCENT))
            painter.drawRoundedRect(rect, 3, 3)
            if (len(self.bars) - 1 - index) % every:
                continue
            center = round((index - low) * slot + slot / 2)
            painter.setPen(QColor(self.theme.TEXT))
            value_box = QRect(center - 50, rect.top() - self.CAPTION_HEIGHT, 100, self.CAPTION_HEIGHT)
            painter.drawText(value_box, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, values[index])
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            caption = QRect(center - 50, self.height() - self.CAPTION_HEIGHT, 100, self.CAPTION_HEIGHT)
            painter.drawText(caption, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, label)
        self.zoom.paint(painter)
        painter.end()
