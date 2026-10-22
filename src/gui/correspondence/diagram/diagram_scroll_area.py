from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Optional

# Third Party Imports.
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QFrame, QScrollArea

# First Party Imports.
from gui.correspondence.diagram.correspondence_diagram import CorrespondenceDiagram
from gui.correspondence.diagram.diagram_header import DiagramHeader


class DiagramScrollArea(QScrollArea):
    """The scroll area of the correspondence diagram: the diagram fills it, and its header follows it sideways.

    Attributes:
        diagram (CorrespondenceDiagram): The diagram.
        header (DiagramHeader): The column headers, kept above the scrolled rows.
        logger (Logger): The area logger.

    Notes:
        Whenever the area is resized, the diagram is placed again to fill its visible width and height: the rows
        scroll vertically, and sideways only once the columns are widened (Ctrl + wheel).
    """

    def __init__(self, diagram: CorrespondenceDiagram, header: DiagramHeader, logger: Optional[Logger] = None) -> None:
        """Build the area around the diagram.

        Args:
            diagram (CorrespondenceDiagram): The diagram.
            header (DiagramHeader): The column headers.
            logger (Optional[Logger]): The area logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.diagram = diagram
        self.header = header
        self.setWidget(diagram)
        self.setWidgetResizable(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumHeight(80)
        scroll_bar = self.horizontalScrollBar()
        if scroll_bar is not None:
            scroll_bar.valueChanged.connect(header.set_offset)
        diagram.laid_out.connect(self._on_laid_out)
        self.logger.debug("Diagram scroll area built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _on_laid_out(self) -> None:
        """Show the columns of the placed diagram in the header."""
        self.header.set_layout(self.diagram.layout_, self.diagram.title)

    ############################
    # Publicly Exposed Methods #
    ############################

    def resizeEvent(self, event: Optional[QResizeEvent]) -> None:
        """Fit the diagram to the new visible area (Qt override).

        Args:
            event (Optional[QResizeEvent]): The resize event.
        """
        super().resizeEvent(event)
        viewport = self.viewport()
        if viewport is not None:
            self.diagram.fit(viewport.width(), viewport.height())
