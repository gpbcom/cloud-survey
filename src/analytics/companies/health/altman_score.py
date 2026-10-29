from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence, Tuple

# First Party Imports.
from analytics.companies.health.indicator_points import IndicatorPoints
from analytics.companies.indicators.currency_rates import CurrencyRates
from analytics.companies.indicators.financial_book import FinancialBook
from models.companies.enums import (
    CompanyIndicator,
    FinancialGranularity,
    FinancialMetric,
    IndicatorUnit,
    StatementKind,
)
from models.companies.values.indicator_value import IndicatorValue

type Ratios = Tuple[float, float, float, float, float, float]


class AltmanScore:
    """Compute the Altman Z-scores of a company: the 1968 Z of the listed companies and the 1995 Z'' on book values.

    Attributes:
        PERIODS (ClassVar[Tuple[FinancialGranularity, ...]]): The periods scored (the flows of a fiscal year or of
            the trailing twelve months, the balances at the period end).
        Z (ClassVar[Tuple[float, float, float, float, float]]): The weights of the 1968 score (working capital,
            retained earnings, operating income, market value of equity over liabilities, revenue, each over assets).
        Z_DOUBLE_PRIME (ClassVar[Tuple[float, float, float, float]]): The weights of the 1995 score (working capital,
            retained earnings, operating income over assets, book equity over liabilities).
        MARKET_DAYS (ClassVar[int]): The most days between the period end and the market capitalisation read.
        rates (CurrencyRates): Converts the market capitalisation into the reporting currency.
        points (IndicatorPoints): Builds the points.
        logger (Logger): The calculator logger.

    Notes:
        - Two series, never one switching formula: their zones differ (Z: distress below 1.81, safe above 2.99, Z'':
          below 1.1 and above 2.6), and a listing would make the series jump. Z'' applies to every company, listed or
          not, manufacturer or not: it is the series to compare across the whole history.
        - A score needs every input: no retained earnings, no working capital, no point (never assumed to be zero).
          The liabilities are stated, else the assets less the equity. A bank is not scored.
    """

    PERIODS: ClassVar[Tuple[FinancialGranularity, ...]] = (FinancialGranularity.YEAR, FinancialGranularity.TTM)
    Z: ClassVar[Tuple[float, float, float, float, float]] = (1.2, 1.4, 3.3, 0.6, 1.0)
    Z_DOUBLE_PRIME: ClassVar[Tuple[float, float, float, float]] = (6.56, 3.26, 6.72, 1.05)
    MARKET_DAYS: ClassVar[int] = 10

    def __init__(self, rates: CurrencyRates, points: IndicatorPoints, logger: Optional[Logger] = None) -> None:
        """Initialize the calculator.

        Args:
            rates (CurrencyRates): Converts the market capitalisation into the reporting currency.
            points (IndicatorPoints): Builds the points.
            logger (Optional[Logger]): The calculator logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.rates = rates
        self.points = points

    ############################
    # Internal Helpers Methods #
    ############################

    def _ratios(self, book: FinancialBook, granularity: FinancialGranularity, end: date) -> Optional[Ratios]:
        """Read the inputs of the scores at a period end, as ratios to the total assets.

        Args:
            book (FinancialBook): The statement lines.
            granularity (FinancialGranularity): A fiscal year or the trailing twelve months.
            end (date): The period end.

        Returns:
            Optional[Ratios]: Working capital, retained earnings, operating income and revenue over the assets, the
                equity over the liabilities, and the liabilities, `None` when an input lacks or the assets or the
                liabilities are not positive.
        """
        assets = book.balance(FinancialMetric.TOTAL_ASSETS, end)
        current_assets = book.balance(FinancialMetric.CURRENT_ASSETS, end)
        current_liabilities = book.balance(FinancialMetric.CURRENT_LIABILITIES, end)
        retained = book.balance(FinancialMetric.RETAINED_EARNINGS, end)
        equity = book.balance(FinancialMetric.TOTAL_EQUITY, end)
        liabilities = book.liabilities(end)
        operating = book.flow(FinancialMetric.OPERATING_INCOME, granularity, end)
        revenue = book.flow(FinancialMetric.REVENUE, granularity, end)
        if (
            assets is None
            or current_assets is None
            or current_liabilities is None
            or retained is None
            or equity is None
            or liabilities is None
            or operating is None
            or revenue is None
        ):
            return None
        if assets[0] <= 0 or liabilities[0] <= 0:
            return None
        total = assets[0]
        return (
            (current_assets[0] - current_liabilities[0]) / total,
            retained[0] / total,
            operating[0] / total,
            revenue[0] / total,
            equity[0] / liabilities[0],
            liabilities[0],
        )

    def _market_cap(self, market: Sequence[IndicatorValue], end: date, currency: Optional[str]) -> Optional[float]:
        """Get the market capitalisation at a period end, in the reporting currency.

        Args:
            market (Sequence[IndicatorValue]): The market capitalisation points of the company.
            end (date): The period end.
            currency (Optional[str]): The reporting currency.

        Returns:
            Optional[float]: The nearest capitalisation within `MARKET_DAYS`, converted, `None` otherwise.
        """
        near = [point for point in market if abs((point.period_end - end).days) <= self.MARKET_DAYS]
        if not near:
            return None
        point = min(near, key=lambda item: abs((item.period_end - end).days))
        if point.currency == currency:
            return point.value
        return self.rates.convert(point.value, point.currency, currency, end)

    ############################
    # Publicly Exposed Methods #
    ############################

    def compute(
        self,
        company: str,
        book: FinancialBook,
        market: Sequence[IndicatorValue],
        statements: StatementKind = StatementKind.INDUSTRIAL,
    ) -> List[IndicatorValue]:
        """Compute the Altman scores of a company at every fiscal year end (and trailing twelve months).

        Args:
            company (str): The company.
            book (FinancialBook): Its statement lines.
            market (Sequence[IndicatorValue]): Its market capitalisation points (none for a private company).
            statements (StatementKind): The shape of its statements (a bank is not scored).

        Returns:
            List[IndicatorValue]: The points of both scores.
        """
        if statements is StatementKind.BANK:
            self.logger.info("%s is a bank: no Altman score.", company)
            return []
        caps = [point for point in market if point.indicator is CompanyIndicator.MARKET_CAP]
        found: List[IndicatorValue] = []
        for granularity in self.PERIODS:
            base = (
                FinancialGranularity.YEAR if granularity is FinancialGranularity.YEAR else FinancialGranularity.QUARTER
            )
            for end in book.ends(base, [FinancialMetric.REVENUE, FinancialMetric.OPERATING_INCOME]):
                ratios = self._ratios(book, granularity, end)
                if ratios is None:
                    continue
                working, retained, operating, revenue, book_equity, liabilities = ratios
                a, b, c, d = self.Z_DOUBLE_PRIME
                double_prime = a * working + b * retained + c * operating + d * book_equity
                inputs = "6.56 WC/TA + 3.26 RE/TA + 6.72 EBIT/TA + 1.05 BE/TL"
                found.append(
                    self.points.point(
                        company,
                        CompanyIndicator.ALTMAN_Z_DOUBLE_PRIME,
                        granularity,
                        end,
                        double_prime,
                        IndicatorUnit.SCORE,
                        inputs,
                    )
                )
                assets = book.balance(FinancialMetric.TOTAL_ASSETS, end)
                cap = self._market_cap(caps, end, assets[1] if assets else None)
                if cap is None:
                    continue
                w1, w2, w3, w4, w5 = self.Z
                score = w1 * working + w2 * retained + w3 * operating + w4 * cap / liabilities + w5 * revenue
                inputs = "1.2 WC/TA + 1.4 RE/TA + 3.3 EBIT/TA + 0.6 MVE/TL + 1.0 S/TA"
                found.append(
                    self.points.point(
                        company, CompanyIndicator.ALTMAN_Z, granularity, end, score, IndicatorUnit.SCORE, inputs
                    )
                )
        self.logger.debug("%s: %d Altman score points.", company, len(found))
        return found
