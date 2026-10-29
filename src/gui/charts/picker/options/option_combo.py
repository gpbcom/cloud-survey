from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QComboBox

ComboOption = Tuple[str, str, Optional[str]]


class OptionCombo(QComboBox):
    """Combo box of chart options, the options which cannot be chosen shown disabled with the reason as tooltip.

    Attributes:
        options (QStandardItemModel): The options.
        logger (Logger): The combo box logger.
    """

    def __init__(self, name: str, logger: Optional[Logger] = None) -> None:
        """Build an empty combo box.

        Args:
            name (str): What the combo box chooses, for the screen readers.
            logger (Optional[Logger]): The combo box logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.options = QStandardItemModel(self)
        self.setModel(self.options)
        self.setAccessibleName(name)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.setMinimumContentsLength(8)

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_options(self, options: List[ComboOption], selected: str) -> None:
        """Show options, without emitting a change.

        Args:
            options (List[ComboOption]): The value, label and blocking reason (`None` when it can be chosen) of each
                option.
            selected (str): The value of the chosen option.
        """
        self.logger.debug(
            "Showing %d options in %s, %s chosen.", len(options), self.accessibleName(), selected or "none"
        )
        self.blockSignals(True)
        self.options.clear()
        for value, label, reason in options:
            item = QStandardItem(label)
            item.setData(value, Qt.ItemDataRole.UserRole)
            if reason is not None:
                item.setEnabled(False)
                item.setToolTip(reason)
            self.options.appendRow(item)
        index = self.findData(selected)
        if options and index < 0:
            self.logger.warning(
                "The chosen option %s is not offered in %s: the first option is shown.", selected, self.accessibleName()
            )
        self.setCurrentIndex(max(index, 0))
        self.blockSignals(False)

    def value(self) -> str:
        """Get the value of the chosen option.

        Returns:
            str: The value, empty without option.
        """
        data = self.currentData()
        return str(data) if data is not None else ""
