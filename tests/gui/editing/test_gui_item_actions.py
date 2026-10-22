from __future__ import annotations

from datetime import timedelta
from typing import Dict, List, Optional

import pytest
from pydantic import JsonValue
from PyQt6.QtCore import QItemSelectionModel
from PyQt6.QtWidgets import QDialog, QTableView, QWidget
from pytestqt.qtbot import QtBot

from conftest import CRAWLED_AT, build_product, build_software, seed_catalogue, seed_marketplace
from gui.editing.dialogs.bulk_edit_dialog import BulkEditDialog
from gui.editing.dialogs.item_editor_dialog import ItemEditorDialog
from gui.editing.item_actions import ItemActions
from gui.marketplace.model.software_row import SoftwareRow
from gui.marketplace.model.software_table_model import SoftwareTableModel
from gui.product_model.product_row import ProductRow
from gui.product_model.product_table_model import ProductTableModel
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.cloud.enums import CloudProvider, SoftwareCategory
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.enums import ItemField, ItemSort
from models.storage.pages.item_query import ItemQuery
from storage.storage import Storage

pytestmark = pytest.mark.db

PROVIDERS = [CloudProvider.CIVO, CloudProvider.AWS]
ProductActions = ItemActions[CloudProduct, ProductRow]
SoftwareActions = ItemActions[MarketplaceSoftware, SoftwareRow]


def fill_form(dialog: QDialog, values: Dict[ItemField, JsonValue], opened: Optional[List[QDialog]] = None) -> bool:
    """Stand-in for a user filling a form in: the fields are set (and ticked), then the form is accepted."""
    assert isinstance(dialog, (ItemEditorDialog, BulkEditDialog))
    if opened is not None:
        opened.append(dialog)
    for field, value in values.items():
        if isinstance(dialog, BulkEditDialog):
            dialog.ticks[field].setChecked(True)
        dialog.editors.set_value(field, value)
    dialog.accept()
    return dialog.result() == QDialog.DialogCode.Accepted


def select(table: QTableView, rows: List[int]) -> None:
    """Select rows as with Ctrl+click."""
    selection, model = table.selectionModel(), table.model()
    assert selection is not None
    assert model is not None
    selection.clearSelection()
    for row in rows:
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        selection.select(model.index(row, 0), flags)


async def names(storage: Storage) -> List[str]:
    return [stored.item.name for stored in (await storage.catalogues.list(ItemQuery(sort=ItemSort.NAME))).items]


@pytest.fixture
def parent(qtbot: QtBot) -> QWidget:
    widget = QWidget()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def products(qtbot: QtBot, gui_loop: StorageLoop, parent: QWidget) -> ProductActions:
    """The actions of a products table showing every stored product, by name."""
    model = ProductTableModel(Theme(), gui_loop)
    table = QTableView(parent)
    table.setModel(model)
    actions = ProductActions(
        Theme(), table, model, gui_loop, CloudProduct, lambda storage: storage.catalogues, PROVIDERS, parent
    )
    return actions


def show(actions: ProductActions, qtbot: QtBot, total: int) -> None:
    """Read the products of the table, every row of the first page."""
    with qtbot.waitSignal(actions.model.loaded, timeout=5000):
        actions.model.set_query(ItemQuery(sort=ItemSort.NAME))
    assert actions.model.total == total
    qtbot.waitUntil(lambda: all(actions.model.row(row) is not None for row in range(min(total, 2))), timeout=5000)


class TestSelection:
    async def test_the_actions_follow_the_selection(
        self, storage: Storage, products: ProductActions, qtbot: QtBot
    ) -> None:
        await seed_catalogue(storage, CloudProvider.CIVO, [build_product(name) for name in ("A", "B", "C")])
        show(products, qtbot, 3)
        assert products.new_action.isEnabled()
        assert not products.edit_action.isEnabled()
        assert not products.delete_action.isEnabled()

        select(products.table, [0, 2])

        assert products.edit_action.isEnabled()
        assert products.edit_action.text() == "✎  Edit 2…"
        assert products.delete_action.text() == "\U0001f5d1  Delete 2"
        assert products.table.actions() == [products.new_action, products.edit_action, products.delete_action]

    async def test_nothing_selected_does_nothing(self, products: ProductActions, qtbot: QtBot) -> None:
        with qtbot.assertNotEmitted(products.changed), qtbot.assertNotEmitted(products.failed):
            products.edit()
            products.delete()


class TestCreate:
    async def test_an_item_is_created_by_hand(
        self, storage: Storage, products: ProductActions, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        values: Dict[ItemField, JsonValue] = {ItemField.NAME: "Object Storage", ItemField.DESCRIPTION: "S3"}
        monkeypatch.setattr(products, "_open", lambda dialog: fill_form(dialog, values))

        with qtbot.waitSignal(products.changed, timeout=5000) as changed:
            products.create()

        assert str(changed.args[0]).endswith("created for Civo.")
        assert await names(storage) == ["Object Storage"]

    async def test_a_cancelled_form_creates_nothing(
        self, storage: Storage, products: ProductActions, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(products, "_open", lambda dialog: False)

        with qtbot.assertNotEmitted(products.changed, wait=200):
            products.create()

        assert await names(storage) == []


class TestEdit:
    async def test_one_selected_item_is_edited_in_its_form(
        self, storage: Storage, products: ProductActions, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await seed_catalogue(storage, CloudProvider.CIVO, [build_product(name) for name in ("A", "B")])
        show(products, qtbot, 2)
        select(products.table, [1])
        monkeypatch.setattr(products, "_open", lambda dialog: fill_form(dialog, {ItemField.DESCRIPTION: "Edited"}))

        with qtbot.waitSignal(products.changed, timeout=5000) as changed:
            products.edit()

        stored = (await storage.catalogues.list(ItemQuery(search="B"))).items[0]
        assert changed.args == [f"Item {stored.id} saved."]
        assert stored.item.description == "Edited"
        assert stored.item.added_at == CRAWLED_AT - timedelta(days=7), "the dates are kept"

    async def test_several_selected_items_are_edited_at_once(
        self, storage: Storage, products: ProductActions, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await seed_catalogue(storage, CloudProvider.CIVO, [build_product(name) for name in ("A", "B", "C")])
        show(products, qtbot, 3)
        select(products.table, [0, 2])
        opened: List[QDialog] = []
        monkeypatch.setattr(
            products, "_open", lambda dialog: fill_form(dialog, {ItemField.DESCRIPTION: "Shared"}, opened)
        )

        with qtbot.waitSignal(products.changed, timeout=5000) as changed:
            products.edit()

        assert changed.args == ["2 items changed."]
        assert isinstance(opened[0], BulkEditDialog)
        assert opened[0].fields == [
            ItemField.DESCRIPTION,
            ItemField.URL,
            ItemField.CATEGORIES,
            ItemField.SERVICE_CATEGORIES,
        ]
        stored = (await storage.catalogues.list(ItemQuery(sort=ItemSort.NAME))).items
        assert [item.item.description for item in stored] == ["Shared", "B description", "Shared"]

    async def test_a_refused_change_is_reported(
        self, storage: Storage, products: ProductActions, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await seed_catalogue(storage, CloudProvider.CIVO, [build_product(name) for name in ("A", "B")])
        show(products, qtbot, 2)
        select(products.table, [0, 1])
        monkeypatch.setattr(products, "_open", lambda dialog: fill_form(dialog, {ItemField.DESCRIPTION: "x"}))

        async with storage.catalogues.writer(CloudProvider.CIVO, CRAWLED_AT, 60.0):
            with qtbot.waitSignal(products.failed, timeout=5000) as failed:
                products.edit()

        assert "civo" in str(failed.args[0]).casefold()
        assert {item.item.description for item in (await storage.catalogues.list(ItemQuery())).items} != {"x"}


class TestDelete:
    async def test_the_selected_items_are_deleted_once_confirmed(
        self, storage: Storage, products: ProductActions, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await seed_catalogue(storage, CloudProvider.CIVO, [build_product(name) for name in ("A", "B", "C")])
        show(products, qtbot, 3)
        select(products.table, [0, 1])
        monkeypatch.setattr(products, "_confirm", lambda count: count == 2)

        with qtbot.waitSignal(products.changed, timeout=5000) as changed:
            products.delete()

        assert changed.args == ["2 items deleted."]
        assert await names(storage) == ["C"]

    async def test_a_cancelled_deletion_keeps_the_items(
        self, storage: Storage, products: ProductActions, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await seed_catalogue(storage, CloudProvider.CIVO, [build_product("A")])
        show(products, qtbot, 1)
        select(products.table, [0])
        monkeypatch.setattr(products, "_confirm", lambda count: False)

        with qtbot.assertNotEmitted(products.changed, wait=200):
            products.delete()

        assert await names(storage) == ["A"]

    async def test_every_row_is_deleted_even_those_not_read(
        self,
        storage: Storage,
        products: ProductActions,
        qtbot: QtBot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await seed_catalogue(storage, CloudProvider.CIVO, [build_product(f"P{number}") for number in range(7)])
        await seed_catalogue(storage, CloudProvider.AWS, [build_product("Kept")])
        monkeypatch.setattr(ProductTableModel, "PAGE_SIZE", 2)
        monkeypatch.setattr(ProductTableModel, "MAX_PAGES", 1)
        with qtbot.waitSignal(products.model.loaded, timeout=5000):
            products.model.set_query(ItemQuery(sort=ItemSort.NAME, providers=[CloudProvider.CIVO]))
        products.table.selectAll()
        assert products.model.loaded_id(6) is None, "the last page is not read"
        monkeypatch.setattr(products, "_confirm", lambda count: count == 7)

        with qtbot.waitSignal(products.changed, timeout=5000) as changed:
            products.delete()

        assert changed.args == ["7 items deleted."]
        assert await names(storage) == ["Kept"]


async def test_software_labels_are_bulk_edited(
    qtbot: QtBot, storage: Storage, gui_loop: StorageLoop, parent: QWidget, monkeypatch: pytest.MonkeyPatch
) -> None:
    software = [build_software(name, ["crm"], [SoftwareCategory.END_USER_SOFTWARE]) for name in "AB"]
    await seed_marketplace(storage, CloudProvider.CIVO, software)
    model = SoftwareTableModel(Theme(), gui_loop)
    table = QTableView(parent)
    table.setModel(model)
    actions = SoftwareActions(
        Theme(), table, model, gui_loop, MarketplaceSoftware, lambda storage: storage.marketplaces, PROVIDERS, parent
    )
    with qtbot.waitSignal(model.loaded, timeout=5000):
        model.set_query(ItemQuery(sort=ItemSort.NAME))
    table.selectAll()
    labels: JsonValue = ["ERP", "HRIS"]
    monkeypatch.setattr(actions, "_open", lambda dialog: fill_form(dialog, {ItemField.MARKETPLACE_CATEGORIES: labels}))

    with qtbot.waitSignal(actions.changed, timeout=5000):
        actions.edit()

    stored = (await storage.marketplaces.list(ItemQuery())).items
    assert [item.item.marketplace_categories for item in stored] == [["ERP", "HRIS"]] * 2


def test_the_confirmation_names_the_count() -> None:
    assert ItemActions.DELETE_CONFIRMATION.format(count=1234).startswith("Delete the 1,234 selected items")
