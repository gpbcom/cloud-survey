from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QListWidget, QListWidgetItem


class ValueChecklist(QListWidget):
    """A list of checkable values (e.g. software kinds): none checked means any value.

    Attributes:
        MAXIMUM_HEIGHT (ClassVar[int]): The largest height of the list, in pixels (it scrolls beyond).
        changed (pyqtSignal): Emitted when a value is checked or unchecked.
        logger (Logger): The list logger.
    """

    MAXIMUM_HEIGHT: ClassVar[int] = 150

    changed = pyqtSignal()

    def __init__(self, labels: Dict[str, str], logger: Optional[Logger] = None) -> None:
        """Build the list, every value unchecked.

        Args:
            labels (Dict[str, str]): The label of each value.
            logger (Optional[Logger]): The list logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        for value, label in labels.items():
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.addItem(item)
        self.setMaximumHeight(self.MAXIMUM_HEIGHT)
        self.itemChanged.connect(self._on_item_changed)
        self.logger.debug("Checklist of %d values built.", len(labels))

    ############################
    # Internal Helpers Methods #
    ############################

    def _items(self) -> List[QListWidgetItem]:
        """Get the items of the list.

        Returns:
            List[QListWidgetItem]: The items, in their order.
        """
        return [item for row in range(self.count()) if (item := self.item(row)) is not None]

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """Tell that the checked values changed.

        Args:
            item (QListWidgetItem): The changed item.
        """
        self.logger.debug("Value %s %s.", item.text(), "checked" if item.checkState() else "unchecked")
        self.changed.emit()

    ############################
    # Publicly Exposed Methods #
    ############################

    def checked(self) -> List[str]:
        """Get the checked values.

        Returns:
            List[str]: The values, in the order of the list.
        """
        return [
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in self._items()
            if item.checkState() == Qt.CheckState.Checked
        ]

    def set_checked(self, values: Sequence[str]) -> None:
        """Check some values only, telling once.

        Args:
            values (Sequence[str]): The values to check, the others being unchecked.
        """
        chosen = set(values)
        self.blockSignals(True)
        for item in self._items():
            checked = item.data(Qt.ItemDataRole.UserRole) in chosen
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.blockSignals(False)
        self.logger.debug("%d values checked.", len(chosen))
        self.changed.emit()
