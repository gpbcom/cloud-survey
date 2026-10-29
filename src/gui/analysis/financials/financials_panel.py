from __future__ import annotations

# Standard Library Imports.
from datetime import date
from functools import partial
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Set, Tuple

# Third Party Imports.
from PyQt6 import sip
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from crawler.companies.catalog_loader import CompaniesCatalogLoader
from crawler.exception import CompaniesCatalogError

# First Party Imports.
from curated.bundle.bundle_catalogs import BundleCatalogs
from curated.exception import CuratedError
from gui.analysis.financials.controls.financial_controls import CompanyChoice, FinancialControls
from gui.analysis.financials.tables.latest_values_model import LatestRow
from gui.analysis.financials.tables.latest_values_table import LatestValuesTable
from gui.analysis.markets.charts.time_series_chart import TimeSeriesChart
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.enums import (
    CompanyIndicator,
    FinancialGranularity,
    FinancialMetric,
    FinancialSource,
    IndicatorFamily,
    IndicatorUnit,
)
from models.companies.help.financials_help import FinancialsHelp
from models.companies.values.indicator_value import IndicatorValue
from models.history.chronology import Chronology
from models.markets.charts.chart_line import ChartLine
from models.markets.markets_catalog import MarketsCatalog
from storage.exception import StorageError
from storage.storage import Storage

type FinancialsQuery = Tuple[Tuple[str, ...], CompanyIndicator, FinancialGranularity, bool]
type Documents = Dict[Tuple[str, str, date], Tuple[FinancialSource, Optional[str], Optional[str]]]
type FinancialsRead = Tuple[List[IndicatorValue], List[IndicatorValue], Documents]
type LineKey = Tuple[str, str, bool]


class CompanyFinancialsPanel(QObject):
    """The company financials cards of the Analysis tab: an indicator over time, and the latest values with sources.

    Attributes:
        GAPS (ClassVar[Dict[FinancialGranularity, int]]): The most days between two points of a line, by period: a
            missing year or quarter breaks the line (and its rate of change).
        DATED (ClassVar[Tuple[CompanyIndicator, ...]]): The indicators stated at a date (drawn as dots, whatever the
            period picked).
        NON_NEGATIVE (ClassVar[Tuple[CompanyIndicator, ...]]): The indicators whose axis starts at zero.
        UNITS (ClassVar[Dict[IndicatorUnit, str]]): The unit printed for each kind of indicator (the currency for an
            amount).
        ESTIMATES (ClassVar[Tuple[str, ...]]): The markers of an estimate or a run-rate in the inputs of a point.
        theme (Theme): The application theme.
        loop (StorageLoop): The storage thread of the GUI.
        helps (FinancialsHelp): The families, titles and explanations of the indicators.
        chronology (Optional[Chronology]): The companies (names, colours, countries).
        controls (FinancialControls): The pickers.
        chart (TimeSeriesChart): A line per company and currency.
        note (QLabel): What the indicator is, how it is computed, its caveat.
        table (LatestValuesTable): The latest value of each indicator of the family, with its source.
        chart_body (QWidget): The card body of the chart: pickers, chart, note.
        table_body (QWidget): The card body of the latest values.
        generation (int): The number of the last request (a late answer is dropped).
        logger (Logger): The panel logger.

    Notes:
        - The data are read through the storage thread (`StorageLoop`), never on the GUI thread, from the stored
          indicators of `CRAWLER_SOURCE=companies` (guide: `docs/analysis/company-financials-and-rd.md`).
        - A company reporting in several currencies over time gets a line per currency: amounts of two currencies are
          never joined. Estimates and run-rates (researched figures a third party estimated, annualized revenues)
          are drawn apart, dashed, never joined to the filed figures.
    """

    GAPS: ClassVar[Dict[FinancialGranularity, int]] = {
        FinancialGranularity.YEAR: 400,
        FinancialGranularity.QUARTER: 100,
        FinancialGranularity.TTM: 100,
    }
    DATED: ClassVar[Tuple[CompanyIndicator, ...]] = (
        CompanyIndicator.EMPLOYEES,
        CompanyIndicator.FUNDING_TOTAL,
        CompanyIndicator.VALUATION,
        CompanyIndicator.REVENUE_RUN_RATE,
    )
    NON_NEGATIVE: ClassVar[Tuple[CompanyIndicator, ...]] = (
        CompanyIndicator.REVENUE,
        CompanyIndicator.TOTAL_ASSETS,
        CompanyIndicator.MARKET_CAP,
        CompanyIndicator.ENTERPRISE_VALUE,
        CompanyIndicator.EMPLOYEES,
        CompanyIndicator.CASH,
        CompanyIndicator.TOTAL_DEBT,
        CompanyIndicator.RD_EXPENSE,
        CompanyIndicator.RD_INTENSITY,
        CompanyIndicator.FUNDING_RAISED,
        CompanyIndicator.FUNDING_TOTAL,
        CompanyIndicator.VALUATION,
        CompanyIndicator.REVENUE_RUN_RATE,
        CompanyIndicator.PIOTROSKI_F,
    )
    UNITS: ClassVar[Dict[IndicatorUnit, str]] = {
        IndicatorUnit.PERCENT: "%",
        IndicatorUnit.RATIO: "x",
        IndicatorUnit.COUNT: "",
        IndicatorUnit.SCORE: "",
    }
    ESTIMATES: ClassVar[Tuple[str, ...]] = ("reported:estimate", "reported:run-rate")

    def __init__(
        self,
        theme: Theme,
        loop: StorageLoop,
        chronology: Optional[Chronology] = None,
        markets: Optional[MarketsCatalog] = None,
        companies: Optional[CompaniesCatalog] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Build the cards, reading nothing until `refresh`.

        Args:
            theme (Theme): The application theme.
            loop (StorageLoop): The storage thread of the GUI.
            chronology (Optional[Chronology]): The chronology, `data/curated/chronology.json` by default.
            markets (Optional[MarketsCatalog]): The markets catalogue (the region of each company),
                `data/curated/markets.json` by default.
            companies (Optional[CompaniesCatalog]): The companies offered, `data/curated/companies.json` by default.
            logger (Optional[Logger]): The panel logger.
        """
        super().__init__()
        self.theme, self.loop = theme, loop
        self.logger = logger if logger else getLogger(__name__)
        self.generation = 0
        message = ""
        self.helps = FinancialsHelp()
        choices: List[CompanyChoice] = []
        try:
            self.helps = CompaniesCatalogLoader(self.logger).help()
            bundled = BundleCatalogs(logger=self.logger)
            chronology = chronology or bundled.chronology()
            catalog = markets or bundled.markets()
            for entry in (companies or bundled.companies()).companies:
                company = chronology.company(entry.key) if chronology else None
                region = catalog.region_of(company.country if company else None)
                choices.append(
                    (entry.key, company.label if company else entry.key, region.label if region else "Other")
                )
        except (CompaniesCatalogError, CuratedError) as e:
            self.logger.error("The company financials cannot be shown: %s", e)
            message = str(e)
        self.chronology = chronology
        self.controls = FinancialControls(self.helps, choices, self.logger)
        self.chart = TimeSeriesChart(theme, self.logger)
        self.note = QLabel("")
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        self.chart_body = QWidget()
        layout = QVBoxLayout(self.chart_body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.controls)
        layout.addWidget(self.chart, 1)
        layout.addWidget(self.note)
        self.table = LatestValuesTable(self.logger)
        self.table_body = QWidget()
        table_layout = QVBoxLayout(self.table_body)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.addWidget(self.table)
        if message:
            self.chart.set_message(message)
        self.controls.changed.connect(self._load)
        self.controls.derivative_box.toggled.connect(self.chart.set_derivative)
        self.logger.debug("Company financials panel built with %d companies.", len(choices))

    ############################
    # Internal Helpers Methods #
    ############################

    def _name(self, key: str) -> str:
        """Name a company.

        Args:
            key (str): The company key.

        Returns:
            str: Its name in the chronology, its key otherwise.
        """
        company = self.chronology.company(key) if self.chronology else None
        return company.label if company else key

    def _color(self, key: str) -> str:
        """Get the colour of a company's lines.

        Args:
            key (str): The company key.

        Returns:
            str: Its colour, `#rrggbb` (the muted text colour when unknown).
        """
        company = self.chronology.company(key) if self.chronology else None
        return self.theme.company_color(company).name() if company else self.theme.TEXT_MUTED

    def _title(self, indicator: CompanyIndicator) -> str:
        """Name an indicator.

        Args:
            indicator (CompanyIndicator): The indicator.

        Returns:
            str: Its title, its key when it has no help.
        """
        found = self.helps.indicator(indicator)
        return found.title if found else indicator.value

    def _family(self, indicator: CompanyIndicator) -> Optional[IndicatorFamily]:
        """Get the family of an indicator.

        Args:
            indicator (CompanyIndicator): The indicator.

        Returns:
            Optional[IndicatorFamily]: Its family, `None` when it has no help.
        """
        found = self.helps.indicator(indicator)
        return found.family if found else None

    def _query(self) -> FinancialsQuery:
        """Get what the card shows.

        Returns:
            FinancialsQuery: The companies, the indicator, the period and whether the amounts are in US dollars.
        """
        controls = self.controls
        return tuple(controls.companies()), controls.indicator(), controls.period(), controls.in_usd()

    def _is_estimate(self, point: IndicatorValue) -> bool:
        """Tell whether a point rests on an estimate or a run-rate.

        Args:
            point (IndicatorValue): The point.

        Returns:
            bool: Whether its inputs name one.
        """
        return any(marker in point.inputs for marker in self.ESTIMATES)

    def _basis(self, point: IndicatorValue) -> str:
        """Say what a point rests on.

        Args:
            point (IndicatorValue): The point.

        Returns:
            str: `estimate`, `researched` (annual reports, press) or `filed` (SEC filings, Google Finance).
        """
        if self._is_estimate(point):
            return "estimate"
        return "researched" if "reported:" in point.inputs else "filed"

    def _format(self, value: float, unit: IndicatorUnit) -> str:
        """Print a value.

        Args:
            value (float): The value.
            unit (IndicatorUnit): Its unit.

        Returns:
            str: The value, amounts in millions or billions.
        """
        if unit is IndicatorUnit.CURRENCY:
            size = abs(value)
            if size >= 1e9:
                return f"{value / 1e9:,.2f} bn"
            return f"{value / 1e6:,.1f} m" if size >= 1e6 else f"{value:,.0f}"
        if unit is IndicatorUnit.COUNT:
            return f"{value:,.0f}"
        return f"{value:,.1f} %" if unit is IndicatorUnit.PERCENT else f"{value:,.2f}"

    async def _read(self, query: FinancialsQuery, storage: Storage) -> FinancialsRead:
        """Read the series of the indicator, the latest values of its family and the documents (storage thread).

        Args:
            query (FinancialsQuery): What the card shows.
            storage (Storage): The open storage.

        Returns:
            FinancialsRead: The points of the series, the latest points of the family, the documents of the lines.
        """
        companies, indicator, granularity, _ = query
        granularities = [granularity, FinancialGranularity.INSTANT]
        if indicator is CompanyIndicator.FUNDING_RAISED:
            granularities = [FinancialGranularity.YEAR]
        series = await storage.indicators.list(companies, indicator, granularities)
        family = self._family(indicator)
        members = [item.indicator for item in self.helps.family_of(family)] if family else [indicator]
        latest = await storage.indicators.latest(companies, members)
        documents = await storage.financials.documents(companies)
        return series, latest, documents

    def _lines(self, points: Sequence[IndicatorValue], in_usd: bool) -> List[ChartLine]:
        """Build the lines of the chart: one per company and currency, the estimates apart.

        Args:
            points (Sequence[IndicatorValue]): The points of the series.
            in_usd (bool): Whether the amounts are drawn in US dollars.

        Returns:
            List[ChartLine]: The lines (dotted for the dated indicators and the estimates).
        """
        grouped: Dict[LineKey, List[Tuple[date, float]]] = {}
        for point in points:
            value = point.value_usd if in_usd and point.unit is IndicatorUnit.CURRENCY else point.value
            if value is None:
                continue
            currency = "USD" if in_usd else (point.currency or "")
            grouped.setdefault((point.company, currency, self._is_estimate(point)), []).append(
                (point.period_end, value)
            )
        currencies: Dict[str, Set[str]] = {}
        for company, currency, _ in grouped:
            currencies.setdefault(company, set()).add(currency)
        lines: List[ChartLine] = []
        for (company, currency, estimate), values in sorted(grouped.items()):
            label = self._name(company)
            if len(currencies[company]) > 1 and currency:
                label = f"{label} ({currency})"
            if estimate:
                label = f"{label}, estimates"
            dated = any(point.indicator in self.DATED for point in points)
            lines.append(
                ChartLine(
                    key=f"{company}:{currency}:{'estimate' if estimate else 'filed'}",
                    label=label,
                    color=self._color(company),
                    dashed=estimate,
                    dots=estimate or dated,
                    points=sorted(values),
                    note="Estimates or annualized run-rates, never joined to the filed figures" if estimate else None,
                )
            )
        return lines

    def _unit(self, points: Sequence[IndicatorValue], in_usd: bool) -> str:
        """Get the unit printed on the chart.

        Args:
            points (Sequence[IndicatorValue]): The points of the series.
            in_usd (bool): Whether the amounts are drawn in US dollars.

        Returns:
            str: The unit, the currency when every amount shares one, empty otherwise.
        """
        units = {point.unit for point in points}
        if units != {IndicatorUnit.CURRENCY}:
            return self.UNITS.get(next(iter(units)), "") if len(units) == 1 else ""
        currencies = {point.currency for point in points}
        return "USD" if in_usd else (str(next(iter(currencies))) if len(currencies) == 1 else "")

    def _rows(self, latest: Sequence[IndicatorValue], documents: Documents) -> List[LatestRow]:
        """Build the rows of the latest values.

        Args:
            latest (Sequence[IndicatorValue]): The latest point of each series of the family.
            documents (Documents): The documents of the stored lines.

        Returns:
            List[LatestRow]: A row per company, indicator and period, by company then indicator.
        """
        rows: List[LatestRow] = []
        metrics = {metric.value for metric in FinancialMetric}
        for point in sorted(latest, key=lambda item: (self._name(item.company), item.indicator.value)):
            document = (
                documents.get((point.company, point.indicator.value, point.period_end))
                if point.indicator.value in metrics
                else None
            )
            usd = self._format(point.value_usd, point.unit) if point.value_usd is not None else ""
            rows.append(
                (
                    self._name(point.company),
                    self._title(point.indicator),
                    f"{point.granularity.value} {point.period_end.isoformat()}",
                    self._format(point.value, point.unit),
                    point.currency or "",
                    usd,
                    self._basis(point),
                    point.inputs,
                    (document[1] or "") if document else "",
                )
            )
        return rows

    def _on_read(self, generation: int, query: FinancialsQuery, read: FinancialsRead) -> None:
        """Draw what was read, unless a later request was made (GUI thread).

        Args:
            generation (int): The number of the request.
            query (FinancialsQuery): What was asked.
            read (FinancialsRead): The series, the latest values and the documents.
        """
        if sip.isdeleted(self.chart) or generation != self.generation:
            self.logger.debug("Late company financials answer %d dropped.", generation)
            return
        companies, indicator, granularity, in_usd = query
        series, latest, documents = read
        help_item = self.helps.indicator(indicator)
        caveat = f" {help_item.caveat}" if help_item and help_item.caveat else ""
        self.note.setText(f"{help_item.formula}. {help_item.summary}{caveat}" if help_item else "")
        self.table.model_.set_rows(self._rows(latest, documents))
        if not series:
            self.chart.set_message(
                f"No {self._title(indicator).lower()} stored for the companies picked "
                "(crawl the companies sources, Companies menu)."
            )
            return
        self.chart.set_gap(self.GAPS.get(granularity))
        self.chart.set_data(
            self._lines(series, in_usd),
            [],
            self._unit(series, in_usd),
            False,
            indicator in self.NON_NEGATIVE,
            f"{indicator.value}:{granularity.value}:{in_usd}",
        )
        self.logger.info("%s of %d companies drawn (%d points).", indicator.value, len(companies), len(series))

    def _on_error(self, error: StorageError) -> None:
        """Report a storage error in the chart (GUI thread).

        Args:
            error (StorageError): The error.
        """
        if sip.isdeleted(self.chart):
            return
        self.logger.error("The company financials cannot be read: %s", error)
        self.chart.set_message(f"The company financials cannot be read: {error}")

    def _load(self) -> None:
        """Read what the pickers ask for (storage thread), then draw it."""
        self.generation += 1
        query = self._query()
        if not query[0]:
            self.chart.set_message("Pick at least one company.")
            return
        self.chart.message = "Reading the company financials..."
        self.loop.submit(
            partial(self._read, query),
            partial(self._on_read, self.generation, query),
            self._on_error,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def refresh(self) -> None:
        """Read the card again (a crawl was written, or the tab opened)."""
        self.logger.debug("Refreshing the company financials card.")
        self._load()

    def focus_company(self, key: str) -> None:
        """Draw a company alone, as a click on its leader band does.

        Args:
            key (str): The company key.
        """
        self.controls.set_companies([key])
        self.logger.info("Company financials focused on %s.", key)
