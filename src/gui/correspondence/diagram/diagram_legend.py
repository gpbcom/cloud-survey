from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QWidget

# First Party Imports.
from gui.theme import Theme
from models.correspondence.enums import CardinalityClass


class DiagramLegend(QWidget):
    """The legend of the correspondence diagram: the colour of each correspondence class, then the line styles.

    Attributes:
        HEIGHT (ClassVar[int]): The height of the legend, in pixels.
        SWATCH (ClassVar[Tuple[int, int]]): The size of a pill swatch.
        GAP (ClassVar[int]): The space between two entries.
        NOTES (ClassVar[List[str]]): The entries after the classes: partial, missing, set by hand, confidence.
        theme (Theme): The application theme.
        logger (Logger): The legend logger.
    """

    HEIGHT: ClassVar[int] = 34
    SWATCH: ClassVar[Tuple[int, int]] = (30, 16)
    GAP: ClassVar[int] = 22
    NOTES: ClassVar[List[str]] = ["Partial service", "No equivalent", "✎ Set by hand", "Thicker: surer"]

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build the legend.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The legend logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.setFixedHeight(self.HEIGHT)
        self.setToolTip("The colour tells how many services of one provider match one service of the next column")
        self.logger.debug("Correspondence legend built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _entries(self) -> List[Tuple[CardinalityClass, str]]:
        """List the classes shown with a pill swatch.

        Returns:
            List[Tuple[CardinalityClass, str]]: The class and the short label of each swatch (e.g. `2:1 match`),
                missing services excluded.
        """
        return [(kind, f"{kind.value} match") for kind in CardinalityClass if kind is not CardinalityClass.MISSING]

    def _paint_note(self, painter: QPainter, left: float, index: int, label: str) -> float:
        """Paint an entry explaining a line or a mark.

        Args:
            painter (QPainter): The painter.
            left (float): Where the entry starts.
            index (int): Which note: 0 partial, 1 missing, 2 set by hand, 3 confidence.
            label (str): Its label.

        Returns:
            float: Where the next entry starts.
        """
        middle = self.HEIGHT / 2
        width, height = self.SWATCH
        edge = self.theme.correspondence_edge(CardinalityClass.TWO_TO_ONE)
        match index:
            case 0:
                painter.setPen(QPen(edge, 1.8, Qt.PenStyle.DashLine))
                painter.drawLine(QPointF(left, middle), QPointF(left + width, middle))
            case 1:
                painter.setPen(QPen(QColor(self.theme.BORDER), 1.2, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(QRectF(left, middle - height / 2, width, height), 6, 6)
            case 3:
                painter.setPen(QPen(edge, 1.2))
                painter.drawLine(QPointF(left, middle - 4), QPointF(left + width, middle - 4))
                painter.setPen(QPen(edge, 2.8))
                painter.drawLine(QPointF(left, middle + 4), QPointF(left + width, middle + 4))
        start = left if index == 2 else left + width + 8
        painter.setPen(QColor(self.theme.TEXT))
        text_width = painter.fontMetrics().horizontalAdvance(label)
        painter.drawText(QRectF(start, 0, text_width + 2, self.HEIGHT), Qt.AlignmentFlag.AlignVCenter, label)
        return start + text_width + self.GAP

    ############################
    # Publicly Exposed Methods #
    ############################

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override): every entry on one line.

        Returns:
            QSize: The preferred size.
        """
        metrics = self.fontMetrics()
        labels = [label for _, label in self._entries()] + self.NOTES
        width = sum(metrics.horizontalAdvance(label) + self.SWATCH[0] + 8 + self.GAP for label in labels)
        return QSize(width, self.HEIGHT)

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint the swatches and their labels (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.SWATCH
        middle = self.HEIGHT / 2
        left = 4.0
        for kind, label in self._entries():
            painter.setPen(QPen(self.theme.correspondence_edge(kind), 1.0))
            painter.setBrush(self.theme.correspondence_fill(kind))
            painter.drawRoundedRect(QRectF(left, middle - height / 2, width, height), 6, 6)
            painter.setPen(QColor(self.theme.TEXT))
            text_width = painter.fontMetrics().horizontalAdvance(label)
            painter.drawText(
                QRectF(left + width + 8, 0, text_width + 2, self.HEIGHT), Qt.AlignmentFlag.AlignVCenter, label
            )
            left += width + 8 + text_width + self.GAP
        for index, label in enumerate(self.NOTES):
            left = self._paint_note(painter, left, index, label)
        painter.end()
