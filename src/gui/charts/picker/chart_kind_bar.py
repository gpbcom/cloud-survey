from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QHBoxLayout, QToolButton, QWidget

KindOption = Tuple[str, str, str]


class ChartKindBar(QWidget):
    """Segmented buttons choosing the kind of chart: line, area, bubble, heatmap or mix.

    Attributes:
        kind_changed (pyqtSignal): Emitted with the value of the chosen kind, when the user chooses one.
        group (QButtonGroup): The exclusive group of the buttons.
        buttons (Dict[str, QToolButton]): The button of each kind value.
        logger (Logger): The bar logger.
    """

    kind_changed = pyqtSignal(str)

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Build the bar, without buttons.

        Args:
            logger (Optional[Logger]): The bar logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: Dict[str, QToolButton] = {}
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(0)
        self.setAccessibleName("Chart kind")

    ############################
    # Internal Helpers Methods #
    ############################

    def _on_clicked(self, value: str) -> None:
        """Report the kind chosen by the user.

        Args:
            value (str): The kind value.
        """
        self.logger.info("Chart kind %s chosen.", value)
        self.kind_changed.emit(value)

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_kinds(self, kinds: List[KindOption], selected: str) -> None:
        """Show one button per kind, without emitting a change.

        Args:
            kinds (List[KindOption]): The value, label and tooltip of each kind.
            selected (str): The value of the chosen kind.
        """
        self.logger.debug("Showing %d chart kinds, %s chosen.", len(kinds), selected)
        if selected not in {value for value, _, _ in kinds}:
            self.logger.warning("The chosen chart kind %s is not offered: no button is checked.", selected)
        if list(self.buttons) != [value for value, _, _ in kinds]:
            self.logger.debug("Chart kind buttons rebuilt: %d buttons.", len(kinds))
            for button in self.buttons.values():
                self.group.removeButton(button)
                button.deleteLater()
            self.buttons = {}
            for value, label, tip in kinds:
                button = QToolButton()
                button.setObjectName("segment")
                button.setText(label)
                button.setToolTip(tip)
                button.setCheckable(True)
                button.setAccessibleName(f"{label} chart")
                button.clicked.connect(lambda checked, chosen=value: self._on_clicked(chosen))
                self.group.addButton(button)
                self.row.addWidget(button)
                self.buttons[value] = button
        for value, button in self.buttons.items():
            button.blockSignals(True)
            button.setChecked(value == selected)
            button.blockSignals(False)
        self.setVisible(len(kinds) > 1)

    def kind(self) -> str:
        """Get the chosen kind.

        Returns:
            str: Its value, empty without buttons.
        """
        return next((value for value, button in self.buttons.items() if button.isChecked()), "")
