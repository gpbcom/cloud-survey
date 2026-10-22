from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import pytest
from PyQt6.QtWidgets import QDialog, QWidget
from pytestqt.qtbot import QtBot

from conftest import CRAWLED_AT, build_product, build_software, seed_catalogue, seed_marketplace
from gui.marketplace.model.software_row import SoftwareRow
from gui.marketplace.model.software_table_model import SoftwareTableModel
from gui.product_model.product_row import ProductRow
from gui.product_model.product_table_model import ProductTableModel
from gui.selection.bulk.bulk_select_dialog import BulkSelectDialog
from gui.selection.bulk.selection_actions import SelectionActions
from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from models.cloud.enums import CloudProvider, SoftwareCategory
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.enums import DeletedState, ExportFormat, ItemSort, SelectionAction
from models.storage.pages.item_query import ItemQuery
from storage.storage import Storage

pytestmark = pytest.mark.db

PROVIDERS = [CloudProvider.CIVO, CloudProvider.AWS, CloudProvider.SCALEWAY]
ProductSelection = SelectionActions[CloudProduct, ProductRow]


def choose(
    qtbot: QtBot, dialog: QDialog, action: SelectionAction, providers: Optional[List[CloudProvider]] = None
) -> bool:
    """Stand-in for a user choosing items in the dialog, waiting for their count, then an action."""
    assert isinstance(dialog, BulkSelectDialog)
    if providers is not None:
        dialog.tree.set_checked(providers)
    qtbot.waitUntil(lambda: dialog.count is not None, timeout=5000)
    dialog.choose(action)
    return dialog.result() == QDialog.DialogCode.Accepted


def remember[V](seen: List[V], value: V, answer: bool) -> bool:
    """Stand-in for a user answer, remembering what was asked."""
    seen.append(value)
    return answer


async def seed(storage: Storage) -> None:
    await seed_catalogue(storage, CloudProvider.CIVO, [build_product(name) for name in ("Alpha", "Beta")])
    await seed_catalogue(storage, CloudProvider.AWS, [build_product("Gamma"), build_product("Old", deleted=True)])


@pytest.fixture
def parent(qtbot: QtBot) -> QWidget:
    widget = QWidget()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def products(gui_loop: StorageLoop, parent: QWidget) -> ProductSelection:
    model = ProductTableModel(Theme(), gui_loop)
    model.query = ItemQuery(sort=ItemSort.NAME)
    return ProductSelection(Theme(), model, gui_loop, lambda storage: storage.catalogues, PROVIDERS, parent)


def dialog_of(gui_loop: StorageLoop, base: ItemQuery) -> BulkSelectDialog[CloudProduct]:
    return BulkSelectDialog[CloudProduct](Theme(), gui_loop, lambda storage: storage.catalogues, PROVIDERS, base, False)


class TestDialog:
    async def test_the_matching_items_are_counted_live(
        self, qtbot: QtBot, storage: Storage, gui_loop: StorageLoop
    ) -> None:
        await seed(storage)
        dialog = dialog_of(gui_loop, ItemQuery())
        qtbot.addWidget(dialog)
        qtbot.waitUntil(lambda: dialog.count == 3, timeout=5000)
        assert dialog.count_label.text() == "3 products match"
        assert dialog.delete_button.text() == "Delete 3…"
        assert dialog.category_list is None, "no software checklist for products"
        assert dialog.category_tree is None, "no category criterion without a taxonomy"

        dialog.tree.set_checked([CloudProvider.CIVO])
        qtbot.waitUntil(lambda: dialog.count == 2, timeout=5000)
        dialog.deleted_box.setCurrentIndex(dialog.deleted_box.findData(DeletedState.DELETED.value))
        dialog.tree.check_all(True)
        qtbot.waitUntil(lambda: dialog.count == 1, timeout=5000)
        assert dialog.query().deleted.known is True
        dialog.search_box.setText("nothing like this")
        qtbot.waitUntil(lambda: dialog.count == 0, timeout=5000)
        assert not dialog.export_button.isEnabled()

    def test_no_provider_matches_nothing(self, qtbot: QtBot, gui_loop: StorageLoop) -> None:
        dialog = dialog_of(gui_loop, ItemQuery())
        qtbot.addWidget(dialog)

        dialog.tree.check_all(False)
        qtbot.waitUntil(lambda: dialog.count == 0, timeout=5000)
        dialog.choose(SelectionAction.DELETE)

        assert dialog.chosen is None
        assert dialog.count_label.text() == "Check at least one cloud provider."

    async def test_nothing_is_exported_or_deleted_before_it_is_counted(
        self, qtbot: QtBot, storage: Storage, gui_loop: StorageLoop
    ) -> None:
        await seed(storage)
        dialog = dialog_of(gui_loop, ItemQuery())
        qtbot.addWidget(dialog)
        qtbot.waitUntil(lambda: dialog.count == 3, timeout=5000)

        dialog.search_box.setText("Alpha")
        assert dialog.count is None, "the former count is forgotten at once"
        assert not dialog.delete_button.isEnabled()
        dialog.choose(SelectionAction.DELETE)

        assert dialog.chosen is None
        assert dialog.count_label.text() == "Wait for the count of the matching items."
        qtbot.waitUntil(lambda: dialog.count == 1, timeout=5000)
        dialog.choose(SelectionAction.DELETE)
        assert dialog.chosen is SelectionAction.DELETE

    def test_the_dialog_starts_from_the_table_filters(self, qtbot: QtBot, gui_loop: StorageLoop) -> None:
        base = ItemQuery(
            providers=[CloudProvider.AWS],
            search="db",
            include_deleted=True,
            service_categories=["relational-database"],
            sort=ItemSort.ADDED_AT,
            descending=True,
        )
        dialog = BulkSelectDialog[MarketplaceSoftware](
            Theme(), gui_loop, lambda storage: storage.marketplaces, PROVIDERS, base, True, taxonomy=TaxonomyCache()
        )
        qtbot.addWidget(dialog)

        query = dialog.query()

        assert dialog.tree.checked() == [CloudProvider.AWS]
        assert dialog.category_tree is not None
        assert dialog.category_tree.picked() == ["relational-database"]
        assert (query.search, query.include_deleted) == ("db", True)
        assert query.service_categories == ["relational-database"]
        assert (query.sort, query.descending) == (ItemSort.ADDED_AT, True), "the order of the table is kept"

    def test_the_picked_categories_filter_the_items(self, qtbot: QtBot, gui_loop: StorageLoop) -> None:
        dialog = BulkSelectDialog[MarketplaceSoftware](
            Theme(),
            gui_loop,
            lambda storage: storage.marketplaces,
            PROVIDERS,
            ItemQuery(),
            True,
            taxonomy=TaxonomyCache(),
        )
        qtbot.addWidget(dialog)
        assert dialog.category_tree is not None
        assert dialog.query().service_categories == []

        dialog.category_tree.set_picked(["data-analytics"])

        assert dialog.query().service_categories == ["data-analytics"], "a fully checked domain is picked whole"
        qtbot.waitUntil(lambda: dialog.count == 0, timeout=5000)


class TestActions:
    async def test_the_chosen_items_are_shown_in_the_table(
        self, qtbot: QtBot, storage: Storage, products: ProductSelection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await seed(storage)
        monkeypatch.setattr(
            products, "_open", lambda dialog: choose(qtbot, dialog, SelectionAction.FILTER, [CloudProvider.AWS])
        )

        with qtbot.waitSignal(products.filter_requested, timeout=5000) as requested:
            products.select()

        [query] = requested.args
        assert isinstance(query, ItemQuery)
        assert query.providers == [CloudProvider.AWS]

    async def test_the_chosen_items_are_exported(
        self,
        qtbot: QtBot,
        storage: Storage,
        products: ProductSelection,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        await seed(storage)
        target = tmp_path / "chosen"
        monkeypatch.setattr(products, "_open", lambda dialog: choose(qtbot, dialog, SelectionAction.EXPORT))
        monkeypatch.setattr(products, "_save_path", lambda count: products._export_path(target, "JSON (*.json)"))

        with qtbot.waitSignal(products.changed, timeout=5000) as changed:
            products.select()

        assert changed.args == [f"3 items exported to {target}.json."]
        names = [item["name"] for item in json.loads((tmp_path / "chosen.json").read_text(encoding="utf-8"))]
        assert names == ["Alpha", "Beta", "Gamma"]

    async def test_the_chosen_items_are_deleted_once_confirmed(
        self, qtbot: QtBot, storage: Storage, products: ProductSelection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await seed(storage)
        asked: List[int] = []
        monkeypatch.setattr(
            products, "_open", lambda dialog: choose(qtbot, dialog, SelectionAction.DELETE, [CloudProvider.CIVO])
        )
        monkeypatch.setattr(products, "_confirm", lambda count: remember(asked, count, True))

        with qtbot.waitSignal(products.changed, timeout=5000) as changed:
            products.select()

        assert changed.args == ["2 items deleted."]
        assert asked == [2]
        remaining = await storage.catalogues.list(ItemQuery(include_deleted=True, sort=ItemSort.NAME))
        assert [stored.item.name for stored in remaining.items] == ["Gamma", "Old"]

    async def test_a_refused_deletion_is_reported(
        self, qtbot: QtBot, storage: Storage, products: ProductSelection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await seed(storage)
        monkeypatch.setattr(products, "_open", lambda dialog: choose(qtbot, dialog, SelectionAction.DELETE))
        monkeypatch.setattr(products, "_confirm", lambda count: True)

        async with storage.catalogues.writer(CloudProvider.AWS, CRAWLED_AT, 60.0):
            with qtbot.waitSignal(products.failed, timeout=5000) as failed:
                products.select()

        assert "amazon-web-services" in str(failed.args[0])
        assert await storage.catalogues.count(ItemQuery()) == 3

    async def test_a_cancelled_selection_does_nothing(
        self, qtbot: QtBot, storage: Storage, products: ProductSelection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await seed(storage)
        monkeypatch.setattr(products, "_open", lambda dialog: choose(qtbot, dialog, SelectionAction.DELETE))
        monkeypatch.setattr(products, "_confirm", lambda count: False)

        with qtbot.assertNotEmitted(products.changed, wait=300):
            products.select()

        assert await storage.catalogues.count(ItemQuery()) == 3

    def test_an_export_file_gets_the_extension_of_its_format(self, products: ProductSelection) -> None:
        assert products._export_path(Path("a.CSV"), "JSON (*.json)") == Path("a.csv")
        assert products._export_path(Path("a"), "JSON lines (*.jsonl)") == Path("a.jsonl")
        assert products._export_path(Path("a.txt"), "unknown") == Path("a.txt.csv")
        assert set(SelectionActions.FILE_FILTERS.values()) == set(ExportFormat)


async def test_software_pickers_fill_the_dialog(
    qtbot: QtBot, storage: Storage, gui_loop: StorageLoop, parent: QWidget, monkeypatch: pytest.MonkeyPatch
) -> None:
    software = [build_software("Gitea", ["crm"], [SoftwareCategory.DEVELOPER_TOOL], publisher="Gitea Ltd")]
    await seed_marketplace(storage, CloudProvider.CIVO, software)
    model = SoftwareTableModel(Theme(), gui_loop)
    actions = SelectionActions[MarketplaceSoftware, SoftwareRow](
        Theme(),
        model,
        gui_loop,
        lambda storage: storage.marketplaces,
        PROVIDERS,
        parent,
        lambda storage: storage.marketplaces.facets(ItemQuery(), pickers=True),
        taxonomy=TaxonomyCache(),
    )
    opened: List[QDialog] = []
    monkeypatch.setattr(actions, "_open", lambda dialog: remember(opened, dialog, False))

    actions.select()

    [dialog] = opened
    assert isinstance(dialog, BulkSelectDialog)
    qtbot.waitUntil(lambda: dialog.advanced.publisher_box.findText("Gitea Ltd") >= 0, timeout=5000)
    qtbot.waitUntil(lambda: dialog.advanced.source_label_box.findText("crm  (1)") >= 0, timeout=5000)
    qtbot.waitUntil(lambda: dialog.count == 1, timeout=5000)
    assert dialog.software
    assert dialog.category_tree is not None, "the taxonomy reaches the dialog"
