from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, List, Optional, Set, Tuple

# Third Party Imports.
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen

# First Party Imports.
from gui.theme import Theme

LegendEntry = Tuple[str, QColor, Qt.PenStyle]


class ChartLegend:
    """Lay out, paint and hit-test the legend of a chart: right of the plot, or below it when the chart is narrow.

    Attributes:
        ROW_HEIGHT (ClassVar[int]): The height of a legend row, in pixels.
        SAMPLE_WIDTH (ClassVar[int]): The width of the colour sample of an entry, in pixels.
        GAP (ClassVar[int]): The space between two entries of a row below the plot, in pixels.
        theme (Theme): The application theme.
        boxes (List[Tuple[QRectF, str]]): The painted box and label of each entry, for the hit tests.

    Notes:
        A hidden entry is painted muted and struck through, the highlighted one bold.
    """

    ROW_HEIGHT: ClassVar[int] = 20
    SAMPLE_WIDTH: ClassVar[int] = 14
    GAP: ClassVar[int] = 16

    def __init__(self, theme: Theme) -> None:
        """Initialize the legend.

        Args:
            theme (Theme): The application theme.
        """
        self.theme = theme
        self.boxes: List[Tuple[QRectF, str]] = []

    ############################
    # Internal Helpers Methods #
    ############################

    def _entry_width(self, metrics: QFontMetrics, label: str) -> int:
        """Get the width of an entry laid out in a row.

        Args:
            metrics (QFontMetrics): The font metrics.
            label (str): The entry label.

        Returns:
            int: The width of the sample, the label and the gap, in pixels.
        """
        return self.SAMPLE_WIDTH + 6 + metrics.horizontalAdvance(label) + self.GAP  # noqa: E501

    def _rows_below(self, metrics: QFontMetrics, entries: List[LegendEntry], width: float) -> List[List[int]]:  # noqa: E501
        """Split the entries into rows fitting a width.

        Args:
            metrics (QFontMetrics): The font metrics.
            entries (List[LegendEntry]): The entries.
            width (float): The available width.

        Returns:
            List[List[int]]: The entry indexes of each row.
        """
        rows: List[List[int]] = [[]]
        used = 0.0
        for index, (label, _, _) in enumerate(entries):
            needed = self._entry_width(metrics, label)
            if rows[-1] and used + needed > width:
                rows.append([])
                used = 0.0
            rows[-1].append(index)
            used += needed
        return rows if rows[0] else []

    ############################
    # Publicly Exposed Methods #
    ############################

    def height_below(self, metrics: QFontMetrics, entries: List[LegendEntry], width: float) -> int:  # noqa: E501
        """Get the height of the legend laid out below the plot.

        Args:
            metrics (QFontMetrics): The font metrics.
            entries (List[LegendEntry]): The entries.
            width (float): The available width.

        Returns:
            int: The height, in pixels.
        """
        return len(self._rows_below(metrics, entries, width)) * self.ROW_HEIGHT

    def paint(
        self,
        painter: QPainter,
        rect: QRectF,
        entries: List[LegendEntry],
        hidden: Set[str],
        highlighted: Optional[str],
        below: bool,
        suffixes: Optional[Dict[str, str]] = None,
    ) -> None:
        """Paint the legend, and remember where each entry is.

        Args:
            painter (QPainter): The painter.
            rect (QRectF): The legend area.
            entries (List[LegendEntry]): The label, colour and line style of each entry.
            hidden (Set[str]): The labels of the hidden entries.
            highlighted (Optional[str]): The label of the highlighted entry, if any.
            below (bool): Whether the legend is laid out in rows below the plot rather than in a column.
            suffixes (Optional[Dict[str, str]]): A text shown after some labels, e.g. their forecast trend.
        """
        metrics = painter.fontMetrics()
        self.boxes = []
        if below:
            positions: List[Tuple[int, QPointF]] = []
            for row, indexes in enumerate(self._rows_below(metrics, entries, rect.width())):
                left = rect.left()
                for index in indexes:
                    positions.append((index, QPointF(left, rect.top() + row * self.ROW_HEIGHT)))
                    left += self._entry_width(metrics, entries[index][0])
        else:
            positions = [
                (index, QPointF(rect.left(), rect.top() + index * self.ROW_HEIGHT)) for index in range(len(entries))
            ]
        for index, origin in positions:
            label, color, style = entries[index]
            text = f"{label}  {suffixes[label]}" if suffixes and label in suffixes else label
            width = rect.width() - self.SAMPLE_WIDTH - 6 if not below else metrics.horizontalAdvance(text) + 4
            if origin.y() + self.ROW_HEIGHT > rect.bottom() + 1:
                break
            is_hidden = label in hidden
            middle = origin.y() + self.ROW_HEIGHT / 2
            sample = QColor(color)
            sample.setAlpha(70 if is_hidden else 255)
            painter.setPen(QPen(sample, 3, style))
            painter.drawLine(QPointF(origin.x(), middle), QPointF(origin.x() + self.SAMPLE_WIDTH, middle))
            font = painter.font()
            font.setBold(label == highlighted)
            font.setStrikeOut(is_hidden)
            painter.setFont(font)
            painter.setPen(QColor(self.theme.TEXT_MUTED if is_hidden else self.theme.TEXT))
            box = QRectF(origin.x() + self.SAMPLE_WIDTH + 6, origin.y(), max(width, 10), self.ROW_HEIGHT)
            elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(box.width()))
            painter.drawText(box, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)
            font.setBold(False)
            font.setStrikeOut(False)
            painter.setFont(font)
            self.boxes.append((QRectF(origin.x(), origin.y(), box.right() - origin.x(), self.ROW_HEIGHT), label))

    def hit(self, position: QPointF) -> Optional[str]:
        """Find the entry under a position.

        Args:
            position (QPointF): The position, in widget pixels.

        Returns:
            Optional[str]: The label of the entry, `None` outside the legend entries.
        """
        return next((label for box, label in self.boxes if box.contains(position)), None)
