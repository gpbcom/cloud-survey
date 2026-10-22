from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Optional

# Third Party Imports.
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QFrame, QScrollArea, QSizePolicy, QWidget


class FittedScrollArea(QScrollArea):
    """A vertical scroll area never taller than its widget: a chart of a few rows keeps its height, at the top.

    Attributes:
        scroll_height (int): The height below which a taller widget scrolls, in pixels.
        logger (Logger): The area logger.

    Notes:
        The area grows with the room it is given up to the
        natural height of its widget (e.g. one row per bar), and
        scrolls below `scroll_height`: a widget shorter than that
        keeps its own height. It fits again whenever its
        widget asks for a new geometry (its rows changed), so that 
        the extra room goes to the other charts of the
        column rather than below a short chart.
    """

    def __init__(self, widget: QWidget, minimum_height: int, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Build the area around a widget.

        Args:
            widget (QWidget): The widget, e.g. a bar chart as tall as its rows.
            minimum_height (int): The height below which a taller widget scrolls, in pixels.
            logger (Optional[Logger]): The area logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.setWidget(widget)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # noqa: E501
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.scroll_height = minimum_height
        self.fit()
        self.logger.debug("Fitted scroll area built (at least %d px).", minimum_height)  # noqa: E501

    ############################
    # Publicly Exposed Methods #
    ############################

    def fit(self) -> None:
        """Fit the area to the natural height of its widget, scrolling it below `scroll_height`."""
        widget = self.widget()
        natural = widget.sizeHint().height() + 2 * self.frameWidth() if widget is not None else 0  # noqa: E501
        if (min(natural, self.scroll_height), natural) != (self.minimumHeight(), self.maximumHeight()):
            self.setMinimumHeight(min(natural, self.scroll_height))
            self.setMaximumHeight(natural)
            self.logger.debug("Fitted scroll area fitted to %d px.", natural)

    def viewportEvent(self, event: Optional[QEvent]) -> bool:
        """Fit again when the widget asks for a new geometry (Qt override).

        Args:
            event (Optional[QEvent]): The viewport event.

        Returns:
            bool: Whether the event was handled.
        """
        if event is not None and event.type() == QEvent.Type.LayoutRequest:
            self.fit()
        return super().viewportEvent(event)
