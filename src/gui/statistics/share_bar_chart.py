from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QWidget

# First Party Imports.
from gui.statistics.share_bar import ShareBar
from gui.theme import Theme

ShareGroup = Tuple[str, List[ShareBar]]


class ShareBarChart(QWidget):
    """Horizontal bar chart of the market shares of one period, one group of bars per region and segment.

    A published band is drawn as a range around its middle, an approximate share is marked `~` and the computed
    share of the others is hatched.

    Attributes:
        ROW_HEIGHT (ClassVar[int]): The height of a bar row, in pixels.
        TITLE_HEIGHT (ClassVar[int]): The height of a group title, in pixels.
        LABEL_WIDTH (ClassVar[int]): The width of the player labels, in pixels.
        VALUE_WIDTH (ClassVar[int]): The width of the share values, in pixels.
        theme (Theme): The application theme.
        groups (List[ShareGroup]): The title and the bars of each group.
    """

    ROW_HEIGHT: ClassVar[int] = 24
    TITLE_HEIGHT: ClassVar[int] = 26
    LABEL_WIDTH: ClassVar[int] = 150
    VALUE_WIDTH: ClassVar[int] = 70

    def __init__(self, theme: Theme) -> None:
        """Build an empty chart.

        Args:
            theme (Theme): The application theme.
        """
        super().__init__()
        self.theme = theme
        self.groups: List[ShareGroup] = []

    ############################
    # Internal Helpers Methods #
    ############################

    def _content_height(self) -> int:
        """Get the height needed by the groups.

        Returns:
            int: The height, in pixels, one row at least.
        """
        rows = sum(len(bars) for _, bars in self.groups)
        return max(self.TITLE_HEIGHT * len(self.groups) + self.ROW_HEIGHT * rows, self.ROW_HEIGHT)

    def _value_text(self, bar: ShareBar) -> str:
        """Get the displayed value of a bar.

        Args:
            bar (ShareBar): The bar.

        Returns:
            str: The share, e.g. `28%`, `~15%` or `32-34%`.
        """
        if bar.low_pct is not None and bar.high_pct is not None:
            return f"{bar.low_pct:g}-{bar.high_pct:g}%"
        return f"{'~' if bar.approximate else ''}{bar.share_pct:g}%"

    def _paint_bar(self, painter: QPainter, bar: ShareBar, top: int, bar_space: int) -> None:
        """Paint a bar row: its label, its track, its bar (band, hatching) and its value.

        Args:
            painter (QPainter): The painter.
            bar (ShareBar): The bar.
            top (int): The top of the row, in pixels.
            bar_space (int): The width of the full (100%) bar, in pixels.
        """
        painter.setPen(QColor(self.theme.TEXT_MUTED))
        painter.drawText(
            QRect(8, top, self.LABEL_WIDTH - 12, self.ROW_HEIGHT), Qt.AlignmentFlag.AlignVCenter, bar.label
        )
        track = QRect(self.LABEL_WIDTH, top + self.ROW_HEIGHT // 4, bar_space, self.ROW_HEIGHT // 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.theme.SURFACE_ALT))
        painter.drawRoundedRect(track, 4, 4)
        width = round(bar_space * min(bar.share_pct, 100) / 100)
        brush = QBrush(bar.color, Qt.BrushStyle.BDiagPattern) if bar.computed else QBrush(bar.color)
        painter.setBrush(brush)
        painter.drawRoundedRect(track.adjusted(0, 0, width - bar_space, 0), 4, 4)
        if bar.low_pct is not None and bar.high_pct is not None:
            low = self.LABEL_WIDTH + round(bar_space * bar.low_pct / 100)
            high = self.LABEL_WIDTH + round(bar_space * bar.high_pct / 100)
            painter.setPen(QPen(QColor(self.theme.TEXT), 2))
            middle = top + self.ROW_HEIGHT // 2
            painter.drawLine(low, middle, high, middle)
            painter.drawLine(low, middle - 5, low, middle + 5)
            painter.drawLine(high, middle - 5, high, middle + 5)
        painter.setPen(QColor(self.theme.TEXT))
        value_box = QRect(self.LABEL_WIDTH + bar_space + 8, top, self.VALUE_WIDTH, self.ROW_HEIGHT)
        painter.drawText(value_box, Qt.AlignmentFlag.AlignVCenter, self._value_text(bar))

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_groups(self, groups: List[ShareGroup]) -> None:
        """Show new groups of bars.

        Args:
            groups (List[ShareGroup]): The title and the bars of each group.
        """
        self.groups = groups
        self.setMinimumHeight(self._content_height())
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override): the height of the groups.

        Returns:
            QSize: The preferred size.
        """
        return QSize(560, self._content_height())

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint the group titles and the bars (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar_space = max(self.width() - self.LABEL_WIDTH - self.VALUE_WIDTH - 8, 1)
        top = 0
        for title, bars in self.groups:
            painter.setPen(QColor(self.theme.TEXT))
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRect(0, top, self.width(), self.TITLE_HEIGHT), Qt.AlignmentFlag.AlignVCenter, title)
            font.setBold(False)
            painter.setFont(font)
            top += self.TITLE_HEIGHT
            for bar in bars:
                self._paint_bar(painter, bar, top, bar_space)
                top += self.ROW_HEIGHT
        painter.end()
