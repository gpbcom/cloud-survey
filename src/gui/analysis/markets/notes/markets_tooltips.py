from __future__ import annotations

# Standard Library Imports.
import html
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional

# First Party Imports.
from analytics.markets.correlation.coverage_checker import CoverageChecker
from analytics.markets.correlation.pair_correlation import PairCorrelation
from gui.theme import Theme
from models.markets.catalog.market_area import MarketArea
from models.markets.catalog.share_segment import ShareSegment
from models.markets.correlation.counterpart import Counterpart
from models.markets.enums import AreaKind, CorrelationCounterpart, Granularity, MarketControl, ShareSource
from models.markets.help.markets_help import MarketsHelp
from models.markets.markets_catalog import MarketsCatalog


class MarketsTooltips:
    """Write the tooltips of the markets cards: each control, each choice of a list, and the correlation to run.

    Attributes:
        UNITS (ClassVar[Dict[Granularity, str]]): The name of the periods of a correlation.
        MONTHLY (ClassVar[ShareSource]): The only share source publishing months (the others publish quarters).
        theme (Theme): The application theme.
        catalog (MarketsCatalog): The segments, areas, labels and listings.
        help (MarketsHelp): The explanations (the `markets` block of `conf/help.yaml`).
        names (Dict[str, str]): The name of each company of the chronology.
        logger (Logger): The writer logger.

    Notes:
        The explanations come from the `markets` block of `conf/help.yaml`, the definitions of the segments and the
        labels of the companies from `data/curated/markets.json`, the figures of the correlation method from the classes
        computing it (`PairCorrelation`, `CoverageChecker`), so that a tooltip never says what the code does not do.
    """

    UNITS: ClassVar[Dict[Granularity, str]] = {Granularity.MONTH: "months", Granularity.QUARTER: "quarters"}
    MONTHLY: ClassVar[ShareSource] = ShareSource.STATCOUNTER

    def __init__(
        self,
        theme: Theme,
        catalog: MarketsCatalog,
        help_: MarketsHelp,
        names: Optional[Dict[str, str]] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the writer.

        Args:
            theme (Theme): The application theme.
            catalog (MarketsCatalog): The segments, areas, labels and listings.
            help_ (MarketsHelp): The explanations.
            names (Optional[Dict[str, str]]): The name of each company, their keys by default.
            logger (Optional[Logger]): The writer logger.
        """
        self.theme, self.catalog, self.help = theme, catalog, help_
        self.names = names or {}
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _title(self, text: str) -> str:
        """Write the first line of a tooltip.

        Args:
            text (str): The title.

        Returns:
            str: The rich text line.
        """
        return f"<p style='margin:0'><b style='color:{self.theme.ACCENT}'>{html.escape(text)}</b></p>"

    def _option(self, control: MarketControl, option: str) -> str:
        """Get the explanation of a choice, escaped.

        Args:
            control (MarketControl): The control offering it.
            option (str): The value of the choice.

        Returns:
            str: The explanation, empty when there is none.
        """
        explained = self.help.option(control, option)
        return html.escape(explained.summary) if explained is not None else ""

    def _period(self, counterpart: Counterpart) -> Granularity:
        """Get the period of a counterpart series.

        Args:
            counterpart (Counterpart): The counterpart.

        Returns:
            Granularity: Monthly for a stock, a currency or a StatCounter share, quarterly otherwise.
        """
        match counterpart.kind:
            case CorrelationCounterpart.STOCK | CorrelationCounterpart.CURRENCY:
                return Granularity.MONTH
            case CorrelationCounterpart.SHARE if counterpart.source is self.MONTHLY:
                return Granularity.MONTH
            case _:
                return Granularity.QUARTER

    def _paragraphs(self, title: str, *texts: str) -> str:
        """Write a tooltip: a title, then a paragraph per non-empty text (already escaped).

        Args:
            title (str): The title.
            *texts (str): The paragraphs.

        Returns:
            str: The rich text tooltip.
        """
        return "<qt>" + self._title(title) + "".join(f"<p>{text}</p>" for text in texts if text) + "</qt>"

    ############################
    # Publicly Exposed Methods #
    ############################

    def control(self, control: MarketControl) -> str:
        """Explain a control.

        Args:
            control (MarketControl): The control.

        Returns:
            str: The rich text tooltip, its name when unexplained.
        """
        explained = self.help.control(control)
        if explained is None:
            return control.value
        return self._paragraphs(explained.title, html.escape(explained.summary))

    def option(self, control: MarketControl, option: str, label: str) -> str:
        """Explain a choice of a list.

        Args:
            control (MarketControl): The control offering it.
            option (str): The value of the choice.
            label (str): Its name in the list.

        Returns:
            str: The rich text tooltip.
        """
        return self._paragraphs(label, self._option(control, option))

    def segment(self, segment: ShareSegment) -> str:
        """Explain a segment: its definition, its source and what it measures.

        Args:
            segment (ShareSegment): The segment.

        Returns:
            str: The rich text tooltip.
        """
        devices = ", ".join(device.value for device in segment.devices)
        return self._paragraphs(
            segment.label,
            html.escape(segment.description),
            self._option(MarketControl.SEGMENT, segment.source.value),
            self._option(MarketControl.SEGMENT, segment.metric.value) + f" Devices: {html.escape(devices)}.",
        )

    def area(self, area: MarketArea) -> str:
        """Explain an area: its kind, and the members of a union.

        Args:
            area (MarketArea): The area.

        Returns:
            str: The rich text tooltip.
        """
        members = f"{len(area.members)} member states: {', '.join(area.members)}." if area.members else ""
        return self._paragraphs(area.label, self._option(MarketControl.AREA, area.kind.value), html.escape(members))

    def device(self, device: str, label: str) -> str:
        """Explain a choice of devices.

        Args:
            device (str): The devices, a `Device` value.
            label (str): Its name in the list.

        Returns:
            str: The rich text tooltip.
        """
        return self.option(MarketControl.DEVICE, device, label)

    def company(self, company: str) -> str:
        """Explain a company of the correlation card: the labels summed into its share, and its listing.

        Args:
            company (str): The company.

        Returns:
            str: The rich text tooltip.
        """
        labels: Dict[str, List[str]] = {}
        for entry in self.catalog.labels:
            if entry.company == company:
                labels.setdefault(entry.source.value, []).append(entry.label)
        mapped = "; ".join(f"{source}: {', '.join(names)}" for source, names in sorted(labels.items()))
        listings = [listing for listing in self.catalog.listings_of(company) if listing.primary]
        listing = f"Primary listing: {listings[0].symbol} ({listings[0].currency})." if listings else "No listing."
        return self._paragraphs(
            self.names.get(company, company),
            f"Labels summed into its share: {html.escape(mapped)}." if mapped else "",
            html.escape(listing),
        )

    def counterpart(self, counterpart: Counterpart) -> str:
        """Explain a choice of the "Against" list: the series, its source, its transform and its alignment.

        Args:
            counterpart (Counterpart): The choice.

        Returns:
            str: The rich text tooltip.
        """
        segment = self.catalog.segment(counterpart.segment) if counterpart.segment else None
        details = self._option(MarketControl.SEGMENT, segment.source.value) if segment is not None else ""
        return self._paragraphs(counterpart.label, self._option(MarketControl.AGAINST, counterpart.kind.value), details)

    def correlate(
        self,
        company: Optional[str],
        segment: Optional[ShareSegment],
        area: Optional[MarketArea],
        device: str,
        counterpart: Optional[Counterpart],
    ) -> str:
        """Say exactly what the Correlate button will compute with the choices made.

        Args:
            company (Optional[str]): The company, `None` without any.
            segment (Optional[ShareSegment]): The segment of the share chart.
            area (Optional[MarketArea]): The area of the share chart.
            device (str): The devices of the share chart.
            counterpart (Optional[Counterpart]): What the share is correlated with, `None` without any.

        Returns:
            str: The rich text tooltip.
        """
        explained = self.help.control(MarketControl.CORRELATE)
        title = explained.title if explained is not None else MarketControl.CORRELATE.value
        if company is None or segment is None or counterpart is None:
            return self._paragraphs(title, "Pick a company and what to correlate it with.")
        own = Granularity.MONTH if segment.source is self.MONTHLY else Granularity.QUARTER
        common = Granularity.QUARTER if Granularity.QUARTER in (own, self._period(counterpart)) else Granularity.MONTH
        unit = self.UNITS[common]
        method = self.help.method.format(
            lags=PairCorrelation.MAX_LAG[common],
            block=PairCorrelation.BLOCK[common],
            resamples=PairCorrelation.RESAMPLES,
            granger=PairCorrelation.GRANGER_LAGS[common],
            points=CoverageChecker.MIN_POINTS[common],
            gap=CoverageChecker.MAX_GAP,
            unit=unit,
        )
        estimate = " (estimate)" if area is not None and area.kind is AreaKind.UNION else ""
        share = (
            f"{self.names.get(company, company)}'s share of {segment.label} in "
            f"{area.label if area else '?'}{estimate}, {device} devices ({segment.source.value}): change in points"
        )
        return self._paragraphs(
            title,
            f"<b>Share:</b> {html.escape(share)}.",
            f"<b>Against:</b> {html.escape(counterpart.label)}. "
            + self._option(MarketControl.AGAINST, counterpart.kind.value),
            f"<b>Period:</b> {unit} (the coarser of the two series).",
            f"<b>Method:</b> {html.escape(method)}",
        )
