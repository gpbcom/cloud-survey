from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Sequence, Type

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from PyQt6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout

# First Party Imports.
from gui.editing.dialogs.field_editors import FieldEditors
from gui.theme import Theme
from models.cloud.dated_item import DatedItem
from models.cloud.enums import CloudProvider
from models.storage.enums import ItemField
from models.taxonomy.enums import CategorySource


class ItemEditorDialog[T: DatedItem](QDialog):
    """The form creating a stored item by hand, or changing one: its provider and the fields which can be edited.

    Attributes:
        MINIMUM_WIDTH (ClassVar[int]): The smallest width of the form.
        model (Type[T]): The model of the item (product or software).
        original (Optional[T]): The changed item, `None` for a new one.
        fields (List[ItemField]): The edited fields: those of the model.
        provider_box (QComboBox): The cloud provider of the item (fixed for a changed item).
        editors (FieldEditors): The editors of the fields.
        error_label (QLabel): Why the form cannot be saved, if it cannot.
        buttons (QDialogButtonBox): Save and Cancel.
        result_item (Optional[T]): The saved item, once the form is accepted.
        logger (Logger): The dialog logger.

    Notes:
        The item is validated by its model when the form is saved:
        an invalid form stays open with the reason. A
        changed item keeps its dates and its other fields.
    """

    MINIMUM_WIDTH: ClassVar[int] = 520

    def __init__(
        self,
        theme: Theme,
        model: Type[T],
        providers: Sequence[CloudProvider],
        original: Optional[T] = None,
        provider: Optional[CloudProvider] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Build the form.

        Args:
            theme (Theme): The application theme.
            model (Type[T]): The model of the item.
            providers (Sequence[CloudProvider]): The cloud providers an item can be created for.
            original (Optional[T]): The changed item, `None` to create one.
            provider (Optional[CloudProvider]): The cloud provider of the changed item, or the default one of a new
                item.
            logger (Optional[Logger]): The dialog logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.model = model
        self.original = original
        self.result_item: Optional[T] = None
        self.fields = [field for field in ItemField if field.value in model.model_fields]
        self.setWindowTitle(
            f"{'Edit' if original else 'New'} {'software' if ItemField.PUBLISHER in self.fields else 'product'}"
        )
        self.setMinimumWidth(self.MINIMUM_WIDTH)
        self.provider_box = QComboBox()
        for choice in providers:
            self.provider_box.addItem(theme.provider_icon(choice), theme.provider_label(choice), choice.value)
        if provider is not None:
            self.provider_box.setCurrentIndex(max(self.provider_box.findData(provider.value), 0))
        self.provider_box.setEnabled(original is None)
        self.editors = FieldEditors(theme, self.fields, self.logger)
        self.error_label = QLabel()
        self.error_label.setObjectName("warning")
        self.error_label.setWordWrap(True)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self._build_layout()
        if original is not None:
            values = original.model_dump(mode="json")
            for field in self.fields:
                self.editors.set_value(field, values[field.value])
        self.logger.debug("Item form built (%s, %d fields).", "edit" if original else "new", len(self.fields))

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_layout(self) -> None:
        """Lay the provider, the fields, the error and the buttons out."""
        form = QFormLayout()
        form.addRow("Provider", self.provider_box)
        for field in self.fields:
            form.addRow(FieldEditors.TITLES[field], self.editors.widget(field))
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addWidget(self.buttons)
        self.logger.debug("Item form laid out.")

    def _build_item(self) -> T:
        """Build the item of the form.

        Returns:
            T: The validated item, with the dates and other fields of the changed item: categories changed by hand
                are pinned (`categories_source` = `user`).

        Raises:
            ValidationError: If a field is invalid.
        """
        values: Dict[str, JsonValue] = self.original.model_dump(mode="json") if self.original is not None else {}
        before = values.get(ItemField.SERVICE_CATEGORIES.value) or []
        values.update({field.value: self.editors.value(field) for field in self.fields})
        if ItemField.SERVICE_CATEGORIES in self.fields and values[ItemField.SERVICE_CATEGORIES.value] != before:
            values["categories_source"] = CategorySource.USER.value
        self.logger.debug("Validating the item of the form.")
        return self.model.model_validate(values)

    ############################
    # Publicly Exposed Methods #
    ############################

    def provider(self) -> CloudProvider:
        """Get the cloud provider chosen for the item.

        Returns:
            CloudProvider: The provider.
        """
        return CloudProvider(self.provider_box.currentData())

    def accept(self) -> None:
        """Save the form when it is valid, else show why it is not and keep it open (Qt override)."""
        try:
            self.result_item = self._build_item()
        except ValidationError as e:
            reasons = "; ".join(f"{'.'.join(map(str, error['loc']))}: {error['msg']}" for error in e.errors())
            self.logger.warning("The item form is invalid: %s", reasons)
            self.error_label.setText(reasons)
            return
        self.logger.info("Item form saved: %s.", getattr(self.result_item, "name", ""))
        super().accept()
