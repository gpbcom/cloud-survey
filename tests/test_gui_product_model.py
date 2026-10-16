from __future__ import annotations

from typing import Callable, Dict, List, Optional

import pytest
from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QApplication

from gui.product_model.product_filter_model import ProductFilterModel
from gui.product_model.product_row import ProductRow
from gui.product_model.product_table_model import ProductTableModel
from gui.theme import Theme
from models.cloud.catalogue import CloudCatalogue
from models.cloud.enums import CloudProvider, Country

MakeCatalogue = Callable[[CloudProvider, List[str]], CloudCatalogue]


@pytest.fixture
def catalogues(make_catalogue: MakeCatalogue) -> Dict[CloudProvider, CloudCatalogue]:
    return {
        CloudProvider.AWS: make_catalogue(CloudProvider.AWS, ["Amazon EC2", "Amazon S3"]),
        CloudProvider.SCALEWAY: make_catalogue(CloudProvider.SCALEWAY, ["Kubernetes Kapsule"]),
    }


@pytest.fixture
def table(catalogues: Dict[CloudProvider, CloudCatalogue]) -> ProductTableModel:
    model = ProductTableModel(Theme())
    model.set_catalogues(catalogues)
    return model


@pytest.fixture
def proxy(table: ProductTableModel) -> ProductFilterModel:
    return ProductFilterModel(table)


def names(proxy: ProductFilterModel) -> List[str]:
    return [proxy.data(proxy.index(row, ProductTableModel.NAME)) for row in range(proxy.rowCount())]


class TestProductTableModel:
    def test_rows(self, table: ProductTableModel, catalogues: Dict[CloudProvider, CloudCatalogue]) -> None:
        assert table.rowCount() == 3
        assert table.columnCount() == 6
        assert table.rows[0] == ProductRow(
            provider=CloudProvider.AWS,
            product=catalogues[CloudProvider.AWS].products[0],
            crawled_at=catalogues[CloudProvider.AWS].crawled_at,
        )

    def test_child_indexes_have_no_rows(self, table: ProductTableModel) -> None:
        index = table.index(0, 0)

        assert table.rowCount(index) == 0
        assert table.columnCount(index) == 0
        assert table.rowCount(QModelIndex()) == 3

    def test_headers(self, table: ProductTableModel) -> None:
        horizontal = Qt.Orientation.Horizontal
        assert [table.headerData(column, horizontal) for column in range(4)] == [
            "Provider",
            "Country",
            "Product",
            "Description",
        ]
        assert table.headerData(0, Qt.Orientation.Vertical) is None
        assert table.headerData(0, horizontal, Qt.ItemDataRole.ToolTipRole) is None

    def test_texts(self, table: ProductTableModel) -> None:
        texts = [table.data(table.index(0, column)) for column in range(4)]

        assert texts == ["Amazon Web Services", "United States", "Amazon EC2", "Amazon EC2 description"]
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
        ],
    )
    def test_other_roles_have_no_data(self, table: ProductTableModel, column: int, role: Qt.ItemDataRole) -> None:
        assert table.data(table.index(0, column), role) is None

    def test_invalid_indexes(self, table: ProductTableModel) -> None:
        assert table.data(QModelIndex()) is None
        assert table.row_at(QModelIndex()) is None

    def test_reload_replaces_the_rows(self, table: ProductTableModel) -> None:
        table.set_catalogues({})

        assert table.rowCount() == 0


class TestProductFilterModel:
    def test_shows_everything_by_default(self, proxy: ProductFilterModel) -> None:
        assert proxy.rowCount() == 3
        assert (proxy.search, proxy.provider, proxy.country) == ("", None, None)

    @pytest.mark.parametrize(
        ("search", "expected"),
        [("s3", ["Amazon S3"]), ("  KUBERNETES ", ["Kubernetes Kapsule"]), ("description", None), ("nothing", [])],
    )
    def test_search_names_and_descriptions(
        self, proxy: ProductFilterModel, search: str, expected: Optional[List[str]]
    ) -> None:
        proxy.set_search(search)

        assert sorted(names(proxy)) == (sorted(expected) if expected is not None else sorted(names(proxy)))
        if expected is None:
            assert proxy.rowCount() == 3

    def test_provider_filter(self, proxy: ProductFilterModel) -> None:
        proxy.set_provider(CloudProvider.SCALEWAY)
        assert names(proxy) == ["Kubernetes Kapsule"]

        proxy.set_provider(None)
        assert proxy.rowCount() == 3

    def test_country_filter(self, proxy: ProductFilterModel) -> None:
        proxy.set_country(Country.FRANCE)
        assert names(proxy) == ["Kubernetes Kapsule"]

        proxy.set_country(Country.CHINA)
        assert proxy.rowCount() == 0

        proxy.set_country(None)
        assert proxy.rowCount() == 3

    def test_country_and_provider_filters_combine(self, proxy: ProductFilterModel) -> None:
        proxy.set_country(Country.UNITED_STATES)
        proxy.set_provider(CloudProvider.SCALEWAY)
        assert proxy.rowCount() == 0

        proxy.set_provider(CloudProvider.AWS)
        proxy.set_search("s3")
        assert names(proxy) == ["Amazon S3"]

    def test_sorting_by_country(self, proxy: ProductFilterModel) -> None:
        proxy.sort(ProductTableModel.COUNTRY, Qt.SortOrder.AscendingOrder)

        assert proxy.data(proxy.index(0, ProductTableModel.COUNTRY)) == "France"

    def test_filters_combine(self, proxy: ProductFilterModel) -> None:
        proxy.set_provider(CloudProvider.AWS)
        proxy.set_search("kubernetes")

        assert proxy.rowCount() == 0

    def test_sorting_is_case_insensitive(self, proxy: ProductFilterModel, table: ProductTableModel) -> None:
        proxy.sort(ProductTableModel.NAME, Qt.SortOrder.DescendingOrder)

        assert names(proxy) == ["Kubernetes Kapsule", "Amazon S3", "Amazon EC2"]

    def test_row_at_maps_to_the_product(self, proxy: ProductFilterModel) -> None:
        proxy.set_search("kapsule")

        row = proxy.row_at(proxy.index(0, 0))

        assert row is not None
        assert (row.provider, row.product.name) == (CloudProvider.SCALEWAY, "Kubernetes Kapsule")
        assert proxy.row_at(QModelIndex()) is None
