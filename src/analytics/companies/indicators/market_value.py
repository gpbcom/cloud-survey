from __future__ import annotations

# Standard Library Imports.
import bisect
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence, Tuple

# First Party Imports.
from analytics.companies.indicators.currency_rates import CurrencyRates
from analytics.companies.indicators.financial_book import FinancialBook
from models.companies.catalog.company_entry import CompanyEntry
from models.companies.enums import (
    CompanyIndicator,
    FinancialGranularity,
    FinancialMetric,
    FinancialSource,
    IndicatorUnit,
)
from models.companies.values.indicator_value import IndicatorValue
from models.markets.facts.price_point import PricePoint
from models.markets.listings.stock_listing import StockListing


class MarketValue:
    """Compute the market capitalisation and the enterprise value of a listed company, week by week.

    Attributes:
        SHARES_AGE (ClassVar[int]): The most days a share count is carried forward.
        BALANCE_AGE (ClassVar[int]): The most days a debt or cash balance is carried forward.
        PERIOD_TOLERANCE (ClassVar[int]): The most days between a period end and the weekly close it is valued at.
        GAP_WARNING (ClassVar[float]): The relative gap with Google's own capitalisation that is warned about.
        DEBT (ClassVar[Tuple[FinancialMetric, ...]]): The lines adding up to the total debt.
        rates (CurrencyRates): Converts between the reporting and the trading currencies.
        logger (Logger): The calculator logger.

    Notes:
        - Market capitalisation = weekly close of the valued listing (the stored Google Finance prices) times the
          units outstanding that day (the last count stated, carried forward a year at most). For a listing of
          depositary shares, Google Finance's count is already per depositary share, and an SEC count of ordinary
          shares is divided by the shares a depositary share stands for.
        - Enterprise value = market capitalisation plus the debt less the cash of the last balance sheet (half a year
          old at most), converted into the trading currency at the day's rates when the company reports in another.
        - The weekly series are also read at each quarter and fiscal-year end (the last close before it).
    """

    SHARES_AGE: ClassVar[int] = 400
    BALANCE_AGE: ClassVar[int] = 200
    PERIOD_TOLERANCE: ClassVar[int] = 10
    GAP_WARNING: ClassVar[float] = 0.35
    DEBT: ClassVar[Tuple[FinancialMetric, ...]] = (
        FinancialMetric.CURRENT_DEBT,
        FinancialMetric.LONG_TERM_DEBT,
        FinancialMetric.CURRENT_BONDS,
        FinancialMetric.NONCURRENT_BONDS,
    )

    def __init__(self, rates: CurrencyRates, logger: Optional[Logger] = None) -> None:
        """Initialize the calculator.

        Args:
            rates (CurrencyRates): Converts between currencies.
            logger (Optional[Logger]): The calculator logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.rates = rates

    ############################
    # Internal Helpers Methods #
    ############################

    def _shares(self, book: FinancialBook, day: date) -> Optional[float]:
        """Get the shares outstanding in force on a day: the last count filed, else the last diluted average.

        Args:
            book (FinancialBook): The statement lines.
            day (date): The day.

        Returns:
            Optional[float]: The shares, `None` when no recent count is stated.
        """
        for metric in (FinancialMetric.SHARES_OUTSTANDING, FinancialMetric.DILUTED_SHARES):
            found = book.latest_balance(metric, day, self.SHARES_AGE)
            if found is not None and found[1][0] > 0:
                return found[1][0]
        quarters = book.flows.get((FinancialMetric.DILUTED_SHARES, FinancialGranularity.QUARTER), {})
        ends = sorted(end for end in quarters if end <= day and (day - end).days <= self.SHARES_AGE)
        return quarters[ends[-1]][0] if ends else None

    def _units(self, entry: CompanyEntry, book: FinancialBook, day: date) -> Optional[float]:
        """Get the traded units the market values on a day: the shares, or the depositary shares they stand for.

        Args:
            entry (CompanyEntry): The company (its shares per unit).
            book (FinancialBook): The statement lines.
            day (date): The day.

        Returns:
            Optional[float]: The units, `None` when no recent count is stated (or the ratio did not hold yet).
        """
        valued = entry.market_cap
        if valued is None:
            return self._shares(book, day)
        google = book.latest_sourced(
            FinancialMetric.SHARES_OUTSTANDING, FinancialSource.GOOGLE_FINANCE, day, self.SHARES_AGE
        )
        if google is not None and google[1][0] > 0:
            return google[1][0]
        filed = book.latest_sourced(FinancialMetric.SHARES_OUTSTANDING, FinancialSource.EDGAR, day, self.SHARES_AGE)
        if filed is None or filed[1][0] <= 0 or (valued.since is not None and day < valued.since):
            return None
        return filed[1][0] / valued.shares_per_unit

    def _net_debt(self, book: FinancialBook, day: date, currency: str) -> Optional[float]:
        """Get the debt less the cash of the last balance sheet, in the trading currency.

        Args:
            book (FinancialBook): The statement lines.
            day (date): The day.
            currency (str): The trading currency.

        Returns:
            Optional[float]: The net debt, `None` when no recent debt is stated or no rate converts it.
        """
        debts = [book.latest_balance(metric, day, self.BALANCE_AGE) for metric in self.DEBT]
        stated = [found for found in debts if found is not None]
        if not stated:
            return None
        cash = book.latest_balance(FinancialMetric.CASH, day, self.BALANCE_AGE)
        investments = book.latest_balance(FinancialMetric.SHORT_TERM_INVESTMENTS, day, self.BALANCE_AGE)
        reporting = stated[0][1][1]
        net = sum(found[1][0] for found in stated) - sum(found[1][0] for found in (cash, investments) if found)
        return self.rates.convert(net, reporting, currency, day)

    def _point(
        self,
        company: str,
        indicator: CompanyIndicator,
        granularity: FinancialGranularity,
        day: date,
        value: float,
        currency: str,
        inputs: str,
    ) -> IndicatorValue:
        """Build a point of a series.

        Args:
            company (str): The company.
            indicator (CompanyIndicator): The indicator.
            granularity (FinancialGranularity): The period.
            day (date): The day.
            value (float): The amount.
            currency (str): Its currency.
            inputs (str): How it was computed.

        Returns:
            IndicatorValue: The point, also in US dollars when a rate is stored.
        """
        return IndicatorValue(
            company=company,
            indicator=indicator,
            period_end=day,
            granularity=granularity,
            value=value,
            unit=IndicatorUnit.CURRENCY,
            currency=currency,
            value_usd=self.rates.to_usd(value, currency, day),
            inputs=inputs,
        )

    def _at_periods(
        self, weekly: List[IndicatorValue], ends: Sequence[date], granularity: FinancialGranularity
    ) -> List[IndicatorValue]:
        """Read a weekly series at period ends: the last close on or before each end.

        Args:
            weekly (List[IndicatorValue]): The weekly points, by day.
            ends (Sequence[date]): The period ends.
            granularity (FinancialGranularity): The period.

        Returns:
            List[IndicatorValue]: A point per period end valued near enough.
        """
        days = [point.period_end for point in weekly]
        points: List[IndicatorValue] = []
        for end in ends:
            index = bisect.bisect_right(days, end)
            if index and (end - days[index - 1]).days <= self.PERIOD_TOLERANCE:
                points.append(weekly[index - 1].model_copy(update={"period_end": end, "granularity": granularity}))
        return points

    ############################
    # Publicly Exposed Methods #
    ############################

    def compute(
        self, entry: CompanyEntry, listing: StockListing, prices: Sequence[PricePoint], book: FinancialBook
    ) -> List[IndicatorValue]:
        """Compute the weekly market capitalisation and enterprise value of a company, and read them at its period ends.

        Args:
            entry (CompanyEntry): The company (its valued listing and shares per unit).
            listing (StockListing): The valued listing.
            prices (Sequence[PricePoint]): The weekly closes of the listing.
            book (FinancialBook): The statement lines (the shares, the debt and the cash).

        Returns:
            List[IndicatorValue]: The points of both series.
        """
        ratio = entry.market_cap.shares_per_unit if entry.market_cap else 1.0
        caps: List[IndicatorValue] = []
        values: List[IndicatorValue] = []
        for price in sorted(prices, key=lambda point: point.day):
            units = self._units(entry, book, price.day)
            if units is None:
                continue
            cap = price.close * units
            caps.append(
                self._point(
                    entry.key,
                    CompanyIndicator.MARKET_CAP,
                    FinancialGranularity.WEEK,
                    price.day,
                    cap,
                    price.currency,
                    f"close of {listing.symbol} * shares / {ratio:g}",
                )
            )
            net_debt = self._net_debt(book, price.day, price.currency)
            if net_debt is not None:
                values.append(
                    self._point(
                        entry.key,
                        CompanyIndicator.ENTERPRISE_VALUE,
                        FinancialGranularity.WEEK,
                        price.day,
                        cap + net_debt,
                        price.currency,
                        "market-cap + total-debt - cash",
                    )
                )
        quarters = book.ends(FinancialGranularity.QUARTER, [FinancialMetric.REVENUE, FinancialMetric.NET_INCOME])
        years = book.ends(FinancialGranularity.YEAR, [FinancialMetric.REVENUE, FinancialMetric.NET_INCOME])
        points = list(caps) + list(values)
        for series in (caps, values):
            points += self._at_periods(series, quarters, FinancialGranularity.QUARTER)
            points += self._at_periods(series, years, FinancialGranularity.YEAR)
        quote = book.balances.get(FinancialMetric.MARKET_CAP, [])
        if caps and quote and quote[-1][1][1] == caps[-1].currency and quote[-1][1][0] > 0:
            gap = abs(caps[-1].value - quote[-1][1][0]) / quote[-1][1][0]
            if gap > self.GAP_WARNING:
                self.logger.warning(
                    "%s: the last computed capitalisation is %.0f%% away from Google's (shares per unit to check).",
                    entry.key,
                    gap * 100,
                )
        self.logger.info("%s: %d weekly capitalisations, %d enterprise values.", entry.key, len(caps), len(values))
        return points
