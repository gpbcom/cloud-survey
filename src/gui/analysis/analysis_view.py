from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, FrozenSet, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

# First Party Imports.
from gui.analysis.compounding.compounding_panel import CompoundingPanel
from gui.analysis.drivers.drivers_panel import DriversPanel
from gui.analysis.financials.financials_panel import CompanyFinancialsPanel
from gui.analysis.history.history_panel import HistoryPanel
from gui.analysis.markets.markets_panel import MarketsPanel
from gui.charts.panels.chart_panel import ChartPanel
from gui.charts.panels.stored_chart_controller import StoredChartController
from gui.charts.sections.chart_state_store import ChartStateStore
from gui.charts.sections.section.chart_section import ChartSection
from gui.charts.sections.section.sections_toolbar import SectionsToolbar
from gui.layout.panes.section_stack import SectionStack
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.compounding.enums import CompoundingCard
from models.curated.records.catalogue_set import CatalogueSet
from models.storage.enums import DatasetKind
from models.trends.enums import ChartPreset, ChartScope


class AnalysisView(QWidget):
    """Cross-dataset analysis: competitive positioning, rank races and geopolitical mixes of the cloud providers.

    Attributes:
        CHARTS (ClassVar[Tuple[Tuple[str, ChartScope, ChartPreset], ...]]): The key, scope and first ready-made chart
            of each section (the marketplace charts compare the software of the providers).
        theme (Theme): The application theme.
        store (ChartStateStore): The store of the chart states.
        panels (List[ChartPanel]): The configurable charts.
        controllers (List[StoredChartController]): Read the data of each chart.
        sections (SectionsToolbar): Expands or collapses every chart of the view.
        chart_sections (List[ChartSection]): The collapsible cards of the charts.
        history (HistoryPanel): The leaders of digital infrastructure since 1964 (the chart, its notable events and
            the chronology).
        history_sections (List[ChartSection]): The cards of the leaders: the chart, then the chronology.
        markets (MarketsPanel): The market shares and stock values of the leaders, worldwide and by area, and their
            correlation.
        market_sections (List[ChartSection]): The cards of the markets: the shares, the stocks, their correlation.
        financials (CompanyFinancialsPanel): The financial statements and health indicators of the companies.
        financial_sections (List[ChartSection]): The cards of the company financials: the chart, then the latest
            values with their sources.
        drivers (DriversPanel): The "Rise drivers" analysis (its pickers and table).
        driver_sections (List[ChartSection]): The cards of the rise drivers: the pickers and table, then the
            correlations, the predominance, the scatters and the stored provider metrics.
        compounding (CompoundingPanel): The "Service compounding" analysis (its pickers, coverage and crawl buttons).
        compounding_sections (List[ChartSection]): The cards of the service compounding: the controls, the inputs,
            every model, the summary and the foundations catalogue.
        logger (Logger): The view logger.

    Notes:
        - The charts compare the datasets with each other: the market statistics, the catalogues and the
          marketplaces, per provider or per geopolitical bloc.
        - Every chart can be switched to any other analysis metric, kind or ready-made chart.
        - The leaders of digital infrastructure (1964 to today) show who led each segment, with the notable events
          drawn as dashed markers, the policy-shock look of mega-trends (`docs/analysis/leaders-chronology.md`).
        - The market shares (StatCounter, Synergy) and the stock values (Google Finance) of the leaders follow, by
          area and currency, with their correlation (`docs/analysis/market-shares-and-stocks.md`). A click on a
          leader band opens them on its segment and company, and the events picked mark all three charts.
        - The rise drivers rank the criteria by their share of the variance of a target they explain
          (`docs/analysis/rise-drivers.md`).
        - The service compounding tests whether mastering some services helps a provider build the next ones, on AWS
          and on every dated public-cloud provider (`docs/analysis/service-capability-compounding.md`, results in
          `docs/analysis/service-capability-compounding-results.md`).
    """

    CHARTS: ClassVar[Tuple[Tuple[str, ChartScope, ChartPreset], ...]] = (
        ("analysis/positioning", ChartScope.ANALYSIS, ChartPreset.SHARE_VS_LISTINGS),
        ("analysis/rank", ChartScope.ANALYSIS, ChartPreset.RANK_RACE),
        ("analysis/blocs", ChartScope.ANALYSIS, ChartPreset.BLOC_CATALOGUE),
        ("analysis/publishers", ChartScope.ANALYSIS, ChartPreset.CATALOGUE_VS_PUBLISHERS),
        ("analysis/domain-trends", ChartScope.MARKETPLACE, ChartPreset.DOMAIN_TRENDS_BY_PROVIDER),
        ("analysis/audience", ChartScope.MARKETPLACE, ChartPreset.AUDIENCE_MIX_BY_PROVIDER),
    )

    def __init__(
        self,
        theme: Theme,
        loop: StorageLoop,
        store: Optional[ChartStateStore] = None,
        statistics_source: str = "synergy",
        logger: Optional[Logger] = None,
        catalogues: Optional[CatalogueSet] = None,
    ) -> None:
        """Build the view, reading nothing until `refresh`.

        Args:
            theme (Theme): The application theme.
            loop (StorageLoop): The storage thread of the GUI.
            store (Optional[ChartStateStore]): The store of the chart states, remembered for the session by default.
            statistics_source (str): The market statistics source compared with the providers.
            logger (Optional[Logger]): The view logger.
            catalogues (Optional[CatalogueSet]): The curated catalogues of the cards, those of the bundle by default.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.store = store if store else ChartStateStore()
        self.sections = SectionsToolbar(self.logger)
        self.panels: List[ChartPanel] = []
        self.controllers: List[StoredChartController] = []
        self.chart_sections: List[ChartSection] = []
        for key, scope, preset in self.CHARTS:
            panel = ChartPanel(theme, scope, key, self.store, preset)
            title, subtitle = panel.heading()
            section = self.sections.add(ChartSection(key, title, panel, self.store, panel.tools))
            section.set_heading(title, subtitle)
            panel.heading_changed.connect(section.set_heading)
            self.panels.append(panel)
            self.controllers.append(StoredChartController(panel, loop, statistics_source))
            self.chart_sections.append(section)
        self.history = HistoryPanel(theme, catalogues.chronology if catalogues else None, logger=self.logger)
        self.history_sections: List[ChartSection] = []
        for card, heading_text, subtitle_text, card_body, card_tool, card_detachable in (
            (
                "analysis/leaders",
                "Leaders of digital infrastructure, 1964\u20132026",
                "Who led each segment of computing, a band per leader. Dashed red lines are notable events "
                "(regulation, deals, bankruptcies, listings, launches), the policy-shock look of mega-trends: hover "
                "them, pick them in the menu, click to find them in the chronology.",
                self.history.chart,
                self.history.selector,
                True,
            ),
            (
                "analysis/leaders/table",
                "Chronology",
                "Every change of leader and every notable event, by date, with its evidence and its source.",
                self.history.table,
                None,
                False,
            ),
        ):
            section = self.sections.add(
                ChartSection(
                    card, heading_text, card_body, self.store, card_tool, logger=self.logger, detachable=card_detachable
                )
            )
            section.set_heading(heading_text, subtitle_text)
            self.history_sections.append(section)
        self.markets = MarketsPanel(
            theme,
            loop,
            catalog=catalogues.markets if catalogues else None,
            chronology=self.history.chronology,
            logger=self.logger,
        )
        self.market_sections: List[ChartSection] = []
        for market_card, market_title, market_subtitle, market_body in (
            (
                "analysis/markets/shares",
                "Market shares",
                "The share of each company over time in a segment, worldwide, by continent, in the EU-27 (estimated) "
                "or in a country, by device. Usage shares (StatCounter) are page views, not users or revenue.",
                self.markets.share_body,
            ),
            (
                "analysis/markets/stocks",
                "Stock values",
                "The value of the listings of the leaders over time, in their currency or converted, indexed or "
                "not, every listing or an index per region of headquarters, and the valuation points of the "
                "companies without a price history.",
                self.markets.stock_body,
            ),
            (
                "analysis/markets/correlation",
                "Share vs stock",
                "Does a company's stock follow its market share, or the other way round? Rank correlation of the "
                "monthly changes lag by lag, with block-bootstrap intervals, and Granger tests both ways.",
                self.markets.correlation_body,
            ),
        ):
            market_section = self.sections.add(
                ChartSection(market_card, market_title, market_body, self.store, logger=self.logger)
            )
            market_section.set_heading(market_title, market_subtitle)
            self.market_sections.append(market_section)
        self.financials = CompanyFinancialsPanel(
            theme,
            loop,
            chronology=self.history.chronology,
            markets=catalogues.markets if catalogues else None,
            companies=catalogues.companies if catalogues else None,
            logger=self.logger,
        )
        self.financial_sections: List[ChartSection] = []
        for financial_card, financial_title, financial_subtitle, financial_body, detachable in (
            (
                "analysis/financials/chart",
                "Company financials",
                "The profit, the R&D expenditure and the health of each company over time (margins, returns, "
                "liquidity, debt, growth, Altman and Piotroski scores), from its filings, Google Finance and its "
                "annual reports since 1980, in its own currency or in US dollars.",
                self.financials.chart_body,
                True,
            ),
            (
                "analysis/financials/latest",
                "Latest company figures",
                "The latest value of every indicator of the family picked, how it was computed and the document it "
                "was read from (double-click a row to open it).",
                self.financials.table_body,
                False,
            ),
        ):
            financial_section = self.sections.add(
                ChartSection(
                    financial_card,
                    financial_title,
                    financial_body,
                    self.store,
                    logger=self.logger,
                    detachable=detachable,
                )
            )
            financial_section.set_heading(financial_title, financial_subtitle)
            self.financial_sections.append(financial_section)
        self.history.selector.changed.connect(self._on_events)
        self.history.chart.picked.connect(self._on_leader)
        self._on_events(self.history.selector.selected())
        self.drivers = DriversPanel(theme, loop, logger=self.logger)
        self.driver_sections: List[ChartSection] = []
        for key, title, subtitle, body, tools, detachable in (
            (
                "analysis/drivers/table",
                "Rise drivers",
                "Which criteria are predominant in the rise of the providers: correlations, regression and the "
                "split of the explained variance.",
                self.drivers,
                None,
                False,
            ),
            (
                "analysis/drivers-correlations",
                "Rise drivers: correlations",
                "Spearman correlation of each criterion with the target, its 95% interval, the partial "
                "correlation (diamond) and the significance (* q < 5%, ** q < 1%).",
                self.drivers.correlation_chart,
                None,
                True,
            ),
            (
                "analysis/drivers-importance",
                "Rise drivers: predominance",
                "Share of the explained variance (R²) each criterion carries (Shapley split), with its 95% interval.",
                self.drivers.importance_chart,
                None,
                True,
            ),
            (
                "analysis/drivers-scatter",
                "Rise drivers: target against each criterion",
                "One chart per criterion, the most predominant first, sharing the target axis: a dot per "
                "observation, coloured by provider, with the least-squares line.",
                self.drivers.scatters,
                self.drivers.scale_button,
                True,
            ),
            (
                "analysis/drivers-metrics",
                "Rise drivers: provider metrics",
                "Every measure stored for the analysis, one per provider, quarter, metric and source: its value with "
                "the unit of the metric, where it comes from and when it was read. Double-click a row to open its "
                "source.",
                self.drivers.metrics_table,
                None,
                True,
            ),
        ):
            section = self.sections.add(
                ChartSection(key, title, body, self.store, tools, logger=self.logger, detachable=detachable)
            )
            section.set_heading(title, subtitle)
            self.driver_sections.append(section)
        self.compounding = CompoundingPanel(theme, loop, chronology=self.history.chronology, logger=self.logger)
        self.compounding_sections: List[ChartSection] = []
        for card, compounding_body, widened in self.compounding.cards():
            card_title = "Service compounding" + (
                "" if card is CompoundingCard.CONTROLS else f": {self.compounding.help.title('cards', card.value)}"
            )
            card_section = self.sections.add(
                ChartSection(
                    f"analysis/compounding-{card.value}",
                    card_title,
                    compounding_body,
                    self.store,
                    logger=self.logger,
                    detachable=widened,
                )
            )
            card_section.set_heading(card_title, self.compounding.help.text("cards", card.value))
            self.compounding_sections.append(card_section)
        heading = QLabel("Competitive & geopolitical analysis")
        heading.setObjectName("title")
        caption = QLabel(
            "The market statistics, catalogues and "
            "marketplaces compared per provider and per bloc "
            "(United States, European Union, China, Russia), "
            "and the software type and audience mix of each provider "
            "(developer tools, end-user software, or both), the leaders of digital infrastructure since 1964 with "
            "their chronology, the drivers of the rise of the providers, and whether mastering some cloud services "
            "helps a provider build the next ones."
        )
        caption.setObjectName("muted")
        caption.setWordWrap(True)
        header = QHBoxLayout()
        header.addWidget(heading)
        header.addStretch(1)
        header.addWidget(self.sections)
        heading_row = QWidget()
        heading_row.setLayout(header)
        column = SectionStack(scrollable=True, logger=self.logger)
        column.add_widget(heading_row)
        column.add_widget(caption)
        for section in self.chart_sections:
            column.add_section(section, 1)
        for index, section in enumerate(self.history_sections):
            column.add_section(section, 0 if index else 1)
        for index, section in enumerate(self.market_sections):
            column.add_section(section, 1 if index < 2 else 0)
        for index, section in enumerate(self.financial_sections):
            column.add_section(section, 0 if index else 1)
        for index, section in enumerate(self.driver_sections):
            column.add_section(section, 1 if index else 0)
        for index, section in enumerate(self.compounding_sections):
            column.add_section(section, 1 if index else 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(column, 1)
        layout.addStretch(0)
        self.logger.debug("Analysis view built with %d charts.", len(self.panels))

    ############################
    # Internal Helpers Methods #
    ############################

    def _on_events(self, keys: List[str]) -> None:
        """Mark the events picked in the leaders card on the market charts too.

        Args:
            keys (List[str]): Their keys.
        """
        chronology = self.history.chronology
        wanted = set(keys)
        if not chronology:
            self.logger.warning("No chronology loaded: the %d events picked are not marked on the markets.", len(keys))
        events = [event for event in chronology.events if event.key in wanted] if chronology else []
        self.logger.debug("Marking %d of the %d picked events on the market charts.", len(events), len(keys))
        self.markets.set_events(events)

    def _on_leader(self, key: str) -> None:
        """Open the market cards on the segment and company of a leader band clicked.

        Args:
            key (str): The key of the band or marker clicked (`reign:...` or `event:...`).
        """
        self.logger.debug("Leader band %s clicked.", key)
        if key.startswith("reign:") and self.markets.focus_reign(key):
            for section in self.market_sections[:2]:
                section.set_expanded(True)
            self.logger.info("Market cards opened on the leader %s.", key)
        else:
            self.logger.debug("The click on %s opens no market card.", key)

    ############################
    # Publicly Exposed Methods #
    ############################

    def refresh(self) -> None:
        """Read every chart again (a dataset was written)."""
        self.logger.debug("Refreshing the %d analysis charts.", len(self.controllers))
        for controller in self.controllers:
            controller.refresh()
        self.markets.refresh()
        self.financials.refresh()
        self.drivers.refresh()
        self.compounding.refresh()
        self.logger.info(
            "Analysis view refreshed: %d charts, the markets, the company financials, the rise drivers and the "
            "service compounding.",
            len(self.controllers),
        )

    def set_available(self, available: FrozenSet[DatasetKind]) -> None:
        """Tell which datasets are stored, for the options and the empty states of the charts.

        Args:
            available (FrozenSet[DatasetKind]): The stored datasets.
        """
        self.logger.debug("Available datasets for the analysis charts: %s.", sorted(kind.value for kind in available))
        if not available:
            self.logger.warning("No dataset stored: the analysis charts show their empty state.")
        for panel in self.panels:
            panel.set_available(available)
