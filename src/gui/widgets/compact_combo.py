from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Optional

# Third Party Imports.
from PyQt6.QtWidgets import QComboBox


class CompactCombo(QComboBox):
    """Combo box as wide as a few characters, whatever its entries, its drop-down list showing them in full.

    Attributes:
        CONTENTS (ClassVar[int]): The default number of characters the closed box is sized for.
        POPUP_PADDING (ClassVar[int]): The room added beside the longest entry of the drop-down list, in pixels.
        logger (Logger): The combo box logger.

    Notes:
        A plain combo box is as wide as its longest entry (e.g. "All providers (2,921)"), which makes the rows of
        filters wider than some screens: the window can then no longer be maximized.
    """

    CONTENTS: ClassVar[int] = 14
    POPUP_PADDING: ClassVar[int] = 36

    def __init__(self, contents: int = CONTENTS, logger: Optional[Logger] = None) -> None:
        """Build an empty combo box.

        Args:
            contents (int): The number of characters the closed box is sized for.
            logger (Optional[Logger]): The combo box logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(contents)

    ############################
    # Publicly Exposed Methods #
    ############################

    def showPopup(self) -> None:
        """Open the drop-down list, wide enough for its longest entry (Qt override)."""
        view = self.view()
        if view is not None:
            longest = view.sizeHintForColumn(0) + self.POPUP_PADDING
            view.setMinimumWidth(max(longest, self.width()))
            self.logger.debug("Drop-down list opened %d px wide.", view.minimumWidth())
        super().showPopup()
