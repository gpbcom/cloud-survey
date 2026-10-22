from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Sequence

# Third Party Imports.
from pydantic import JsonValue
from PyQt6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QLabel, QVBoxLayout

# First Party Imports.
from gui.editing.dialogs.field_editors import FieldEditors
from gui.theme import Theme
from models.storage.enums import ItemField


class BulkEditDialog(QDialog):
    """The form changing some fields of several stored items at once: only the ticked fields are changed.

    Attributes:
        MINIMUM_WIDTH (ClassVar[int]): The smallest width of the form.
        count (int): The number of changed items.
        fields (Sequence[ItemField]): The fields which can be changed (the name is not: it identifies an item).
        editors (FieldEditors): The editors of the fields.
        ticks (Dict[ItemField, QCheckBox]): Whether each field is changed.
        error_label (QLabel): Why the form cannot be saved, if it cannot.
        buttons (QDialogButtonBox): Apply and Cancel.
        logger (Logger): The dialog logger.
    """

    MINIMUM_WIDTH: ClassVar[int] = 560

    def __init__(self, theme: Theme, fields: Sequence[ItemField], count: int, logger: Optional[Logger] = None) -> None:
        """Build the form.

        Args:
            theme (Theme): The application theme.
            fields (Sequence[ItemField]): The fields of the items.
            count (int): The number of changed items.
            logger (Optional[Logger]): The dialog logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.count = count
        self.fields = [field for field in fields if field is not ItemField.NAME]
        self.setWindowTitle(f"Edit {count:,} items")
        self.setMinimumWidth(self.MINIMUM_WIDTH)
        self.editors = FieldEditors(theme, self.fields, self.logger)
        self.ticks: Dict[ItemField, QCheckBox] = {field: QCheckBox(FieldEditors.TITLES[field]) for field in self.fields}
        self.error_label = QLabel()
        self.error_label.setObjectName("warning")
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        apply_button = self.buttons.button(QDialogButtonBox.StandardButton.Apply)
        if apply_button is not None:
            apply_button.clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        for field, tick in self.ticks.items():
            editor = self.editors.widget(field)
            editor.setEnabled(False)
            tick.toggled.connect(editor.setEnabled)
        self._build_layout()
        self.logger.debug("Bulk edit form of %d items built (%d fields).", count, len(self.fields))

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_layout(self) -> None:
        """Lay a row per field out: whether it is changed, and its new value."""
        grid = QGridLayout()
        for row, field in enumerate(self.fields):
            grid.addWidget(self.ticks[field], row, 0)
            grid.addWidget(self.editors.widget(field), row, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Tick the fields to change in the {self.count:,} selected items."))
        layout.addLayout(grid)
        layout.addWidget(self.error_label)
        layout.addWidget(self.buttons)
        self.logger.debug("Bulk edit form laid out.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def changes(self) -> Dict[ItemField, JsonValue]:
        """Get the new value of each ticked field.

        Returns:
            Dict[ItemField, JsonValue]: The changes, as JSON values.
        """
        changes = {field: self.editors.value(field) for field, tick in self.ticks.items() if tick.isChecked()}
        self.logger.debug("Bulk changes: %s.", ", ".join(field.value for field in changes))
        return changes

    def accept(self) -> None:
        """Apply the changes when a field is ticked, else say so and keep the form open (Qt override)."""
        if not self.changes():
            self.logger.warning("No field ticked in the bulk edit form.")
            self.error_label.setText("Tick at least one field to change.")
            return
        self.logger.info("Bulk edit of %d items applied.", self.count)
        super().accept()
