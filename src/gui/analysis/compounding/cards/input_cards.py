from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget

# First Party Imports.
from gui.analysis.compounding.cards.card_format import CardFormat
from gui.analysis.compounding.cards.report_table import ReportTable
from gui.analysis.markets.charts.time_series_chart import TimeSeriesChart
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.compounding.compounding_report import CompoundingReport
from models.compounding.config.compounding_config import CompoundingConfig
from models.compounding.enums import CompoundingControl, ValueOrigin
from models.compounding.help.compounding_help import CompoundingHelp
from models.markets.charts.chart_dot import ChartDot
from models.markets.charts.chart_line import ChartLine


class InputCards:
    """The cards of the Service compounding inputs: the catalogues, the market size, the shares and the curated scope.

    Attributes:
        theme (Theme): The application theme.
        help (CompoundingHelp): The explanations shown in the tooltips.
        config (Optional[CompoundingConfig]): The scope of the analysis, `None` when it cannot be read.
        format (CardFormat): The writer of the figures.
        launches_chart (TimeSeriesChart): The yearly catalogue size of each provider.
        market_chart (TimeSeriesChart): The yearly cloud-market size.
        shares_chart (TimeSeriesChart): The yearly cloud-market share of each provider.
        foundations_table (ReportTable): The foundation sets used.
        scope_label (QLabel): The providers and domains kept, and why a provider is left out.
        launches_body (QWidget): The card of the catalogues.
        market_body (QWidget): The card of the market size.
        shares_body (QWidget): The card of the shares.
        foundations_body (QWidget): The card of the curated scope.
        logger (Logger): The cards logger.
    """

    def __init__(
        self,
        theme: Theme,
        help_texts: CompoundingHelp,
        config: Optional[CompoundingConfig],
        logger: Optional[Logger] = None,
    ) -> None:
        """Build the cards, empty.

        Args:
            theme (Theme): The application theme.
            help_texts (CompoundingHelp): The explanations shown in the tooltips.
            config (Optional[CompoundingConfig]): The scope of the analysis.
            logger (Optional[Logger]): The cards logger.
        """
        self.theme = theme
        self.help = help_texts
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        self.format = CardFormat(theme, self.logger)
        self.launches_chart = TimeSeriesChart(theme, self.logger)
        self.market_chart = TimeSeriesChart(theme, self.logger)
        self.shares_chart = TimeSeriesChart(theme, self.logger)
        self.foundations_table = ReportTable(self.logger)
        self.scope_label = QLabel()
        self.scope_label.setObjectName("muted")
        self.scope_label.setWordWrap(True)
        self.launches_body = self._body(self.launches_chart, True)
        self.market_body = self._body(self.market_chart, True)
        self.shares_body = self._body(self.shares_chart, True)
        self.foundations_body = QWidget()
        layout = QVBoxLayout(self.foundations_body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scope_label)
        layout.addWidget(self.foundations_table)
        self.clear("Run the analysis to see its inputs.")
        self._show_scope()

    ############################
    # Internal Helpers Methods #
    ############################

    def _body(self, chart: TimeSeriesChart, derivative: bool) -> QWidget:
        """Stack a line chart under its rate-of-change switch.

        Args:
            chart (TimeSeriesChart): The chart.
            derivative (bool): Whether the chart offers the rate of change.

        Returns:
            QWidget: The card body.
        """
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        if derivative:
            switch = QCheckBox(self.help.title("controls", CompoundingControl.DERIVATIVE.value))
            switch.setToolTip(self.help.text("controls", CompoundingControl.DERIVATIVE.value))
            switch.toggled.connect(chart.set_derivative)
            layout.addWidget(switch)
        layout.addWidget(chart, 1)
        return body

    def _fill_foundations(self, foundations: Dict[str, List[str]], curated: bool) -> None:
        """Write the foundation sets used in their table.

        Args:
            foundations (Dict[str, List[str]]): The foundations of each dependent category.
            curated (bool): Whether they are the curated sets (their sources are then shown).
        """
        sources: Dict[Tuple[str, str], str] = {}
        if curated and self.config is not None:
            sources = {
                (entry.category, link.foundation): link.source
                for entry in self.config.foundations
                for link in entry.links
            }
        rows = [
            [category, foundation, sources.get((category, foundation), "data-driven")]
            for category, found in sorted(foundations.items())
            for foundation in found
        ]
        self.foundations_table.fill(
            ["Category", "Foundation", "Source"],
            [
                "The dependent category.",
                "A category it is built on.",
                "The document showing the link, or data-driven when the order of entries found it.",
            ],
            rows,
        )

    def _show_scope(self) -> None:
        """Write the providers and the domains kept, and the curated foundation sets."""
        if self.config is None:
            self.scope_label.setText("The compounding configuration cannot be read.")
            return
        kept = ", ".join(self.format.provider(scope.provider) for scope in self.config.providers)
        excluded = " ".join(
            f"{self.format.provider(entry.provider)} is left out: {entry.reason}" for entry in self.config.excluded
        )
        self.scope_label.setText(
            f"Providers analysed: {kept}. {excluded} Domains kept: {', '.join(self.config.domains)}."
        )
        self._fill_foundations(self.config.foundation_sets(), True)

    def _provider_lines(self, values: Dict[CloudProvider, List[Tuple[int, float]]], unit: str) -> List[ChartLine]:
        """Draw one line per provider.

        Args:
            values (Dict[CloudProvider, List[Tuple[int, float]]]): The yearly values of each provider.
            unit (str): What the values are.

        Returns:
            List[ChartLine]: The lines.
        """
        return [
            ChartLine(
                key=provider.value,
                label=self.format.provider(provider),
                color=self.format.color(provider),
                points=[(self.format.day(year), value) for year, value in points],
                note=unit,
            )
            for provider, points in values.items()
            if points
        ]

    ############################
    # Publicly Exposed Methods #
    ############################

    def show_foundations(self, foundations: Dict[str, List[str]], curated: bool) -> None:
        """Show the foundation sets used.

        Args:
            foundations (Dict[str, List[str]]): The foundations of each dependent category.
            curated (bool): Whether they are the curated sets (their sources are then shown).
        """
        self._fill_foundations(foundations, curated)

    def clear(self, message: str) -> None:
        """Empty the charts.

        Args:
            message (str): What they say.
        """
        for chart in (self.launches_chart, self.market_chart, self.shares_chart):
            chart.set_message(message)

    def show(self, report: CompoundingReport) -> None:
        """Draw the inputs of an analysis.

        Args:
            report (CompoundingReport): The analysis.
        """
        sizes: Dict[CloudProvider, List[Tuple[int, float]]] = {}
        shares: Dict[CloudProvider, List[Tuple[int, float]]] = {}
        manual: List[ChartDot] = []
        for row in report.provider_years:
            sizes.setdefault(row.provider, []).append((row.year, float(row.size)))
            if row.share is not None and row.share > 0:
                if row.share_origin is ValueOrigin.MANUAL:
                    manual.append(
                        ChartDot(
                            day=self.format.day(row.year),
                            value=row.share,
                            color=self.format.color(row.provider),
                            label=self.format.provider(row.provider),
                            tooltip="Hand-typed share of the dossier.",
                        )
                    )
                else:
                    shares.setdefault(row.provider, []).append((row.year, row.share))
        self.launches_chart.set_data(
            self._provider_lines(sizes, "products"), [], "", False, True, "compounding/launches"
        )
        if not sizes:
            self.launches_chart.set_message("No dated product: crawl the catalogues.")
        known = [year for year in report.market_years if year.size_bn]
        line = ChartLine(
            key="market",
            label="Cloud infrastructure services",
            color=self.theme.ACCENT,
            points=[(self.format.day(year.year), float(year.size_bn or 0)) for year in known],
            note="billion USD",
        )
        flagged = [
            ChartDot(
                day=self.format.day(year.year),
                value=float(year.size_bn or 0),
                color=self.theme.WARNING,
                label="Interpolated" if year.origin is ValueOrigin.INTERPOLATED else "Older perimeter",
                tooltip="Quarters interpolated between their neighbours."
                if year.origin is ValueOrigin.INTERPOLATED
                else "The source measured another perimeter that year.",
            )
            for year in known
            if year.origin is not ValueOrigin.CRAWLED or year.perimeter_break
        ]
        self.market_chart.set_data([line] if known else [], flagged, " bn", False, True, "compounding/market")
        if not known:
            self.market_chart.set_message("No market size: crawl the cloud market history.")
        self.shares_chart.set_data(self._provider_lines(shares, "%"), manual, "%", False, True, "compounding/shares")
        if not shares and not manual:
            self.shares_chart.set_message("No market share: crawl the cloud market history.")
        self._fill_foundations(report.foundations, report.query.source.value == "curated")
        self.logger.debug("Compounding inputs drawn: %d providers, %d market years.", len(sizes), len(known))
