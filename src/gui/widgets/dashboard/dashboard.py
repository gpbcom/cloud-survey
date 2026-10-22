from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, FrozenSet, Optional

# Third Party Imports.
from PyQt6.QtWidgets import QWidget

# First Party Imports.
from gui.charts.panels.chart_panel import ChartPanel
from gui.charts.panels.stored_chart_controller import StoredChartController
from gui.charts.sections.chart_state_store import ChartStateStore
from gui.charts.sections.section.chart_section import ChartSection
from gui.charts.sections.section.sections_toolbar import SectionsToolbar
from gui.layout.fitted_scroll_area import FittedScrollArea
from gui.layout.flow_layout import FlowLayout
from gui.layout.panes.section_stack import SectionStack
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from gui.widgets.dashboard.provider_bar_chart import ProviderBarChart
from gui.widgets.dashboard.stat_card import StatCard
from models.cloud.enums import CloudProvider, Country
from models.storage.dataset_stamp import DatasetStamp
from models.storage.enums import DatasetKind
from models.storage.pages.item_query import ItemQuery
from models.trends.enums import ChartScope


class Dashboard(SectionStack):
    """Overview of the loaded catalogues: headline figures, products per provider and the catalogue trends.

    Attributes:
        PROVIDER_TITLE (ClassVar[str]): The title of the products per provider chart.
        PROVIDER_CHART_HEIGHT (ClassVar[int]): The smallest height of the products per provider chart, which scrolls
            below it.
        theme (Theme): The application theme.
        store (ChartStateStore): The store of the chart states.
        products_card (StatCard): The total number of products.
        providers_card (StatCard): The number of crawled providers.
        crawl_card (StatCard): The most recent crawl.
        chart (ProviderBarChart): The products per provider.
        chart_area (FittedScrollArea): The scrollable area of the products per provider chart, as tall as its rows.
        trends (ChartPanel): The configurable chart of the catalogue trends.
        controller (Optional[StoredChartController]): Reads the catalogue trends, `None` without storage thread.
        sections (SectionsToolbar): Expands or collapses every chart of the dashboard.
        provider_section (ChartSection): The collapsible card of the products per provider.
        trends_section (ChartSection): The collapsible card of the catalogue trends.
        logger (Logger): The dashboard logger.

    Notes:
        - The figures cover every country or the chosen one, the trends follow the filters of the product table.
        - The charts keep their minimum height: the dashboard scrolls rather than squeezing them. The expanded charts
          share the rest of the height, the trends getting twice the share of the products per provider.
    """

    PROVIDER_TITLE: ClassVar[str] = "Products per provider"
    PROVIDER_CHART_HEIGHT: ClassVar[int] = 160

    def __init__(
        self,
        theme: Theme,
        loop: Optional[StorageLoop] = None,
        store: Optional[ChartStateStore] = None,
        statistics_source: str = "synergy",
        logger: Optional[Logger] = None,
    ) -> None:
        """Build the dashboard.

        Args:
            theme (Theme): The application theme.
            loop (Optional[StorageLoop]): The storage thread of the GUI, `None` to show no trends.
            store (Optional[ChartStateStore]): The store of the chart states, remembered for the session by default.
            statistics_source (str): The market statistics source compared with the providers.
            logger (Optional[Logger]): The dashboard logger.
        """
        super().__init__(scrollable=True, logger=logger if logger else getLogger(__name__))
        self.theme = theme
        self.store = store if store else ChartStateStore(logger=self.logger)
        self.products_card = StatCard("Products")
        self.providers_card = StatCard("Providers crawled")
        self.crawl_card = StatCard("Latest crawl")
        self.chart = ProviderBarChart(theme)
        self.chart_area = FittedScrollArea(self.chart, self.PROVIDER_CHART_HEIGHT, self.logger)
        self.trends = ChartPanel(theme, ChartScope.CATALOGUE, "catalogue/trends", self.store, None, self.logger)
        self.controller = StoredChartController(self.trends, loop, statistics_source, self.logger) if loop else None
        self.sections = SectionsToolbar(self.logger)
        self.provider_section = self.sections.add(
            ChartSection("catalogue/providers", self.PROVIDER_TITLE, self.chart_area, self.store, logger=self.logger)
        )
        title, subtitle = self.trends.heading()
        self.trends_section = self.sections.add(
            ChartSection("catalogue/trends", title, self.trends, self.store, self.trends.tools, self.logger)
        )
        self.trends_section.set_heading(title, subtitle)
        self.trends.heading_changed.connect(self.trends_section.set_heading)
        cards = FlowLayout(gap=16, logger=self.logger)
        for card in (self.products_card, self.providers_card, self.crawl_card):
            cards.addWidget(card)
        cards.addWidget(self.sections)
        figures = QWidget()
        figures.setLayout(cards)
        self.add_widget(figures)
        self.add_section(self.provider_section, 1)
        self.add_section(self.trends_section, 2)

    ############################
    # Publicly Exposed Methods #
    ############################

    def update_catalogues(
        self, catalogues: Dict[CloudProvider, DatasetStamp], country: Optional[Country] = None
    ) -> None:
        """Show the figures of the loaded catalogues, of every country or of one.

        Args:
            catalogues (Dict[CloudProvider, DatasetStamp]): The state of the stored catalogues, by cloud provider.
            country (Optional[Country]): The only country shown, `None` for all of them.
        """
        providers = [provider for provider in CloudProvider if country is None or provider.country is country]
        shown = {provider: catalogues[provider] for provider in providers if provider in catalogues}
        counts = {provider: catalogue.size for provider, catalogue in shown.items()}
        scope = "across the crawled catalogues" if country is None else f"in {self.theme.country_label(country)}"
        self.products_card.set_value(f"{sum(counts.values()):,}", scope)
        self.providers_card.set_value(f"{len(shown)} / {len(providers)}", "catalogues stored")
        if shown:
            latest = max(shown, key=lambda provider: shown[provider].crawled_at)
            self.crawl_card.set_value(
                shown[latest].crawled_at.astimezone().strftime("%d %b %H:%M"), Theme.PROVIDER_LABELS[latest]
            )
        else:
            self.crawl_card.set_value("\u2013", "no catalogue crawled yet")
        title = self.PROVIDER_TITLE
        if country is not None:
            title = f"{title} \u2014 {self.theme.country_label(country)}"
        self.provider_section.set_heading(title)
        self.chart.set_counts(counts, providers)

    def set_query(self, query: ItemQuery) -> None:
        """Apply the filters of the product table to the catalogue trends.

        Args:
            query (ItemQuery): The filters of the product table.
        """
        if self.controller is not None:
            self.controller.set_query(query)

    def refresh(self) -> None:
        """Read the catalogue trends again (the catalogues were written)."""
        if self.controller is not None:
            self.controller.refresh()

    def set_available(self, available: FrozenSet[DatasetKind]) -> None:
        """Tell which datasets are stored, for the options and the empty states of the trends.

        Args:
            available (FrozenSet[DatasetKind]): The stored datasets.
        """
        self.trends.set_available(available)
