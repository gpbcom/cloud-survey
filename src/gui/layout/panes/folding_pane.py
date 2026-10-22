from __future__ import annotations

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget


class FoldingPane(QWidget):
    """A pane of a `FoldingSplitter` which can fold to a thin header (or strip), giving its space to the others.

    Attributes:
        folded_changed (pyqtSignal): Emitted with whether the pane is now folded, when it folds or unfolds.

    Notes:
        The subclasses tell whether they are folded (`is_folded`),
        along which direction they fold (`folds_along`)
        and how much room they keep folded (`folded_extent`),
        the splitter does the rest.
    """

    folded_changed = pyqtSignal(bool)

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_folded(self) -> bool:
        """Tell whether the pane is folded.

        Returns:
            bool: Whether only its header (or strip) is shown.
        """
        return False

    def folds_along(self) -> Qt.Orientation:
        """Tell along which direction the pane folds.

        Returns:
            Qt.Orientation: `Vertical` for a pane folding to its header,
                `Horizontal` for one folding to a strip.
        """
        return Qt.Orientation.Vertical

    def folded_extent(self) -> int:
        """Get the room the pane keeps once folded.

        Returns:
            int: Its height (folding vertically) or its width
                (folding horizontally) once folded, in pixels.
        """
        hint = self.sizeHint()
        return hint.height() if self.folds_along() is Qt.Orientation.Vertical else hint.width()  # noqa: E501
