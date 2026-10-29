from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence

# First Party Imports.
from analytics.companies.health.indicator_points import IndicatorPoints
from analytics.companies.indicators.financial_book import FinancialBook
from models.companies.enums import CompanyIndicator, FinancialGranularity, FinancialMetric, IndicatorUnit
from models.companies.values.indicator_value import IndicatorValue
from models.markets.listings.valuation_point import ValuationPoint


class PrivateProxies:
    """Compute the figures a company without published accounts makes public, as dated series.

    Attributes:
        BILLION (ClassVar[float]): The factor of a valuation in billions.
        USD (ClassVar[str]): The currency of the valuations.
        DATED (ClassVar[Dict[CompanyIndicator, FinancialMetric]]): The indicators read as dated points, by line.
        points (IndicatorPoints): Builds the points.
        logger (Logger): The calculator logger.

    Notes:
        - The employees, the revenue run-rates and the funding rounds are dated points (the day the company stated
          them). The rounds are also added up per calendar year (`funding-raised`, dated the 31st of December) and
          since the creation (`funding-total`, at each round), the rounds in another currency than the first one
          left out of the totals (logged).
        - The valuations come from the markets catalogue (a funding round, an acquisition, an IPO), in US dollars,
          dated by the first day of their partial date: they are not copied into the statements.
    """

    BILLION: ClassVar[float] = 1e9
    USD: ClassVar[str] = "USD"
    DATED: ClassVar[Dict[CompanyIndicator, FinancialMetric]] = {
        CompanyIndicator.EMPLOYEES: FinancialMetric.EMPLOYEES,
        CompanyIndicator.REVENUE_RUN_RATE: FinancialMetric.REVENUE_RUN_RATE,
    }

    def __init__(self, points: IndicatorPoints, logger: Optional[Logger] = None) -> None:
        """Initialize the calculator.

        Args:
            points (IndicatorPoints): Builds the points.
            logger (Optional[Logger]): The calculator logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.points = points

    ############################
    # Internal Helpers Methods #
    ############################

    def _day(self, partial: str) -> date:
        """Get the first day of a partial date.

        Args:
            partial (str): `YYYY`, `YYYY-MM` or `YYYY-MM-DD`.

        Returns:
            date: Its first day.
        """
        parts = [int(part) for part in partial.split("-")]
        return date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)

    def _funding(self, company: str, book: FinancialBook) -> List[IndicatorValue]:
        """Add up the funding rounds per calendar year and since the creation.

        Args:
            company (str): The company.
            book (FinancialBook): Its statement lines (the rounds as dated balances).

        Returns:
            List[IndicatorValue]: The yearly and cumulative points.
        """
        rounds = book.balances.get(FinancialMetric.FUNDING_RAISED, [])
        if not rounds:
            return []
        currency = rounds[0][1][1]
        found: List[IndicatorValue] = []
        yearly: Dict[int, float] = {}
        total = 0.0
        for day, (value, round_currency, source) in rounds:
            if round_currency != currency:
                self.logger.warning("%s round of %s in %s left out of the totals.", company, day, round_currency)
                continue
            total += value
            yearly[day.year] = yearly.get(day.year, 0.0) + value
            inputs = self.points.inputs("sum of the funding rounds so far", [source])
            found.append(
                self.points.point(
                    company,
                    CompanyIndicator.FUNDING_TOTAL,
                    FinancialGranularity.INSTANT,
                    day,
                    total,
                    IndicatorUnit.CURRENCY,
                    inputs,
                    currency,
                )
            )
        for year, value in sorted(yearly.items()):
            found.append(
                self.points.point(
                    company,
                    CompanyIndicator.FUNDING_RAISED,
                    FinancialGranularity.YEAR,
                    date(year, 12, 31),
                    value,
                    IndicatorUnit.CURRENCY,
                    "sum of the funding rounds of the year",
                    currency,
                )
            )
        return found

    ############################
    # Publicly Exposed Methods #
    ############################

    def compute(self, company: str, book: FinancialBook, valuations: Sequence[ValuationPoint]) -> List[IndicatorValue]:
        """Compute the dated series of a company: employees, run-rates, funding, valuations.

        Args:
            company (str): The company.
            book (FinancialBook): Its statement lines.
            valuations (Sequence[ValuationPoint]): The valuations of the markets catalogue (any company).

        Returns:
            List[IndicatorValue]: The points of the series.
        """
        found: List[IndicatorValue] = []
        for indicator, metric in self.DATED.items():
            unit = IndicatorUnit.COUNT if metric is FinancialMetric.EMPLOYEES else IndicatorUnit.CURRENCY
            for day, (value, currency, source) in book.balances.get(metric, []):
                inputs = self.points.inputs(metric.value, [source])
                found.append(
                    self.points.point(
                        company, indicator, FinancialGranularity.INSTANT, day, value, unit, inputs, currency
                    )
                )
        found += self._funding(company, book)
        for valuation in valuations:
            if valuation.company != company:
                continue
            inputs = self.points.inputs(f"{valuation.kind.value}: {valuation.label}", [valuation.source])
            found.append(
                self.points.point(
                    company,
                    CompanyIndicator.VALUATION,
                    FinancialGranularity.INSTANT,
                    self._day(valuation.date),
                    valuation.value_bn * self.BILLION,
                    IndicatorUnit.CURRENCY,
                    inputs,
                    self.USD,
                )
            )
        if found:
            self.logger.debug("%s: %d dated points (employees, funding, valuations).", company, len(found))
        return found
