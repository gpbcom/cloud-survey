from __future__ import annotations

# Standard Library Imports.
from collections import Counter
from datetime import date
from functools import partial
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# Third Party Imports.
from PyQt6 import sip
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

# First Party Imports.
from analytics.markets.correlation.share_stock_correlation import ShareStockCorrelation
from analytics.markets.shares.share_table import ShareTable
from analytics.markets.stocks.fx_converter import FxConverter
from analytics.markets.stocks.stock_table import StockTable
from crawler.exception import MarketsCatalogError
from crawler.markets.catalog_loader import MarketsCatalogLoader
from gui.analysis.markets.lag_chart import LagChart
from gui.analysis.markets.share_controls import ShareControls
from gui.analysis.markets.stock_controls import StockControls
from gui.analysis.markets.time_series_chart import TimeSeriesChart
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from gui.widgets.compact_combo import CompactCombo
from models.history.chronology import Chronology
from models.history.timeline.notable_event import NotableEvent
from models.history.timeline.partial_date import PartialDate
from models.markets.charts.chart_dot import ChartDot
from models.markets.charts.chart_line import ChartLine
from models.markets.enums import AreaKind, Device, Granularity, PriceScale, ShareSource, StockView
from models.markets.markets_catalog import MarketsCatalog
from models.markets.series.share_series import ShareSeries
from models.markets.series.share_stock_result import ShareStockResult
from models.markets.series.stock_series import StockSeries
from storage.exception import StorageError
from storage.storage import Storage

type ShareQuery = Tuple[str, str, Device, Optional[ShareSource], int]
type StockQuery = Tuple[StockView, Tuple[str, ...], str, PriceScale, bool]


class MarketsPanel(QObject):
    """The market shares, the stock values and their correlation, the cards under the leaders in the Analysis tab.

    Attributes:
        SOURCES (ClassVar[Dict[ShareSource, str]]): The attribution printed under the share chart, by source.
        RHO (ClassVar[str]): The Greek letter rho, naming the Spearman correlation.
        RANGE (ClassVar[str]): The en dash of a range of values.
        REGION_COLORS (ClassVar[Tuple[str, ...]]): The colours of the region indexes, in order.
        theme (Theme): The application theme.
        loop (StorageLoop): The storage thread of the GUI.
        catalog (MarketsCatalog): The segments, areas, listings and valuations.
        chronology (Optional[Chronology]): The companies (names, colours, countries) and the events.
        share_controls (ShareControls): The pickers of the share chart.
        share_chart (TimeSeriesChart): A line per company: its share of the segment in the area.
        share_note (QLabel): The definition and the source of the shares shown.
        share_body (QWidget): The card body of the shares: pickers, chart, note.
        stock_controls (StockControls): The pickers of the stock chart.
        stock_chart (TimeSeriesChart): A line per listing, per region index, or the valuation points.
        stock_note (QLabel): The source and the limits of the values shown.
        stock_body (QWidget): The card body of the stocks.
        company_box (CompactCombo): The company correlated, among those of the share chart.
        correlate_button (QPushButton): Runs the correlation.
        correlation_summary (QLabel): The Granger tests, the months used, or why nothing was computed.
        lag_chart (LagChart): The correlation by lag.
        correlation_body (QWidget): The card body of the correlation.
        generations (Dict[str, int]): The number of the last request of each card (a late answer is dropped).
        logger (Logger): The panel logger.

    Notes:
        The data are read through the storage thread (`StorageLoop`), never on the GUI thread, and drawn from the
        stored crawls of `CRAWLER_SOURCE=markets`: the guide is `docs/analysis/market-shares-and-stocks.md`.
    """

    SOURCES: ClassVar[Dict[ShareSource, str]] = {
        ShareSource.STATCOUNTER: "Source: StatCounter Global Stats (gs.statcounter.com), CC BY-SA 3.0.",
        ShareSource.SYNERGY: "Source: Synergy Research Group press releases (quarterly), via the statistics crawl.",
        ShareSource.MANUAL: "Source: the dossier of the leaders chronology.",
        ShareSource.TRENDFORCE: "Source: TrendForce press releases (quarterly revenue rankings, from their text).",
        ShareSource.IDC: "Source: IDC press releases (quarterly Top 5 tables, sell-in shipments).",
    }
    RHO: ClassVar[str] = chr(0x03C1)
    RANGE: ClassVar[str] = chr(0x2013)
    REGION_COLORS: ClassVar[Tuple[str, ...]] = (
        "#4f8cff",
        "#e3a008",
        "#a77bf3",
        "#3fb950",
        "#f85149",
        "#26a69a",
        "#ff7043",
        "#9aa4b2",
        "#ec407a",
        "#8d6e63",
    )

    def __init__(
        self,
        theme: Theme,
        loop: StorageLoop,
        catalog: Optional[MarketsCatalog] = None,
        chronology: Optional[Chronology] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Build the cards, reading nothing until `refresh`.

        Args:
            theme (Theme): The application theme.
            loop (StorageLoop): The storage thread of the GUI.
            catalog (Optional[MarketsCatalog]): The markets catalogue, `conf/history/markets.yaml` by default.
            chronology (Optional[Chronology]): The chronology, `conf/history/chronology.yaml` by default.
            logger (Optional[Logger]): The panel logger.
        """
        super().__init__()
        self.theme, self.loop = theme, loop
        self.logger = logger if logger else getLogger(__name__)
        message = ""
        if catalog is None or chronology is None:
            try:
                loader = MarketsCatalogLoader(self.logger)
                catalog = catalog or loader.load()
                chronology = chronology or loader.chronology()
            except MarketsCatalogError as e:
                self.logger.error("The market shares and stock values cannot be shown: %s", e)
                message = str(e)
        self.catalog = catalog or MarketsCatalog()
        self.chronology = chronology
        self.generations: Dict[str, int] = {"shares": 0, "stocks": 0, "correlation": 0}
        self.share_controls = ShareControls(self.catalog, self.logger)
        self.share_chart = TimeSeriesChart(theme, self.logger)
        self.share_note = self._note()
        self.share_body = self._body(self.share_controls, self.share_chart, self.share_note)
        self.stock_controls = StockControls(self.catalog, chronology, self.logger)
        self.stock_chart = TimeSeriesChart(theme, self.logger)
        self.stock_note = self._note()
        self.stock_body = self._body(self.stock_controls, self.stock_chart, self.stock_note)
        self.company_box = CompactCombo(18)
        self.company_box.setToolTip("The company whose share changes are correlated with its stock returns")
        self.correlate_button = QPushButton("Correlate")
        self.correlate_button.setToolTip(
            "Spearman correlation of the monthly share changes (segment, area and devices of the share chart) with "
            "the monthly returns of the company's primary listing in US dollars, lag by lag, and Granger tests"
        )
        self.correlation_summary = self._note()
        self.correlation_summary.setText("Pick a company drawn in the share chart, then Correlate.")
        self.lag_chart = LagChart(theme, self.logger)
        picker = QWidget()
        row = QHBoxLayout(picker)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("Company"))
        row.addWidget(self.company_box)
        row.addWidget(self.correlate_button)
        row.addStretch(1)
        self.correlation_body = self._body(picker, self.lag_chart, self.correlation_summary)
        if message:
            self.share_chart.set_message(message)
            self.stock_chart.set_message(message)
        self.share_controls.changed.connect(self._load_shares)
        self.stock_controls.changed.connect(self._load_stocks)
        self.correlate_button.clicked.connect(self.correlate)
        self.logger.debug("Markets panel built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _note(self) -> QLabel:
        """Build a muted, wrapped note label.

        Returns:
            QLabel: The label.
        """
        label = QLabel("")
        label.setObjectName("muted")
        label.setWordWrap(True)
        return label

    def _body(self, top: QWidget, chart: QWidget, note: QLabel) -> QWidget:
        """Stack a card body: its pickers, its chart, its note.

        Args:
            top (QWidget): The pickers.
            chart (QWidget): The chart.
            note (QLabel): The note.

        Returns:
            QWidget: The body.
        """
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(top)
        layout.addWidget(chart, 1)
        layout.addWidget(note)
        return body

    def _names(self) -> Dict[str, str]:
        """Name every company of the chronology.

        Returns:
            Dict[str, str]: The name of each company key.
        """
        return {company.key: company.label for company in self.chronology.companies} if self.chronology else {}

    def _color(self, company: Optional[str]) -> str:
        """Get the colour of a company's lines.

        Args:
            company (Optional[str]): The company, `None` for the others.

        Returns:
            str: Its colour, `#rrggbb` (the muted text colour for the others).
        """
        found = self.chronology.company(company) if self.chronology and company else None
        return self.theme.company_color(found).name() if found else self.theme.TEXT_MUTED

    def _day(self, text: str) -> date:
        """Read a partial date of the catalogue.

        Args:
            text (str): `YYYY`, `YYYY-MM` or `YYYY-MM-DD`.

        Returns:
            date: Its first day.
        """
        year, month, day, _ = PartialDate().parts(text)
        return date(year, month, day)

    def _share_query(self) -> ShareQuery:
        """Get what the share chart shows.

        Returns:
            ShareQuery: The segment, the area, the devices, the source and the top count.
        """
        segment, area, device, top = self.share_controls.query()
        return segment.key, area.key, device, segment.source, top

    def _on_error(self, chart: TimeSeriesChart, error: StorageError) -> None:
        """Report a storage error in a chart (GUI thread).

        Args:
            chart (TimeSeriesChart): The chart whose data failed.
            error (StorageError): The error.
        """
        if sip.isdeleted(chart):
            return
        self.logger.error("The markets data cannot be read: %s", error)
        chart.set_message(f"The markets data cannot be read: {error}")
        self.correlate_button.setEnabled(True)

    async def _read_shares(self, query: ShareQuery, storage: Storage) -> List[ShareSeries]:
        """Read the shares of the segment, area and devices, and fold them into lines (storage thread).

        Args:
            query (ShareQuery): What the chart shows.
            storage (Storage): The open storage.

        Returns:
            List[ShareSeries]: The top companies, then the others.

        Notes:
            The segment's own source is drawn in its main granularity (IDC's quarters, not its yearly totals), with
            the dossier's manual shares of the periods it does not cover (the pre-2009 points), never both for a
            company and a period.
        """
        segment, area, device, source, top = query
        values = await storage.shares.read(segment, area, device)
        own = [value for value in values if value.source is source]
        granularities = Counter(value.granularity for value in own)
        main = granularities.most_common(1)[0][0] if granularities else None
        own = [value for value in own if value.granularity is main]
        stated = {(value.company or value.label, value.period) for value in own}
        manual = [
            value
            for value in values
            if value.source is ShareSource.MANUAL
            and source is not ShareSource.MANUAL
            and (value.company or value.label, value.period) not in stated
        ]
        return ShareTable(self.logger).series([*own, *manual], self._names(), top)

    def _on_shares(self, generation: int, query: ShareQuery, series: List[ShareSeries]) -> None:
        """Draw the share lines read, unless a later request was made (GUI thread).

        Args:
            generation (int): The number of the request.
            query (ShareQuery): What it read.
            series (List[ShareSeries]): The lines.
        """
        if sip.isdeleted(self.share_chart) or generation != self.generations["shares"]:
            return
        segment_key, area_key, device, source, _ = query
        segment, area = self.catalog.segment(segment_key), self.catalog.area(area_key)
        quarterly = source is not ShareSource.STATCOUNTER
        lines = [
            ChartLine(
                key=line.company or "others",
                label=line.label + (" (est.)" if line.estimate else ""),
                color=self._color(line.company),
                dashed=line.estimate,
                dots=quarterly,
                points=line.points,
                note=", ".join(line.labels[:6]) + ("\u2026" if len(line.labels) > 6 else ""),
            )
            for line in series
        ]
        if not lines:
            self.share_chart.set_message(
                f"No {segment.label if segment else segment_key} shares stored for "
                f"{area.label if area else area_key} ({device.value}). Run CRAWLER_SOURCE=markets "
                f"(MARKETS_AREAS={area_key} to read only this area)."
            )
        else:
            self.share_chart.set_data(lines, [], "%", False, True, f"{segment_key}/{area_key}/{device.value}")
        estimate = area is not None and area.kind is AreaKind.UNION
        self.share_note.setText(
            " ".join(
                part
                for part in (
                    segment.description if segment else "",
                    "The EU-27 is estimated from its member states weighted by their internet users (World Bank)."
                    if estimate
                    else "",
                    self.SOURCES.get(source, "") if source else "",
                )
                if part
            )
        )
        companies = [line.company for line in series if line.company and self.catalog.listings_of(line.company)]
        current = self.company_box.currentData()
        self.company_box.blockSignals(True)
        self.company_box.clear()
        for key in companies:
            self.company_box.addItem(self._names().get(key, key), key)
        index = self.company_box.findData(current)
        self.company_box.setCurrentIndex(max(index, 0))
        self.company_box.blockSignals(False)
        self.logger.info(
            "Market shares shown: %s in %s (%s), %d lines.", segment_key, area_key, device.value, len(lines)
        )

    def _load_shares(self) -> None:
        """Read the shares picked (storage thread), then draw them."""
        if not self.catalog.segments:
            return
        self.generations["shares"] += 1
        query = self._share_query()
        self.share_chart.message = "Reading the market shares..."
        self.loop.submit(
            partial(self._read_shares, query),
            partial(self._on_shares, self.generations["shares"], query),
            partial(self._on_error, self.share_chart),
        )

    def _stock_query(self) -> StockQuery:
        """Get what the stock chart shows.

        Returns:
            StockQuery: The view, the companies, the currency, the scale and whether the secondary listings show.
        """
        controls = self.stock_controls
        return controls.view(), tuple(controls.companies()), controls.currency(), controls.scale(), controls.secondary()

    async def _read_stocks(self, query: StockQuery, storage: Storage) -> List[StockSeries]:
        """Read the prices and the rates, and fold them into lines (storage thread).

        Args:
            query (StockQuery): What the chart shows.
            storage (Storage): The open storage.

        Returns:
            List[StockSeries]: The lines of the listings or of the region indexes.
        """
        view, companies, currency, scale, secondary = query
        if view is StockView.VALUATIONS:
            return []
        if view is StockView.REGIONS:
            listings = [listing for listing in self.catalog.listings if listing.primary]
        else:
            listings = [
                listing
                for company in companies
                for listing in self.catalog.listings_of(company)
                if listing.primary or secondary
            ]
        prices = await storage.stocks.read([listing.symbol for listing in listings])
        table = StockTable(FxConverter(await storage.fx.read(), self.logger), self.logger)
        if view is StockView.REGIONS:
            countries = (
                {company.key: company.country or "" for company in self.chronology.companies} if self.chronology else {}
            )
            target = "USD" if currency == StockTable.LISTING_CURRENCY else currency
            return table.region_indexes(prices, listings, self.catalog.regions, countries, target)
        return table.listing_lines(prices, listings, self._names(), currency, scale)

    def _valuation_dots(self) -> List[ChartDot]:
        """Turn the sourced valuation points into dots.

        Returns:
            List[ChartDot]: A dot per valuation, in its company's colour.
        """
        names = self._names()
        dots: List[ChartDot] = []
        for point in self.catalog.valuations:
            span = f"{point.value_bn:g}" + (f"{self.RANGE}{point.high_bn:g}" if point.high_bn else "")
            dots.append(
                ChartDot(
                    day=self._day(point.date),
                    value=point.value_bn,
                    color=self._color(point.company),
                    label=f"{names.get(point.company, point.company)}: {point.label}",
                    tooltip=f"{point.date} · {point.kind.value} · ${span} bn<br>Source: {point.source} [{point.tag}]",
                )
            )
        return dots

    def _on_stocks(self, generation: int, query: StockQuery, series: List[StockSeries]) -> None:
        """Draw the stock lines read, unless a later request was made (GUI thread).

        Args:
            generation (int): The number of the request.
            query (StockQuery): What it read.
            series (List[StockSeries]): The lines.
        """
        if sip.isdeleted(self.stock_chart) or generation != self.generations["stocks"]:
            return
        view, companies, currency, scale, secondary = query
        key = f"{view.value}/{','.join(companies)}/{currency}/{scale.value}/{secondary}"
        if view is StockView.VALUATIONS:
            self.stock_chart.set_data([], self._valuation_dots(), "USD bn", True, False, key)
            self.stock_note.setText(
                "Sourced valuation points of the dossier (Tab 3): IPOs, acquisitions, private rounds (post-money) and "
                "market caps, in billions of US dollars. Tags: P primary filing, J journalistic, B blog or aggregator."
            )
            return
        lines = [
            ChartLine(
                key=line.key,
                label=line.label,
                color=self._color(line.company)
                if line.company
                else self.REGION_COLORS[index % len(self.REGION_COLORS)],
                dashed=not line.primary,
                points=line.points,
                note=line.note,
            )
            for index, line in enumerate(series)
        ]
        units = {line.currency for line in series}
        unit = (
            "" if scale is PriceScale.INDEXED or view is StockView.REGIONS else units.pop() if len(units) == 1 else ""
        )
        log_y = scale is not PriceScale.LINEAR or view is StockView.REGIONS
        if lines:
            self.stock_chart.set_data(lines, [], unit, log_y, False, key)
        else:
            self.stock_chart.set_message(
                "No stock prices stored for these companies. "
                "Run CRAWLER_SOURCE=markets CRAWLER_TARGET=google-finance,fred."
            )
        self.stock_note.setText(
            "Source: Google Finance weekly closes (split-adjusted, dividends not reinvested), converted on each day "
            "with the FRED noon rates (H.10). Dashed lines are secondary listings (ADRs, second exchanges). "
            "A subsidiary trades as its parent: AWS as Amazon, Google Cloud as Alphabet."
            + (
                " Region indexes: equal-weight, chain-linked monthly over the primary listings."
                if view is StockView.REGIONS
                else ""
            )
        )
        self.logger.info("Stock values shown: %s, %d lines.", view.value, len(lines))

    def _load_stocks(self) -> None:
        """Read the stock values picked (storage thread), then draw them."""
        self.generations["stocks"] += 1
        query = self._stock_query()
        self.stock_chart.message = "Reading the stock values..."
        self.loop.submit(
            partial(self._read_stocks, query),
            partial(self._on_stocks, self.generations["stocks"], query),
            partial(self._on_error, self.stock_chart),
        )

    async def _read_correlation(self, company: str, query: ShareQuery, storage: Storage) -> ShareStockResult:
        """Read a company's shares and prices, and correlate them (storage thread).

        Args:
            company (str): The company.
            query (ShareQuery): The segment, area and devices of the shares.
            storage (Storage): The open storage.

        Returns:
            ShareStockResult: The correlation by lag and the Granger tests, or why nothing was computed.
        """
        segment, area, device, source, _ = query
        values = await storage.shares.read(segment, area, device, source=source, companies=[company])
        listings = [listing for listing in self.catalog.listings_of(company) if listing.primary]
        listing = listings[0].symbol if listings else None
        prices = await storage.stocks.read([listing]) if listing else []
        table = StockTable(FxConverter(await storage.fx.read(), self.logger), self.logger)
        return ShareStockCorrelation(table, self.logger).analyse(
            company, segment, area, device.value, values, listing, prices
        )

    def _on_correlation(self, generation: int, result: ShareStockResult) -> None:
        """Show a correlation, unless a later one was asked (GUI thread).

        Args:
            generation (int): The number of the request.
            result (ShareStockResult): The correlation.
        """
        if sip.isdeleted(self.lag_chart) or generation != self.generations["correlation"]:
            return
        self.correlate_button.setEnabled(True)
        if result.refusal:
            self.lag_chart.set_lags([], f"Not computed: {result.refusal}")
            self.correlation_summary.setText(f"Not computed: {result.refusal}")
            return
        months = max((lag.months for lag in result.lags), default=0)
        best = max(
            (lag for lag in result.lags if lag.rho is not None), key=lambda lag: abs(lag.rho or 0.0), default=None
        )
        share_p = f"{result.share_leads_p:.3g}" if result.share_leads_p is not None else "-"
        stock_p = f"{result.stock_leads_p:.3g}" if result.stock_leads_p is not None else "-"
        strongest = (
            f"Strongest: lag {best.lag:+d}, {self.RHO} {best.rho:+.2f} (q {best.q_value:.2g})."
            if best is not None and best.rho is not None and best.q_value is not None
            else ""
        )
        unit = "months" if result.granularity is Granularity.MONTH else "quarters"
        self.lag_chart.set_lags(result.lags, unit=unit)
        self.correlation_summary.setText(
            f"{self._names().get(result.company, result.company)} ({result.listing}) in {result.segment}, "
            f"{result.area}, {result.device}: up to {months} {unit} paired. {strongest} Granger ({result.granger_lags} "
            f"{unit} of past): share changes lead returns p = {share_p}, returns lead share changes p = {stock_p}. "
            "Correlation is not causation: both may follow the same cycle."
        )
        self.logger.info("Share-stock correlation shown for %s.", result.company)

    ############################
    # Publicly Exposed Methods #
    ############################

    def refresh(self) -> None:
        """Read both charts again (a crawl was written, or the tab opened)."""
        self.logger.debug("Refreshing the markets cards.")
        self._load_shares()
        self._load_stocks()

    def correlate(self) -> None:
        """Correlate the company picked with its stock, on the shares of the share chart."""
        company = self.company_box.currentData()
        if not company or not self.catalog.segments:
            self.correlation_summary.setText("No listed company in the share chart: pick another segment or area.")
            return
        self.generations["correlation"] += 1
        self.correlate_button.setEnabled(False)
        self.correlation_summary.setText("Correlating...")
        self.loop.submit(
            partial(self._read_correlation, str(company), self._share_query()),
            partial(self._on_correlation, self.generations["correlation"]),
            partial(self._on_error, self.share_chart),
        )

    def set_events(self, events: Sequence[NotableEvent]) -> None:
        """Draw the notable events picked in the leaders card on both time charts.

        Args:
            events (Sequence[NotableEvent]): The events.
        """
        self.share_chart.set_events(events, self.chronology)
        self.stock_chart.set_events(events, self.chronology)

    def focus_reign(self, key: str) -> bool:
        """Show the segment and the company of a leader band clicked in the leaders chart.

        Args:
            key (str): The band key, `reign:<segment>:<company>:<start>`.

        Returns:
            bool: Whether a share segment measures that chronology segment.
        """
        parts = key.split(":")
        if len(parts) < 3 or parts[0] != "reign":
            return False
        chronology_segment, company = parts[1], parts[2]
        segment = next((entry for entry in self.catalog.segments if entry.chronology == chronology_segment), None)
        if self.catalog.listings_of(company):
            self.stock_controls.set_companies([company])
        if segment is None:
            self.logger.debug("No market share segment measures %s.", chronology_segment)
            return False
        self.share_controls.set_segment(segment.key)
        index = self.company_box.findData(company)
        if index >= 0:
            self.company_box.setCurrentIndex(index)
        self.logger.info("Markets cards focused on %s (%s).", company, segment.key)
        return True
