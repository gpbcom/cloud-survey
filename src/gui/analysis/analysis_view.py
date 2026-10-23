from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, FrozenSet, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

# First Party Imports.
from gui.analysis.drivers.drivers_panel import DriversPanel
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
        drivers (DriversPanel): The "Rise drivers" analysis (its pickers and table).
        driver_sections (List[ChartSection]): The cards of the rise drivers: the pickers and table, then the
            correlations, the predominance and the scatters.
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
    ) -> None:
        """Build the view, reading nothing until `refresh`.

        Args:
            theme (Theme): The application theme.
            loop (StorageLoop): The storage thread of the GUI.
            store (Optional[ChartStateStore]): The store of the chart states, remembered for the session by default.
            statistics_source (str): The market statistics source compared with the providers.
            logger (Optional[Logger]): The view logger.
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
        self.history = HistoryPanel(theme, logger=self.logger)
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
        self.markets = MarketsPanel(theme, loop, chronology=self.history.chronology, logger=self.logger)
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
        ):
            section = self.sections.add(
                ChartSection(key, title, body, self.store, tools, logger=self.logger, detachable=detachable)
            )
            section.set_heading(title, subtitle)
            self.driver_sections.append(section)
        heading = QLabel("Competitive & geopolitical analysis")
        heading.setObjectName("title")
        caption = QLabel(
            "The market statistics, catalogues and "
            "marketplaces compared per provider and per bloc "
            "(United States, European Union, China, Russia), "
            "and the software type and audience mix of each provider "
            "(developer tools, end-user software, or both), the leaders of digital infrastructure since 1964 with "
            "their chronology, and the drivers of the rise of the providers."
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
        for index, section in enumerate(self.driver_sections):
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
        self.markets.set_events([event for event in chronology.events if event.key in wanted] if chronology else [])

    def _on_leader(self, key: str) -> None:
        """Open the market cards on the segment and company of a leader band clicked.

        Args:
            key (str): The key of the band or marker clicked (`reign:...` or `event:...`).
        """
        if key.startswith("reign:") and self.markets.focus_reign(key):
            for section in self.market_sections[:2]:
                section.set_expanded(True)

    ############################
    # Publicly Exposed Methods #
    ############################

    def refresh(self) -> None:
        """Read every chart again (a dataset was written)."""
        self.logger.debug("Refreshing the %d analysis charts.", len(self.controllers))
        for controller in self.controllers:
            controller.refresh()
        self.markets.refresh()
        self.drivers.refresh()

    def set_available(self, available: FrozenSet[DatasetKind]) -> None:
        """Tell which datasets are stored, for the options and the empty states of the charts.

        Args:
            available (FrozenSet[DatasetKind]): The stored datasets.
        """
        for panel in self.panels:
            panel.set_available(available)
