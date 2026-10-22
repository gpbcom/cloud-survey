from __future__ import annotations

# Standard Library Imports.
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
    """

    def __init__(self, name: str) -> None:
        """Build an empty combo box.

        Args:
            name (str): What the combo box chooses, for the screen readers.
        """
        super().__init__()
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
        self.blockSignals(True)
        self.options.clear()
        for value, label, reason in options:
            item = QStandardItem(label)
            item.setData(value, Qt.ItemDataRole.UserRole)
            if reason is not None:
                item.setEnabled(False)
                item.setToolTip(reason)
            self.options.appendRow(item)
        self.setCurrentIndex(max(self.findData(selected), 0))
        self.blockSignals(False)

    def value(self) -> str:
        """Get the value of the chosen option.

        Returns:
            str: The value, empty without option.
        """
        data = self.currentData()
        return str(data) if data is not None else ""
