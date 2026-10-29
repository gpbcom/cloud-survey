from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# First Party Imports.
from analytics.companies.health.indicator_points import IndicatorPoints
from analytics.companies.indicators.financial_book import FinancialBook
from models.companies.enums import (
    CompanyIndicator,
    FinancialGranularity,
    FinancialMetric,
    IndicatorUnit,
    StatementKind,
)
from models.companies.values.indicator_value import IndicatorValue

type Test = Tuple[str, Optional[bool]]


class PiotroskiScore:
    """Compute the Piotroski F-score of a company: nine yearly tests of profitability, leverage and efficiency.

    Attributes:
        LONG_DEBT (ClassVar[Tuple[FinancialMetric, ...]]): The lines adding up to the long-term debt.
        YEAR (ClassVar[FinancialGranularity]): The period scored.
        points (IndicatorPoints): Builds the points.
        logger (Logger): The calculator logger.

    Notes:
        - The tests of a fiscal year t (one point each): positive return on assets (net income over the assets of
          t-1), positive operating cash flow, a return on assets above that of t-1, an operating cash flow above the
          net income (both over the assets of t-1), a lower long-term debt over the average assets than in t-1 (both
          years without debt pass), a higher current ratio, no more shares outstanding, a higher gross margin, a
          higher asset turnover (revenue over the assets of the year before).
        - A score needs the fiscal years t, t-1 and t-2 and all nine tests: no partial score. A bank is not scored.
    """

    LONG_DEBT: ClassVar[Tuple[FinancialMetric, ...]] = (
        FinancialMetric.LONG_TERM_DEBT,
        FinancialMetric.NONCURRENT_BONDS,
    )
    YEAR: ClassVar[FinancialGranularity] = FinancialGranularity.YEAR

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

    def _flow(self, book: FinancialBook, metric: FinancialMetric, end: date) -> Optional[float]:
        """Get a flow of a fiscal year.

        Args:
            book (FinancialBook): The statement lines.
            metric (FinancialMetric): The line.
            end (date): The fiscal year end.

        Returns:
            Optional[float]: The figure, `None` when not stated.
        """
        figure = book.flow(metric, self.YEAR, end)
        return figure[0] if figure else None

    def _balance(self, book: FinancialBook, metric: FinancialMetric, day: date) -> Optional[float]:
        """Get a balance at a fiscal year end.

        Args:
            book (FinancialBook): The statement lines.
            metric (FinancialMetric): The line.
            day (date): The fiscal year end.

        Returns:
            Optional[float]: The figure, `None` when not stated.
        """
        figure = book.balance(metric, day)
        return figure[0] if figure else None

    def _greater(self, current: Optional[float], previous: Optional[float]) -> Optional[bool]:
        """Compare a figure with that of the year before.

        Args:
            current (Optional[float]): The figure of the year.
            previous (Optional[float]): The figure of the year before.

        Returns:
            Optional[bool]: Whether it rose, `None` when one lacks.
        """
        return None if current is None or previous is None else current > previous

    def _shares(self, book: FinancialBook, end: date) -> Optional[float]:
        """Get the shares at a fiscal year end: outstanding, else the diluted average of the year.

        Args:
            book (FinancialBook): The statement lines.
            end (date): The fiscal year end.

        Returns:
            Optional[float]: The shares, `None` when neither is stated.
        """
        outstanding = self._balance(book, FinancialMetric.SHARES_OUTSTANDING, end)
        return outstanding if outstanding is not None else self._flow(book, FinancialMetric.DILUTED_SHARES, end)

    def _gross_margin(self, book: FinancialBook, end: date) -> Optional[float]:
        """Get the gross margin of a fiscal year.

        Args:
            book (FinancialBook): The statement lines.
            end (date): The fiscal year end.

        Returns:
            Optional[float]: The gross profit (or revenue less cost) over the revenue, `None` when not computable.
        """
        revenue = self._flow(book, FinancialMetric.REVENUE, end)
        gross = self._flow(book, FinancialMetric.GROSS_PROFIT, end)
        cost = self._flow(book, FinancialMetric.COST_OF_REVENUE, end)
        if gross is None and revenue is not None and cost is not None:
            gross = revenue - cost
        return self.points.ratio(gross, revenue)

    def _leverage(self, book: FinancialBook, end: date, before: date) -> Optional[float]:
        """Get the long-term debt of a fiscal year end over the average assets of the year.

        Args:
            book (FinancialBook): The statement lines.
            end (date): The fiscal year end.
            before (date): The fiscal year end before.

        Returns:
            Optional[float]: The leverage, `None` when the debt or an assets figure is not stated.
        """
        debt = book.total(self.LONG_DEBT, end)
        assets, opening = (
            self._balance(book, FinancialMetric.TOTAL_ASSETS, end),
            self._balance(book, FinancialMetric.TOTAL_ASSETS, before),
        )
        if debt is None or assets is None or opening is None:
            return None
        return self.points.ratio(debt[0], (assets + opening) / 2)

    def _tests(self, book: FinancialBook, end: date, before: date, earlier: date) -> List[Test]:
        """Run the nine tests of a fiscal year.

        Args:
            book (FinancialBook): The statement lines.
            end (date): The fiscal year end (t).
            before (date): The fiscal year end before (t-1).
            earlier (date): The fiscal year end two years before (t-2).

        Returns:
            List[Test]: The name and the outcome of each test (`None` when not computable).
        """
        assets_before = self._balance(book, FinancialMetric.TOTAL_ASSETS, before)
        assets_earlier = self._balance(book, FinancialMetric.TOTAL_ASSETS, earlier)
        income = self._flow(book, FinancialMetric.NET_INCOME, end)
        income_before = self._flow(book, FinancialMetric.NET_INCOME, before)
        cash_flow = self._flow(book, FinancialMetric.OPERATING_CASH_FLOW, end)
        roa = self.points.ratio(income, assets_before)
        roa_before = self.points.ratio(income_before, assets_earlier)
        accruals = self.points.ratio(cash_flow, assets_before)
        leverage, leverage_before = self._leverage(book, end, before), self._leverage(book, before, earlier)
        if leverage is None or leverage_before is None:
            lower_debt = None
        else:
            lower_debt = leverage < leverage_before or leverage == leverage_before == 0
        current = self.points.ratio(
            self._balance(book, FinancialMetric.CURRENT_ASSETS, end),
            self._balance(book, FinancialMetric.CURRENT_LIABILITIES, end),
        )
        current_before = self.points.ratio(
            self._balance(book, FinancialMetric.CURRENT_ASSETS, before),
            self._balance(book, FinancialMetric.CURRENT_LIABILITIES, before),
        )
        shares, shares_before = self._shares(book, end), self._shares(book, before)
        turnover = self.points.ratio(self._flow(book, FinancialMetric.REVENUE, end), assets_before)
        turnover_before = self.points.ratio(self._flow(book, FinancialMetric.REVENUE, before), assets_earlier)
        return [
            ("ROA>0", None if roa is None else roa > 0),
            ("CFO>0", None if cash_flow is None else cash_flow > 0),
            ("dROA>0", self._greater(roa, roa_before)),
            ("CFO>NI", self._greater(accruals, roa)),
            ("dLeverage<0", lower_debt),
            ("dCurrent>0", self._greater(current, current_before)),
            ("noDilution", None if shares is None or shares_before is None else shares <= shares_before),
            ("dGM>0", self._greater(self._gross_margin(book, end), self._gross_margin(book, before))),
            ("dTurnover>0", self._greater(turnover, turnover_before)),
        ]

    ############################
    # Publicly Exposed Methods #
    ############################

    def compute(
        self, company: str, book: FinancialBook, statements: StatementKind = StatementKind.INDUSTRIAL
    ) -> List[IndicatorValue]:
        """Compute the F-score of a company for every fiscal year whose nine tests can all be run.

        Args:
            company (str): The company.
            book (FinancialBook): Its statement lines.
            statements (StatementKind): The shape of its statements (a bank is not scored).

        Returns:
            List[IndicatorValue]: The points of the score.
        """
        if statements is StatementKind.BANK:
            self.logger.info("%s is a bank: no Piotroski score.", company)
            return []
        found: List[IndicatorValue] = []
        for end in book.ends(self.YEAR, [FinancialMetric.REVENUE, FinancialMetric.NET_INCOME]):
            before = book.year_before(end, self.YEAR)
            earlier = book.year_before(before, self.YEAR) if before else None
            if before is None or earlier is None:
                continue
            tests = self._tests(book, end, before, earlier)
            if any(outcome is None for _, outcome in tests):
                continue
            score = float(sum(1 for _, outcome in tests if outcome))
            inputs = " ".join(f"{'+' if outcome else '-'}{name}" for name, outcome in tests)
            found.append(
                self.points.point(
                    company, CompanyIndicator.PIOTROSKI_F, self.YEAR, end, score, IndicatorUnit.SCORE, inputs
                )
            )
        self.logger.debug("%s: %d Piotroski score points.", company, len(found))
        return found
