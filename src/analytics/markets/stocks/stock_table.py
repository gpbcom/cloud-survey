from __future__ import annotations

# Standard Library Imports.
import itertools
from collections import defaultdict
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# First Party Imports.
from analytics.markets.stocks.fx_converter import FxConverter
from models.markets.enums import PriceScale
from models.markets.facts.price_point import PricePoint
from models.markets.listings.hq_region import HqRegion
from models.markets.listings.stock_listing import StockListing
from models.markets.series.stock_series import StockSeries


class StockTable:
    """Fold the stored prices into the lines of the stock chart: per listing, per currency, per region.

    Attributes:
        LISTING_CURRENCY (ClassVar[str]): The currency choice keeping each listing in its own currency.
        INDEX (ClassVar[str]): The currency of a series rebased to 100.
        converter (FxConverter): The exchange rates.
        logger (Logger): The table logger.

    Notes:
        - A price converts on its own day. The days without rate (before the currency's first, e.g. the euro
          before 1999) are left out of a converted line, and its note says from when it converts.
        - An indexed line is rebased to 100 at its first point in the window, so lines of different currencies
          and sizes compare.
        - A region index is equal-weighted and chain-linked over the month-end closes of the primary listings of
          its companies: each month it moves by the average return of the listings quoted that month and the one
          before, so a listing joining (an IPO) or leaving does not jump it.
    """

    LISTING_CURRENCY: ClassVar[str] = "listing"
    INDEX: ClassVar[str] = "index"

    def __init__(self, converter: FxConverter, logger: Optional[Logger] = None) -> None:
        """Initialize the table.

        Args:
            converter (FxConverter): The exchange rates.
            logger (Optional[Logger]): The table logger.
        """
        self.converter = converter
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _converted(
        self, points: Sequence[PricePoint], currency: str, start: Optional[date], end: Optional[date]
    ) -> List[Tuple[date, float]]:
        """Convert the prices of a listing in the window.

        Args:
            points (Sequence[PricePoint]): The prices of one listing.
            currency (str): The currency wanted, or `listing`.
            start (Optional[date]): Only from this day.
            end (Optional[date]): Only up to this day.

        Returns:
            List[Tuple[date, float]]: The converted prices by day, the days without rate left out.
        """
        values: List[Tuple[date, float]] = []
        for point in points:
            if (start and point.day < start) or (end and point.day > end):
                continue
            target = point.currency if currency == self.LISTING_CURRENCY else currency
            value = self.converter.convert(point.close, point.currency, target, point.day)
            if value is not None:
                values.append((point.day, value))
        self.logger.debug("%d of %d prices converted to %s.", len(values), len(points), currency)
        return values

    def _rebased(self, values: List[Tuple[date, float]]) -> List[Tuple[date, float]]:
        """Rebase a line to 100 at its first point.

        Args:
            values (List[Tuple[date, float]]): The line.

        Returns:
            List[Tuple[date, float]]: The line, its first point at 100.
        """
        if not values or values[0][1] <= 0:
            self.logger.warning("No positive first price among %d prices: nothing to rebase.", len(values))
            return []
        base = values[0][1]
        self.logger.debug("%d prices rebased to 100 on %s.", len(values), values[0][0])
        return [(day, value / base * 100.0) for day, value in values]

    ############################
    # Publicly Exposed Methods #
    ############################

    def month_ends(self, values: Sequence[Tuple[date, float]]) -> Dict[date, float]:
        """Reduce a line to its last value of each month.

        Args:
            values (Sequence[Tuple[date, float]]): The line, by day.

        Returns:
            Dict[date, float]: The last value of each month, keyed by the month's first day.
        """
        ends: Dict[date, Tuple[date, float]] = {}
        for day, value in values:
            month = day.replace(day=1)
            if month not in ends or day >= ends[month][0]:
                ends[month] = (day, value)
        self.logger.debug("%d month-end values out of %d daily values.", len(ends), len(values))
        return {month: value for month, (_, value) in sorted(ends.items())}

    def listing_lines(
        self,
        points: Sequence[PricePoint],
        listings: Sequence[StockListing],
        names: Dict[str, str],
        currency: str = LISTING_CURRENCY,
        scale: PriceScale = PriceScale.LINEAR,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> List[StockSeries]:
        """Build a line per listing.

        Args:
            points (Sequence[PricePoint]): The prices of the listings.
            listings (Sequence[StockListing]): The listings drawn, in order.
            names (Dict[str, str]): The name of each company.
            currency (str): `listing` (each in its own currency), or the currency wanted (`USD`, `EUR`, `GBP`).
            scale (PriceScale): Linear, logarithmic, or indexed (rebased to 100).
            start (Optional[date]): Only from this day.
            end (Optional[date]): Only up to this day.

        Returns:
            List[StockSeries]: A line per listing with prices in the window.
        """
        by_listing: Dict[str, List[PricePoint]] = defaultdict(list)
        for point in points:
            by_listing[point.listing].append(point)
        lines: List[StockSeries] = []
        for listing in listings:
            prices = sorted(by_listing.get(listing.symbol, []), key=lambda point: point.day)
            values = self._converted(prices, currency, start, end)
            if not values:
                continue
            target = listing.currency if currency == self.LISTING_CURRENCY else currency
            note = listing.note
            first = self.converter.first_day(listing.currency) if target != listing.currency else None
            if first and prices and prices[0].day < first:
                note = (
                    f"{note + '. ' if note else ''}In {target} from {first.isoformat()} (first {listing.currency} rate)"
                )
            if scale is PriceScale.INDEXED:
                values = self._rebased(values)
            lines.append(
                StockSeries(
                    key=listing.symbol,
                    company=listing.company,
                    label=f"{names.get(listing.company, listing.company)} ({listing.symbol})",
                    currency=self.INDEX if scale is PriceScale.INDEXED else target,
                    primary=listing.primary,
                    points=values,
                    note=note,
                )
            )
        self.logger.debug("%d stock lines built (%s, %s).", len(lines), currency, scale.value)
        return lines

    def region_indexes(
        self,
        points: Sequence[PricePoint],
        listings: Sequence[StockListing],
        regions: Sequence[HqRegion],
        countries: Dict[str, str],
        currency: str = "USD",
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> List[StockSeries]:
        """Build an equal-weight index per region of headquarters, over the primary listings.

        Args:
            points (Sequence[PricePoint]): The prices of the listings.
            listings (Sequence[StockListing]): The listings (only the primary ones are used).
            regions (Sequence[HqRegion]): The regions.
            countries (Dict[str, str]): The country of the headquarters of each company.
            currency (str): The currency the returns are measured in.
            start (Optional[date]): Only from this day.
            end (Optional[date]): Only up to this day.

        Returns:
            List[StockSeries]: An index (100 at its first month) per region with at least one listing quoted.
        """
        by_listing: Dict[str, List[PricePoint]] = defaultdict(list)
        for point in points:
            by_listing[point.listing].append(point)
        lines: List[StockSeries] = []
        for region in regions:
            members = [
                listing
                for listing in listings
                if listing.primary and countries.get(listing.company) in region.countries
            ]
            closes = [
                self.month_ends(
                    self._converted(
                        sorted(by_listing.get(listing.symbol, []), key=lambda p: p.day), currency, start, end
                    )
                )
                for listing in members
            ]
            months = sorted({month for listing_closes in closes for month in listing_closes})
            if len(months) < 2:
                continue
            level, values = 100.0, [(months[0], 100.0)]
            for previous, month in itertools.pairwise(months):
                returns = [c[month] / c[previous] for c in closes if month in c and previous in c and c[previous] > 0]
                if returns:
                    level *= sum(returns) / len(returns)
                values.append((month, level))
            lines.append(
                StockSeries(
                    key=f"region:{region.key}",
                    label=f"{region.label} ({len(members)} listings)",
                    currency=self.INDEX,
                    points=values,
                    note=f"Equal-weight index of the primary listings, returns in {currency}",
                )
            )
        self.logger.debug("%d region indexes built.", len(lines))
        return lines
