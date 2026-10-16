from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from pytestqt.qtbot import QtBot

from catalogue.store import CatalogueStore
from crawler.runner import CatalogueRunner
from gui.main_window import MainWindow
from gui.marketplace.marketplace_view import MarketplaceView
from gui.marketplace.software_details import SoftwareDetails
from gui.marketplace.software_row import SoftwareRow
from gui.marketplace.software_table_model import SoftwareTableModel
from gui.product_model.product_filter_model import ProductFilterModel
from gui.product_model.product_row import ProductRow
from gui.product_model.product_table_model import ProductTableModel
from gui.theme import Theme
from gui.widgets.product_details import ProductDetails
from models.cloud.catalogue import CloudCatalogue
from models.cloud.enums import CloudProvider, DateSource, SoftwareCategory, SoftwareType
from models.cloud.marketplace import CloudMarketplace
from models.cloud.marketplace_software import MarketplaceSoftware
from models.cloud.product import CloudProduct

ADDED = datetime(2024, 3, 1, 10, tzinfo=UTC)
UPDATED = datetime(2026, 9, 1, 10, tzinfo=UTC)
DELETED = datetime(2026, 10, 16, 7, tzinfo=UTC)
CRAWLED = datetime(2026, 10, 16, 7, tzinfo=UTC)


def local(value: datetime, pattern: str) -> str:
    return value.astimezone().strftime(pattern)


@pytest.fixture
def catalogue() -> CloudCatalogue:
    products = [
        CloudProduct(
            name="Amazon EC2",
            description="Virtual machines",
            added_at=ADDED,
            added_from=DateSource.WEBSITE,
            updated_at=UPDATED,
            updated_from=DateSource.CRAWL,
        ),
        CloudProduct(name="Amazon SimpleDB", description="Retired database", deleted_at=DELETED),
    ]
    return CloudCatalogue(provider=CloudProvider.AWS, crawled_at=CRAWLED, products=products)


@pytest.fixture
def marketplace(make_software: Callable[..., MarketplaceSoftware]) -> CloudMarketplace:
    listed = make_software("Grafana", [SoftwareType.MONITORING], [SoftwareCategory.DEVELOPER_TOOL])
    gone = make_software("Old CRM", [SoftwareType.CRM], [SoftwareCategory.END_USER_SOFTWARE])
    software = [
        listed.model_copy(update={"added_at": ADDED, "added_from": DateSource.WEBSITE}),
        gone.model_copy(update={"deleted_at": DELETED}),
    ]
    return CloudMarketplace(provider=CloudProvider.CIVO, crawled_at=CRAWLED, software=software)


class TestTheme:
    def test_dates(self, catalogue: CloudCatalogue) -> None:
        theme = Theme()

        assert (theme.date_label(None), theme.date_description(None)) == ("", "unknown")
        assert theme.date_label(ADDED) == local(ADDED, "%Y-%m-%d")
        assert theme.date_description(ADDED) == local(ADDED, "%Y-%m-%d %H:%M")
        assert theme.date_description(ADDED, DateSource.WEBSITE).endswith(", published by the website")
        assert theme.history_text(catalogue.products[0]).splitlines() == [
            f"Added: {local(ADDED, '%Y-%m-%d %H:%M')}, published by the website",
            f"Updated: {local(UPDATED, '%Y-%m-%d %H:%M')}, seen by a crawl",
        ]
        assert theme.history_text(catalogue.products[1]).splitlines() == [
            "Added: unknown",
            "Updated: unknown",
            f"Deleted from the website: {local(DELETED, '%Y-%m-%d %H:%M')}",
        ]


class TestProducts:
    @pytest.fixture
    def table(self, catalogue: CloudCatalogue) -> ProductTableModel:
        model = ProductTableModel(Theme())
        model.set_catalogues({CloudProvider.AWS: catalogue})
        return model

    def test_date_columns_and_deleted_rows(self, table: ProductTableModel) -> None:
        tooltip = Qt.ItemDataRole.ToolTipRole
        listed, deleted = table.index(0, ProductTableModel.ADDED), table.index(1, ProductTableModel.NAME)

        assert table.data(listed) == local(ADDED, "%Y-%m-%d")
        assert str(table.data(listed, tooltip)).startswith("Added: ")
        assert str(table.data(table.index(0, ProductTableModel.UPDATED), tooltip)).endswith("seen by a crawl")
        assert table.data(table.index(1, ProductTableModel.UPDATED)) == ""
        assert table.data(table.index(0, ProductTableModel.NAME), tooltip) == "Amazon EC2"
        assert str(table.data(deleted, tooltip)).startswith("Amazon SimpleDB\nDeleted: ")
        font = table.data(deleted, Qt.ItemDataRole.FontRole)
        assert isinstance(font, QFont)
        assert font.strikeOut()
        assert table.data(deleted, Qt.ItemDataRole.ForegroundRole) == QColor(Theme.TEXT_MUTED)
        assert table.data(table.index(0, ProductTableModel.NAME), Qt.ItemDataRole.FontRole) is None

    def test_deleted_products_are_hidden_by_default(self, table: ProductTableModel) -> None:
        proxy = ProductFilterModel(table)

        assert proxy.rowCount() == 1
        proxy.set_show_deleted(True)
        assert proxy.rowCount() == 2

    def test_details_show_the_history(self, qtbot: QtBot, catalogue: CloudCatalogue) -> None:
        details = ProductDetails(Theme())
        qtbot.addWidget(details)

        details.show_row(ProductRow(provider=CloudProvider.AWS, product=catalogue.products[1], crawled_at=CRAWLED))
        assert "Deleted from the website" in details.history_label.text()
        details.show_row(None)
        assert details.history_label.text() == ""


class TestMarketplaces:
    @pytest.fixture
    def view(self, qtbot: QtBot, marketplace: CloudMarketplace) -> MarketplaceView:
        widget = MarketplaceView(Theme(), [CloudProvider.CIVO])
        qtbot.addWidget(widget)
        widget.set_marketplaces({CloudProvider.CIVO: marketplace})
        return widget

    def test_date_columns_and_deleted_rows(self, marketplace: CloudMarketplace) -> None:
        table = SoftwareTableModel(Theme())
        table.set_marketplaces({CloudProvider.CIVO: marketplace})
        tooltip = Qt.ItemDataRole.ToolTipRole
        rows = {row.software.name: index for index, row in enumerate(table.rows)}
        grafana, old = rows["Grafana"], rows["Old CRM"]

        assert table.data(table.index(grafana, SoftwareTableModel.ADDED)) == local(ADDED, "%Y-%m-%d")
        assert table.data(table.index(grafana, SoftwareTableModel.UPDATED)) == ""
        assert str(table.data(table.index(grafana, SoftwareTableModel.ADDED), tooltip)).endswith("by the website")
        assert table.data(table.index(grafana, SoftwareTableModel.UPDATED), tooltip) == "Updated: unknown"
        assert table.data(table.index(grafana, SoftwareTableModel.NAME), tooltip) == "Grafana description"
        assert str(table.data(table.index(old, SoftwareTableModel.NAME), tooltip)).startswith(
            "Old CRM description\nDeleted: "
        )
        font = table.data(table.index(old, SoftwareTableModel.NAME), Qt.ItemDataRole.FontRole)
        assert isinstance(font, QFont)
        assert font.strikeOut()
        assert table.data(table.index(old, SoftwareTableModel.NAME), Qt.ItemDataRole.ForegroundRole) == QColor(
            Theme.TEXT_MUTED
        )

    def test_show_deleted(self, view: MarketplaceView) -> None:
        assert view.filter_model.rowCount() == 1
        assert view.count_label.text() == "1 of 1 software shown (1 deleted hidden)"
        assert view.provider_box.itemText(view.provider_box.findData(CloudProvider.CIVO.value)).endswith("(1)")

        view.deleted_box.setChecked(True)

        assert view.filter_model.rowCount() == 2
        assert view.count_label.text() == "2 of 1 software shown (1 deleted included)"

    def test_details_show_the_history(self, qtbot: QtBot, marketplace: CloudMarketplace) -> None:
        details = SoftwareDetails(Theme())
        qtbot.addWidget(details)

        details.show_row(SoftwareRow(provider=CloudProvider.CIVO, software=marketplace.software[0], crawled_at=CRAWLED))
        assert details.history_label.text().startswith("Added: ")
        details.show_row(None)
        assert details.history_label.text() == ""


class TestMainWindow:
    @pytest.fixture
    def window(self, qtbot: QtBot, tmp_path: Path, catalogue: CloudCatalogue, isolated_logging: None) -> MainWindow:
        store = CatalogueStore(tmp_path / "output")
        store.save(catalogue)
        widget = MainWindow(store, runner=CatalogueRunner(store=store, concurrency=3), theme=Theme())
        qtbot.addWidget(widget)
        return widget

    def test_show_deleted_products(self, window: MainWindow) -> None:
        assert window.count_label.text() == "1 of 1 products shown (1 deleted hidden)"

        window.deleted_box.setChecked(True)

        assert window.count_label.text() == "2 of 1 products shown (1 deleted included)"

    def test_no_deleted_products(self, window: MainWindow, catalogue: CloudCatalogue) -> None:
        window.store.save(catalogue.model_copy(update={"products": catalogue.products[:1]}))
        window.deleted_box.setChecked(True)

        window.reload()

        assert window.count_label.text() == "1 of 1 products shown"

    def test_concurrency_box(self, window: MainWindow, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("INFO", logger="gui.main_window")
        assert window.concurrency_box.value() == 3
        assert window.concurrency_box.maximum() == len(CloudProvider)

        window.concurrency_box.setValue(6)

        assert window.runner.concurrency == 6
        assert "The next crawls run 6 providers at the same time." in caplog.messages
