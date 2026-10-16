from __future__ import annotations

# Standard Library Imports.
from collections import Counter
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Tuple

# Third Party Imports.
from PyQt6.QtCore import QItemSelectionModel, QModelIndex, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from gui.marketplace.software_details import SoftwareDetails
from gui.marketplace.software_filter_model import SoftwareFilterModel
from gui.marketplace.software_row import SoftwareRow
from gui.marketplace.software_table_model import SoftwareTableModel
from gui.marketplace.type_bar_chart import Bar, TypeBarChart
from gui.theme import Theme
from gui.widgets.dashboard.stat_card import StatCard
from models.cloud.enums import CloudProvider, Country, DeliveryMethod, SoftwareCategory, SoftwareType
from models.cloud.marketplace import CloudMarketplace

ComboItem = Tuple[str, str, Optional[QIcon], int]


class MarketplaceView(QWidget):
    """Explorer of the marketplace software: figures, filters, the software table and the selected software details.

    Attributes:
        copied (pyqtSignal): Emitted with the copied text when a software is copied to the clipboard.
        theme (Theme): The application theme.
        providers (List[CloudProvider]): The cloud providers having a marketplace crawler.
        marketplaces (Dict[CloudProvider, CloudMarketplace]): The loaded marketplaces.
        table_model (SoftwareTableModel): The software of every loaded marketplace.
        filter_model (SoftwareFilterModel): The filtered and sorted software.
        software_card (StatCard): The number of shown software.
        developer_card (StatCard): The number of shown developer tools.
        end_user_card (StatCard): The number of shown end-user software.
        marketplaces_card (StatCard): The number of crawled marketplaces.
        chart (TypeBarChart): The shown software per type.
        search_box (QLineEdit): The searched text.
        country_box (QComboBox): The country filter.
        provider_box (QComboBox): The provider filter.
        category_box (QComboBox): The category filter.
        type_box (QComboBox): The type filter.
        delivery_box (QComboBox): The delivery method filter.
        table (QTableView): The software table.
        details (SoftwareDetails): The selected software details.
        count_label (QLabel): How many software are shown.
        deleted_box (QCheckBox): Shows the software deleted from its marketplace.
    """

    copied = pyqtSignal(str)

    def __init__(self, theme: Theme, providers: Sequence[CloudProvider], logger: Optional[Logger] = None) -> None:
        """Build the view, without marketplace.

        Args:
            theme (Theme): The application theme.
            providers (Sequence[CloudProvider]): The cloud providers having a marketplace crawler.
            logger (Optional[Logger]): The view logger.
        """
        super().__init__()
        self.theme = theme
        self.providers = list(providers)
        self.logger = logger if logger else getLogger(__name__)
        self.marketplaces: Dict[CloudProvider, CloudMarketplace] = {}
        self.table_model = SoftwareTableModel(theme)
        self.filter_model = SoftwareFilterModel(self.table_model)
        self.software_card = StatCard("Software")
        self.developer_card = StatCard("Developer tools")
        self.end_user_card = StatCard("End-user software")
        self.marketplaces_card = StatCard("Marketplaces crawled")
        self.chart = TypeBarChart(theme)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search software by name, description or publisher\u2026")
        self.search_box.setClearButtonEnabled(True)
        self.country_box, self.provider_box = QComboBox(), QComboBox()
        self.category_box, self.type_box, self.delivery_box = QComboBox(), QComboBox(), QComboBox()
        self.table = QTableView()
        self.details = SoftwareDetails(theme)
        self.count_label = QLabel()
        self.count_label.setObjectName("muted")
        self.deleted_box = QCheckBox("Show deleted")
        self.deleted_box.setToolTip("Show the software which disappeared from its marketplace, struck through")
        self._build_layout()
        self._build_table()
        self._update_combos()
        self._apply_filters()
        self.search_box.textChanged.connect(self._apply_filters)
        self.deleted_box.toggled.connect(self._apply_filters)
        for box in self._filter_boxes():
            box.currentIndexChanged.connect(self._apply_filters)
        self.details.copied.connect(self.copied.emit)

    ############################
    # Internal Helpers Methods #
    ############################

    def _filter_boxes(self) -> List[QComboBox]:
        """Get the filter combo boxes.

        Returns:
            List[QComboBox]: The country, provider, category, type and delivery filters.
        """
        return [self.country_box, self.provider_box, self.category_box, self.type_box, self.delivery_box]

    def _build_layout(self) -> None:
        """Lay the figures, the type chart, the filters, the table and the details out."""
        chart_area = QScrollArea()
        chart_area.setWidget(self.chart)
        chart_area.setWidgetResizable(True)
        chart_area.setFrameShape(QFrame.Shape.NoFrame)
        chart_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        chart_frame = QFrame()
        chart_frame.setObjectName("card")
        chart_layout = QVBoxLayout(chart_frame)
        chart_title = QLabel("SOFTWARE PER TYPE")
        chart_title.setObjectName("muted")
        chart_layout.addWidget(chart_title)
        chart_layout.addWidget(chart_area)
        stats = QWidget()
        stats.setMaximumHeight(185)
        stats_layout = QHBoxLayout(stats)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        for card in (self.software_card, self.developer_card, self.end_user_card, self.marketplaces_card):
            stats_layout.addWidget(card, 2)
        stats_layout.addWidget(chart_frame, 5)
        filters = QHBoxLayout()
        filters.setSpacing(8)
        filters.addWidget(self.search_box, 3)
        for box in self._filter_boxes():
            box.setMinimumWidth(150)
            filters.addWidget(box, 1)
        filters.addWidget(self.deleted_box)
        software = QWidget()
        software_layout = QVBoxLayout(software)
        software_layout.setContentsMargins(0, 0, 0, 0)
        software_layout.setSpacing(10)
        software_layout.addWidget(stats)
        software_layout.addLayout(filters)
        software_layout.addWidget(self.table, 1)
        software_layout.addWidget(self.count_label)
        splitter = QSplitter()
        splitter.addWidget(software)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([1100, 340])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(splitter)

    def _build_table(self) -> None:
        """Set the software table up: sortable, single row selection, details on selection."""
        header = QHeaderView(Qt.Orientation.Horizontal)
        header.setSectionsClickable(True)
        header.setStretchLastSection(True)
        vertical_header = QHeaderView(Qt.Orientation.Vertical)
        vertical_header.setVisible(False)
        self.table.setHorizontalHeader(header)
        self.table.setVerticalHeader(vertical_header)
        self.table.setModel(self.filter_model)
        selection = QItemSelectionModel(self.filter_model)
        self.table.setSelectionModel(selection)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(SoftwareTableModel.NAME, Qt.SortOrder.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        for column, width in (
            (SoftwareTableModel.PROVIDER, 170),
            (SoftwareTableModel.COUNTRY, 130),
            (SoftwareTableModel.NAME, 280),
            (SoftwareTableModel.PUBLISHER, 170),
            (SoftwareTableModel.CATEGORIES, 170),
            (SoftwareTableModel.TYPES, 190),
            (SoftwareTableModel.DELIVERY, 130),
            (SoftwareTableModel.ADDED, 100),
        ):
            self.table.setColumnWidth(column, width)
        selection.currentRowChanged.connect(self._on_current_changed)

    def _fill_combo(self, box: QComboBox, all_label: str, items: List[ComboItem]) -> None:
        """Fill a filter combo box, keeping its selection.

        Args:
            box (QComboBox): The combo box.
            all_label (str): The label of the "every value" entry.
            items (List[ComboItem]): The label, value, icon and software count of each entry.
        """
        selected = box.currentData()
        box.blockSignals(True)
        box.clear()
        box.addItem(f"{all_label}  ({sum(count for _, _, _, count in items):,})", "")
        for label, value, icon, count in items:
            text = f"{label}  ({count:,})"
            if icon is None:
                box.addItem(text, value)
            else:
                box.addItem(icon, text, value)
        box.setCurrentIndex(max(box.findData(selected), 0))
        box.blockSignals(False)

    def _update_combos(self) -> None:
        """Show the number of listed software of each filter value in the filter combo boxes."""
        rows = [row for row in self.table_model.rows if not row.software.is_deleted]
        countries = Counter(row.provider.country for row in rows)
        providers = Counter(row.provider for row in rows)
        categories = Counter(category for row in rows for category in row.software.categories)
        kinds = Counter(kind for row in rows for kind in row.software.types)
        deliveries = Counter(row.software.delivery for row in rows)
        shown_countries = list(dict.fromkeys(provider.country for provider in self.providers))
        self._fill_combo(
            self.country_box,
            "All countries",
            [
                (self.theme.country_label(c), c.value, self.theme.flag_icon(c, 14), countries[c])
                for c in shown_countries
            ],
        )
        self._fill_combo(
            self.provider_box,
            "All marketplaces",
            [
                (self.theme.provider_label(p), p.value, self.theme.provider_icon(p), providers[p])
                for p in self.providers
            ],
        )
        self._fill_combo(
            self.category_box,
            "All categories",
            [(self.theme.category_label(c), c.value, None, categories[c]) for c in SoftwareCategory],
        )
        self._fill_combo(
            self.type_box,
            "All types",
            [(self.theme.type_label(kind), kind.value, None, kinds[kind]) for kind in SoftwareType if kinds[kind]],
        )
        self._fill_combo(
            self.delivery_box,
            "All deliveries",
            [(self.theme.delivery_label(d), d.value, None, deliveries[d]) for d in DeliveryMethod if deliveries[d]],
        )

    def _shown_rows(self) -> List[SoftwareRow]:
        """Get the rows matching the filters.

        Returns:
            List[SoftwareRow]: The shown rows, in table order.
        """
        return [row for row in self.table_model.rows if self.filter_model._accepts(row)]

    def _update_stats(self) -> None:
        """Show the figures and the type chart of the shown software."""
        rows = self._shown_rows()
        deleted = sum(1 for row in self.table_model.rows if row.software.is_deleted)
        listed = len(self.table_model.rows) - deleted
        categories = Counter(category for row in rows for category in row.software.categories)
        self.software_card.set_value(f"{len(rows):,}", f"of {listed:,} listed")
        self.developer_card.set_value(f"{categories[SoftwareCategory.DEVELOPER_TOOL]:,}", "to build and run apps")
        self.end_user_card.set_value(f"{categories[SoftwareCategory.END_USER_SOFTWARE]:,}", "for the business users")
        crawled = f"{len(self.marketplaces)} / {len(self.providers)}"
        self.marketplaces_card.set_value(crawled, "files in output/marketplaces")
        kinds = Counter(kind for row in rows for kind in row.software.types)
        developer_kinds = Counter(
            kind
            for row in rows
            if SoftwareCategory.DEVELOPER_TOOL in row.software.categories
            for kind in row.software.types
        )
        bars: List[Bar] = [
            (
                self.theme.type_label(kind),
                count,
                self.theme.CATEGORY_COLORS[
                    SoftwareCategory.DEVELOPER_TOOL
                    if developer_kinds[kind] * 2 >= count
                    else SoftwareCategory.END_USER_SOFTWARE
                ],
            )
            for kind, count in kinds.items()
        ]
        self.chart.set_bars(bars)
        state = "included" if self.filter_model.show_deleted else "hidden"
        suffix = f" ({deleted:,} deleted {state})" if deleted else ""
        self.count_label.setText(f"{len(rows):,} of {listed:,} software shown{suffix}")

    def _apply_filters(self) -> None:
        """Show only the software matching the search and the filters, and their figures."""
        values = [box.currentData() or "" for box in self._filter_boxes()]
        country, provider, category, kind, delivery = values
        self.filter_model.set_filters(
            self.search_box.text(),
            CloudProvider(provider) if provider else None,
            Country(country) if country else None,
            SoftwareCategory(category) if category else None,
            SoftwareType(kind) if kind else None,
            DeliveryMethod(delivery) if delivery else None,
            self.deleted_box.isChecked(),
        )
        self._update_stats()

    def _on_current_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        """Show the details of the selected software.

        Args:
            current (QModelIndex): The selected index.
            previous (QModelIndex): The previously selected index.
        """
        self.details.show_row(self.filter_model.row_at(current))

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_marketplaces(self, marketplaces: Dict[CloudProvider, CloudMarketplace]) -> None:
        """Show the software of the loaded marketplaces, keeping the filters.

        Args:
            marketplaces (Dict[CloudProvider, CloudMarketplace]): The loaded marketplaces, by cloud provider.
        """
        self.marketplaces = marketplaces
        self.table.setSortingEnabled(False)
        self.table_model.set_marketplaces(marketplaces)
        self.table.setSortingEnabled(True)
        self._update_combos()
        self._apply_filters()
        self.details.show_row(None)
        self.logger.debug("%d software shown from %d marketplaces.", len(self.table_model.rows), len(marketplaces))

    def selected_provider(self) -> Optional[CloudProvider]:
        """Get the provider chosen in the provider filter.

        Returns:
            Optional[CloudProvider]: The provider, `None` for all of them.
        """
        value = self.provider_box.currentData()
        return CloudProvider(value) if value else None

    def selected_country(self) -> Optional[Country]:
        """Get the country chosen in the country filter.

        Returns:
            Optional[Country]: The country, `None` for all of them.
        """
        value = self.country_box.currentData()
        return Country(value) if value else None
