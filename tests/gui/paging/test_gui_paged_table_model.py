from __future__ import annotations

from typing import List

import pytest
from PyQt6.QtCore import QModelIndex, Qt
from pytestqt.qtbot import QtBot

from conftest import build_product, seed_catalogue
from gui.product_model.product_table_model import ProductTableModel
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.configuration.storage.storage_settings import StorageSettings
from models.storage.enums import ItemSort
from models.storage.pages.item_query import ItemQuery
from storage.storage import Storage

pytestmark = pytest.mark.db


def names(table: ProductTableModel, qtbot: QtBot) -> List[str]:
    qtbot.waitUntil(lambda: all(table.row(number) is not None for number in range(table.total)))
    return [row.product.name for number in range(table.total) if (row := table.row(number)) is not None]


async def test_the_rows_are_read_page_by_page(
    qtbot: QtBot, storage: Storage, gui_loop: StorageLoop, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed_catalogue(storage, CloudProvider.CIVO, [build_product(f"Product {number:02d}") for number in range(7)])
    monkeypatch.setattr(ProductTableModel, "PAGE_SIZE", 2)
    monkeypatch.setattr(ProductTableModel, "MAX_PAGES", 2)
    table = ProductTableModel(Theme(), gui_loop)

    with qtbot.waitSignal(table.loaded) as loaded:
        table.set_query(ItemQuery(sort=ItemSort.NAME))

    assert loaded.args == [7]
    assert table.rowCount() == 7
    assert table.rowCount(table.index(0, 0)) == 0
    assert table.data(table.index(6, ProductTableModel.NAME)) == ProductTableModel.LOADING
    qtbot.waitUntil(lambda: table.row(6) is not None)
    last = table.row(6)
    assert last is not None
    assert last.product.name == "Product 06"
    assert table.cache.row_count <= 4, "at most MAX_PAGES pages are kept"
    assert table.row(7) is None
    assert table.row_at(QModelIndex()) is None


async def test_the_server_sorts_the_sortable_columns(qtbot: QtBot, storage: Storage, gui_loop: StorageLoop) -> None:
    await seed_catalogue(storage, CloudProvider.CIVO, [build_product(name) for name in ("Beta", "Alpha", "Gamma")])
    table = ProductTableModel(Theme(), gui_loop)
    with qtbot.waitSignal(table.loaded):
        table.set_query(ItemQuery(sort=ItemSort.NAME))

    with qtbot.waitSignal(table.loaded):
        table.sort(ProductTableModel.NAME, Qt.SortOrder.DescendingOrder)
    table.sort(ProductTableModel.DESCRIPTION, Qt.SortOrder.AscendingOrder)
    table.sort(ProductTableModel.NAME, Qt.SortOrder.DescendingOrder)

    assert names(table, qtbot) == ["Gamma", "Beta", "Alpha"]


async def test_a_refresh_shows_the_written_rows_without_reset(
    qtbot: QtBot, storage: Storage, gui_loop: StorageLoop
) -> None:
    await seed_catalogue(storage, CloudProvider.CIVO, [build_product("Alpha")])
    table = ProductTableModel(Theme(), gui_loop)
    with qtbot.waitSignal(table.loaded):
        table.set_query(ItemQuery(sort=ItemSort.NAME))
    assert names(table, qtbot) == ["Alpha"]
    await storage.catalogues.create(CloudProvider.CIVO, build_product("Beta"))

    with qtbot.assertNotEmitted(table.modelReset), qtbot.waitSignal(table.loaded):
        table.refresh()
        assert table.row(0) is not None, "the stale row is shown until read again"

    assert names(table, qtbot) == ["Alpha", "Beta"]
    await storage.catalogues.delete((await storage.catalogues.list(ItemQuery(search="Alpha"))).items[0].id)
    with qtbot.waitSignal(table.loaded):
        table.refresh()
    assert names(table, qtbot) == ["Beta"]


def test_an_unreadable_page_is_reported(qtbot: QtBot) -> None:
    loop = StorageLoop(Storage(StorageSettings(url="postgresql+asyncpg://u:p@127.0.0.1:9/nowhere")))
    table = ProductTableModel(Theme(), loop)
    try:
        with qtbot.waitSignal(table.failed, timeout=10_000) as failed:
            table.set_query(ItemQuery())
    finally:
        loop.stop()

    assert "Cannot use the database" in failed.args[0]
    assert table.total == 0
