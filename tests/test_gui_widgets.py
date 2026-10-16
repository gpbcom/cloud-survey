from __future__ import annotations

import logging
from typing import Callable, Dict, List
from unittest.mock import patch

import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from gui.product_model.product_row import ProductRow
from gui.theme import Theme
from gui.widgets.dashboard.dashboard import Dashboard
from gui.widgets.dashboard.provider_bar_chart import ProviderBarChart
from gui.widgets.dashboard.stat_card import StatCard
from gui.widgets.log_panel import LogPanel
from gui.widgets.product_details import ProductDetails
from gui.widgets.provider_sidebar import ProviderSidebar
from models.cloud.catalogue import CloudCatalogue
from models.cloud.enums import CloudProvider, Country

MakeCatalogue = Callable[[CloudProvider, List[str]], CloudCatalogue]


@pytest.fixture
def catalogues(make_catalogue: MakeCatalogue) -> Dict[CloudProvider, CloudCatalogue]:
    return {
        CloudProvider.AWS: make_catalogue(CloudProvider.AWS, ["Amazon EC2", "Amazon S3"]),
        CloudProvider.SCALEWAY: make_catalogue(CloudProvider.SCALEWAY, ["Kubernetes Kapsule"]),
    }


class TestProviderSidebar:
    @pytest.fixture
    def sidebar(self, qtbot: QtBot) -> ProviderSidebar:
        widget = ProviderSidebar(Theme())
        qtbot.addWidget(widget)
        return widget

    def test_lists_all_providers_first(self, sidebar: ProviderSidebar) -> None:
        assert sidebar.count() == 1 + len(Country) + len(CloudProvider)
        assert sidebar.currentItem() is sidebar.all_item
        assert sidebar.selected_provider() is None
        assert sidebar.selected_country() is None

    def test_providers_are_grouped_under_their_country(self, sidebar: ProviderSidebar) -> None:
        rows = [sidebar.item(row) for row in range(sidebar.count())]

        for provider, item in sidebar.provider_items.items():
            header = sidebar.country_items[provider.country]
            assert rows.index(header) < rows.index(item)
            following = rows[rows.index(header) + 1 : rows.index(item)]
            assert all(other not in sidebar.country_items.values() for other in following)
        uk = sidebar.country_items[Country.UNITED_KINGDOM]
        assert uk.text() == "United Kingdom"
        assert uk.font().bold()
        assert not uk.icon().isNull()

    def test_country_header_selection(self, sidebar: ProviderSidebar, qtbot: QtBot) -> None:
        with qtbot.waitSignals([sidebar.country_changed, sidebar.provider_changed]) as signals:
            sidebar.setCurrentItem(sidebar.country_items[Country.CHINA])

        assert [list(signal.args) for signal in signals.all_signals_and_args] == [["cn"], [""]]
        assert sidebar.selected_country() is Country.CHINA
        assert sidebar.selected_provider() is None

    def test_provider_selection_gives_its_country(self, sidebar: ProviderSidebar, qtbot: QtBot) -> None:
        with qtbot.waitSignal(sidebar.country_changed) as signal:
            sidebar.setCurrentItem(sidebar.provider_items[CloudProvider.INFOMANIAK])

        assert signal.args == ["ch"]
        assert sidebar.selected_country() is Country.SWITZERLAND

    def test_select_country(self, sidebar: ProviderSidebar) -> None:
        sidebar.select_country(Country.FRANCE)
        assert sidebar.currentItem() is sidebar.country_items[Country.FRANCE]

        sidebar.setCurrentItem(sidebar.provider_items[CloudProvider.OVH])
        sidebar.select_country(Country.FRANCE)
        assert sidebar.currentItem() is sidebar.provider_items[CloudProvider.OVH]

        sidebar.select_country(None)
        assert sidebar.currentItem() is sidebar.provider_items[CloudProvider.OVH]

        sidebar.select_country(Country.SPAIN)
        assert sidebar.currentItem() is sidebar.country_items[Country.SPAIN]

        sidebar.select_country(None)
        assert sidebar.currentItem() is sidebar.all_item

    def test_selection_is_emitted(self, sidebar: ProviderSidebar, qtbot: QtBot) -> None:
        with qtbot.waitSignal(sidebar.provider_changed) as signal:
            sidebar.setCurrentItem(sidebar.provider_items[CloudProvider.GCP])

        assert signal.args == ["google-cloud-platform"]
        assert sidebar.selected_provider() is CloudProvider.GCP

        with qtbot.waitSignal(sidebar.provider_changed) as signal:
            sidebar.setCurrentItem(sidebar.all_item)
        assert signal.args == [""]

    def test_no_selection(self, sidebar: ProviderSidebar, qtbot: QtBot) -> None:
        with qtbot.waitSignal(sidebar.provider_changed) as signal:
            sidebar.setCurrentItem(None)

        assert signal.args == [""]
        assert sidebar.selected_provider() is None

    def test_catalogue_states(self, sidebar: ProviderSidebar, catalogues: Dict[CloudProvider, CloudCatalogue]) -> None:
        sidebar.update_catalogues(catalogues, {CloudProvider.OVH: "the file is not valid JSON"})

        assert sidebar.all_item.text() == "All providers\n3 products · 2/28 crawled"
        assert sidebar.country_items[Country.UNITED_STATES].text() == "United States\n2 products · 1/5 crawled"
        assert sidebar.country_items[Country.FRANCE].text() == "France\n1 products · 1/2 crawled"
        assert sidebar.country_items[Country.CHINA].text() == "China\n0 products · 0/7 crawled"
        aws = sidebar.provider_items[CloudProvider.AWS]
        assert aws.text().startswith("Amazon Web Services\n2 products · ")
        assert aws.foreground().color() == QColor(Theme.TEXT)
        ovh = sidebar.provider_items[CloudProvider.OVH]
        assert ovh.text() == "OVHcloud\n⚠ Unusable catalogue file"
        assert ovh.toolTip() == "the file is not valid JSON"
        azure = sidebar.provider_items[CloudProvider.AZURE]
        assert azure.text() == "Microsoft Azure\nNot crawled yet"
        assert azure.foreground().color() == QColor(Theme.TEXT_MUTED)


class TestDashboard:
    def test_stat_card(self, qtbot: QtBot) -> None:
        card = StatCard("Products")
        qtbot.addWidget(card)

        card.set_value("42", "caption")

        assert (card.value_label.text(), card.caption_label.text()) == ("42", "caption")

    def test_figures(self, qtbot: QtBot, catalogues: Dict[CloudProvider, CloudCatalogue]) -> None:
        dashboard = Dashboard(Theme())
        qtbot.addWidget(dashboard)

        dashboard.update_catalogues(catalogues)

        assert dashboard.products_card.value_label.text() == "3"
        assert dashboard.providers_card.value_label.text() == "2 / 28"
        assert dashboard.crawl_card.caption_label.text() in {"Amazon Web Services", "Scaleway"}
        assert dashboard.chart.counts == {CloudProvider.AWS: 2, CloudProvider.SCALEWAY: 1}

    def test_figures_of_a_country(self, qtbot: QtBot, catalogues: Dict[CloudProvider, CloudCatalogue]) -> None:
        dashboard = Dashboard(Theme())
        qtbot.addWidget(dashboard)

        dashboard.update_catalogues(catalogues, Country.FRANCE)

        assert dashboard.products_card.value_label.text() == "1"
        assert dashboard.products_card.caption_label.text() == "in France"
        assert dashboard.providers_card.value_label.text() == "1 / 2"
        assert dashboard.crawl_card.caption_label.text() == "Scaleway"
        assert dashboard.chart_title.text() == "PRODUCTS PER PROVIDER \u2014 France"
        assert dashboard.chart.providers == [CloudProvider.OVH, CloudProvider.SCALEWAY]
        assert dashboard.chart.counts == {CloudProvider.SCALEWAY: 1}

        dashboard.update_catalogues(catalogues)
        assert dashboard.chart_title.text() == "PRODUCTS PER PROVIDER"
        assert dashboard.chart.providers == list(CloudProvider)

    def test_without_catalogue(self, qtbot: QtBot) -> None:
        dashboard = Dashboard(Theme())
        qtbot.addWidget(dashboard)

        dashboard.update_catalogues({})

        assert dashboard.products_card.value_label.text() == "0"
        assert dashboard.crawl_card.caption_label.text() == "no catalogue crawled yet"

    @pytest.mark.parametrize("counts", [{}, {CloudProvider.AWS: 267, CloudProvider.SCALEWAY: 68}])
    def test_chart_paints_the_bars(self, qtbot: QtBot, counts: Dict[CloudProvider, int]) -> None:
        chart = ProviderBarChart(Theme())
        qtbot.addWidget(chart)
        chart.resize(chart.sizeHint())
        chart.set_counts(counts)

        image = chart.grab().toImage()

        assert chart.sizeHint().height() == ProviderBarChart.ROW_HEIGHT * len(CloudProvider)
        assert chart.minimumHeight() == chart.sizeHint().height()
        aws_bar = image.pixelColor(chart._label_width() + 5, ProviderBarChart.ROW_HEIGHT // 2)
        expected = Theme.PROVIDER_COLORS[CloudProvider.AWS] if counts else Theme.SURFACE_ALT
        assert aws_bar == QColor(expected)
        assert image.pixelColor(3, ProviderBarChart.ROW_HEIGHT // 2 - 2) == QColor("#3c3b6e")

    def test_chart_of_some_providers(self, qtbot: QtBot) -> None:
        chart = ProviderBarChart(Theme())
        qtbot.addWidget(chart)

        chart.set_counts({CloudProvider.CIVO: 27}, [CloudProvider.CIVO, CloudProvider.KRYSTAL])

        assert chart.sizeHint().height() == 2 * ProviderBarChart.ROW_HEIGHT
        assert chart.minimumHeight() == 2 * ProviderBarChart.ROW_HEIGHT

    def test_chart_scrolls_in_the_dashboard(self, qtbot: QtBot) -> None:
        dashboard = Dashboard(Theme())
        qtbot.addWidget(dashboard)

        assert dashboard.chart_area.widget() is dashboard.chart


class TestProductDetails:
    @pytest.fixture
    def details(self, qtbot: QtBot) -> ProductDetails:
        widget = ProductDetails(Theme())
        qtbot.addWidget(widget)
        return widget

    @pytest.fixture
    def row(self, catalogues: Dict[CloudProvider, CloudCatalogue]) -> ProductRow:
        catalogue = catalogues[CloudProvider.SCALEWAY]
        return ProductRow(CloudProvider.SCALEWAY, catalogue.products[0], catalogue.crawled_at)

    def test_placeholder(self, details: ProductDetails) -> None:
        assert details.name_label.text() == "No product selected"
        assert not details.copy_button.isEnabled()

    def test_shows_a_product(self, details: ProductDetails, row: ProductRow) -> None:
        details.show_row(row)

        assert details.name_label.text() == "Kubernetes Kapsule"
        assert details.provider_label.text().strip() == "Scaleway"
        assert Theme.PROVIDER_COLORS[CloudProvider.SCALEWAY] in details.provider_label.styleSheet()
        assert details.description_label.text() == "Kubernetes Kapsule description"
        assert details.crawled_label.text().startswith("Crawled on 16 Oct 2026")
        assert details.country_label.text() == "France"
        pixmap = details.flag_label.pixmap()
        assert pixmap is not None
        assert not pixmap.isNull()
        assert details.copy_button.isEnabled()

        details.show_row(None)
        assert details.provider_label.styleSheet() == ""
        assert details.country_label.text() == ""

    def test_copy(self, details: ProductDetails, row: ProductRow, qtbot: QtBot, qapp: QApplication) -> None:
        details.show_row(row)

        with qtbot.waitSignal(details.copied) as signal:
            details.copy_button.click()

        expected = "Scaleway — Kubernetes Kapsule: Kubernetes Kapsule description"
        assert signal.args == [expected]
        clipboard = qapp.clipboard()
        assert clipboard is not None
        assert clipboard.text() == expected

    def test_copy_without_clipboard(self, details: ProductDetails, row: ProductRow, qtbot: QtBot) -> None:
        details.show_row(row)

        with (
            patch("gui.widgets.product_details.QApplication.clipboard", return_value=None),
            qtbot.waitSignal(details.copied),
        ):
            details.copy()

    def test_copy_without_product(self, details: ProductDetails, qtbot: QtBot) -> None:
        with qtbot.assertNotEmitted(details.copied):
            details.copy()


class TestLogPanel:
    @pytest.fixture
    def panel(self, qtbot: QtBot) -> LogPanel:
        widget = LogPanel(Theme())
        qtbot.addWidget(widget)
        return widget

    def test_shows_info_and_above_by_default(self, panel: LogPanel) -> None:
        panel.append_record(logging.DEBUG, "crawler", "hidden")
        panel.append_record(logging.INFO, "crawler", "Product extracted <b>bold</b>")
        panel.append_record(logging.ERROR, "crawler", "Fetching failed")

        assert panel.minimum_level() == logging.INFO
        lines = panel.view.toPlainText().splitlines()
        assert [line.split(maxsplit=2)[2] for line in lines] == ["Product extracted <b>bold</b>", "Fetching failed"]
        assert lines[1].startswith("ERROR")
        document = panel.view.document()
        assert document is not None
        assert Theme.LEVEL_COLORS[logging.ERROR] in document.toHtml()

    def test_level_filter_and_clear(self, panel: LogPanel) -> None:
        panel.level_box.setCurrentText("DEBUG")
        panel.append_record(logging.DEBUG, "crawler", "now shown")
        assert "now shown" in panel.view.toPlainText()

        panel.clear_button.click()
        assert panel.view.toPlainText() == ""
