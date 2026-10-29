from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest
from PyQt6 import sip
from pytestqt.qtbot import QtBot

from conftest import CRAWLED_AT
from gui.marketplace.model.software_row import SoftwareRow
from gui.marketplace.widgets.software_details import SoftwareDetails
from gui.product_model.product_row import ProductRow
from gui.theme import Theme
from gui.widgets.details.history.version_history import VersionHistory
from gui.widgets.details.product_details import ProductDetails
from models.cloud.enums import CloudProvider, SoftwareCategory
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.enums import DatasetKind
from models.storage.versions.item_version import ItemVersion
from storage.exception import StorageReadError

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def versions() -> List[ItemVersion]:
    return [
        ItemVersion(
            crawl_id=2,
            recorded_at=T0 + timedelta(days=1),
            crawl_status="succeeded",
            content={"name": "Compute", "description": "New VMs", "url": "https://a.example"},
        ),
        ItemVersion(
            crawl_id=1, recorded_at=T0, crawl_status="imported", content={"name": "Compute", "description": "VMs"}
        ),
    ]


def product_row(item_id: int) -> ProductRow:
    return ProductRow(CloudProvider.OVH, CloudProduct(name="Compute", description="VMs"), CRAWLED_AT, id=item_id)


class TestVersionHistory:
    @pytest.fixture
    def loop(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def details(self, qtbot: QtBot, loop: MagicMock) -> ProductDetails:
        widget = ProductDetails(Theme(), loop=loop)
        qtbot.addWidget(widget)
        return widget

    def test_the_versions_of_the_shown_product_are_read_and_compared(
        self, details: ProductDetails, loop: MagicMock
    ) -> None:
        details.show_row(product_row(7))

        assert loop.submit.call_count == 1
        job, on_done, _ = loop.submit.call_args.args
        storage = MagicMock()
        storage.catalogues.versions = AsyncMock(return_value=versions())
        read = asyncio.run(job(storage))
        storage.catalogues.versions.assert_awaited_once_with(7)
        on_done(read)

        history = details.history
        assert not history.isHidden()
        assert history.toggle.text() == "History (2 versions)"
        assert history.table.rowCount() == 2
        assert history.table.isHidden()
        history.toggle.click()
        assert not history.table.isHidden()
        newest = [history.table.item(0, column).text() for column in range(3)]  # type: ignore[union-attr]
        assert newest[1] == "#2 succeeded"
        assert newest[2] == "Changed description · added url"
        assert history.table.item(1, 2).text() == "First seen"  # type: ignore[union-attr]
        tooltip = history.table.item(0, 0).toolTip()  # type: ignore[union-attr]
        assert "description: VMs → New VMs" in tooltip
        assert "Added: url" in tooltip

    def test_a_late_answer_for_another_item_is_dropped(self, details: ProductDetails, loop: MagicMock) -> None:
        details.show_row(product_row(7))
        _, first_done, first_error = loop.submit.call_args.args
        details.show_row(product_row(8))

        first_done(versions())
        first_error(StorageReadError("versions", "gone"))

        assert details.history.item_id == 8
        assert details.history.table.rowCount() == 0
        assert details.history.toggle.text() == "History"

    def test_a_read_error_is_shown(self, details: ProductDetails, loop: MagicMock) -> None:
        details.show_row(product_row(7))
        _, _, on_error = loop.submit.call_args.args

        on_error(StorageReadError("versions", "gone"))

        assert details.history.toggle.text() == "History (unavailable)"
        assert "cannot be read" in details.history.status_label.text()

    def test_no_item_hides_the_section(self, details: ProductDetails, loop: MagicMock) -> None:
        details.show_row(product_row(7))
        details.show_row(None)

        assert details.history.isHidden()
        assert details.history.item_id is None
        assert loop.submit.call_count == 1

    def test_no_loop_keeps_the_section_hidden(self, qtbot: QtBot) -> None:
        details = ProductDetails(Theme())
        qtbot.addWidget(details)

        details.show_row(product_row(7))

        assert details.history.isHidden()

    def test_the_software_versions_are_read_from_the_marketplaces(self, qtbot: QtBot, loop: MagicMock) -> None:
        details = SoftwareDetails(Theme(), loop=loop)
        qtbot.addWidget(details)
        software = MarketplaceSoftware(
            name="Redis", description="Cache", publisher="Redis Labs", categories=[SoftwareCategory.DEVELOPER_TOOL]
        )

        details.show_row(SoftwareRow(CloudProvider.CIVO, software, CRAWLED_AT, id=4))
        job, on_done, _ = loop.submit.call_args.args
        storage = MagicMock()
        storage.marketplaces.versions = AsyncMock(return_value=[])
        on_done(asyncio.run(job(storage)))

        storage.marketplaces.versions.assert_awaited_once_with(4)
        assert details.history.toggle.text() == "History (0 versions)"
        details.history.set_expanded(True)
        assert details.history.status_label.text() == "No version stored for this item."
        assert details.history.table.isHidden()

    def test_an_answer_reaching_a_deleted_widget_is_dropped(self, loop: MagicMock) -> None:
        history = VersionHistory(loop)
        history.load(3, DatasetKind.CATALOGUE)
        _, on_done, _ = loop.submit.call_args.args
        sip.delete(history)

        on_done(versions())

        assert sip.isdeleted(history)
