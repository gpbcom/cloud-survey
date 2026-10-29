from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional

# Third Party Imports.
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter, QWidget

# First Party Imports.
from gui.layout.panes.folding_pane import FoldingPane


class FoldingSplitter(QSplitter):
    """Splitter whose folding panes give their room to the other panes, and take it back when they unfold.

    Attributes:
        saved (Dict[int, int]): The size of each folded pane before it folded, by index.
        logger (Logger): The splitter logger.

    Notes:
        - A folding pane folded along the orientation of the splitter keeps its folded extent (header or strip),
          the freed room goes to the largest pane which is not folded.
        - Unfolding gives the pane its former size back, taken from the other panes in proportion to their size.
    """

    def __init__(self, orientation: Qt.Orientation, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Build an empty splitter.

        Args:
            orientation (Qt.Orientation): The orientation of the splitter.
            logger (Optional[Logger]): The splitter logger.
        """
        super().__init__(orientation)
        self.logger = logger if logger else getLogger(__name__)
        self.saved: Dict[int, int] = {}
        self.setChildrenCollapsible(False)
        self.logger.debug("Folding splitter ready (%s).", orientation.name)

    ############################
    # Internal Helpers Methods #
    ############################

    def _folding(self, index: int) -> Optional[FoldingPane]:
        """Get the pane at an index when it folds along the splitter.

        Args:
            index (int): The pane index.

        Returns:
            Optional[FoldingPane]: The pane, `None` for a pane which does not fold (or folds the other way).
        """
        pane = self.widget(index)
        if isinstance(pane, FoldingPane) and pane.folds_along() is self.orientation():  # noqa: E501
            return pane
        return None

    def _receiver(self, sizes: List[int], index: int) -> Optional[int]:
        """Choose the pane taking the room freed by a folded one.

        Args:
            sizes (List[int]): The sizes of the panes.
            index (int): The index of the folded pane.

        Returns:
            Optional[int]: The index of the largest other pane which is not folded, `None` when there is none.
        """
        candidates = [
            other
            for other in range(len(sizes))
            if other != index and not ((pane := self._folding(other)) is not None and pane.is_folded())  # noqa: E501
        ]
        if not candidates:
            self.logger.debug("No unfolded pane takes the room of the pane %d.", index)
            return None
        receiver = max(candidates, key=lambda other: sizes[other])
        self.logger.debug("The pane %d takes the room of the pane %d.", receiver, index)
        return receiver

    def _on_folded(self, pane: FoldingPane, folded: bool) -> None:
        """Give the room of a pane to the others when it folds, and take it back when it unfolds.

        Args:
            pane (FoldingPane): The pane.
            folded (bool): Whether it is now folded.
        """
        index = self.indexOf(pane)
        sizes = self.sizes()
        if index < 0 or pane.folds_along() is not self.orientation():
            self.logger.debug("The folded pane does not fold along this splitter: sizes left as they are.")
            return
        if folded:
            extent = pane.folded_extent()
            self.saved[index] = max(sizes[index], self.saved.get(index, 0)) if sizes[index] > extent else 0  # noqa: E501
            receiver = self._receiver(sizes, index)
            if receiver is not None:
                sizes[receiver] += max(sizes[index] - extent, 0)
            sizes[index] = extent
        else:
            total = sum(sizes)
            others = sum(size for other, size in enumerate(sizes) if other != index)  # noqa: E501
            wanted = self.saved.pop(index, 0) or total // max(len(sizes), 1)
            wanted = min(wanted, max(total - (len(sizes) - 1) * 80, 0))
            taken = max(wanted - sizes[index], 0)
            for other in range(len(sizes)):
                if other != index and others > 0:
                    sizes[other] -= round(taken * sizes[other] / others)
            sizes[index] = wanted
        self.setSizes(sizes)
        self.logger.debug("Splitter pane %d %s: sizes %s.", index, "folded" if folded else "unfolded", sizes)  # noqa: E501

    ############################
    # Publicly Exposed Methods #
    ############################

    def add_pane(self, widget: QWidget, stretch: int = 0) -> QWidget:
        """Add a pane, following its folds when it is a folding pane.

        Args:
            widget (QWidget): The pane.
            stretch (int): Its stretch factor when the splitter grows.

        Returns:
            QWidget: The same pane.
        """
        self.addWidget(widget)
        self.setStretchFactor(self.indexOf(widget), stretch)
        if isinstance(widget, FoldingPane):
            widget.folded_changed.connect(lambda folded, pane=widget: self._on_folded(pane, folded))  # noqa: E501
        self.logger.debug("Splitter pane %d added.", self.indexOf(widget))
        return widget
