from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, FrozenSet, List, Optional, Tuple

# First Party Imports.
from analytics.markets.correlation.share_stock_correlation import ShareStockCorrelation
from analytics.markets.criteria.context_criteria import ContextCriteria
from models.history.chronology import Chronology
from models.markets.correlation.counterpart import Counterpart
from models.markets.enums import CorrelationCounterpart, Device, Granularity, ShareSource
from models.markets.markets_catalog import MarketsCatalog
from storage.storage import Storage


class CounterpartSeries:
    """List the series a company's share can be correlated with, and read the one picked.

    Attributes:
        PIVOT (ClassVar[str]): The currency the home currency is measured against.
        WORLD (ClassVar[str]): The area of the context series.
        SKIPPED (ClassVar[FrozenSet[ShareSource]]): The share sources too sparse to correlate (the dossier points).
        catalog (MarketsCatalog): The segments, areas, listings and currencies.
        chronology (Optional[Chronology]): The companies (their country).
        context (ContextCriteria): The TrendForce concentrations.
        logger (Logger): The reader logger.

    Notes:
        - The choices are, in this order: the company's primary listing, its other share series (another segment
          or source, in the area of the share chart, worldwide or in its home country, its yearly totals left out),
          its home currency when it is not the US dollar, then the TrendForce concentrations.
        - The share series being correlated is never offered against itself.
    """

    PIVOT: ClassVar[str] = "USD"
    WORLD: ClassVar[str] = "ww"
    SKIPPED: ClassVar[FrozenSet[ShareSource]] = frozenset({ShareSource.MANUAL})

    def __init__(
        self, catalog: MarketsCatalog, chronology: Optional[Chronology], logger: Optional[Logger] = None
    ) -> None:
        """Initialize the reader.

        Args:
            catalog (MarketsCatalog): The segments, areas, listings and currencies.
            chronology (Optional[Chronology]): The companies (their country).
            logger (Optional[Logger]): The reader logger.
        """
        self.catalog, self.chronology = catalog, chronology
        self.logger = logger if logger else getLogger(__name__)
        self.context = ContextCriteria(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _share_label(self, segment: str, area: str, source: ShareSource) -> str:
        """Name a share series.

        Args:
            segment (str): The segment.
            area (str): The area.
            source (ShareSource): The source.

        Returns:
            str: e.g. `Smartphones / Worldwide / idc`.
        """
        found_segment, found_area = self.catalog.segment(segment), self.catalog.area(area)
        if found_segment is None or found_area is None:
            self.logger.warning("Segment %s or area %s missing from the catalogue: its key is shown.", segment, area)
        return (
            f"{found_segment.label if found_segment else segment} / "
            f"{found_area.label if found_area else area} / {source.value}"
        )

    def _country(self, company: str) -> Optional[str]:
        """Get the country of a company's headquarters.

        Args:
            company (str): The company.

        Returns:
            Optional[str]: Its country, `None` when the chronology does not say.
        """
        companies = self.chronology.companies if self.chronology is not None else []
        country = next((entry.country for entry in companies if entry.key == company), None)
        self.logger.debug("Home country of %s: %s.", company, country)
        return country

    ############################
    # Publicly Exposed Methods #
    ############################

    async def options(
        self, company: str, segment: str, area: str, source: Optional[ShareSource], storage: Storage
    ) -> List[Counterpart]:
        """List what a company's share in a segment and an area can be correlated with.

        Args:
            company (str): The company.
            segment (str): The segment of the share correlated.
            area (str): Its area.
            source (Optional[ShareSource]): Its source.
            storage (Storage): The open storage.

        Returns:
            List[Counterpart]: The choices, in display order.

        Raises:
            StorageReadError: If the share series cannot be read.
        """
        choices: List[Counterpart] = []
        listings = [listing for listing in self.catalog.listings_of(company) if listing.primary]
        if listings:
            symbol = listings[0].symbol
            choices.append(Counterpart(kind=CorrelationCounterpart.STOCK, label=f"{symbol} stock", listing=symbol))
        country = self._country(company)
        areas = {area, self.WORLD, country}
        for other_segment, other_area, other_source, granularity in await storage.shares.series_of(company):
            if granularity is Granularity.YEAR or other_source in self.SKIPPED or other_area not in areas:
                continue
            if (other_segment, other_area, other_source) == (segment, area, source):
                continue
            choices.append(
                Counterpart(
                    kind=CorrelationCounterpart.SHARE,
                    label=self._share_label(other_segment, other_area, other_source),
                    segment=other_segment,
                    area=other_area,
                    source=other_source,
                )
            )
        currency = self.catalog.currency_of(country)
        if currency and currency != self.PIVOT:
            choices.append(
                Counterpart(
                    kind=CorrelationCounterpart.CURRENCY,
                    label=f"{currency} per US dollar (home currency)",
                    currency=currency,
                )
            )
        for key in ContextCriteria.METRICS:
            found = self.catalog.segment(key)
            if found is not None:
                choices.append(
                    Counterpart(
                        kind=CorrelationCounterpart.CONTEXT,
                        label=f"{found.label} concentration (HHI)",
                        segment=key,
                        source=found.source,
                    )
                )
        self.logger.debug("%d counterparts offered for %s in %s (%s).", len(choices), company, segment, area)
        return choices

    async def levels(
        self, company: str, counterpart: Counterpart, engine: ShareStockCorrelation, storage: Storage
    ) -> Tuple[Dict[date, float], Granularity]:
        """Read the levels of a counterpart series.

        Args:
            company (str): The company correlated.
            counterpart (Counterpart): The series picked.
            engine (ShareStockCorrelation): Reduces the shares, the closes and the rates to levels.
            storage (Storage): The open storage.

        Returns:
            Tuple[Dict[date, float], Granularity]: The levels by period, and their period.

        Raises:
            StorageReadError: If the series cannot be read.
        """
        match counterpart.kind:
            case CorrelationCounterpart.STOCK if counterpart.listing:
                prices = await storage.stocks.list([counterpart.listing])
                return engine.stock_levels(counterpart.listing, prices), Granularity.MONTH
            case CorrelationCounterpart.SHARE if counterpart.segment and counterpart.area:
                values = await storage.shares.list(
                    counterpart.segment, counterpart.area, Device.ALL, source=counterpart.source, companies=[company]
                )
                return engine.share_levels(values, company)
            case CorrelationCounterpart.CURRENCY if counterpart.currency:
                rates = await storage.fx.list([counterpart.currency])
                return engine.currency_levels(counterpart.currency, rates), Granularity.MONTH
            case CorrelationCounterpart.CONTEXT if counterpart.segment:
                shares = await storage.shares.list(
                    counterpart.segment, self.WORLD, Device.ALL, source=counterpart.source
                )
                return self.context.concentration(shares), Granularity.QUARTER
            case _:
                self.logger.warning("The counterpart %s names no series: nothing to read.", counterpart.label)
                return {}, Granularity.MONTH
