from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import QWidget

# First Party Imports.
from gui.theme import Theme

Bar = Tuple[str, int, str]


class TypeBarChart(QWidget):
    """Horizontal bar chart of the number of software of each type, the largest first.

    Attributes:
        ROW_HEIGHT (ClassVar[int]): The height of a type row, in pixels.
        LABEL_WIDTH (ClassVar[int]): The width of the type labels, in pixels.
        COUNT_WIDTH (ClassVar[int]): The width of the counts, in pixels.
        theme (Theme): The application theme.
        bars (List[Bar]): The label, count and colour of each bar.
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
        self.theme = theme
        self.bars: List[Bar] = []

    ############################
    # Publicly Exposed Methods #
    ############################

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
        """Paint one labelled bar per type (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        highest = max((count for _, count, _ in self.bars), default=0) or 1
        bar_space = max(self.width() - self.LABEL_WIDTH - self.COUNT_WIDTH - 8, 1)
        for row, (label, count, color) in enumerate(self.bars):
            top = row * self.ROW_HEIGHT
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            label_box = QRect(0, top, self.LABEL_WIDTH - 6, self.ROW_HEIGHT)
            painter.drawText(label_box, Qt.AlignmentFlag.AlignVCenter, label)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.theme.SURFACE_ALT))
            track = QRect(self.LABEL_WIDTH, top + self.ROW_HEIGHT // 4, bar_space, self.ROW_HEIGHT // 2)
            painter.drawRoundedRect(track, 4, 4)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(track.adjusted(0, 0, -bar_space + bar_space * count // highest, 0), 4, 4)
            painter.setPen(QColor(self.theme.TEXT))
            count_box = QRect(self.LABEL_WIDTH + bar_space + 8, top, self.COUNT_WIDTH, self.ROW_HEIGHT)
            painter.drawText(count_box, Qt.AlignmentFlag.AlignVCenter, f"{count:,}")
        painter.end()
