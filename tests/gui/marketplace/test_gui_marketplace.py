from __future__ import annotations

from typing import Callable, Dict, List
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from conftest import CRAWLED_AT, fill_table, seed_marketplace
from gui.marketplace.model.software_row import SoftwareRow
from gui.marketplace.model.software_table_model import SoftwareTableModel
from gui.marketplace.widgets.domain_bar_chart import DomainBarChart
from gui.marketplace.widgets.marketplace_view import MarketplaceView
from gui.marketplace.widgets.software_details import SoftwareDetails
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.cloud.enums import CloudProvider, Country, DeliveryMethod, GeoBloc, SoftwareCategory
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.dataset_stamp import DatasetStamp
from models.storage.enums import ItemFilter
from models.storage.pages.software_facets import SoftwareFacets
from storage.storage import Storage

DEV = SoftwareCategory.DEVELOPER_TOOL
USER = SoftwareCategory.END_USER_SOFTWARE
PROVIDERS = [CloudProvider.AWS, CloudProvider.STACKIT, CloudProvider.CIVO]

MakeSoftware = Callable[..., MarketplaceSoftware]


def filed(listing: MarketplaceSoftware, *categories: str) -> MarketplaceSoftware:
    """File a software under taxonomy categories (and their domains)."""
    domains = sorted({category.split("/")[0] for category in categories})
    slugs = [category.split("/")[-1] for category in categories]
    return listing.model_copy(update={"service_categories": slugs, "service_domains": domains})


@pytest.fixture
def software(make_software: MakeSoftware) -> Dict[CloudProvider, List[MarketplaceSoftware]]:
    return {
        CloudProvider.AWS: [
            filed(make_software("Greenhouse", ["ats", "hris"], [USER]), "human-capital/ats", "human-capital/hris"),
            filed(
                make_software("Datadog", ["monitoring"], [DEV], publisher="Datadog Inc"),
                "management-observability/monitoring",
            ),
        ],
        CloudProvider.STACKIT: [
            filed(make_software("Odoo", ["erp"], [USER], DeliveryMethod.CONTAINER), "business-applications/erp")
        ],
    }


@pytest.fixture
def table(
    qapp: QApplication, offline_loop: StorageLoop, software: Dict[CloudProvider, List[MarketplaceSoftware]]
) -> SoftwareTableModel:
    model = SoftwareTableModel(Theme(), offline_loop)
    rows = [SoftwareRow(provider, item, CRAWLED_AT, id=1) for provider, items in software.items() for item in items]
    fill_table(model, rows)
    return model


class TestSoftwareTableModel:
    def test_rows_and_headers(self, table: SoftwareTableModel) -> None:
        assert (table.rowCount(), table.columnCount()) == (3, 10)
        assert table.headerData(SoftwareTableModel.DELIVERY, Qt.Orientation.Horizontal) == "Delivery"
        assert "Types" not in SoftwareTableModel.HEADERS
        assert table.headerData(0, Qt.Orientation.Vertical) is None
        assert table.rowCount(table.index(0, 0)) == 0
        assert table.columnCount(table.index(0, 0)) == 0

    def test_texts(self, table: SoftwareTableModel) -> None:
        texts = [table.data(table.index(0, column)) for column in range(SoftwareTableModel.ADDED)]

        assert texts == [
            "Amazon Web Services",
            "United States",
            "Greenhouse",
            "ACME",
            "Recruiting & applicant tracking, HR management (HRIS)",
            "ats, hris",
            "End-user software",
            "SaaS",
        ]
        assert table.data(table.index(2, SoftwareTableModel.DELIVERY)) == "Container"
        assert table.data(table.index(0, SoftwareTableModel.NAME), Qt.ItemDataRole.ToolTipRole) == (
            "Greenhouse description"
        )
        assert table.data(table.index(0, SoftwareTableModel.CATEGORIES), Qt.ItemDataRole.ToolTipRole) == (
            "Human Capital > Recruiting & applicant tracking\nHuman Capital > HR management (HRIS)"
        )
        assert table.data(table.index(0, SoftwareTableModel.LABELS), Qt.ItemDataRole.ToolTipRole) == "ats, hris"

    def test_missing_publisher_is_blank(
        self, qapp: QApplication, offline_loop: StorageLoop, make_software: MakeSoftware
    ) -> None:
        listing = make_software("Grafana", ["monitoring"], [DEV]).model_copy(update={"publisher": None})
        model = SoftwareTableModel(Theme(), offline_loop)
        fill_table(model, [SoftwareRow(CloudProvider.CIVO, listing, CRAWLED_AT)])

        assert model.data(model.index(0, SoftwareTableModel.PUBLISHER)) == ""

    def test_decorations(self, table: SoftwareTableModel) -> None:
        provider = table.index(0, SoftwareTableModel.PROVIDER)

        assert isinstance(table.data(provider, Qt.ItemDataRole.DecorationRole), QIcon)
        assert isinstance(table.data(table.index(0, SoftwareTableModel.COUNTRY), Qt.ItemDataRole.DecorationRole), QIcon)
        assert table.data(provider, Qt.ItemDataRole.ForegroundRole) == QColor(Theme.PROVIDER_COLORS[CloudProvider.AWS])
        assert table.data(table.index(0, SoftwareTableModel.NAME), Qt.ItemDataRole.FontRole) is None
        assert table.data(table.index(0, SoftwareTableModel.NAME), Qt.ItemDataRole.SizeHintRole) is None

    def test_invalid_index(self, table: SoftwareTableModel) -> None:
        assert table.data(QModelIndex()) is None

    def test_rows_carry_the_crawl_date_of_their_marketplace(self, table: SoftwareTableModel) -> None:
        table.set_crawl_dates({CloudProvider.AWS: CRAWLED_AT})

        assert table.crawled_at == {CloudProvider.AWS: CRAWLED_AT}


class TestDomainBarChart:
    def test_bars_are_sorted_and_painted(self, qtbot: QtBot) -> None:
        chart = DomainBarChart(Theme())
        qtbot.addWidget(chart)

        chart.set_bars([("CRM", 2, "#3fb950"), ("Monitoring", 5, "#4f8cff"), ("ATS", 2, "#3fb950")])
        chart.resize(chart.sizeHint())
        image = chart.grab().toImage()

        assert [label for label, _, _ in chart.bars] == ["Monitoring", "ATS", "CRM"]
        assert chart.sizeHint().height() == 3 * DomainBarChart.ROW_HEIGHT
        assert image.pixelColor(DomainBarChart.LABEL_WIDTH + 4, DomainBarChart.ROW_HEIGHT // 2) == QColor("#4f8cff")

    def test_empty_chart(self, qtbot: QtBot) -> None:
        chart = DomainBarChart(Theme())
        qtbot.addWidget(chart)
        chart.set_bars([])

        assert chart.sizeHint().height() == DomainBarChart.ROW_HEIGHT
        assert not chart.grab().isNull()


class TestSoftwareDetails:
    @pytest.fixture
    def details(self, qtbot: QtBot) -> SoftwareDetails:
        widget = SoftwareDetails(Theme())
        qtbot.addWidget(widget)
        return widget

    @pytest.fixture
    def row(self, software: Dict[CloudProvider, List[MarketplaceSoftware]]) -> SoftwareRow:
        return SoftwareRow(CloudProvider.AWS, software[CloudProvider.AWS][0], CRAWLED_AT)

    def test_placeholder(self, details: SoftwareDetails) -> None:
        assert details.name_label.text() == "No software selected"
        assert not details.copy_button.isEnabled()

    def test_shows_a_software(self, details: SoftwareDetails, row: SoftwareRow) -> None:
        details.show_row(row)

        assert details.name_label.text() == "Greenhouse"
        assert details.provider_label.text().strip() == "Amazon Web Services"
        assert details.country_label.text() == "United States"
        assert "ACME" in details.facts_label.text()
        assert "filter:publishers:ACME" in details.facts_label.text()
        assert "filter:deliveries:saas" in details.facts_label.text()
        assert "AUDIENCE" in details.chips_label.text()
        assert "End-user software" in details.chips_label.text()
        assert "filter:categories:end-user-software" in details.chips_label.text()
        assert "filter:service-categories:ats" in details.categories_label.text()
        assert "&nbsp;ats&nbsp;" in details.categories_label.text(), "the raw labels until the stored ones are read"
        assert details.marketplace_label.text() == "", "no taxonomy given by the marketplace"
        assert "https://marketplace.example.com/greenhouse" in details.link_label.text()
        assert details.crawled_label.text().startswith("Marketplace crawled on")

        details.show_row(None)
        assert details.link_label.text() == ""

    def test_shows_the_category_paths_of_the_marketplace(self, details: SoftwareDetails, row: SoftwareRow) -> None:
        paths = [MarketplaceCategory(path=["Business", "HR & Recruiting"], id="hr"), MarketplaceCategory(path=["AI"])]
        software = row.software.model_copy(update={"marketplace_category_paths": paths})

        details.show_row(SoftwareRow(row.provider, software, row.crawled_at))

        text = details.marketplace_label.text()
        assert "MARKETPLACE TAXONOMY" in text
        assert "Business &gt; HR &amp; Recruiting" in text
        assert "&nbsp;AI&nbsp;" in text
        assert "filter:" not in text, "the paths do not filter: the source labels do"
        assert details.marketplace_label.toolTip() == "Business > HR & Recruiting (hr)"

    def test_software_without_publisher_link_or_categories(self, details: SoftwareDetails, row: SoftwareRow) -> None:
        bare = row.software.model_copy(update={"publisher": None, "url": None, "marketplace_categories": []})

        details.show_row(SoftwareRow(row.provider, bare, row.crawled_at))

        assert "Unknown publisher" in details.facts_label.text()
        assert "filter:publishers" not in details.facts_label.text()
        assert (details.link_label.text(), details.marketplace_label.text()) == ("", "")

    def test_a_clicked_chip_asks_to_filter_the_table(
        self, details: SoftwareDetails, row: SoftwareRow, qtbot: QtBot
    ) -> None:
        details.show_row(row)

        with qtbot.waitSignal(details.filter_requested) as blocker:
            details._on_link(details.sheet.href(ItemFilter.SERVICE_CATEGORIES, "ats"))

        assert blocker.args == [ItemFilter.SERVICE_CATEGORIES.value, "ats"]

    def test_copy(self, details: SoftwareDetails, row: SoftwareRow, qtbot: QtBot) -> None:
        details.show_row(row)

        with qtbot.waitSignal(details.copied) as signal:
            details.copy_button.click()

        assert signal.args == [
            "Amazon Web Services — Greenhouse (Recruiting & applicant tracking, HR management (HRIS)): "
            "Greenhouse description"
        ]

    def test_copy_without_clipboard_or_software(self, details: SoftwareDetails, row: SoftwareRow, qtbot: QtBot) -> None:
        with qtbot.assertNotEmitted(details.copied):
            details.copy()
        details.show_row(row)
        with (
            patch("gui.marketplace.widgets.software_details.QApplication.clipboard", return_value=None),
            qtbot.waitSignal(details.copied),
        ):
            details.copy()


@pytest.mark.db
class TestMarketplaceView:
    @pytest.fixture
    async def stamps(
        self, storage: Storage, software: Dict[CloudProvider, List[MarketplaceSoftware]]
    ) -> Dict[CloudProvider, DatasetStamp]:
        for provider, items in software.items():
            await seed_marketplace(storage, provider, items)
        return {CloudProvider(stamp.dataset): stamp for stamp in await storage.datasets.stamps()}

    @pytest.fixture
    def view(self, qtbot: QtBot, gui_loop: StorageLoop, stamps: Dict[CloudProvider, DatasetStamp]) -> MarketplaceView:
        widget = MarketplaceView(Theme(), PROVIDERS, gui_loop)
        qtbot.addWidget(widget)
        widget.refresh(stamps)
        qtbot.waitUntil(lambda: widget.count_label.text() == "3 of 3 software shown", timeout=5000)
        return widget

    def test_empty_view(self, qtbot: QtBot, gui_loop: StorageLoop) -> None:
        view = MarketplaceView(Theme(), PROVIDERS, gui_loop)
        qtbot.addWidget(view)

        view.refresh({})

        qtbot.waitUntil(lambda: view.count_label.text() == "0 of 0 software shown", timeout=5000)
        assert view.marketplaces_card.value_label.text() == "0 / 3"

    def test_figures_and_combos(self, view: MarketplaceView, qtbot: QtBot) -> None:
        qtbot.waitUntil(lambda: view.software_card.value_label.text() == "3", timeout=5000)
        qtbot.waitUntil(lambda: view.country_box.itemText(0) == "All countries  (3)", timeout=5000)
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
        assert view.delivery_box.count() == 1 + 2
        assert view._filter_boxes() == [view.country_box, view.provider_box, view.category_box, view.delivery_box]
        assert sorted(label for label, _, _ in view.chart.bars) == [
            "Business Applications",
            "Human Capital",
            "Management & Observability",
        ]
        colours = {label: color for label, _, color in view.chart.bars}
        assert colours["Management & Observability"] == Theme.CATEGORY_COLORS[DEV]
        assert colours["Human Capital"] == Theme.CATEGORY_COLORS[USER]
        assert view.facets.by_domain == {"business-applications": 1, "human-capital": 1, "management-observability": 1}

    def test_filters(self, view: MarketplaceView, qtbot: QtBot) -> None:
        view.category_picker.set_picked(["business-applications"])
        qtbot.waitUntil(lambda: view.count_label.text() == "1 of 3 software shown", timeout=5000)

        view.category_picker.reset()
        view.search_box.setText("datadog")
        qtbot.waitUntil(lambda: view.table_model.total == 1, timeout=5000)
        qtbot.waitUntil(lambda: view.developer_card.value_label.text() == "1", timeout=5000)

        view.country_box.setCurrentIndex(view.country_box.findData(Country.GERMANY.value))
        qtbot.waitUntil(lambda: view.count_label.text() == "0 of 3 software shown", timeout=5000)

    def test_a_clicked_chip_filters_the_table(self, view: MarketplaceView, qtbot: QtBot) -> None:
        view.details._on_link(view.details.sheet.href(ItemFilter.SERVICE_CATEGORIES, "erp"))

        assert view.category_picker.picked() == ["erp"]
        qtbot.waitUntil(lambda: view.count_label.text() == "1 of 3 software shown", timeout=5000)
        view.details._on_link(view.details.sheet.href(ItemFilter.PUBLISHERS, "Nobody"))
        assert view.more_button.isChecked()
        qtbot.waitUntil(lambda: view.count_label.text() == "0 of 3 software shown", timeout=5000)

    def test_the_table_and_the_details_fold(self, view: MarketplaceView) -> None:
        view.table_section.set_expanded(False)
        assert view.table_stack.is_folded()
        view.details_pane.set_folded(True)
        assert view.details.isHidden()
        view.table_section.set_expanded(True)
        view.details_pane.set_folded(False)
        assert not view.table_stack.is_folded()

    def test_selection_shows_the_details(self, view: MarketplaceView, qtbot: QtBot) -> None:
        view.search_box.setText("odoo")
        qtbot.waitUntil(lambda: view.table_model.total == 1 and view.table_model.row(0) is not None, timeout=5000)

        view.table.selectRow(0)

        assert view.details.name_label.text() == "Odoo"
        with qtbot.waitSignal(view.copied):
            view.details.copy_button.click()

    def test_refresh_keeps_the_filters(
        self, view: MarketplaceView, qtbot: QtBot, stamps: Dict[CloudProvider, DatasetStamp]
    ) -> None:
        qtbot.waitUntil(lambda: view.provider_box.findData(CloudProvider.STACKIT.value) > 0, timeout=5000)
        view.provider_box.setCurrentIndex(view.provider_box.findData(CloudProvider.STACKIT.value))

        view.refresh(stamps)

        assert view.selected_provider() is CloudProvider.STACKIT
        qtbot.waitUntil(lambda: view.count_label.text() == "1 of 3 software shown", timeout=5000)

    def test_the_bloc_filter_shows_the_software_of_its_providers(self, view: MarketplaceView, qtbot: QtBot) -> None:
        qtbot.waitUntil(lambda: view.bloc_box.itemText(0) == "All blocs  (3)", timeout=5000)
        eu = view.bloc_box.findData(GeoBloc.EUROPEAN_UNION.value)
        assert view.bloc_box.itemText(eu).endswith("(1)")

        view.bloc_box.setCurrentIndex(eu)

        qtbot.waitUntil(lambda: view.count_label.text() == "1 of 3 software shown", timeout=5000)
        assert view.provider_picker.shown == {CloudProvider.STACKIT}, "the providers of the bloc are offered"
        assert view.table_model.query.providers == [CloudProvider.STACKIT]

    def test_several_providers_are_picked_at_once(self, view: MarketplaceView, qtbot: QtBot) -> None:
        picker = view.provider_picker
        assert picker.text().startswith("All providers")
        qtbot.waitUntil(lambda: picker.tree.provider_items[CloudProvider.AWS].text(0).endswith("(2)"), timeout=5000)

        picker.tree.provider_items[CloudProvider.STACKIT].setCheckState(0, Qt.CheckState.Unchecked)

        qtbot.waitUntil(lambda: view.count_label.text() == "2 of 3 software shown", timeout=5000)
        assert picker.text().startswith("2 providers")
        assert view.table_model.query.providers == [CloudProvider.AWS, CloudProvider.CIVO]
        picker.none_button.click()
        qtbot.waitUntil(lambda: view.count_label.text() == "0 of 3 software shown", timeout=5000)
        assert picker.text().startswith("No provider")
        assert (view.table_model.query.providers, view.table_model.query.restrict_providers) == ([], True)
        picker.all_button.click()
        qtbot.waitUntil(lambda: view.count_label.text() == "3 of 3 software shown", timeout=5000)
        assert (view.table_model.query.providers, view.table_model.query.restrict_providers) == ([], False)

    def test_the_picked_providers_combine_with_the_country(self, view: MarketplaceView, qtbot: QtBot) -> None:
        view.provider_picker.tree.provider_items[CloudProvider.STACKIT].setCheckState(0, Qt.CheckState.Unchecked)
        qtbot.waitUntil(lambda: view.count_label.text() == "2 of 3 software shown", timeout=5000)

        view.country_box.setCurrentIndex(view.country_box.findData(Country.GERMANY.value))

        qtbot.waitUntil(lambda: view.count_label.text() == "0 of 3 software shown", timeout=5000)
        assert view.provider_picker.text().startswith("No provider")
        view.country_box.setCurrentIndex(view.country_box.findData(Country.UNITED_STATES.value))
        qtbot.waitUntil(lambda: view.count_label.text() == "2 of 3 software shown", timeout=5000)
        assert view.provider_picker.text().startswith("All providers"), "the hidden check is kept"

    def test_selected_provider_and_country(self, view: MarketplaceView) -> None:
        assert (view.selected_provider(), view.selected_country()) == (None, None)

        view.country_box.setCurrentIndex(view.country_box.findData(Country.UNITED_KINGDOM.value))
        view.provider_box.setCurrentIndex(view.provider_box.findData(CloudProvider.CIVO.value))

        assert (view.selected_provider(), view.selected_country()) == (CloudProvider.CIVO, Country.UNITED_KINGDOM)

    def test_more_filters_filter_on_every_field(self, view: MarketplaceView, qtbot: QtBot) -> None:
        assert not view.advanced.isVisibleTo(view)
        view.more_button.click()
        assert view.advanced.isVisibleTo(view)
        qtbot.waitUntil(lambda: view.advanced.publisher_box.findText("Datadog Inc") > 0, timeout=5000)

        view.advanced.publisher_box.setCurrentIndex(view.advanced.publisher_box.findText("Datadog Inc"))

        qtbot.waitUntil(lambda: view.count_label.text() == "1 of 3 software shown", timeout=5000)
        assert view.more_button.text() == "More filters (1)"
        view.advanced.reset_button.click()
        qtbot.waitUntil(lambda: view.count_label.text() == "3 of 3 software shown", timeout=5000)
        assert view.more_button.text() == "More filters"
        view.advanced.name_box.setText("odo")
        qtbot.waitUntil(lambda: view.count_label.text() == "1 of 3 software shown", timeout=5000)


def test_the_software_meant_for_both_audiences_is_counted(qtbot: QtBot, offline_loop: StorageLoop) -> None:
    view = MarketplaceView(Theme(), PROVIDERS, offline_loop)
    qtbot.addWidget(view)
    facets = SoftwareFacets(total=10, by_category={DEV: 6, USER: 7})

    view._show_stats(facets)

    assert view.both_card.value_label.text() == "3"
    assert view.both_card.caption_label.text() == "30% of the software"
    view._show_stats(SoftwareFacets())
    assert view.both_card.value_label.text() == "0"


def test_the_domains_are_named_by_the_taxonomy_and_coloured_by_audience(
    qtbot: QtBot, offline_loop: StorageLoop
) -> None:
    view = MarketplaceView(Theme(), PROVIDERS, offline_loop)
    qtbot.addWidget(view)
    facets = SoftwareFacets(
        total=6,
        by_domain={"databases": 4, "human-capital": 2},
        by_domain_and_category={"databases": {DEV: 3, USER: 1}, "human-capital": {USER: 2}},
    )

    view._show_stats(facets)

    expected = [("Databases", 4, Theme.CATEGORY_COLORS[DEV]), ("Human Capital", 2, Theme.CATEGORY_COLORS[USER])]
    assert view.chart.bars == expected
    assert view.facets is facets
    assert (view.domains_section.key, view.domains_section.title()) == ("marketplace/domains", "Software per domain")
    view.chart.set_bars([])
    view.taxonomy.changed.emit()
    assert view.chart.bars == expected, "the domains are named again once the taxonomy is read"
