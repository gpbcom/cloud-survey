from __future__ import annotations

# Third Party Imports.
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath

# First Party Imports.
from models.correspondence.enums import CardinalityClass


class DiagramEdge:
    """A curved connector between two pills of adjacent columns of the correspondence diagram.

    Attributes:
        start (QPointF): The middle of the right side of the left pill.
        end (QPointF): The middle of the left side of the right pill.
        concept_id (int): The concept of its row.
        kind (CardinalityClass): The class colouring it.
        partial (bool): Whether one of its services covers part of the concept only (drawn dashed).
        confidence (int): The lower confidence of its two services, from 0 to 100 (thinner when low).
    """

    def __init__(
        self,
        start: QPointF,
        end: QPointF,
        concept_id: int,
        kind: CardinalityClass,
        partial: bool = False,
        confidence: int = 100,
    ) -> None:
        """Initialize the connector.

        Args:
            start (QPointF): Where it leaves the left pill.
            end (QPointF): Where it reaches the right pill.
            concept_id (int): The concept of its row.
            kind (CardinalityClass): The class colouring it.
            partial (bool): Whether one of its services is partial.
            confidence (int): The lower confidence of its two services.
        """
        self.start = start
        self.end = end
        self.concept_id = concept_id
        self.kind = kind
        self.partial = partial
        self.confidence = confidence

    ############################
    # Publicly Exposed Methods #
    ############################

    def path(self) -> QPainterPath:
        """Get the curve of the connector: a horizontal S (a cubic Bézier curve with horizontal tangents).

        Returns:
            QPainterPath: The curve, from `start` to `end`.
        """
        middle = (self.start.x() + self.end.x()) / 2
        path = QPainterPath(self.start)
        path.cubicTo(QPointF(middle, self.start.y()), QPointF(middle, self.end.y()), self.end)
        return path

    def width(self) -> float:
        """Get the pen width of the connector, from its confidence.

        Returns:
            float: From 1.2 (no confidence) to 2.8 pixels (sure).
        """
        return 1.2 + 1.6 * max(0, min(100, self.confidence)) / 100
