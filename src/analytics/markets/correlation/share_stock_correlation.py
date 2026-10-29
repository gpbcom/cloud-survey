from __future__ import annotations

# Standard Library Imports.
from collections import defaultdict
from datetime import date
from logging import Logger, getLogger
from statistics import fmean
from typing import ClassVar, Dict, FrozenSet, List, Optional, Sequence, Tuple

# First Party Imports.
from analytics.markets.correlation.coverage_checker import CoverageChecker
from analytics.markets.correlation.pair_correlation import PairCorrelation
from analytics.markets.stocks.stock_table import StockTable
from models.markets.correlation.counterpart import Counterpart
from models.markets.enums import CorrelationCounterpart, Granularity
from models.markets.facts.price_point import PricePoint
from models.markets.series.share_stock_result import ShareStockResult
from models.markets.values.fx_rate import FxRate
from models.markets.values.market_share_value import MarketShareValue


class ShareStockCorrelation:
    """Correlate a company's share changes with another series: its stock returns, another share, a rate, a context.

    Attributes:
        LOG_CHANGES (ClassVar[FrozenSet[CorrelationCounterpart]]): The counterparts whose changes are log changes
            (prices, exchange rates). The others change in points (shares, concentrations).
        PERIOD_END (ClassVar[FrozenSet[CorrelationCounterpart]]): The counterparts whose quarter takes its last month
            (a close). The others average the months of the quarter.
        pair (PairCorrelation): The lags, the bootstrap, the q-values and the Granger tests.
        coverage (CoverageChecker): The thresholds.
        table (StockTable): The month-end reduction, and the exchange rates.
        logger (Logger): The analysis logger.

    Notes:
        - The period is the coarser of the two series': monthly when both are (StatCounter against a stock or a
          rate), else quarterly (an analyst release, a TrendForce concentration). A monthly series is brought to
          quarters (`PairCorrelation.to_quarters`), never the other way.
        - The share change is in points of share. The counterpart changes in points (a share, a concentration) or
          as a log change (a close in US dollars, units of the home currency per US dollar).
        - The analysis refuses to run below 36 months (16 quarters) of either series or with a gap over 3 periods,
          and says so.
    """

    LOG_CHANGES: ClassVar[FrozenSet[CorrelationCounterpart]] = frozenset(
        {CorrelationCounterpart.STOCK, CorrelationCounterpart.CURRENCY}
    )
    PERIOD_END: ClassVar[FrozenSet[CorrelationCounterpart]] = frozenset({CorrelationCounterpart.STOCK})

    def __init__(self, table: StockTable, logger: Optional[Logger] = None) -> None:
        """Initialize the analysis.

        Args:
            table (StockTable): The month-end reduction, and the exchange rates.
            logger (Optional[Logger]): The analysis logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.table = table
        self.pair = PairCorrelation(self.logger)
        self.coverage = CoverageChecker()

    ############################
    # Internal Helpers Methods #
    ############################

    def _granularity(self, values: Sequence[MarketShareValue]) -> Granularity:
        """Choose the period of a share series: monthly when the shares are, else quarterly.

        Args:
            values (Sequence[MarketShareValue]): The shares.

        Returns:
            Granularity: The month or the quarter.
        """
        return (
            Granularity.MONTH
            if any(value.granularity is Granularity.MONTH for value in values)
            else Granularity.QUARTER
        )

    def _at(
        self, levels: Dict[date, float], own: Granularity, common: Granularity, period_end: bool
    ) -> Dict[date, float]:
        """Bring a series to the period of the analysis.

        Args:
            levels (Dict[date, float]): The levels by period.
            own (Granularity): Their period.
            common (Granularity): The period of the analysis.
            period_end (bool): Whether a quarter takes its last month rather than the mean of its months.

        Returns:
            Dict[date, float]: The levels by period of the analysis.
        """
        return self.pair.to_quarters(levels, period_end) if own is not common else levels

    ############################
    # Publicly Exposed Methods #
    ############################

    def period_shares(
        self, values: Sequence[MarketShareValue], company: str, granularity: Granularity = Granularity.MONTH
    ) -> Dict[date, float]:
        """Sum a company's labels into its share of each period.

        Args:
            values (Sequence[MarketShareValue]): The shares of one segment, area and device.
            company (str): The company.
            granularity (Granularity): The period kept (the others are left out).

        Returns:
            Dict[date, float]: Its share by period.
        """
        shares: Dict[date, float] = defaultdict(float)
        for value in values:
            if value.company == company and value.granularity is granularity:
                shares[value.period] += value.value
        if not shares:
            self.logger.warning("No %s share of %s among %d values.", granularity, company, len(values))
        else:
            self.logger.debug("%d %s shares of %s.", len(shares), granularity, company)
        return dict(sorted(shares.items()))

    def share_levels(self, values: Sequence[MarketShareValue], company: str) -> Tuple[Dict[date, float], Granularity]:
        """Get a company's share by period, in the main period of the values.

        Args:
            values (Sequence[MarketShareValue]): The shares of one segment, area and device.
            company (str): The company.

        Returns:
            Tuple[Dict[date, float], Granularity]: The share by period, and the period.
        """
        granularity = self._granularity(values)
        self.logger.debug("Share levels of %s at the %s granularity.", company, granularity)
        return self.period_shares(values, company, granularity), granularity

    def stock_levels(self, listing: str, prices: Sequence[PricePoint]) -> Dict[date, float]:
        """Get the month-end closes of a listing in US dollars.

        Args:
            listing (str): The listing.
            prices (Sequence[PricePoint]): Its prices.

        Returns:
            Dict[date, float]: The close by month (its first day).
        """
        ordered = sorted((point for point in prices if point.listing == listing), key=lambda point: point.day)
        usd = [
            (point.day, value)
            for point in ordered
            if (value := self.table.converter.convert(point.close, point.currency, "USD", point.day)) is not None
        ]
        if len(usd) < len(ordered):
            self.logger.warning(
                "%d of %d prices of %s could not be converted to USD.", len(ordered) - len(usd), len(ordered), listing
            )
        self.logger.debug("%d USD prices of %s.", len(usd), listing)
        return self.table.month_ends(usd)

    def currency_levels(self, currency: str, rates: Sequence[FxRate]) -> Dict[date, float]:
        """Get the mean units of a currency per US dollar of each month.

        Args:
            currency (str): The currency.
            rates (Sequence[FxRate]): The exchange rates.

        Returns:
            Dict[date, float]: The mean by month (its first day).
        """
        months: Dict[date, List[float]] = defaultdict(list)
        for rate in rates:
            if rate.currency == currency:
                months[rate.day.replace(day=1)].append(1.0 / rate.usd_per_unit)
        if not months:
            self.logger.warning("No exchange rate of %s among %d rates.", currency, len(rates))
        else:
            self.logger.debug("%d monthly levels of %s per USD.", len(months), currency)
        return {month: fmean(values) for month, values in sorted(months.items())}

    def compare(
        self,
        company: str,
        segment: str,
        area: str,
        device: str,
        values: Sequence[MarketShareValue],
        counterpart: Counterpart,
        levels: Dict[date, float],
        granularity: Granularity,
    ) -> ShareStockResult:
        """Correlate a company's share with a counterpart series.

        Args:
            company (str): The company.
            segment (str): The segment of the shares.
            area (str): The area of the shares.
            device (str): The devices of the shares.
            values (Sequence[MarketShareValue]): The shares of that segment, area and device.
            counterpart (Counterpart): What the shares are correlated with.
            levels (Dict[date, float]): The counterpart's levels by period (closes, shares, rates, concentrations).
            granularity (Granularity): The period of those levels.

        Returns:
            ShareStockResult: The correlations by lag and the Granger p-values, or why they were not computed.
        """
        shares, own = self.share_levels(values, company)
        common = Granularity.QUARTER if Granularity.QUARTER in (own, granularity) else Granularity.MONTH
        shares = self._at(shares, own, common, period_end=False)
        other = self._at(levels, granularity, common, counterpart.kind in self.PERIOD_END)
        share_coverage = self.coverage.entry(f"{segment} / {area} / {device} / {company}", list(shares), common)
        other_coverage = self.coverage.entry(counterpart.label, list(other), common)
        result = ShareStockResult(
            company=company,
            segment=segment,
            area=area,
            device=device,
            listing=counterpart.listing,
            counterpart=counterpart.kind,
            counterpart_label=counterpart.label,
            granularity=common,
            share_coverage=share_coverage,
            stock_coverage=other_coverage,
            granger_lags=PairCorrelation.GRANGER_LAGS[common],
        )
        unit = "months" if common is Granularity.MONTH else "quarters"
        for coverage in (share_coverage, other_coverage):
            if not coverage.enough:
                reason = (
                    f"{coverage.key}: {coverage.points} {unit}, longest gap {coverage.longest_gap} "
                    f"(at least {CoverageChecker.MIN_POINTS[common]} {unit} and gaps of at most "
                    f"{CoverageChecker.MAX_GAP} are needed)."
                )
                self.logger.info("Share correlation refused: %s", reason)
                return result.model_copy(update={"refusal": reason})
        lags, share_leads, other_leads = self.pair.correlate(
            self.pair.changes(shares, common, log=False),
            self.pair.changes(other, common, log=counterpart.kind in self.LOG_CHANGES),
            common,
        )
        self.logger.info(
            "Share correlation of %s (%s, %s) against %s by %s: Granger share->other p=%s, other->share p=%s.",
            company,
            segment,
            area,
            counterpart.label,
            common.value,
            share_leads,
            other_leads,
        )
        return result.model_copy(update={"lags": lags, "share_leads_p": share_leads, "stock_leads_p": other_leads})

    def analyse(
        self,
        company: str,
        segment: str,
        area: str,
        device: str,
        values: Sequence[MarketShareValue],
        listing: Optional[str],
        prices: Sequence[PricePoint],
    ) -> ShareStockResult:
        """Correlate a company's share with its stock value.

        Args:
            company (str): The company.
            segment (str): The segment of the shares.
            area (str): The area of the shares.
            device (str): The devices of the shares.
            values (Sequence[MarketShareValue]): The shares of that segment, area and device.
            listing (Optional[str]): The company's primary listing, `None` when it has none.
            prices (Sequence[PricePoint]): The prices of that listing.

        Returns:
            ShareStockResult: The correlations by lag and the Granger p-values, or why they were not computed.
        """
        if listing is None:
            self.logger.warning("%s has no listing: its share is not correlated with a stock.", company)
            granularity = self._granularity(values)
            return ShareStockResult(
                company=company,
                segment=segment,
                area=area,
                device=device,
                granularity=granularity,
                share_coverage=self.coverage.entry(
                    f"{segment} / {area} / {device} / {company}",
                    list(self.period_shares(values, company, granularity)),
                    granularity,
                ),
                granger_lags=PairCorrelation.GRANGER_LAGS[granularity],
                refusal=f"{company} has no listing: its value cannot be correlated.",
            )
        counterpart = Counterpart(kind=CorrelationCounterpart.STOCK, label=listing, listing=listing)
        self.logger.debug("Correlating the %s share of %s with its stock %s.", segment, company, listing)
        return self.compare(
            company, segment, area, device, values, counterpart, self.stock_levels(listing, prices), Granularity.MONTH
        )
