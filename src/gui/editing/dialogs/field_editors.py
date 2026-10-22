from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Union

# Third Party Imports.
from pydantic import JsonValue
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QWidget

# First Party Imports.
from gui.theme import Theme
from models.cloud.enums import DeliveryMethod, SoftwareCategory
from models.storage.enums import ItemField
from models.taxonomy.nodes.taxonomy import Taxonomy
from taxonomy.seed_loader import TaxonomySeedLoader

Editor = Union[QLineEdit, QPlainTextEdit, QComboBox, QListWidget]


class FieldEditors:
    """The editors of the fields of a stored item which can be changed by hand, read and written as JSON values.

    Attributes:
        LABEL_SEPARATOR (ClassVar[str]): The separator of the marketplace categories typed in one line.
        TITLES (ClassVar[Dict[ItemField, str]]): The title of each field.
        theme (Theme): The application theme, for the labels of the enumerations.
        taxonomy (Optional[Taxonomy]): The unified taxonomy, read when its categories are edited.
        editors (Dict[ItemField, Editor]): The editor of each field.
        logger (Logger): The editors logger.
    """

    LABEL_SEPARATOR: ClassVar[str] = ","
    TITLES: ClassVar[Dict[ItemField, str]] = {
        ItemField.NAME: "Name",
        ItemField.DESCRIPTION: "Description",
        ItemField.URL: "Page",
        ItemField.PUBLISHER: "Publisher",
        ItemField.DELIVERY: "Delivery",
        ItemField.MARKETPLACE_CATEGORIES: "Marketplace categories",
        ItemField.CATEGORIES: "Meant for",
        ItemField.SERVICE_CATEGORIES: "Categories",
    }

    def __init__(self, theme: Theme, fields: Sequence[ItemField], logger: Optional[Logger] = None) -> None:
        """Build the editors of some fields.

        Args:
            theme (Theme): The application theme.
            fields (Sequence[ItemField]): The edited fields, in their order.
            logger (Optional[Logger]): The editors logger.
        """
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.taxonomy: Optional[Taxonomy] = None
        if ItemField.SERVICE_CATEGORIES in fields:
            self.taxonomy = TaxonomySeedLoader(self.logger).load_taxonomy()
        self.editors: Dict[ItemField, Editor] = {field: self._editor(field) for field in fields}
        self.logger.debug("Editors of %d fields built.", len(self.editors))

    ############################
    # Internal Helpers Methods #
    ############################

    def _checklist(self, labels: Dict[str, str]) -> QListWidget:
        """Build a list of checkable values.

        Args:
            labels (Dict[str, str]): The label of each value.

        Returns:
            QListWidget: The list, every value unchecked.
        """
        box = QListWidget()
        for value, label in labels.items():
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            box.addItem(item)
        box.setMaximumHeight(140)
        self.logger.debug("Checkable list of %d values built.", len(labels))
        return box

    def _editor(self, field: ItemField) -> Editor:
        """Build the editor of a field.

        Args:
            field (ItemField): The field.

        Returns:
            Editor: Its editor, empty.
        """
        self.logger.debug("Building the editor of the %s.", field.value)
        match field:
            case ItemField.DESCRIPTION:
                description = QPlainTextEdit()
                description.setMaximumHeight(110)
                return description
            case ItemField.DELIVERY:
                delivery = QComboBox()
                for method in DeliveryMethod:
                    delivery.addItem(self.theme.delivery_label(method), method.value)
                return delivery
            case ItemField.CATEGORIES:
                return self._checklist(
                    {category.value: self.theme.category_label(category) for category in SoftwareCategory}
                )
            case ItemField.SERVICE_CATEGORIES if self.taxonomy is not None:
                taxonomy = self.taxonomy
                return self._checklist(
                    {
                        node.slug: f"{domain.name_en} > {node.name_en}"
                        for domain in taxonomy.domains()
                        for node in taxonomy.children(domain.slug)
                        if not node.hidden
                    }
                )
            case ItemField.MARKETPLACE_CATEGORIES:
                labels = QLineEdit()
                labels.setPlaceholderText("Comma-separated categories")
                return labels
            case _:
                return QLineEdit()

    ############################
    # Publicly Exposed Methods #
    ############################

    def widget(self, field: ItemField) -> QWidget:
        """Get the editor of a field.

        Args:
            field (ItemField): The field.

        Returns:
            QWidget: Its editor.
        """
        return self.editors[field]

    def value(self, field: ItemField) -> JsonValue:
        """Read the value of a field.

        Args:
            field (ItemField): The field.

        Returns:
            JsonValue: The value as JSON: a text (`None` when blank, but for the name and description), the
                delivery value, or the list of the marketplace categories or checked values.
        """
        editor = self.editors[field]
        match editor:
            case QPlainTextEdit():
                return editor.toPlainText().strip()
            case QComboBox():
                delivery: JsonValue = editor.currentData()
                return delivery
            case QListWidget():
                items = [editor.item(row) for row in range(editor.count())]
                checked: List[JsonValue] = [
                    item.data(Qt.ItemDataRole.UserRole)
                    for item in items
                    if item is not None and item.checkState() == Qt.CheckState.Checked
                ]
                return checked
            case _ if field is ItemField.MARKETPLACE_CATEGORIES:
                labels: List[JsonValue] = [
                    label.strip() for label in editor.text().split(self.LABEL_SEPARATOR) if label.strip()
                ]
                return labels
            case _:
                text = editor.text().strip()
                return text or (None if field in (ItemField.URL, ItemField.PUBLISHER) else "")

    def set_value(self, field: ItemField, value: JsonValue) -> None:
        """Write the value of a field.

        Args:
            field (ItemField): The field.
            value (JsonValue): The value as JSON (see `value`).
        """
        editor = self.editors[field]
        self.logger.debug("Showing the %s of the item.", field.value)
        match editor:
            case QPlainTextEdit():
                editor.setPlainText(str(value or ""))
            case QComboBox():
                editor.setCurrentIndex(max(editor.findData(value), 0))
            case QListWidget():
                wanted = set(value) if isinstance(value, list) else set()
                for row in range(editor.count()):
                    item = editor.item(row)
                    if item is not None:
                        checked = item.data(Qt.ItemDataRole.UserRole) in wanted
                        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            case _ if isinstance(value, list):
                editor.setText(f"{self.LABEL_SEPARATOR} ".join(str(label) for label in value))
            case _:
                editor.setText(str(value or ""))
