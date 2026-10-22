from __future__ import annotations

from datetime import UTC, datetime
from typing import Dict, List

import pytest
from pydantic import JsonValue
from PyQt6.QtCore import QItemSelectionModel
from pytestqt.qtbot import QtBot

from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.manager.categories_manager import CategoriesManager
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.configuration.llm.llm_settings import LLMSettings
from storage.storage import Storage

pytestmark = pytest.mark.db

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def software(name: str, *labels: str) -> MarketplaceSoftware:
    return MarketplaceSoftware(
        name=name,
        description="Zz",
        url=f"https://marketplace.example.com/{name.casefold()}",
        categories=["developer-tool"],
        marketplace_categories=list(labels),
    )


async def crawl(storage: Storage, items: List[MarketplaceSoftware]) -> None:
    async with storage.marketplaces.writer(CloudProvider.CIVO, T0, 0.0) as writer:
        for item in items:
            await writer.add(item)
        await writer.finish()


@pytest.fixture
def manager(qtbot: QtBot, gui_loop: StorageLoop) -> CategoriesManager:
    window = CategoriesManager(Theme(), gui_loop, TaxonomyCache(gui_loop))
    qtbot.addWidget(window)
    return window


async def test_the_labels_are_listed_and_linked_by_hand(
    storage: Storage, manager: CategoriesManager, qtbot: QtBot
) -> None:
    await crawl(storage, [software("Acme", "Zz label"), software("Beta", "Databases")])
    editor = manager.labels_editor

    manager.open_on(1)
    qtbot.waitUntil(lambda: editor.model.rowCount() > 2, timeout=10_000)
    editor.find_box.setText("Zz label")
    assert editor.model.rowCount() == 1
    row = 0
    selection = editor.table.selectionModel()
    assert selection is not None
    selection.select(
        editor.model.index(row, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
    )
    editor.node_box.setCurrentIndex(editor.node_box.findData("crm"))
    with qtbot.waitSignal(manager.edited, timeout=20_000):
        editor._on_link(True)

    marketplace = await storage.marketplaces.load(CloudProvider.CIVO)
    assert marketplace is not None
    assert {item.name: item.service_categories for item in marketplace.software}["Acme"] == ["crm"]
    assert "Saved" in manager.status_label.text()


async def test_the_unclassified_items_get_categories_by_hand(
    storage: Storage, manager: CategoriesManager, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    await crawl(storage, [software("Acme"), software("Beta", "Databases")])
    panel = manager.unclassified_panel

    manager.open_on(2)
    qtbot.waitUntil(lambda: panel.counts_table.rowCount() == 1, timeout=10_000)
    assert panel.counts[0].unclassified == 1
    panel.counts_table.selectRow(0)
    qtbot.waitUntil(lambda: panel.items_table.rowCount() == 1, timeout=10_000)
    panel.items_table.selectRow(0)
    monkeypatch.setattr(panel, "_pick_categories", lambda: ["erp"])
    with qtbot.waitSignal(manager.edited, timeout=20_000):
        panel._on_assign()

    marketplace = await storage.marketplaces.load(CloudProvider.CIVO)
    assert marketplace is not None
    acme = next(item for item in marketplace.software if item.name == "Acme")
    assert (acme.service_categories, acme.categories_source.value if acme.categories_source else None) == (
        ["erp"],
        "user",
    )


async def test_a_category_is_added_and_renamed(storage: Storage, manager: CategoriesManager, qtbot: QtBot) -> None:
    editor = manager.taxonomy_editor
    manager.open_on(0)
    domain = editor.tree.topLevelItem(0)
    assert domain is not None
    editor.tree.setCurrentItem(domain)
    editor.new_box.setText("Quantum networking")

    with qtbot.waitSignal(manager.edited, timeout=20_000):
        editor._on_add(True)

    taxonomy = await storage.taxonomy.read()
    node = taxonomy.node("quantum-networking")
    assert node is not None
    assert node.parent_slug == taxonomy.domains()[0].slug
    qtbot.waitUntil(lambda: manager.cache.taxonomy.node("quantum-networking") is not None, timeout=10_000)


def test_the_language_model_actions_need_a_key(
    qtbot: QtBot, gui_loop: StorageLoop, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_LLM_KEY", "secret")
    profile: Dict[str, JsonValue] = {
        "provider": "anthropic",
        "model_name": "claude-haiku-5-5",
        "api_key": "TEST_LLM_KEY",
    }
    cache = TaxonomyCache(gui_loop)
    plain = CategoriesManager(Theme(), gui_loop, cache, llm_settings=LLMSettings())
    keyed = CategoriesManager(Theme(), gui_loop, cache, llm_settings=LLMSettings.model_validate({"llm": profile}))
    for window in (plain, keyed):
        qtbot.addWidget(window)

    assert plain.translate_button.isHidden()
    assert plain.classify_button.isHidden()
    assert plain.cost_label.isHidden()
    assert not keyed.translate_button.isHidden()
    assert not keyed.classify_button.isHidden()
    keyed._refresh_cost()
    qtbot.waitUntil(lambda: keyed.cost_label.text().startswith("Language model: 0.00 of 10.00 USD"), timeout=10000)
