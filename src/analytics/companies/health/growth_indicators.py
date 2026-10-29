from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

# First Party Imports.
from analytics.companies.health.indicator_points import IndicatorPoints
from analytics.companies.indicators.financial_book import FinancialBook
from models.companies.enums import CompanyIndicator, FinancialGranularity, FinancialMetric, IndicatorUnit
from models.companies.values.indicator_value import IndicatorValue


class GrowthIndicators:
    """Compute how fast a company's revenue, net income and research expense grow, year over year.

    Attributes:
        PERIODS (ClassVar[Tuple[FinancialGranularity, ...]]): The periods compared (a quarter with the same quarter
            a year before, a fiscal year, the trailing twelve months).
        GROWTHS (ClassVar[Dict[CompanyIndicator, FinancialMetric]]): The line each growth measures.
        HUNDRED (ClassVar[float]): The factor of a percentage.
        points (IndicatorPoints): Builds the points.
        logger (Logger): The calculator logger.

    Notes:
        A growth needs the same period a year before (340 to 390 days earlier), in the same currency, with a positive
        value: a growth from a loss means nothing, a currency change would read as growth.
    """

    PERIODS: ClassVar[Tuple[FinancialGranularity, ...]] = (
        FinancialGranularity.QUARTER,
        FinancialGranularity.YEAR,
        FinancialGranularity.TTM,
    )
    GROWTHS: ClassVar[Dict[CompanyIndicator, FinancialMetric]] = {
        CompanyIndicator.REVENUE_GROWTH: FinancialMetric.REVENUE,
        CompanyIndicator.NET_INCOME_GROWTH: FinancialMetric.NET_INCOME,
        CompanyIndicator.RD_GROWTH: FinancialMetric.RD_EXPENSE,
    }
    HUNDRED: ClassVar[float] = 100.0

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

    def _growth(
        self,
        company: str,
        book: FinancialBook,
        indicator: CompanyIndicator,
        granularity: FinancialGranularity,
        end: date,
    ) -> Optional[IndicatorValue]:
        """Compute a growth over the year ending at a period end.

        Args:
            company (str): The company.
            book (FinancialBook): Its statement lines.
            indicator (CompanyIndicator): The growth.
            granularity (FinancialGranularity): The period.
            end (date): The period end.

        Returns:
            Optional[IndicatorValue]: The point, `None` when the period a year before lacks, is not positive or is
                in another currency.
        """
        metric = self.GROWTHS[indicator]
        before = book.year_before(end, granularity)
        current = book.flow(metric, granularity, end)
        previous = book.flow(metric, granularity, before) if before else None
        if current is None or previous is None or current[1] != previous[1]:
            return None
        value = self.points.ratio(current[0] - previous[0], previous[0], self.HUNDRED)
        if value is None:
            return None
        formula = f"({metric.value} - {metric.value} a year before) / {metric.value} a year before"
        inputs = self.points.inputs(formula, [current[2], previous[2]])
        return self.points.point(company, indicator, granularity, end, value, IndicatorUnit.PERCENT, inputs)

    ############################
    # Publicly Exposed Methods #
    ############################

    def compute(self, company: str, book: FinancialBook) -> List[IndicatorValue]:
        """Compute the growths of a company over every period its statements state twice a year apart.

        Args:
            company (str): The company.
            book (FinancialBook): Its statement lines.

        Returns:
            List[IndicatorValue]: The points of the growth series.
        """
        found: List[IndicatorValue] = []
        for granularity in self.PERIODS:
            base = (
                FinancialGranularity.YEAR if granularity is FinancialGranularity.YEAR else FinancialGranularity.QUARTER
            )
            for indicator, metric in self.GROWTHS.items():
                for end in book.ends(base, [metric]):
                    point = self._growth(company, book, indicator, granularity, end)
                    if point is not None:
                        found.append(point)
        self.logger.debug("%s: %d growth points.", company, len(found))
        return found
