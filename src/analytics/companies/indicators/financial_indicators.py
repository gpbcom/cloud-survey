from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

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


class FinancialIndicators:
    """Compute the wealth and research effort indicators of a company from its statement lines, period by period.

    Attributes:
        PERIODS (ClassVar[Tuple[FinancialGranularity, ...]]): The periods the flows are measured over.
        ANCHORS (ClassVar[Tuple[FinancialMetric, ...]]): The flows whose periods make the time axis.
        HUNDRED (ClassVar[float]): The factor of a percentage.
        BANK_SKIPPED (ClassVar[Tuple[CompanyIndicator, ...]]): The indicators a bank's statements do not support (no
            current assets, no cost of revenue).
        rates (CurrencyRates): Converts the amounts into US dollars.
        points (IndicatorPoints): Builds the points.
        logger (Logger): The calculator logger.

    Notes:
        - Every indicator is a time series: one point per quarter, per fiscal year and per trailing twelve months
          (TTM, the four quarters ending on a quarter end) wherever its inputs are stated.
        - The returns (ROE, ROA, ROIC) and the leverage on the EBITDA need a year of flow: they are measured on the
          fiscal years and the trailing twelve months only, over the average of the opening and closing balances
          when both are stated.
        - The ROIC is the operating income after the period's effective tax rate (income tax over pretax income)
          over the invested capital (equity plus debt less cash). Without a tax rate it is not computed.
        - The R&D return is the revenue growth over a year divided by the research expense of the year before.
        - A ratio whose denominator is zero or negative (a negative equity) is left out.
        - The interest coverage keeps a negative operating income (a loss covers no interest). The cash conversion
          and the payout ratio need a positive net income. The payout ratio counts the dividends and the
          repurchases stated (one of them is enough).
    """

    PERIODS: ClassVar[Tuple[FinancialGranularity, ...]] = (
        FinancialGranularity.QUARTER,
        FinancialGranularity.YEAR,
        FinancialGranularity.TTM,
    )
    ANCHORS: ClassVar[Tuple[FinancialMetric, ...]] = (
        FinancialMetric.REVENUE,
        FinancialMetric.NET_INCOME,
        FinancialMetric.OPERATING_INCOME,
    )
    HUNDRED: ClassVar[float] = 100.0
    BANK_SKIPPED: ClassVar[Tuple[CompanyIndicator, ...]] = (
        CompanyIndicator.GROSS_MARGIN,
        CompanyIndicator.CURRENT_RATIO,
        CompanyIndicator.QUICK_RATIO,
        CompanyIndicator.WORKING_CAPITAL,
    )

    def __init__(self, rates: CurrencyRates, logger: Optional[Logger] = None) -> None:
        """Initialize the calculator.

        Args:
            rates (CurrencyRates): Converts the amounts into US dollars.
            logger (Optional[Logger]): The calculator logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.rates = rates
        self.points = IndicatorPoints(rates, logger=self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _point(
        self,
        company: str,
        indicator: CompanyIndicator,
        granularity: FinancialGranularity,
        end: date,
        value: float,
        unit: IndicatorUnit,
        inputs: str,
        currency: Optional[str] = None,
    ) -> IndicatorValue:
        """Build a point of a series.

        Args:
            company (str): The company.
            indicator (CompanyIndicator): The indicator.
            granularity (FinancialGranularity): The period.
            end (date): The period end.
            value (float): The value.
            unit (IndicatorUnit): The unit.
            inputs (str): How it was computed.
            currency (Optional[str]): The currency of an amount.

        Returns:
            IndicatorValue: The point, an amount also in US dollars when a rate is stored.
        """
        return self.points.point(company, indicator, granularity, end, value, unit, inputs, currency)

    def _ratio(self, numerator: Optional[float], denominator: Optional[float], factor: float = 1.0) -> Optional[float]:
        """Divide two figures, only over a positive denominator.

        Args:
            numerator (Optional[float]): The numerator.
            denominator (Optional[float]): The denominator.
            factor (float): The factor of the result (100 for a percentage).

        Returns:
            Optional[float]: The ratio, `None` when a figure lacks or the denominator is not positive.
        """
        return self.points.ratio(numerator, denominator, factor)

    def _flows(
        self, company: str, book: FinancialBook, granularity: FinancialGranularity, end: date
    ) -> List[IndicatorValue]:
        """Compute the flow indicators of a period: the amounts, the margins and the research intensity.

        Args:
            company (str): The company.
            book (FinancialBook): The statement lines.
            granularity (FinancialGranularity): The period.
            end (date): The period end.

        Returns:
            List[IndicatorValue]: The points of the period.
        """
        points: List[IndicatorValue] = []
        amounts = {
            CompanyIndicator.REVENUE: book.flow(FinancialMetric.REVENUE, granularity, end),
            CompanyIndicator.NET_INCOME: book.flow(FinancialMetric.NET_INCOME, granularity, end),
            CompanyIndicator.OPERATING_INCOME: book.flow(FinancialMetric.OPERATING_INCOME, granularity, end),
            CompanyIndicator.EBITDA: book.ebitda(granularity, end),
            CompanyIndicator.RD_EXPENSE: book.flow(FinancialMetric.RD_EXPENSE, granularity, end),
            CompanyIndicator.CAPITALISED_DEVELOPMENT: book.flow(
                FinancialMetric.CAPITALISED_DEVELOPMENT, granularity, end
            ),
            CompanyIndicator.FREE_CASH_FLOW: book.free_cash_flow(granularity, end),
        }
        for indicator, figure in amounts.items():
            if figure is not None:
                points.append(
                    self._point(
                        company, indicator, granularity, end, figure[0], IndicatorUnit.CURRENCY, figure[2], figure[1]
                    )
                )
        revenue = amounts[CompanyIndicator.REVENUE]
        sales = revenue[0] if revenue else None
        gross = book.flow(FinancialMetric.GROSS_PROFIT, granularity, end)
        cost = book.flow(FinancialMetric.COST_OF_REVENUE, granularity, end)
        gross_profit = gross[0] if gross else (sales - cost[0] if sales is not None and cost else None)
        operating, net, research = (
            amounts[CompanyIndicator.OPERATING_INCOME],
            amounts[CompanyIndicator.NET_INCOME],
            amounts[CompanyIndicator.RD_EXPENSE],
        )
        ratios = {
            CompanyIndicator.GROSS_MARGIN: (self._ratio(gross_profit, sales, self.HUNDRED), "gross-profit / revenue"),
            CompanyIndicator.OPERATING_MARGIN: (
                self._ratio(operating[0] if operating else None, sales, self.HUNDRED),
                "operating-income / revenue",
            ),
            CompanyIndicator.NET_MARGIN: (
                self._ratio(net[0] if net else None, sales, self.HUNDRED),
                "net-income / revenue",
            ),
            CompanyIndicator.RD_INTENSITY: (
                self._ratio(research[0] if research else None, sales, self.HUNDRED),
                "rd-expense / revenue",
            ),
        }
        free = amounts[CompanyIndicator.FREE_CASH_FLOW]
        ratios[CompanyIndicator.CASH_CONVERSION] = (
            self._ratio(free[0] if free else None, net[0] if net else None, self.HUNDRED),
            "free-cash-flow / net-income",
        )
        for indicator, (value, inputs) in ratios.items():
            if value is not None:
                points.append(self._point(company, indicator, granularity, end, value, IndicatorUnit.PERCENT, inputs))
        interest = book.flow(FinancialMetric.INTEREST_EXPENSE, granularity, end)
        coverage = self._ratio(operating[0] if operating else None, interest[0] if interest else None)
        if coverage is not None:
            points.append(
                self._point(
                    company,
                    CompanyIndicator.INTEREST_COVERAGE,
                    granularity,
                    end,
                    coverage,
                    IndicatorUnit.RATIO,
                    "operating-income / interest-expense",
                )
            )
        return points

    def _returns(
        self, company: str, book: FinancialBook, granularity: FinancialGranularity, end: date
    ) -> List[IndicatorValue]:
        """Compute the indicators needing a year of flow: ROE, ROA, ROIC, net debt to EBITDA and R&D return.

        Args:
            company (str): The company.
            book (FinancialBook): The statement lines.
            granularity (FinancialGranularity): A fiscal year or the trailing twelve months.
            end (date): The period end.

        Returns:
            List[IndicatorValue]: The points of the period.
        """
        points: List[IndicatorValue] = []
        net = book.flow(FinancialMetric.NET_INCOME, granularity, end)
        income = net[0] if net else None
        equity = book.average(FinancialMetric.TOTAL_EQUITY, end)
        assets = book.average(FinancialMetric.TOTAL_ASSETS, end)
        values = {
            CompanyIndicator.ROE: (self._ratio(income, equity, self.HUNDRED), "net-income / avg(total-equity)"),
            CompanyIndicator.ROA: (self._ratio(income, assets, self.HUNDRED), "net-income / avg(total-assets)"),
        }
        operating = book.flow(FinancialMetric.OPERATING_INCOME, granularity, end)
        tax = book.flow(FinancialMetric.INCOME_TAX, granularity, end)
        pretax = book.flow(FinancialMetric.PRETAX_INCOME, granularity, end)
        rate = self._ratio(tax[0] if tax else None, pretax[0] if pretax else None)
        debt, cash, closing = (
            book.debt(end),
            book.cash(end),
            book.balance(FinancialMetric.TOTAL_EQUITY, end),
        )
        if operating and rate is not None and 0 <= rate <= 1 and closing:
            invested = closing[0] + (debt[0] if debt else 0.0) - (cash[0] if cash else 0.0)
            values[CompanyIndicator.ROIC] = (
                self._ratio(operating[0] * (1 - rate), invested, self.HUNDRED),
                "operating-income * (1 - tax rate) / (equity + debt - cash)",
            )
        ebitda = book.ebitda(granularity, end)
        if debt is not None:
            net_debt = debt[0] - (cash[0] if cash else 0.0)
            values[CompanyIndicator.NET_DEBT_TO_EBITDA] = (
                self._ratio(net_debt, ebitda[0] if ebitda else None),
                "net-debt / ebitda",
            )
        before = book.year_before(end, granularity)
        revenue = book.flow(FinancialMetric.REVENUE, granularity, end)
        if before is not None and revenue:
            previous = book.flow(FinancialMetric.REVENUE, granularity, before)
            research = book.flow(FinancialMetric.RD_EXPENSE, granularity, before)
            growth = revenue[0] - previous[0] if previous else None
            values[CompanyIndicator.RD_RETURN] = (
                self._ratio(growth, research[0] if research else None),
                "revenue growth / rd-expense of the year before",
            )
        dividends = book.flow(FinancialMetric.DIVIDENDS_PAID, granularity, end)
        buybacks = book.flow(FinancialMetric.BUYBACKS, granularity, end)
        if dividends or buybacks:
            paid = (dividends[0] if dividends else 0.0) + (buybacks[0] if buybacks else 0.0)
            stated = [name for name, figure in (("dividends-paid", dividends), ("buybacks", buybacks)) if figure]
            values[CompanyIndicator.PAYOUT_RATIO] = (
                self._ratio(paid, income, self.HUNDRED),
                f"({' + '.join(stated)}) / net-income",
            )
        for indicator, (value, inputs) in values.items():
            if value is not None:
                unit = (
                    IndicatorUnit.RATIO
                    if indicator in (CompanyIndicator.NET_DEBT_TO_EBITDA, CompanyIndicator.RD_RETURN)
                    else IndicatorUnit.PERCENT
                )
                points.append(self._point(company, indicator, granularity, end, value, unit, inputs))
        return points

    def _balances(
        self, company: str, book: FinancialBook, granularity: FinancialGranularity, end: date
    ) -> List[IndicatorValue]:
        """Compute the balance indicators at a period end: size, cash, debt, leverage and liquidity.

        Args:
            company (str): The company.
            book (FinancialBook): The statement lines.
            granularity (FinancialGranularity): The period whose end it is (a quarter or a year).
            end (date): The period end.

        Returns:
            List[IndicatorValue]: The points at the period end.
        """
        points: List[IndicatorValue] = []
        assets, equity = (
            book.balance(FinancialMetric.TOTAL_ASSETS, end),
            book.balance(FinancialMetric.TOTAL_EQUITY, end),
        )
        cash, debt = book.cash(end), book.debt(end)
        amounts = {
            CompanyIndicator.TOTAL_ASSETS: assets,
            CompanyIndicator.TOTAL_EQUITY: equity,
            CompanyIndicator.CASH: cash,
            CompanyIndicator.TOTAL_DEBT: debt,
        }
        if debt is not None:
            amounts[CompanyIndicator.NET_DEBT] = (debt[0] - (cash[0] if cash else 0.0), debt[1], "total-debt - cash")
        for indicator, figure in amounts.items():
            if figure is not None:
                points.append(
                    self._point(
                        company, indicator, granularity, end, figure[0], IndicatorUnit.CURRENCY, figure[2], figure[1]
                    )
                )
        current_assets = book.balance(FinancialMetric.CURRENT_ASSETS, end)
        current_liabilities = book.balance(FinancialMetric.CURRENT_LIABILITIES, end)
        if current_assets and current_liabilities and current_assets[1] == current_liabilities[1]:
            points.append(
                self._point(
                    company,
                    CompanyIndicator.WORKING_CAPITAL,
                    granularity,
                    end,
                    current_assets[0] - current_liabilities[0],
                    IndicatorUnit.CURRENCY,
                    "current-assets - current-liabilities",
                    current_assets[1],
                )
            )
        inventory = book.balance(FinancialMetric.INVENTORY, end)
        liabilities = current_liabilities[0] if current_liabilities else None
        quick = current_assets[0] - (inventory[0] if inventory else 0.0) if current_assets else None
        ratios = {
            CompanyIndicator.DEBT_TO_EQUITY: (
                self._ratio(debt[0] if debt else None, equity[0] if equity else None),
                "total-debt / total-equity",
            ),
            CompanyIndicator.CURRENT_RATIO: (
                self._ratio(current_assets[0] if current_assets else None, liabilities),
                "current-assets / current-liabilities",
            ),
            CompanyIndicator.QUICK_RATIO: (
                self._ratio(quick, liabilities),
                "(current-assets - inventory) / current-liabilities",
            ),
        }
        for indicator, (value, inputs) in ratios.items():
            if value is not None:
                points.append(self._point(company, indicator, granularity, end, value, IndicatorUnit.RATIO, inputs))
        return points

    ############################
    # Publicly Exposed Methods #
    ############################

    def compute(
        self, company: str, book: FinancialBook, statements: StatementKind = StatementKind.INDUSTRIAL
    ) -> List[IndicatorValue]:
        """Compute every financial indicator of a company over every period its statements state.

        Args:
            company (str): The company.
            book (FinancialBook): Its statement lines.
            statements (StatementKind): The shape of its statements (a bank's skip the liquidity ratios and the gross
                margin).

        Returns:
            List[IndicatorValue]: The points of every series.
        """
        points: Dict[Tuple[CompanyIndicator, FinancialGranularity, date], IndicatorValue] = {}
        for granularity in self.PERIODS:
            base = (
                FinancialGranularity.YEAR if granularity is FinancialGranularity.YEAR else FinancialGranularity.QUARTER
            )
            for end in book.ends(base, self.ANCHORS):
                found = self._flows(company, book, granularity, end)
                if granularity is not FinancialGranularity.QUARTER:
                    found += self._returns(company, book, granularity, end)
                if granularity is not FinancialGranularity.TTM:
                    found += self._balances(company, book, granularity, end)
                for point in found:
                    if statements is StatementKind.BANK and point.indicator in self.BANK_SKIPPED:
                        continue
                    points[(point.indicator, point.granularity, point.period_end)] = point
        self.logger.info("%s: %d financial indicator points.", company, len(points))
        return list(points.values())
