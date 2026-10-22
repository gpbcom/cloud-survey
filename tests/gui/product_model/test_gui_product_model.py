from __future__ import annotations

import pytest
from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QApplication

from conftest import CRAWLED_AT, fill_table
from gui.product_model.product_row import ProductRow
from gui.product_model.product_table_model import ProductTableModel
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.cloud.products.product import CloudProduct
from models.storage.enums import ItemSort
from models.storage.pages.stored_item import StoredItem


def row(provider: CloudProvider, name: str) -> ProductRow:
    return ProductRow(provider, CloudProduct(name=name, description=f"{name} description"), CRAWLED_AT, id=1)


@pytest.fixture
def table(qapp: QApplication, offline_loop: StorageLoop) -> ProductTableModel:
    model = ProductTableModel(Theme(), offline_loop)
    fill_table(
        model,
        [
            row(CloudProvider.AWS, "Amazon EC2"),
            row(CloudProvider.AWS, "Amazon S3"),
            row(CloudProvider.SCALEWAY, "Kubernetes Kapsule"),
        ],
    )
    return model


class TestProductTableModel:
    def test_rows(self, table: ProductTableModel) -> None:
        assert table.rowCount() == 3
        assert table.columnCount() == 8
        assert table.row(0) == row(CloudProvider.AWS, "Amazon EC2")
        assert [item.product.name for item in table.rows()] == ["Amazon EC2", "Amazon S3", "Kubernetes Kapsule"]

    def test_child_indexes_have_no_rows(self, table: ProductTableModel) -> None:
        index = table.index(0, 0)

        assert table.rowCount(index) == 0
        assert table.columnCount(index) == 0
        assert table.rowCount(QModelIndex()) == 3

    def test_headers(self, table: ProductTableModel) -> None:
        horizontal = Qt.Orientation.Horizontal
        assert [table.headerData(column, horizontal) for column in range(6)] == [
            "Provider",
            "Country",
            "Product",
            "Categories",
            "Source labels",
            "Description",
        ]
        assert table.headerData(0, Qt.Orientation.Vertical) is None
        assert table.headerData(0, horizontal, Qt.ItemDataRole.ToolTipRole) is None

    def test_texts(self, table: ProductTableModel) -> None:
        texts = [table.data(table.index(0, column)) for column in range(6)]

        assert texts == ["Amazon Web Services", "United States", "Amazon EC2", "", "", "Amazon EC2 description"]
        description = table.index(0, ProductTableModel.DESCRIPTION)
        assert table.data(description, Qt.ItemDataRole.ToolTipRole) == "Amazon EC2 description"

    def test_country_cell_shows_the_flag(self, table: ProductTableModel, qapp: QApplication) -> None:
        index = table.index(2, ProductTableModel.COUNTRY)

        assert table.data(index) == "France"
        assert isinstance(table.data(index, Qt.ItemDataRole.DecorationRole), QIcon)
        assert table.data(index, Qt.ItemDataRole.ForegroundRole) is None

    def test_provider_cell_is_colourized(self, table: ProductTableModel, qapp: QApplication) -> None:
        index = table.index(2, ProductTableModel.PROVIDER)

        assert isinstance(table.data(index, Qt.ItemDataRole.DecorationRole), QIcon)
        assert table.data(index, Qt.ItemDataRole.ForegroundRole) == QColor(
            Theme.PROVIDER_COLORS[CloudProvider.SCALEWAY]
        )

    @pytest.mark.parametrize(
        ("column", "role"),
        [
            (ProductTableModel.NAME, Qt.ItemDataRole.DecorationRole),
            (ProductTableModel.NAME, Qt.ItemDataRole.ForegroundRole),
            (ProductTableModel.PROVIDER, Qt.ItemDataRole.FontRole),
            (ProductTableModel.NAME, Qt.ItemDataRole.SizeHintRole),
        ],
    )
    def test_other_roles_have_no_data(self, table: ProductTableModel, column: int, role: Qt.ItemDataRole) -> None:
        assert table.data(table.index(0, column), role) is None

    def test_invalid_indexes(self, table: ProductTableModel) -> None:
        assert table.data(QModelIndex()) is None
        assert table.row_at(QModelIndex()) is None

    def test_rows_being_read_show_a_placeholder(self, qapp: QApplication, offline_loop: StorageLoop) -> None:
        model = ProductTableModel(Theme(), offline_loop)
        model._resize(1)
        model.cache.pending.add(0)

        assert model.data(model.index(0, ProductTableModel.NAME)) == ProductTableModel.LOADING
        assert model.data(model.index(0, ProductTableModel.PROVIDER)) is None

    def test_rows_carry_the_crawl_date_of_their_catalogue(self, table: ProductTableModel) -> None:
        table.set_crawl_dates({CloudProvider.AWS: CRAWLED_AT})
        stored = StoredItem[CloudProduct](
            id=7, provider=CloudProvider.AWS, item=CloudProduct(name="Lambda", description="Functions")
        )

        built = table._row(stored)

        assert (built.id, built.crawled_at) == (7, CRAWLED_AT)
        assert table._row(stored.model_copy(update={"provider": CloudProvider.GCP})).crawled_at is None

    def test_unsortable_columns_keep_the_order(self, table: ProductTableModel) -> None:
        table.sort(ProductTableModel.DESCRIPTION)

        assert table.query.sort is ItemSort.ID


def test_the_category_columns_name_the_taxonomy_and_the_catalogue_categories(
    qapp: QApplication, offline_loop: StorageLoop
) -> None:
    model = ProductTableModel(Theme(), offline_loop)
    product = CloudProduct(
        name="Lambda",
        description="Functions",
        catalogue_categories=["Compute", "Serverless"],
        service_categories=["serverless", "batch-computing"],
    )
    built = model._row(StoredItem[CloudProduct](id=1, provider=CloudProvider.AWS, item=product))

    assert model._text(built, ProductTableModel.LABELS) == "Compute, Serverless"
    assert model._text(built, ProductTableModel.CATEGORIES) == "Serverless functions, Batch computing"
    assert model._tooltip(built, ProductTableModel.CATEGORIES).splitlines()[0] == "Compute > Serverless functions"
