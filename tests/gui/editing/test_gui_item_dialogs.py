from __future__ import annotations

from datetime import timedelta
from typing import Dict

import pytest
from pydantic import JsonValue
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QComboBox, QDialog, QLineEdit, QListWidget, QPlainTextEdit

from conftest import CRAWLED_AT, build_software
from gui.editing.dialogs.bulk_edit_dialog import BulkEditDialog
from gui.editing.dialogs.field_editors import FieldEditors
from gui.editing.dialogs.item_editor_dialog import ItemEditorDialog
from gui.theme import Theme
from models.cloud.enums import CloudProvider, DeliveryMethod, SoftwareCategory
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.enums import ItemField

PROVIDERS = [CloudProvider.AWS, CloudProvider.CIVO]


@pytest.fixture
def theme(qapp: QApplication) -> Theme:
    return Theme()


class TestFieldEditors:
    def test_each_field_has_its_editor(self, theme: Theme) -> None:
        editors = FieldEditors(theme, list(ItemField))

        assert isinstance(editors.widget(ItemField.NAME), QLineEdit)
        assert isinstance(editors.widget(ItemField.DESCRIPTION), QPlainTextEdit)
        assert isinstance(editors.widget(ItemField.DELIVERY), QComboBox)
        assert isinstance(editors.widget(ItemField.CATEGORIES), QListWidget)
        assert isinstance(editors.widget(ItemField.MARKETPLACE_CATEGORIES), QLineEdit)
        assert set(FieldEditors.TITLES) == set(ItemField)

    def test_values_round_trip(self, theme: Theme) -> None:
        editors = FieldEditors(theme, list(ItemField))
        values: Dict[ItemField, JsonValue] = {
            ItemField.NAME: "Gitea",
            ItemField.DESCRIPTION: "Git hosting",
            ItemField.URL: "https://example.com/gitea",
            ItemField.PUBLISHER: "Gitea Ltd",
            ItemField.DELIVERY: DeliveryMethod.CONTAINER.value,
            ItemField.MARKETPLACE_CATEGORIES: ["DevOps", "Git"],
            ItemField.CATEGORIES: [SoftwareCategory.DEVELOPER_TOOL.value],
        }

        for field, value in values.items():
            editors.set_value(field, value)

        assert {field: editors.value(field) for field in values} == values

    def test_blank_optional_texts_are_none(self, theme: Theme) -> None:
        editors = FieldEditors(theme, [ItemField.URL, ItemField.PUBLISHER, ItemField.NAME])

        editors.set_value(ItemField.URL, None)
        editors.set_value(ItemField.PUBLISHER, "  ")

        assert editors.value(ItemField.URL) is None
        assert editors.value(ItemField.PUBLISHER) is None
        assert editors.value(ItemField.NAME) == ""

    def test_labels_are_split_on_commas(self, theme: Theme) -> None:
        editors = FieldEditors(theme, [ItemField.MARKETPLACE_CATEGORIES])
        editor = editors.widget(ItemField.MARKETPLACE_CATEGORIES)
        assert isinstance(editor, QLineEdit)

        editor.setText(" Security ,, Networking ,")

        assert editors.value(ItemField.MARKETPLACE_CATEGORIES) == ["Security", "Networking"]


class TestItemEditorDialog:
    def test_a_product_form_has_the_product_fields(self, theme: Theme) -> None:
        dialog = ItemEditorDialog[CloudProduct](theme, CloudProduct, PROVIDERS)

        assert dialog.fields == [
            ItemField.NAME,
            ItemField.DESCRIPTION,
            ItemField.URL,
            ItemField.CATEGORIES,
            ItemField.SERVICE_CATEGORIES,
        ]
        assert dialog.windowTitle() == "New product"
        assert dialog.provider_box.isEnabled()
        assert dialog.provider() is CloudProvider.AWS

    def test_an_invalid_form_stays_open_with_the_reasons(self, theme: Theme) -> None:
        dialog = ItemEditorDialog[CloudProduct](theme, CloudProduct, PROVIDERS, provider=CloudProvider.CIVO)

        dialog.accept()

        assert dialog.result_item is None
        assert dialog.result() != QDialog.DialogCode.Accepted
        assert "cannot be empty" in dialog.error_label.text()
        assert dialog.provider() is CloudProvider.CIVO

    def test_a_new_item_is_built_from_the_form(self, theme: Theme) -> None:
        dialog = ItemEditorDialog[CloudProduct](theme, CloudProduct, PROVIDERS)
        dialog.editors.set_value(ItemField.NAME, "Object Storage")
        dialog.editors.set_value(ItemField.DESCRIPTION, "S3 buckets")

        dialog.accept()

        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.result_item == CloudProduct(name="Object Storage", description="S3 buckets", url=None)

    def test_an_edited_item_keeps_its_dates_and_provider(self, theme: Theme) -> None:
        original = build_software("Gitea", ["crm"], [SoftwareCategory.DEVELOPER_TOOL])
        original = original.model_copy(update={"added_at": CRAWLED_AT - timedelta(days=3)})
        dialog = ItemEditorDialog[MarketplaceSoftware](
            theme, MarketplaceSoftware, PROVIDERS, original, CloudProvider.CIVO
        )
        assert dialog.windowTitle() == "Edit software"
        assert not dialog.provider_box.isEnabled()
        assert dialog.editors.value(ItemField.PUBLISHER) == "ACME"
        dialog.editors.set_value(ItemField.PUBLISHER, "Gitea Ltd")

        dialog.accept()

        assert dialog.result_item is not None
        assert dialog.result_item.publisher == "Gitea Ltd"
        assert dialog.result_item.added_at == original.added_at
        assert dialog.result_item.marketplace_categories == original.marketplace_categories == ["crm"]
        assert dialog.provider() is CloudProvider.CIVO

    def test_software_needs_a_category(self, theme: Theme) -> None:
        dialog = ItemEditorDialog[MarketplaceSoftware](theme, MarketplaceSoftware, PROVIDERS)
        dialog.editors.set_value(ItemField.NAME, "Gitea")
        dialog.editors.set_value(ItemField.DESCRIPTION, "Git hosting")

        dialog.accept()

        assert dialog.result_item is None
        assert "categories" in dialog.error_label.text()


class TestBulkEditDialog:
    def test_the_name_is_not_bulk_edited(self, theme: Theme) -> None:
        dialog = BulkEditDialog(theme, list(ItemField), 3)

        assert ItemField.NAME not in dialog.fields
        assert set(dialog.ticks) == set(ItemField) - {ItemField.NAME}

    def test_a_field_is_edited_once_ticked(self, theme: Theme) -> None:
        dialog = BulkEditDialog(theme, [ItemField.NAME, ItemField.DESCRIPTION, ItemField.URL], 2)
        editor = dialog.editors.widget(ItemField.URL)
        assert not editor.isEnabled()

        dialog.ticks[ItemField.URL].setCheckState(Qt.CheckState.Checked)

        assert editor.isEnabled()
        assert dialog.changes() == {ItemField.URL: None}

    def test_nothing_ticked_keeps_the_form_open(self, theme: Theme) -> None:
        dialog = BulkEditDialog(theme, [ItemField.DESCRIPTION], 2)

        dialog.accept()

        assert dialog.result() != QDialog.DialogCode.Accepted
        assert dialog.error_label.text() == "Tick at least one field to change."

    def test_the_ticked_changes_are_applied(self, theme: Theme) -> None:
        dialog = BulkEditDialog(theme, [ItemField.DESCRIPTION, ItemField.PUBLISHER], 2)
        dialog.ticks[ItemField.PUBLISHER].setChecked(True)
        dialog.editors.set_value(ItemField.PUBLISHER, "ACME")
        dialog.editors.set_value(ItemField.DESCRIPTION, "not ticked")

        dialog.accept()

        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.changes() == {ItemField.PUBLISHER: "ACME"}
