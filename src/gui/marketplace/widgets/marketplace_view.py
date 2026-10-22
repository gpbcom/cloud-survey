from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, FrozenSet, List, Optional, Sequence, Tuple

# Third Party Imports.
from PyQt6.QtCore import QItemSelectionModel, QModelIndex, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.charts.panels.chart_panel import ChartPanel
from gui.charts.panels.stored_chart_controller import StoredChartController
from gui.charts.sections.chart_state_store import ChartStateStore
from gui.charts.sections.section.chart_section import ChartSection
from gui.charts.sections.section.sections_toolbar import SectionsToolbar

# First Party Imports.
from gui.editing.item_actions import ItemActions
from gui.layout.fitted_scroll_area import FittedScrollArea
from gui.layout.flow_layout import FlowLayout
from gui.layout.folding_splitter import FoldingSplitter
from gui.layout.panes.section_stack import SectionStack
from gui.layout.panes.side_pane import SidePane
from gui.marketplace.model.software_row import SoftwareRow
from gui.marketplace.model.software_table_model import SoftwareTableModel
from gui.marketplace.widgets.advanced_filters import AdvancedSoftwareFilters
from gui.marketplace.widgets.domain_bar_chart import Bar, DomainBarChart
from gui.marketplace.widgets.software_details import SoftwareDetails
from gui.selection.bulk.selection_actions import SelectionActions
from gui.selection.pickers.provider_picker import ProviderPicker
from gui.selection.taxonomy.category_picker import CategoryPicker
from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from gui.widgets.compact_combo import CompactCombo
from gui.widgets.dashboard.stat_card import StatCard
from models.cloud.enums import CloudProvider, Country, DeliveryMethod, GeoBloc, SoftwareCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.dataset_stamp import DatasetStamp
from models.storage.enums import DatasetKind, ItemFilter, ItemSort
from models.storage.pages.item_query import ItemQuery
from models.storage.pages.software_facets import SoftwareFacets
from models.trends.enums import ChartScope
from storage.exception import StorageError

ComboItem = Tuple[str, str, Optional[QIcon], int]


class MarketplaceView(QWidget):
    """Explorer of the marketplace software: figures, filters, the software table and the selected software details.

    Attributes:
        SEARCH_DELAY_MS (ClassVar[int]): How long the search text must stay unchanged before it is searched.
        DOMAIN_CHART_HEIGHT (ClassVar[int]): The height below which the chart of the software per domain scrolls.
        copied (pyqtSignal): Emitted with the copied text when a software is copied to the clipboard.
        theme (Theme): The application theme.
        providers (List[CloudProvider]): The cloud providers having a marketplace crawler.
        loop (StorageLoop): The storage thread of the GUI.
        stamps (Dict[CloudProvider, DatasetStamp]): The state of the stored marketplaces.
        deleted (int): The number of stored software deleted from their marketplace.
        facets (SoftwareFacets): The counts of the software matching the filters, last read.
        table_model (SoftwareTableModel): The software matching the filters, read page by page.
        search_timer (QTimer): Delays the search while the text is typed.
        software_card (StatCard): The number of shown software.
        developer_card (StatCard): The number of shown developer tools.
        end_user_card (StatCard): The number of shown end-user software.
        both_card (StatCard): The number of shown software meant for both (developer tool and end-user software),
            and their share.
        marketplaces_card (StatCard): The number of crawled marketplaces.
        chart (DomainBarChart): The shown software per taxonomy domain.
        store (ChartStateStore): The store of the chart states.
        trends (ChartPanel): The configurable chart of the marketplace analysis.
        controller (StoredChartController): Reads the marketplace analysis.
        sections (SectionsToolbar): Expands or collapses every chart of the view.
        domains_section (ChartSection): The collapsible card of the software per domain.
        trends_section (ChartSection): The collapsible card of the marketplace analysis.
        table_section (ChartSection): The collapsible card of the software table (its actions in the header).
        stats_stack (SectionStack): The figures and the charts, sharing the height of the view.
        table_stack (SectionStack): Holds the software table card, folding when it is collapsed.
        details_pane (SidePane): Holds the software details, folding to a strip on request.
        search_box (QLineEdit): The searched text.
        country_box (QComboBox): The country filter.
        provider_box (QComboBox): The provider filter.
        bloc_box (QComboBox): The geopolitical bloc filter (the providers of a bloc).
        provider_picker (ProviderPicker): The providers filter, several at once (those of the chosen bloc and
            country are offered).
        category_box (QComboBox): The category filter.
        delivery_box (QComboBox): The delivery method filter.
        taxonomy (TaxonomyCache): The unified taxonomy and the names of the source labels.
        category_picker (CategoryPicker): The filter on the categories and domains of the unified taxonomy.
        table (QTableView): The software table.
        details (SoftwareDetails): The selected software details.
        count_label (QLabel): How many software are shown.
        deleted_box (QCheckBox): Shows the software deleted from its marketplace.
        description_box (QCheckBox): Searches the descriptions too.
        advanced (AdvancedSoftwareFilters): The filters on the other fields (texts, publisher, marketplace
            categories, dates), shown on request.
        more_button (QPushButton): Shows or hides the other filters, with the number of those set.
        new_button, edit_button, delete_button (QToolButton): Create a software, edit or delete the selected ones.
        item_actions (ItemActions[MarketplaceSoftware, SoftwareRow]): The create, edit and delete actions of the
            selected software (several rows at once, also in the context menu of the table).
        select_button (QToolButton): Opens the bulk selection dialog.
        selection_button (QPushButton): Shown while the table shows a bulk selection: clears it.
        selection_actions (SelectionActions[MarketplaceSoftware, SoftwareRow]): The bulk selection of the software
            (chosen by criteria, then shown, exported or deleted).
        selection_query (Optional[ItemQuery]): The bulk selection shown instead of the filters, `None` for none.

    Notes:
        - Every figure is counted by the server (`MarketplaceRepository.facets`), and the table reads the matching
          software page by page: the view never holds every software of the marketplaces.
        - The charts follow the filters of the table, and scroll above it (the splitter sets their share). A collapsed
          table gives its height to the charts, collapsed charts give theirs to the table.
    """

    SEARCH_DELAY_MS: ClassVar[int] = 300
    DOMAIN_CHART_HEIGHT: ClassVar[int] = 160

    copied = pyqtSignal(str)

    def __init__(
        self,
        theme: Theme,
        providers: Sequence[CloudProvider],
        loop: StorageLoop,
        logger: Optional[Logger] = None,
        store: Optional[ChartStateStore] = None,
        statistics_source: str = "synergy",
        taxonomy: Optional[TaxonomyCache] = None,
    ) -> None:
        """Build the view, without software until `refresh`.

        Args:
            theme (Theme): The application theme.
            providers (Sequence[CloudProvider]): The cloud providers having a marketplace crawler.
            loop (StorageLoop): The storage thread of the GUI.
            logger (Optional[Logger]): The view logger.
            store (Optional[ChartStateStore]): The store of the chart states, remembered for the session by default.
            statistics_source (str): The market statistics source compared with the providers.
            taxonomy (Optional[TaxonomyCache]): The taxonomy shared with the other views, a new one by default.
        """
        super().__init__()
        self.theme = theme
        self.providers = list(providers)
        self.loop = loop
        self.logger = logger if logger else getLogger(__name__)
        self.stamps: Dict[CloudProvider, DatasetStamp] = {}
        self.deleted = 0
        self.facets = SoftwareFacets()
        self.taxonomy = taxonomy if taxonomy else TaxonomyCache(loop, self.logger)
        self.category_picker = CategoryPicker(self.taxonomy, self.logger)
        self.table_model = SoftwareTableModel(theme, loop, taxonomy=self.taxonomy)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(self.SEARCH_DELAY_MS)
        self.software_card = StatCard("Software")
        self.developer_card = StatCard("Developer tools")
        self.end_user_card = StatCard("End-user software")
        self.both_card = StatCard("Both audiences")
        self.marketplaces_card = StatCard("Marketplaces crawled")
        self.chart = DomainBarChart(theme)
        self.store = store if store else ChartStateStore(logger=self.logger)
        self.trends = ChartPanel(theme, ChartScope.MARKETPLACE, "marketplace/trends", self.store, None, self.logger)
        self.controller = StoredChartController(self.trends, loop, statistics_source, self.logger)
        self.sections = SectionsToolbar(self.logger)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search software by name or publisher\u2026")
        self.search_box.setClearButtonEnabled(True)
        self.country_box, self.provider_box = CompactCombo(logger=self.logger), CompactCombo(logger=self.logger)
        self.category_box = CompactCombo(logger=self.logger)
        self.delivery_box = CompactCombo(logger=self.logger)
        self.bloc_box = CompactCombo(logger=self.logger)
        self.bloc_box.setToolTip("Show only the software of the providers of a geopolitical bloc")
        self.provider_picker = ProviderPicker(theme, self.providers, self.logger)
        self.table = QTableView()
        self.details = SoftwareDetails(theme, taxonomy=self.taxonomy)
        self.count_label = QLabel()
        self.count_label.setObjectName("muted")
        self.deleted_box = QCheckBox("Show deleted")
        self.deleted_box.setToolTip("Show the software which disappeared from its marketplace, struck through")
        self.description_box = QCheckBox("In descriptions")
        self.description_box.setToolTip("Search the descriptions too (slower)")
        self.advanced = AdvancedSoftwareFilters(theme)
        self.advanced.setVisible(False)
        self.more_button = QPushButton("More filters")
        self.more_button.setCheckable(True)
        self.more_button.setToolTip("Filter on every other field: texts, publisher, categories and dates")
        self.new_button, self.edit_button, self.delete_button = QToolButton(), QToolButton(), QToolButton()
        self.select_button = QToolButton()
        self.selection_button = QPushButton()
        self.selection_button.setToolTip("Clear the bulk selection: the table shows the filters again")
        self.selection_button.setVisible(False)
        self.selection_query: Optional[ItemQuery] = None
        self._build_layout()
        self._build_table()
        self.item_actions = ItemActions[MarketplaceSoftware, SoftwareRow](
            theme,
            self.table,
            self.table_model,
            loop,
            MarketplaceSoftware,
            lambda storage: storage.marketplaces,
            self.providers,
            self,
            self.logger,
        )
        for button, action in (
            (self.new_button, self.item_actions.new_action),
            (self.edit_button, self.item_actions.edit_action),
            (self.delete_button, self.item_actions.delete_action),
        ):
            button.setDefaultAction(action)
        self.selection_actions = SelectionActions[MarketplaceSoftware, SoftwareRow](
            theme,
            self.table_model,
            loop,
            lambda storage: storage.marketplaces,
            self.providers,
            self,
            lambda storage: storage.marketplaces.facets(ItemQuery(), pickers=True),
            self.logger,
            self.taxonomy,
        )
        self.select_button.setDefaultAction(self.selection_actions.select_action)
        self.selection_actions.filter_requested.connect(self.apply_selection)
        self.selection_button.clicked.connect(self.clear_selection)
        self._fill_combos(SoftwareFacets())
        self.search_timer.timeout.connect(self._apply_filters)
        self.search_box.textChanged.connect(self.search_timer.start)
        self.deleted_box.toggled.connect(self._apply_filters)
        self.description_box.toggled.connect(self._apply_filters)
        self.table_model.loaded.connect(self._on_loaded)
        self.advanced.changed.connect(self._on_advanced_changed)
        self.more_button.toggled.connect(self.advanced.setVisible)
        for scope_box in (self.bloc_box, self.country_box):
            scope_box.currentIndexChanged.connect(self._on_provider_scope_changed)
        self.bloc_box.currentIndexChanged.connect(self._apply_filters)
        self.provider_picker.changed.connect(self._apply_filters)
        self.category_picker.changed.connect(self._apply_filters)
        self.taxonomy.changed.connect(self._show_domains)
        for box in self._filter_boxes():
            box.currentIndexChanged.connect(self._apply_filters)
        self.details.copied.connect(self.copied.emit)
        self.details.filter_requested.connect(self._on_detail_filter)
        self.logger.debug("Marketplace view built for %d marketplaces.", len(self.providers))

    ############################
    # Internal Helpers Methods #
    ############################

    def _filter_boxes(self) -> List[QComboBox]:
        """Get the filter combo boxes.

        Returns:
            List[QComboBox]: The country, provider, audience and delivery filters.
        """
        return [self.country_box, self.provider_box, self.category_box, self.delivery_box]

    def _build_layout(self) -> None:
        """Lay the filters out above the figures and charts (scrollable), the table below them, the details right."""
        chart_area = FittedScrollArea(self.chart, self.DOMAIN_CHART_HEIGHT, self.logger)
        self.domains_section = self.sections.add(
            ChartSection("marketplace/domains", "Software per domain", chart_area, self.store, logger=self.logger)
        )
        title, subtitle = self.trends.heading()
        self.trends_section = self.sections.add(
            ChartSection("marketplace/trends", title, self.trends, self.store, self.trends.tools, self.logger)
        )
        self.trends_section.set_heading(title, subtitle)
        self.trends.heading_changed.connect(self.trends_section.set_heading)
        cards = FlowLayout(gap=16, logger=self.logger)
        for card in (
            self.software_card,
            self.developer_card,
            self.end_user_card,
            self.both_card,
            self.marketplaces_card,
        ):
            cards.addWidget(card)
        cards.addWidget(self.sections)
        figures = QWidget()
        figures.setLayout(cards)
        self.stats_stack = SectionStack(scrollable=True, logger=self.logger)
        self.stats_stack.add_widget(figures)
        self.stats_stack.add_section(self.domains_section, 1)
        self.stats_stack.add_section(self.trends_section, 2)
        filters = FlowLayout(gap=8, logger=self.logger)
        self.search_box.setMinimumWidth(220)
        filters.addWidget(self.search_box)
        filters.addWidget(self.description_box)
        for box in self._filter_boxes():
            if box is self.country_box:
                filters.addWidget(self.bloc_box)
            filters.addWidget(box)
            if box is self.provider_box:
                filters.addWidget(self.provider_picker)
            if box is self.category_box:
                filters.addWidget(self.category_picker)
        filters.addWidget(self.deleted_box)
        filters.addWidget(self.more_button)
        table = QWidget()
        table_layout = QVBoxLayout(table)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(6)
        self.table.setMinimumHeight(160)
        table_layout.addWidget(self.table, 1)
        table_layout.addWidget(self.count_label)
        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        for button in (self.select_button, self.selection_button, self.new_button, self.edit_button):
            actions_layout.addWidget(button)
        actions_layout.addWidget(self.delete_button)
        self.table_section = ChartSection(
            "marketplace/table", "Software", table, self.store, actions, logger=self.logger, detachable=False
        )
        self.table_stack = SectionStack(scrollable=False, logger=self.logger)
        self.table_stack.add_section(self.table_section, 1)
        charts_and_table = FoldingSplitter(Qt.Orientation.Vertical, self.logger)
        charts_and_table.add_pane(self.stats_stack, 1)
        charts_and_table.add_pane(self.table_stack, 1)
        charts_and_table.setSizes([420, 420])
        software = QWidget()
        software_layout = QVBoxLayout(software)
        software_layout.setContentsMargins(0, 0, 0, 0)
        software_layout.setSpacing(10)
        software_layout.addLayout(filters)
        software_layout.addWidget(self.advanced)
        software_layout.addWidget(charts_and_table, 1)
        software_layout.addStretch(0)
        self.details_pane = SidePane("marketplace/details", "Software details", self.details, self.store, self.logger)
        splitter = FoldingSplitter(Qt.Orientation.Horizontal, self.logger)
        splitter.add_pane(software, 1)
        splitter.add_pane(self.details_pane)
        splitter.setSizes([1100, 340])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(splitter)
        self.logger.debug("Marketplace view laid out.")

    def _build_table(self) -> None:
        """Set the software table up: sortable, several rows selected at once, details of the current one."""
        header = QHeaderView(Qt.Orientation.Horizontal)
        header.setSectionsClickable(True)
        header.setStretchLastSection(True)
        vertical_header = QHeaderView(Qt.Orientation.Vertical)
        vertical_header.setVisible(False)
        self.table.setHorizontalHeader(header)
        self.table.setVerticalHeader(vertical_header)
        self.table.setModel(self.table_model)
        selection = QItemSelectionModel(self.table_model)
        self.table.setSelectionModel(selection)
        self.table_model.query = self.table_model.query.model_copy(update={"sort": ItemSort.NAME})
        header.setSortIndicator(SoftwareTableModel.NAME, Qt.SortOrder.AscendingOrder)
        header.setSortIndicatorShown(True)
        header.sortIndicatorChanged.connect(self.table_model.sort)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        for column, width in (
            (SoftwareTableModel.PROVIDER, 170),
            (SoftwareTableModel.COUNTRY, 130),
            (SoftwareTableModel.NAME, 280),
            (SoftwareTableModel.PUBLISHER, 170),
            (SoftwareTableModel.CATEGORIES, 220),
            (SoftwareTableModel.LABELS, 200),
            (SoftwareTableModel.AUDIENCE, 170),
            (SoftwareTableModel.DELIVERY, 130),
            (SoftwareTableModel.ADDED, 100),
        ):
            self.table.setColumnWidth(column, width)
        selection.currentRowChanged.connect(self._on_current_changed)
        self.logger.debug("Software table set up.")

    def _fill_combo(self, box: QComboBox, all_label: str, items: List[ComboItem]) -> None:
        """Fill a filter combo box, keeping its selection.

        Args:
            box (QComboBox): The combo box.
            all_label (str): The label of the "every value" entry.
            items (List[ComboItem]): The label, value, icon and software count of each entry.
        """
        self.logger.debug("Filling the filter %r with %d entries.", all_label, len(items))
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

    def _fill_combos(self, facets: SoftwareFacets) -> None:
        """Show the number of listed software of each filter value in the filter combo boxes.

        Args:
            facets (SoftwareFacets): The counts of every listed software, whatever the filters.
        """
        self.advanced.set_pickers(facets)
        self.logger.debug("Filter counts read: %d listed software.", facets.total)
        countries: Dict[Country, int] = {}
        for provider, count in facets.by_provider.items():
            countries[provider.country] = countries.get(provider.country, 0) + count
        shown_countries = list(dict.fromkeys(provider.country for provider in self.providers))
        blocs: Dict[GeoBloc, int] = {}
        for provider, count in facets.by_provider.items():
            blocs[provider.bloc] = blocs.get(provider.bloc, 0) + count
        shown_blocs = [bloc for bloc in GeoBloc if any(provider.bloc is bloc for provider in self.providers)]
        self._fill_combo(
            self.bloc_box,
            "All blocs",
            [
                (self.theme.bloc_label(b), b.value, self.theme.dot_icon(self.theme.bloc_color(b)), blocs.get(b, 0))
                for b in shown_blocs
            ],
        )
        self.provider_picker.set_counts(dict(facets.by_provider))
        self._fill_combo(
            self.country_box,
            "All countries",
            [
                (self.theme.country_label(c), c.value, self.theme.flag_icon(c, 14), countries.get(c, 0))
                for c in shown_countries
            ],
        )
        self._fill_combo(
            self.provider_box,
            "All marketplaces",
            [
                (self.theme.provider_label(p), p.value, self.theme.provider_icon(p), facets.by_provider.get(p, 0))
                for p in self.providers
            ],
        )
        self._fill_combo(
            self.category_box,
            "All categories",
            [(self.theme.category_label(c), c.value, None, facets.by_category.get(c, 0)) for c in SoftwareCategory],
        )
        self._fill_combo(
            self.delivery_box,
            "All deliveries",
            [
                (self.theme.delivery_label(d), d.value, None, facets.by_delivery[d])
                for d in DeliveryMethod
                if facets.by_delivery.get(d)
            ],
        )

    def _scoped_providers(self) -> List[CloudProvider]:
        """Get the providers of the chosen bloc and country.

        Returns:
            List[CloudProvider]: The marketplace providers in the bloc and the country filters, all of them when none
                is chosen.
        """
        bloc, country = self.bloc_box.currentData() or "", self.country_box.currentData() or ""
        return [
            provider
            for provider in self.providers
            if (not bloc or provider.bloc is GeoBloc(bloc)) and (not country or provider.country is Country(country))
        ]

    def _on_provider_scope_changed(self) -> None:
        """Offer the providers of the chosen bloc and country in the providers filter (before the filters apply)."""
        scoped = self._scoped_providers()
        self.logger.debug("Provider filter scoped to %d providers.", len(scoped))
        self.provider_picker.show_only(scoped)

    def _query(self) -> ItemQuery:
        """Build the query of the filters, keeping the order of the table.

        Returns:
            ItemQuery: The software matching the search and the filters, or the bulk selection when one is shown.
        """
        if self.selection_query is not None:
            self.logger.debug("Showing the bulk selection instead of the filters.")
            order = {"sort": self.table_model.query.sort, "descending": self.table_model.query.descending}
            return self.selection_query.model_copy(update=order)
        self.logger.debug("Reading the software filters.")
        country, provider, category, delivery = [box.currentData() or "" for box in self._filter_boxes()]
        picked = self.provider_picker.picked()
        restricted = bool(self.bloc_box.currentData() or country or provider or picked is not None)
        providers = [
            chosen
            for chosen in self._scoped_providers()
            if (not provider or chosen is CloudProvider(provider)) and (picked is None or chosen in picked)
        ]
        main = self.table_model.query.model_copy(
            update={
                "providers": providers if restricted else [],
                "restrict_providers": restricted,
                "search": self.search_box.text().strip() or None,
                "search_description": self.description_box.isChecked(),
                "include_deleted": self.deleted_box.isChecked(),
                "categories": [SoftwareCategory(category)] if category else [],
                "deliveries": [DeliveryMethod(delivery)] if delivery else [],
                "service_categories": self.category_picker.picked(),
            }
        )
        return self.advanced.apply(main)

    def _set_filters_enabled(self, enabled: bool) -> None:
        """Enable the filters, or disable them while a bulk selection is shown.

        Args:
            enabled (bool): Whether the filters can be used.
        """
        self.logger.debug("Software filters %s.", "enabled" if enabled else "disabled")
        for widget in (self.search_box, self.description_box, self.deleted_box, self.more_button, self.advanced):
            widget.setEnabled(enabled)
        self.bloc_box.setEnabled(enabled)
        self.provider_picker.setEnabled(enabled)
        self.category_picker.setEnabled(enabled)
        for box in self._filter_boxes():
            box.setEnabled(enabled)

    def _on_advanced_changed(self) -> None:
        """Show how many other filters are set, and search once they stop changing."""
        count = self.advanced.active_count()
        self.logger.debug("Advanced filters changed: %d set.", count)
        self.more_button.setText(f"More filters ({count})" if count else "More filters")
        self.search_timer.start()

    def _show_domains(self) -> None:
        """Show the software per domain, named by the taxonomy (again once it is read)."""
        facets = self.facets
        bars: List[Bar] = [
            (
                self.taxonomy.name(domain),
                count,
                self.theme.CATEGORY_COLORS[
                    SoftwareCategory.DEVELOPER_TOOL
                    if facets.by_domain_and_category.get(domain, {}).get(SoftwareCategory.DEVELOPER_TOOL, 0) * 2
                    >= count
                    else SoftwareCategory.END_USER_SOFTWARE
                ],
            )
            for domain, count in facets.by_domain.items()
        ]
        self.chart.set_bars(bars)

    def _show_stats(self, facets: SoftwareFacets) -> None:
        """Show the figures and the domain chart of the software matching the filters.

        Args:
            facets (SoftwareFacets): The counts of the matching software.
        """
        self.facets = facets
        self.logger.debug("Figures read: %d software match the filters.", facets.total)
        listed = sum(stamp.size for stamp in self.stamps.values())
        self.software_card.set_value(f"{facets.total:,}", f"of {listed:,} listed")
        developers = facets.by_category.get(SoftwareCategory.DEVELOPER_TOOL, 0)
        end_users = facets.by_category.get(SoftwareCategory.END_USER_SOFTWARE, 0)
        self.developer_card.set_value(f"{developers:,}", "to build and run apps")
        self.end_user_card.set_value(f"{end_users:,}", "for the business users")
        both = max(developers + end_users - facets.total, 0)
        share = f"{100 * both / facets.total:.0f}% of the software" if facets.total else "of the software"
        self.both_card.set_value(f"{both:,}", share)
        self._show_domains()

    def _show_count(self) -> None:
        """Show how many software match the filters."""
        self.logger.debug("%d software match the filters.", self.table_model.total)
        listed = sum(stamp.size for stamp in self.stamps.values())
        state = "included" if self.deleted_box.isChecked() else "hidden"
        suffix = f" ({self.deleted:,} deleted {state})" if self.deleted else ""
        self.count_label.setText(f"{self.table_model.total:,} of {listed:,} software shown{suffix}")

    def _on_loaded(self, total: int) -> None:
        """Show the number of matching software once counted.

        Args:
            total (int): The number of matching software.
        """
        self.logger.debug("Software table counted: %d rows.", total)
        self._show_count()

    def _on_counted(self, every: int) -> None:
        """Keep the number of deleted software: every stored one minus the listed ones.

        Args:
            every (int): The number of stored software, the deleted ones included.
        """
        self.logger.debug("%d software stored, deleted ones included.", every)
        self.deleted = max(every - sum(stamp.size for stamp in self.stamps.values()), 0)
        self._show_count()

    def _on_error(self, error: StorageError) -> None:
        """Report a figure which cannot be read.

        Args:
            error (StorageError): The error.
        """
        self.logger.warning("The marketplace figures cannot be read: %s", error)
        self.count_label.setText(f"The storage is unavailable: {error}")

    def _request_figures(self) -> None:
        """Read the figures of the filters, and of every listed software for the filter combo boxes."""
        self.logger.debug("Reading the marketplace figures.")
        query = self._query()
        self.loop.submit(lambda storage: storage.marketplaces.facets(query), self._show_stats, self._on_error)
        self.loop.submit(
            lambda storage: storage.marketplaces.facets(ItemQuery(), pickers=True), self._fill_combos, self._on_error
        )
        self.loop.submit(
            lambda storage: storage.marketplaces.category_counts(ItemQuery()),
            self.category_picker.set_counts,
            self._on_error,
        )
        self.loop.submit(
            lambda storage: storage.marketplaces.label_counts(ItemQuery()), self.advanced.set_labels, self._on_error
        )
        self.taxonomy.load()
        every = ItemQuery(include_deleted=True)
        self.loop.submit(lambda storage: storage.marketplaces.count(every), self._on_counted, self._on_error)

    def _apply_filters(self) -> None:
        """Show only the software matching the search and the filters, and their figures."""
        self.logger.debug("Applying the software filters.")
        self.search_timer.stop()
        self.table_model.set_query(self._query())
        self.controller.set_query(self._query())
        self.loop.submit(lambda storage: storage.marketplaces.facets(self._query()), self._show_stats, self._on_error)

    def _on_detail_filter(self, name: str, value: str) -> None:
        """Filter the software on a chip clicked in the details panel.

        Args:
            name (str): The `ItemFilter` value of the chip: audience, category, delivery, publisher or marketplace
                category.
            value (str): The value filtered on.
        """
        if self.selection_query is not None:
            self.logger.warning("The software is not filtered on %r while a bulk selection is shown.", value)
            return
        item_filter = ItemFilter(name)
        if item_filter is ItemFilter.SERVICE_CATEGORIES:
            self.category_picker.set_picked([value])
            return
        if item_filter is ItemFilter.SOURCE_LABELS:
            self.advanced.source_label_box.pick(int(value), self.taxonomy)
            self.more_button.setChecked(True)
            return
        match item_filter:
            case ItemFilter.CATEGORIES:
                box: Optional[QComboBox] = self.category_box
            case ItemFilter.DELIVERIES:
                box = self.delivery_box
            case _:
                box = None
        if box is None:
            if self.advanced.pick(item_filter, value):
                self.more_button.setChecked(True)
            else:
                self.logger.error("The software cannot be filtered on %s %r.", name, value)
            return
        index = box.findData(value)
        if index < 0:
            self.logger.warning("The filter %s has no entry %r.", name, value)
            return
        self.logger.info("Software filtered on %s %r.", name, value)
        box.setCurrentIndex(index)

    def _on_current_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        """Show the details of the selected software.

        Args:
            current (QModelIndex): The selected index.
            previous (QModelIndex): The previously selected index.
        """
        self.logger.debug("Software row %d selected.", current.row())
        self.details.show_row(self.table_model.row_at(current))

    ############################
    # Publicly Exposed Methods #
    ############################

    def refresh(self, stamps: Dict[CloudProvider, DatasetStamp]) -> None:
        """Show the stored marketplaces again (they were written), keeping the filters and the selection.

        Args:
            stamps (Dict[CloudProvider, DatasetStamp]): The state of the stored marketplaces, by cloud provider.
        """
        first = not self.table_model.cache.pages and self.table_model.total == 0
        self.stamps = dict(stamps)
        crawled = f"{len(stamps)} / {len(self.providers)}"
        self.marketplaces_card.set_value(crawled, "marketplaces stored")
        self.table_model.set_crawl_dates({provider: stamp.crawled_at for provider, stamp in stamps.items()})
        if first:
            self.table_model.set_query(self._query())
        else:
            self.table_model.refresh()
        self._request_figures()
        self.controller.set_query(self._query())
        self.logger.debug("Marketplace view refreshed: %d marketplaces stored.", len(stamps))

    def apply_selection(self, query: ItemQuery) -> None:
        """Show a bulk selection in the table instead of the filters, until it is cleared.

        Args:
            query (ItemQuery): The chosen software.
        """
        self.logger.info("Showing a bulk selection of software.")
        self.selection_query = query
        self.selection_button.setText("Selection  \u2715")
        self.selection_button.setVisible(True)
        self._set_filters_enabled(False)
        self._apply_filters()

    def clear_selection(self) -> None:
        """Show the software of the filters again."""
        self.logger.info("Bulk selection of software cleared.")
        self.selection_query = None
        self.selection_button.setVisible(False)
        self._set_filters_enabled(True)
        self._apply_filters()

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

    def set_available(self, available: FrozenSet[DatasetKind]) -> None:
        """Tell which datasets are stored, for the options and the empty states of the analysis.

        Args:
            available (FrozenSet[DatasetKind]): The stored datasets.
        """
        self.trends.set_available(available)
