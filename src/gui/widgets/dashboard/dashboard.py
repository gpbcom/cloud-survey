from __future__ import annotations

# Standard Library Imports.
from typing import Dict, Optional

# Third Party Imports.
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

# First Party Imports.
from gui.theme import Theme
from gui.widgets.dashboard.provider_bar_chart import ProviderBarChart
from gui.widgets.dashboard.stat_card import StatCard
from models.cloud.catalogue import CloudCatalogue
from models.cloud.enums import CloudProvider, Country


class Dashboard(QWidget):
    """Overview of the loaded catalogues, of every country or of one: headline figures and products per provider.

    Attributes:
        theme (Theme): The application theme.
        products_card (StatCard): The total number of products.
        providers_card (StatCard): The number of crawled providers.
        crawl_card (StatCard): The most recent crawl.
        chart_title (QLabel): The chart title, naming the shown country.
        chart (ProviderBarChart): The products per provider.
        chart_area (QScrollArea): The scrollable area of the chart.
    """

    def __init__(self, theme: Theme) -> None:
        """Build the dashboard.

        Args:
            theme (Theme): The application theme.
        """
        super().__init__()
        self.theme = theme
        self.products_card = StatCard("Products")
        self.providers_card = StatCard("Providers crawled")
        self.crawl_card = StatCard("Latest crawl")
        self.chart = ProviderBarChart(theme)
        self.chart_area = QScrollArea()
        self.chart_area.setWidget(self.chart)
        self.chart_area.setWidgetResizable(True)
        self.chart_area.setFrameShape(QFrame.Shape.NoFrame)
        self.chart_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        chart_frame = QFrame()
        chart_frame.setObjectName("card")
        chart_layout = QVBoxLayout(chart_frame)
        self.chart_title = QLabel("PRODUCTS PER PROVIDER")
        self.chart_title.setObjectName("muted")
        chart_layout.addWidget(self.chart_title)
        chart_layout.addWidget(self.chart_area)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for card in (self.products_card, self.providers_card, self.crawl_card):
            layout.addWidget(card, 2)
        layout.addWidget(chart_frame, 5)
        self.setMaximumHeight(185)

    ############################
    # Publicly Exposed Methods #
    ############################

    def update_catalogues(
        self, catalogues: Dict[CloudProvider, CloudCatalogue], country: Optional[Country] = None
    ) -> None:
        """Show the figures of the loaded catalogues, of every country or of one.

        Args:
            catalogues (Dict[CloudProvider, CloudCatalogue]): The loaded catalogues, by cloud provider.
            country (Optional[Country]): The only country shown, `None` for all of them.
        """
        providers = [provider for provider in CloudProvider if country is None or provider.country is country]
        shown = {provider: catalogues[provider] for provider in providers if provider in catalogues}
        counts = {provider: catalogue.size for provider, catalogue in shown.items()}
        scope = "across the crawled catalogues" if country is None else f"in {self.theme.country_label(country)}"
        self.products_card.set_value(f"{sum(counts.values()):,}", scope)
        self.providers_card.set_value(f"{len(shown)} / {len(providers)}", "catalogue files in output/")
        if shown:
            latest = max(shown.values(), key=lambda catalogue: catalogue.crawled_at)
            self.crawl_card.set_value(
                latest.crawled_at.astimezone().strftime("%d %b %H:%M"), Theme.PROVIDER_LABELS[latest.provider]
            )
        else:
            self.crawl_card.set_value("\u2013", "no catalogue crawled yet")
        title = "PRODUCTS PER PROVIDER"
        self.chart_title.setText(title if country is None else f"{title} \u2014 {self.theme.country_label(country)}")
        self.chart.set_counts(counts, providers)
