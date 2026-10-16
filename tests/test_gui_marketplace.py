from __future__ import annotations

from typing import Callable, Dict, List
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from gui.marketplace.marketplace_view import MarketplaceView
from gui.marketplace.software_details import SoftwareDetails
from gui.marketplace.software_filter_model import SoftwareFilterModel
from gui.marketplace.software_row import SoftwareRow
from gui.marketplace.software_table_model import SoftwareTableModel
from gui.marketplace.type_bar_chart import TypeBarChart
from gui.theme import Theme
from models.cloud.enums import CloudProvider, Country, DeliveryMethod, SoftwareCategory, SoftwareType
from models.cloud.marketplace import CloudMarketplace
from models.cloud.marketplace_software import MarketplaceSoftware

MakeMarketplace = Callable[[CloudProvider, List[MarketplaceSoftware]], CloudMarketplace]
DEV = SoftwareCategory.DEVELOPER_TOOL
USER = SoftwareCategory.END_USER_SOFTWARE
PROVIDERS = [CloudProvider.AWS, CloudProvider.STACKIT, CloudProvider.CIVO]


MakeSoftware = Callable[..., MarketplaceSoftware]


@pytest.fixture
def marketplaces(
    make_marketplace: MakeMarketplace, make_software: MakeSoftware
) -> Dict[CloudProvider, CloudMarketplace]:
    software = make_software
    return {
        CloudProvider.AWS: make_marketplace(
            CloudProvider.AWS,
            [
                software("Greenhouse", [SoftwareType.ATS, SoftwareType.HRIS], [USER]),
                software("Datadog", [SoftwareType.MONITORING], [DEV], publisher="Datadog Inc"),
            ],
        ),
        CloudProvider.STACKIT: make_marketplace(
            CloudProvider.STACKIT,
            [software("Odoo", [SoftwareType.ERP], [USER], DeliveryMethod.CONTAINER)],
        ),
    }


@pytest.fixture
def table(marketplaces: Dict[CloudProvider, CloudMarketplace]) -> SoftwareTableModel:
    model = SoftwareTableModel(Theme())
    model.set_marketplaces(marketplaces)
    return model


def names(proxy: SoftwareFilterModel) -> List[str]:
    return sorted(proxy.data(proxy.index(row, SoftwareTableModel.NAME)) for row in range(proxy.rowCount()))


class TestSoftwareRow:
    def test_haystack(self, marketplaces: Dict[CloudProvider, CloudMarketplace]) -> None:
        marketplace = marketplaces[CloudProvider.AWS]
        row = SoftwareRow(CloudProvider.AWS, marketplace.software[1], marketplace.crawled_at)

        assert row.haystack == "datadog\ndatadog description\ndatadog inc"


class TestSoftwareTableModel:
    def test_rows_and_headers(self, table: SoftwareTableModel) -> None:
        horizontal = Qt.Orientation.Horizontal

        assert (table.rowCount(), table.columnCount()) == (3, 9)
        assert [table.headerData(column, horizontal) for column in range(9)] == SoftwareTableModel.HEADERS
        assert table.headerData(0, Qt.Orientation.Vertical) is None
        assert table.rowCount(table.index(0, 0)) == 0
        assert table.columnCount(table.index(0, 0)) == 0

    def test_texts(self, table: SoftwareTableModel) -> None:
        texts = [table.data(table.index(0, column)) for column in range(7)]

        assert texts == [
            "Amazon Web Services",
            "United States",
            "Greenhouse",
            "ACME",
            "End-user software",
            "ATS, HRIS",
            "SaaS",
        ]
        assert table.data(table.index(2, SoftwareTableModel.DELIVERY)) == "Container"
        assert table.data(table.index(0, SoftwareTableModel.NAME), Qt.ItemDataRole.ToolTipRole) == (
            "Greenhouse description"
        )
        assert table.data(table.index(0, SoftwareTableModel.TYPES), Qt.ItemDataRole.ToolTipRole) == "ATS, HRIS"

    def test_missing_publisher_is_blank(self, make_marketplace: MakeMarketplace, make_software: MakeSoftware) -> None:
        listing = make_software("Grafana", [SoftwareType.MONITORING], [DEV]).model_copy(update={"publisher": None})
        model = SoftwareTableModel(Theme())
        model.set_marketplaces({CloudProvider.CIVO: make_marketplace(CloudProvider.CIVO, [listing])})

        assert model.data(model.index(0, SoftwareTableModel.PUBLISHER)) == ""

    def test_decorations(self, table: SoftwareTableModel, qapp: QApplication) -> None:
        provider = table.index(0, SoftwareTableModel.PROVIDER)

        assert isinstance(table.data(provider, Qt.ItemDataRole.DecorationRole), QIcon)
        assert isinstance(table.data(table.index(0, SoftwareTableModel.COUNTRY), Qt.ItemDataRole.DecorationRole), QIcon)
        assert table.data(provider, Qt.ItemDataRole.ForegroundRole) == QColor(Theme.PROVIDER_COLORS[CloudProvider.AWS])
        assert table.data(table.index(0, SoftwareTableModel.NAME), Qt.ItemDataRole.FontRole) is None

    def test_invalid_index(self, table: SoftwareTableModel) -> None:
        assert table.data(QModelIndex()) is None


class TestSoftwareFilterModel:
    @pytest.fixture
    def proxy(self, table: SoftwareTableModel) -> SoftwareFilterModel:
        return SoftwareFilterModel(table)

    def test_shows_everything_by_default(self, proxy: SoftwareFilterModel) -> None:
        assert names(proxy) == ["Datadog", "Greenhouse", "Odoo"]

    @pytest.mark.parametrize(
        ("apply", "expected"),
        [
            (lambda proxy: proxy.set_filters(search=" DATADOG INC "), ["Datadog"]),
            (lambda proxy: proxy.set_filters(provider=CloudProvider.STACKIT), ["Odoo"]),
            (lambda proxy: proxy.set_filters(country=Country.UNITED_STATES), ["Datadog", "Greenhouse"]),
            (lambda proxy: proxy.set_filters(category=DEV), ["Datadog"]),
            (lambda proxy: proxy.set_filters(kind=SoftwareType.HRIS), ["Greenhouse"]),
            (lambda proxy: proxy.set_filters(delivery=DeliveryMethod.CONTAINER), ["Odoo"]),
            (lambda proxy: proxy.set_filters(country=Country.GERMANY, kind=SoftwareType.ATS), []),
        ],
        ids=["search", "provider", "country", "category", "type", "delivery", "combined"],
    )
    def test_filters(
        self, proxy: SoftwareFilterModel, apply: Callable[[SoftwareFilterModel], None], expected: List[str]
    ) -> None:
        apply(proxy)

        assert names(proxy) == expected

    def test_row_at(self, proxy: SoftwareFilterModel) -> None:
        proxy.set_filters(search="odoo")

        row = proxy.row_at(proxy.index(0, 0))

        assert row is not None
        assert row.software.name == "Odoo"
        assert proxy.row_at(QModelIndex()) is None


class TestTypeBarChart:
    def test_bars_are_sorted_and_painted(self, qtbot: QtBot) -> None:
        chart = TypeBarChart(Theme())
        qtbot.addWidget(chart)

        chart.set_bars([("CRM", 2, "#3fb950"), ("Monitoring", 5, "#4f8cff"), ("ATS", 2, "#3fb950")])
        chart.resize(chart.sizeHint())
        image = chart.grab().toImage()

        assert [label for label, _, _ in chart.bars] == ["Monitoring", "ATS", "CRM"]
        assert chart.sizeHint().height() == 3 * TypeBarChart.ROW_HEIGHT
        assert image.pixelColor(TypeBarChart.LABEL_WIDTH + 4, TypeBarChart.ROW_HEIGHT // 2) == QColor("#4f8cff")

    def test_empty_chart(self, qtbot: QtBot) -> None:
        chart = TypeBarChart(Theme())
        qtbot.addWidget(chart)
        chart.set_bars([])

        assert chart.sizeHint().height() == TypeBarChart.ROW_HEIGHT
        assert not chart.grab().isNull()


class TestSoftwareDetails:
    @pytest.fixture
    def details(self, qtbot: QtBot) -> SoftwareDetails:
        widget = SoftwareDetails(Theme())
        qtbot.addWidget(widget)
        return widget

    @pytest.fixture
    def row(self, marketplaces: Dict[CloudProvider, CloudMarketplace]) -> SoftwareRow:
        marketplace = marketplaces[CloudProvider.AWS]
        return SoftwareRow(CloudProvider.AWS, marketplace.software[0], marketplace.crawled_at)

    def test_placeholder(self, details: SoftwareDetails) -> None:
        assert details.name_label.text() == "No software selected"
        assert not details.copy_button.isEnabled()

    def test_shows_a_software(self, details: SoftwareDetails, row: SoftwareRow) -> None:
        details.show_row(row)

        assert details.name_label.text() == "Greenhouse"
        assert details.provider_label.text().strip() == "Amazon Web Services"
        assert details.country_label.text() == "United States"
        assert details.facts_label.text() == "ACME · SaaS"
        assert "ATS" in details.chips_label.text()
        assert "End-user software" in details.chips_label.text()
        assert details.marketplace_label.text() == "Marketplace categories: ats, hris"
        assert "https://marketplace.example.com/greenhouse" in details.link_label.text()

        details.show_row(None)
        assert details.link_label.text() == ""

    def test_software_without_publisher_link_or_categories(self, details: SoftwareDetails, row: SoftwareRow) -> None:
        bare = row.software.model_copy(update={"publisher": None, "url": None, "marketplace_categories": []})

        details.show_row(SoftwareRow(row.provider, bare, row.crawled_at))

        assert details.facts_label.text() == "Unknown publisher · SaaS"
        assert (details.link_label.text(), details.marketplace_label.text()) == ("", "")

    def test_copy(self, details: SoftwareDetails, row: SoftwareRow, qtbot: QtBot) -> None:
        details.show_row(row)

        with qtbot.waitSignal(details.copied) as signal:
            details.copy_button.click()

        assert signal.args == ["Amazon Web Services — Greenhouse (ATS, HRIS): Greenhouse description"]

    def test_copy_without_clipboard_or_software(self, details: SoftwareDetails, row: SoftwareRow, qtbot: QtBot) -> None:
        with qtbot.assertNotEmitted(details.copied):
            details.copy()
        details.show_row(row)
        with (
            patch("gui.marketplace.software_details.QApplication.clipboard", return_value=None),
            qtbot.waitSignal(details.copied),
        ):
            details.copy()


class TestMarketplaceView:
    @pytest.fixture
    def view(self, qtbot: QtBot, marketplaces: Dict[CloudProvider, CloudMarketplace]) -> MarketplaceView:
        widget = MarketplaceView(Theme(), PROVIDERS)
        qtbot.addWidget(widget)
        widget.set_marketplaces(marketplaces)
        return widget

    def test_empty_view(self, qtbot: QtBot) -> None:
        view = MarketplaceView(Theme(), PROVIDERS)
        qtbot.addWidget(view)

        assert view.count_label.text() == "0 of 0 software shown"
        assert view.marketplaces_card.value_label.text() == "0 / 3"

    def test_figures_and_combos(self, view: MarketplaceView) -> None:
        assert view.count_label.text() == "3 of 3 software shown"
        assert view.software_card.value_label.text() == "3"
        assert view.developer_card.value_label.text() == "1"
        assert view.end_user_card.value_label.text() == "2"
        assert view.marketplaces_card.value_label.text() == "2 / 3"
        assert [view.country_box.itemText(index) for index in range(view.country_box.count())] == [
            "All countries  (3)",
            "United States  (2)",
            "Germany  (1)",
            "United Kingdom  (0)",
        ]
        assert view.provider_box.itemText(3) == "Civo  (0)"
        assert view.type_box.count() == 1 + 4
        assert view.delivery_box.count() == 1 + 2
        assert sorted(label for label, _, _ in view.chart.bars) == ["ATS", "ERP", "HRIS", "Monitoring"]

    def test_filters(self, view: MarketplaceView) -> None:
        view.type_box.setCurrentIndex(view.type_box.findData(SoftwareType.ERP.value))
        assert view.count_label.text() == "1 of 3 software shown"

        view.type_box.setCurrentIndex(0)
        view.search_box.setText("datadog")
        assert view.count_label.text() == "1 of 3 software shown"
        assert view.developer_card.value_label.text() == "1"

        view.country_box.setCurrentIndex(view.country_box.findData(Country.GERMANY.value))
        assert view.count_label.text() == "0 of 3 software shown"

    def test_chart_colours_follow_the_categories(self, view: MarketplaceView) -> None:
        colours = {label: color for label, _, color in view.chart.bars}

        assert colours["Monitoring"] == Theme.CATEGORY_COLORS[DEV]
        assert colours["ATS"] == Theme.CATEGORY_COLORS[USER]

    def test_selection_shows_the_details(self, view: MarketplaceView, qtbot: QtBot) -> None:
        view.search_box.setText("odoo")

        view.table.selectRow(0)

        assert view.details.name_label.text() == "Odoo"
        with qtbot.waitSignal(view.copied):
            view.details.copy_button.click()

    def test_reload_keeps_the_filters(
        self, view: MarketplaceView, marketplaces: Dict[CloudProvider, CloudMarketplace]
    ) -> None:
        view.provider_box.setCurrentIndex(view.provider_box.findData(CloudProvider.STACKIT.value))

        view.set_marketplaces(marketplaces)

        assert view.selected_provider() is CloudProvider.STACKIT
        assert view.count_label.text() == "1 of 3 software shown"

    def test_selected_provider_and_country(self, view: MarketplaceView) -> None:
        assert (view.selected_provider(), view.selected_country()) == (None, None)

        view.country_box.setCurrentIndex(view.country_box.findData(Country.UNITED_KINGDOM.value))
        view.provider_box.setCurrentIndex(view.provider_box.findData(CloudProvider.CIVO.value))

        assert (view.selected_provider(), view.selected_country()) == (CloudProvider.CIVO, Country.UNITED_KINGDOM)
