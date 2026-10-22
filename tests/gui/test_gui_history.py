from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from conftest import fill_table
from gui.marketplace.model.software_row import SoftwareRow
from gui.marketplace.model.software_table_model import SoftwareTableModel
from gui.marketplace.widgets.software_details import SoftwareDetails
from gui.product_model.product_row import ProductRow
from gui.product_model.product_table_model import ProductTableModel
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from gui.widgets.details.product_details import ProductDetails
from models.cloud.enums import CloudProvider, DateCaveat, DateSource, SoftwareCategory
from models.cloud.products.catalogue import CloudCatalogue
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace import CloudMarketplace
from models.cloud.software.marketplace_software import MarketplaceSoftware

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
    listed = make_software("Grafana", ["monitoring"], [SoftwareCategory.DEVELOPER_TOOL])
    gone = make_software("Old CRM", ["crm"], [SoftwareCategory.END_USER_SOFTWARE])
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
    def table(self, qapp: QApplication, offline_loop: StorageLoop, catalogue: CloudCatalogue) -> ProductTableModel:
        model = ProductTableModel(Theme(), offline_loop)
        fill_table(model, [ProductRow(CloudProvider.AWS, product, CRAWLED) for product in catalogue.products])
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

    def test_details_show_the_history(self, qtbot: QtBot, catalogue: CloudCatalogue) -> None:
        details = ProductDetails(Theme())
        qtbot.addWidget(details)

        details.show_row(ProductRow(provider=CloudProvider.AWS, product=catalogue.products[1], crawled_at=CRAWLED))
        assert "Deleted from the website" in details.history_label.text()
        details.show_row(None)
        assert details.history_label.text() == ""


class TestMarketplaces:
    def test_date_columns_and_deleted_rows(
        self, qapp: QApplication, offline_loop: StorageLoop, marketplace: CloudMarketplace
    ) -> None:
        table = SoftwareTableModel(Theme(), offline_loop)
        fill_table(table, [SoftwareRow(CloudProvider.CIVO, software, CRAWLED) for software in marketplace.software])
        tooltip = Qt.ItemDataRole.ToolTipRole
        rows = {row.software.name: index for index, row in enumerate(table.rows())}
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

    def test_details_show_the_history(self, qtbot: QtBot, marketplace: CloudMarketplace) -> None:
        details = SoftwareDetails(Theme())
        qtbot.addWidget(details)

        details.show_row(SoftwareRow(provider=CloudProvider.CIVO, software=marketplace.software[0], crawled_at=CRAWLED))
        assert details.history_label.text().startswith("Added: ")
        details.show_row(None)
        assert details.history_label.text() == ""


class TestCaveats:
    @pytest.fixture
    def item(self) -> CloudProduct:
        return CloudProduct(
            name="Secret Manager",
            description="Secrets",
            added_at=ADDED,
            added_from=DateSource.WEBSITE,
            added_caveat=DateCaveat.WEBSITE_RECORD,
            updated_at=UPDATED,
            updated_from=DateSource.WEBSITE,
            updated_caveat=DateCaveat.PAGE_MODIFIED,
        )

    def test_texts(self, item: CloudProduct) -> None:
        theme = Theme()

        assert theme.caveat_text(item).splitlines() == [
            f"⚠ The added date is approximate: {Theme.CAVEAT_LABELS[DateCaveat.WEBSITE_RECORD]}.",
            f"⚠ The updated date is approximate: {Theme.CAVEAT_LABELS[DateCaveat.PAGE_MODIFIED]}.",
        ]
        assert theme.caveat_text(CloudProduct(name="VM", description="VMs")) == ""
        assert theme.date_description(ADDED, DateSource.WEBSITE, DateCaveat.ASSUMED_TIMEZONE).splitlines()[1] == (
            f"⚠ Approximate: {Theme.CAVEAT_LABELS[DateCaveat.ASSUMED_TIMEZONE]}."
        )
        assert set(Theme.CAVEAT_LABELS) == set(DateCaveat)
        assert not theme.warning_icon().isNull()

    def test_product_table(self, qapp: QApplication, offline_loop: StorageLoop, item: CloudProduct) -> None:
        table = ProductTableModel(Theme(), offline_loop)
        fill_table(table, [ProductRow(CloudProvider.SCALEWAY, item, CRAWLED)])
        added, name = table.index(0, ProductTableModel.ADDED), table.index(0, ProductTableModel.NAME)

        assert table.data(added, Qt.ItemDataRole.DecorationRole) is table.warning_icon
        assert table.data(added, Qt.ItemDataRole.ForegroundRole) == QColor(Theme.WARNING)
        assert "⚠ Approximate" in str(
            table.data(table.index(0, ProductTableModel.UPDATED), Qt.ItemDataRole.ToolTipRole)
        )
        assert table.data(name, Qt.ItemDataRole.DecorationRole) is None
        assert str(
            table.headerData(ProductTableModel.ADDED, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
        ).startswith("⚠ marks an approximate date")
        assert table.headerData(ProductTableModel.NAME, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole) is None

    def test_software_table(
        self, qapp: QApplication, offline_loop: StorageLoop, make_software: Callable[..., MarketplaceSoftware]
    ) -> None:
        listing = make_software("Solana", ["other"], [SoftwareCategory.DEVELOPER_TOOL]).model_copy(
            update={"added_at": ADDED, "added_caveat": DateCaveat.ASSUMED_TIMEZONE}
        )
        table = SoftwareTableModel(Theme(), offline_loop)
        fill_table(table, [SoftwareRow(CloudProvider.TENCENT, listing, CRAWLED)])
        added, updated = table.index(0, SoftwareTableModel.ADDED), table.index(0, SoftwareTableModel.UPDATED)

        assert table.data(added, Qt.ItemDataRole.DecorationRole) is table.warning_icon
        assert table.data(added, Qt.ItemDataRole.ForegroundRole) == QColor(Theme.WARNING)
        assert "China's time" in str(table.data(added, Qt.ItemDataRole.ToolTipRole))
        assert table.data(updated, Qt.ItemDataRole.DecorationRole) is None
        assert table.headerData(SoftwareTableModel.UPDATED, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
        assert table.headerData(SoftwareTableModel.NAME, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole) is None

    def test_details_warn(self, qtbot: QtBot, item: CloudProduct, marketplace: CloudMarketplace) -> None:
        product_details, software_details = ProductDetails(Theme()), SoftwareDetails(Theme())
        qtbot.addWidget(product_details)
        qtbot.addWidget(software_details)

        product_details.show_row(ProductRow(provider=CloudProvider.SCALEWAY, product=item, crawled_at=CRAWLED))
        software_details.show_row(
            SoftwareRow(provider=CloudProvider.CIVO, software=marketplace.software[0], crawled_at=CRAWLED)
        )

        assert product_details.caveat_label.objectName() == "warning"
        assert product_details.caveat_label.text().count("⚠") == 2
        assert software_details.caveat_label.text() == ""
        product_details.show_row(None)
        assert product_details.caveat_label.text() == ""


def test_year_only_dates_show_the_year() -> None:
    theme = Theme()

    assert theme.date_label(ADDED, DateCaveat.YEAR_ONLY) == "2024"
    assert theme.date_description(ADDED, DateSource.WEBSITE, DateCaveat.YEAR_ONLY).startswith("2024, published")
