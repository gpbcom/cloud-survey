from __future__ import annotations

# Standard Library Imports.
import json
from enum import StrEnum
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Set

# Third Party Imports.
from pydantic import BaseModel, ValidationError
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from gui.catalogues.rows.curated_row_model import CuratedRowValues
from models.curated.enums import RecordOrigin


class RowEditorDialog(QDialog):
    """The form creating or changing a row of a curated catalogue: its key, rank, content and note.

    Attributes:
        MINIMUM_SIZE (ClassVar[List[int]]): The smallest width and height of the form.
        HIDDEN (ClassVar[Set[str]]): The fields set by the editor, never typed: where the row comes from, whether a
            person changed it, when a resolver checked it.
        JSON_FIELDS (ClassVar[Set[str]]): The fields typed as JSON (the entry as its catalogue writes it).
        MAXIMUM (ClassVar[int]): The largest number a number field takes.
        model (type[BaseModel]): The model of the row, which validates the form.
        original (CuratedRowValues): The changed row, or the values a new row starts from.
        lines (Dict[str, QLineEdit]): The editors of the text fields.
        numbers (Dict[str, QSpinBox]): The editors of the number fields.
        choices (Dict[str, QComboBox]): The editors of the fields taking one of a list of values.
        texts (Dict[str, QPlainTextEdit]): The editors of the long texts and the JSON fields.
        error_label (QLabel): Why the form cannot be saved, if it cannot.
        buttons (QDialogButtonBox): Save and Cancel.
        result_values (Optional[CuratedRowValues]): The saved row, once the form is accepted.
        logger (Logger): The dialog logger.

    Notes:
        The row is validated by its model when the form is saved: an invalid form (or invalid JSON) stays open with
        the reason. A saved row is marked as changed by a person (`edited`, origin `user`), so that a seed never
        writes over it. Whether the catalogue it belongs to stays valid is checked when it is written.
    """

    MINIMUM_SIZE: ClassVar[List[int]] = [640, 520]
    HIDDEN: ClassVar[Set[str]] = {"origin", "edited", "checked_at"}
    JSON_FIELDS: ClassVar[Set[str]] = {"body"}
    MAXIMUM: ClassVar[int] = 1_000_000

    def __init__(
        self,
        title: str,
        model: type[BaseModel],
        original: CuratedRowValues,
        logger: Optional[Logger] = None,
    ) -> None:
        """Build the form.

        Args:
            title (str): The title of the window.
            model (type[BaseModel]): The model of the row.
            original (CuratedRowValues): The changed row, or the values a new row starts from.
            logger (Optional[Logger]): The dialog logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.model = model
        self.original = dict(original)
        self.result_values: Optional[CuratedRowValues] = None
        self.lines: Dict[str, QLineEdit] = {}
        self.numbers: Dict[str, QSpinBox] = {}
        self.choices: Dict[str, QComboBox] = {}
        self.texts: Dict[str, QPlainTextEdit] = {}
        self.setWindowTitle(title)
        self.setMinimumSize(*self.MINIMUM_SIZE)
        self.error_label = QLabel()
        self.error_label.setObjectName("warning")
        self.error_label.setWordWrap(True)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self._build_layout()
        self.logger.debug("Curated row form built (%s, %d fields).", model.__name__, len(model.model_fields))

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_layout(self) -> None:
        """Lay an editor per field out, filled with the row's values."""
        form = QFormLayout()
        for name, field in self.model.model_fields.items():
            if name in self.HIDDEN:
                continue
            value = self.original.get(name)
            annotation = field.annotation
            widget: QWidget
            if name in self.JSON_FIELDS or name == "note":
                editor = QPlainTextEdit()
                text = json.dumps(value, ensure_ascii=False, indent=2) if name in self.JSON_FIELDS else value or ""
                editor.setPlainText(str(text))
                self.texts[name] = widget = editor
            elif isinstance(annotation, type) and issubclass(annotation, StrEnum):
                box = QComboBox()
                for member in annotation:
                    box.addItem(member.value, member.value)
                box.setCurrentIndex(max(box.findData(value), 0))
                self.choices[name] = widget = box
            elif annotation is int:
                spin = QSpinBox()
                spin.setRange(0, self.MAXIMUM)
                spin.setValue(value if isinstance(value, int) else 0)
                self.numbers[name] = widget = spin
            else:
                self.lines[name] = widget = QLineEdit(str(value) if value is not None else "")
            label = QLabel(name.replace("_", " ").capitalize())
            label.setToolTip(field.description or "")
            form.addRow(label, widget)
        layout = QVBoxLayout(self)
        layout.addLayout(form, 1)
        layout.addWidget(self.error_label)
        layout.addWidget(self.buttons)

    def _values(self) -> CuratedRowValues:
        """Read the values of the form.

        Returns:
            CuratedRowValues: The row: the original one with the typed values, marked as changed by a person.

        Raises:
            ValueError: If a JSON field is not valid JSON.
        """
        values: CuratedRowValues = dict(self.original)
        for name, line in self.lines.items():
            text = line.text().strip()
            values[name] = text or None
        for name, spin in self.numbers.items():
            values[name] = spin.value()
        for name, box in self.choices.items():
            values[name] = box.currentData()
        for name, editor in self.texts.items():
            text = editor.toPlainText().strip()
            if name in self.JSON_FIELDS:
                values[name] = json.loads(text)
            else:
                values[name] = text or None
        values["edited"] = True
        values["origin"] = RecordOrigin.USER.value
        return values

    ############################
    # Publicly Exposed Methods #
    ############################

    def accept(self) -> None:
        """Save the form when it is valid, else show why it is not and keep it open (Qt override)."""
        try:
            row = self.model.model_validate(self._values())
        except json.JSONDecodeError as e:
            self.logger.warning("The curated row form holds invalid JSON: %s", e)
            self.error_label.setText(f"Invalid JSON: {e}")
            return
        except ValidationError as e:
            reasons = "; ".join(f"{'.'.join(map(str, error['loc']))}: {error['msg']}" for error in e.errors())
            self.logger.warning("The curated row form is invalid: %s", reasons)
            self.error_label.setText(reasons)
            return
        self.result_values = row.model_dump(mode="json")
        self.logger.info("Curated row form saved (%s).", self.model.__name__)
        super().accept()
