from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from PyQt6.QtCore import QRectF

# First Party Imports.
from models.correspondence.rows.concept_row import ConceptRow


class DiagramGroup:
    """A group of rows of the correspondence diagram: the concepts of one taxonomy domain, under its header.

    Attributes:
        title (str): The name of the domain.
        color (str): The colour of the domain band.
        concepts (List[ConceptRow]): The concepts of the group, in their order.
        header (QRectF): Where the header is drawn (filled by the layout).
        band (QRectF): The band spanning the rows of the group (filled by the layout).
    """

    def __init__(self, title: str, color: str, concepts: List[ConceptRow]) -> None:
        """Initialize the group, not laid out yet.

        Args:
            title (str): The name of the domain.
            color (str): The colour of the domain band.
            concepts (List[ConceptRow]): The concepts of the group.
        """
        self.title = title
        self.color = color
        self.concepts = concepts
        self.header = QRectF()
        self.band = QRectF()
