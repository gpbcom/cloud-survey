from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import QWidget

# First Party Imports.
from gui.charts.base.chart_zoom import ChartZoom
from gui.charts.base.plot_frame import PlotFrame
from gui.theme import Theme

Bar = Tuple[str, int, str]


class DomainBarChart(QWidget):
    """Horizontal bar chart of the number of software of each taxonomy domain, the largest first.

    Attributes:
        ROW_HEIGHT (ClassVar[int]): The height of a domain row, in pixels.
        LABEL_WIDTH (ClassVar[int]): The smallest width of the domain labels, in pixels (wider for longer labels: no
            label is shortened).
        COUNT_WIDTH (ClassVar[int]): The width of the counts, in pixels.
        theme (Theme): The application theme.
        bars (List[Bar]): The label, count and colour of each bar.
        zoom (ChartZoom): The zoom of the counts (Ctrl + wheel or a dragged rectangle, reset by a double-click).
    """

    ROW_HEIGHT: ClassVar[int] = 20
    LABEL_WIDTH: ClassVar[int] = 150
    COUNT_WIDTH: ClassVar[int] = 56

    def __init__(self, theme: Theme) -> None:
        """Build an empty chart.

        Args:
            theme (Theme): The application theme.
        """
        super().__init__()
        self.zoom = ChartZoom(self, zoom_y=False, anchor_low=True)
        self.theme = theme
        self.bars: List[Bar] = []

    ############################
    # Publicly Exposed Methods #
    ############################

    def label_width(self) -> int:
        """Get the width of the label column, fitting the longest domain label.

        Returns:
            int: The width, at least `LABEL_WIDTH`, in pixels.
        """
        metrics = self.fontMetrics()
        return max(
            self.LABEL_WIDTH, max((metrics.horizontalAdvance(label) for label, _, _ in self.bars), default=0) + 12
        )

    def set_bars(self, bars: List[Bar]) -> None:
        """Show new bars, sorted by decreasing count.

        Args:
            bars (List[Bar]): The label, count and colour of each bar.
        """
        self.bars = sorted(bars, key=lambda bar: (-bar[1], bar[0]))
        self.setMinimumHeight(self.ROW_HEIGHT * max(len(self.bars), 1))
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override): one fixed height row per bar.

        Returns:
            QSize: The preferred size.
        """
        return QSize(420, self.ROW_HEIGHT * max(len(self.bars), 1))

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint one labelled bar per domain (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        highest = max((count for _, count, _ in self.bars), default=0) or 1
        label_width = self.label_width()
        bar_space = max(self.width() - label_width - self.COUNT_WIDTH - 8, 1)
        shown = self.zoom.x_range(0.0, float(highest))[1]
        frame = PlotFrame(QRectF(label_width, 0, bar_space, self.height()), (0.0, shown), (0.0, 1.0))   # noqa: E501
        self.zoom.set_frame(frame, (0.0, float(highest)), None)
        for row, (label, count, color) in enumerate(self.bars):
            top = row * self.ROW_HEIGHT
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            label_box = QRect(0, top, label_width - 6, self.ROW_HEIGHT)
            painter.drawText(label_box, Qt.AlignmentFlag.AlignVCenter, label)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.theme.SURFACE_ALT))
            track = QRect(label_width, top + self.ROW_HEIGHT // 4, bar_space, self.ROW_HEIGHT // 2)   # noqa: E501
            painter.drawRoundedRect(track, 4, 4)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(
                track.adjusted(0, 0, -bar_space + round(bar_space * min(count / shown, 1)), 0), 4, 4   # noqa: E501
            )
            painter.setPen(QColor(self.theme.TEXT))
            count_box = QRect(label_width + bar_space + 8, top, self.COUNT_WIDTH, self.ROW_HEIGHT)
            painter.drawText(count_box, Qt.AlignmentFlag.AlignVCenter, f"{count:,}")   # noqa: E501
        self.zoom.paint(painter)
        painter.end()
