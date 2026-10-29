from __future__ import annotations

# Standard Library Imports.
import bisect
from datetime import date, timedelta
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Set, Tuple

# First Party Imports.
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import FinancialGranularity, FinancialMetric, FinancialNature, FinancialSource
from models.companies.values.financial_value import FinancialValue

type Figure = Tuple[float, Optional[str], str]


class FinancialBook:
    """The statement lines of a company, one per line and period: SEC filings, Google Finance, researched figures.

    Attributes:
        NATURES (ClassVar[Dict[FinancialMetric, FinancialNature]]): The nature of the lines no XBRL concept maps (only
            Google Finance or the researched figures state them).
        SOURCES (ClassVar[Tuple[FinancialSource, ...]]): The sources in the order they fill (the last one wins).
        FILED (ClassVar[Tuple[FinancialSource, ...]]): The sources of filed figures, which a researched figure never
            overrides.
        RECONCILE_DAYS (ClassVar[int]): The most days between a researched figure and a filed one of the same line
            for them to be the same period (a 52 or 53-week year ends a few days off the calendar).
        QUARTER_GAP (ClassVar[Tuple[int, int]]): The days between two consecutive quarter ends.
        DEBT (ClassVar[Tuple[FinancialMetric, ...]]): The lines adding up to the total debt.
        flows (Dict[Tuple[FinancialMetric, FinancialGranularity], Dict[date, Figure]]): The flows, by line and
            period (quarter or year), each figure with its currency and where it was read.
        balances (Dict[FinancialMetric, List[Tuple[date, Figure]]]): The balances of each line, by date.
        balance_days (Dict[FinancialMetric, List[date]]): The dates of the balances of each line, sorted.
        sourced (Dict[Tuple[FinancialMetric, FinancialSource], List[Tuple[date, Figure]]]): The balances of each line
            as each source states them, by date (a share count of Google Finance is per traded unit).
        logger (Logger): The book logger.

    Notes:
        - A balance read at the end of a Google quarter and a balance filed at the same date are the same balance:
          the balances are kept by date whatever the period they were read with.
        - A researched figure (`reported`) is dropped when a filed source states the same line within
          `RECONCILE_DAYS` of its date: it only fills the periods no filing covers.
    """

    NATURES: ClassVar[Dict[FinancialMetric, FinancialNature]] = {
        FinancialMetric.EBITDA: FinancialNature.FLOW,
        FinancialMetric.FREE_CASH_FLOW: FinancialNature.FLOW,
        FinancialMetric.MARKET_CAP: FinancialNature.BALANCE,
        FinancialMetric.EMPLOYEES: FinancialNature.BALANCE,
        FinancialMetric.FUNDING_RAISED: FinancialNature.BALANCE,
        FinancialMetric.REVENUE_RUN_RATE: FinancialNature.BALANCE,
    }
    SOURCES: ClassVar[Tuple[FinancialSource, ...]] = (
        FinancialSource.REPORTED,
        FinancialSource.EDGAR_FDS,
        FinancialSource.GOOGLE_FINANCE,
        FinancialSource.EDGAR,
    )
    FILED: ClassVar[Tuple[FinancialSource, ...]] = (
        FinancialSource.EDGAR_FDS,
        FinancialSource.GOOGLE_FINANCE,
        FinancialSource.EDGAR,
    )
    RECONCILE_DAYS: ClassVar[int] = 20
    QUARTER_GAP: ClassVar[Tuple[int, int]] = (80, 100)
    DEBT: ClassVar[Tuple[FinancialMetric, ...]] = (
        FinancialMetric.CURRENT_DEBT,
        FinancialMetric.LONG_TERM_DEBT,
        FinancialMetric.CURRENT_BONDS,
        FinancialMetric.NONCURRENT_BONDS,
    )

    def __init__(
        self, values: Sequence[FinancialValue], concepts: FinancialConcepts, logger: Optional[Logger] = None
    ) -> None:
        """Initialize the book.

        Args:
            values (Sequence[FinancialValue]): The stored lines of the company, every source.
            concepts (FinancialConcepts): How the lines are read (their nature).
            logger (Optional[Logger]): The book logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        values = self._reconciled(values)
        self.flows: Dict[Tuple[FinancialMetric, FinancialGranularity], Dict[date, Figure]] = {}
        dated: Dict[FinancialMetric, Dict[date, Figure]] = {}
        by_source: Dict[Tuple[FinancialMetric, FinancialSource], Dict[date, Figure]] = {}
        for source in self.SOURCES:
            for value in values:
                if value.source is not source:
                    continue
                figure = (value.value, value.currency, f"{value.source.value}:{value.concept}")
                nature = concepts.nature(value.metric) or self.NATURES.get(value.metric, FinancialNature.FLOW)
                if nature is FinancialNature.BALANCE or value.granularity is FinancialGranularity.INSTANT:
                    dated.setdefault(value.metric, {})[value.period_end] = figure
                    by_source.setdefault((value.metric, value.source), {})[value.period_end] = figure
                else:
                    self.flows.setdefault((value.metric, value.granularity), {})[value.period_end] = figure
        self.balances: Dict[FinancialMetric, List[Tuple[date, Figure]]] = {
            metric: sorted(points.items(), key=lambda point: point[0]) for metric, points in dated.items()
        }
        self.balance_days: Dict[FinancialMetric, List[date]] = {
            metric: [day for day, _ in points] for metric, points in self.balances.items()
        }
        self.sourced: Dict[Tuple[FinancialMetric, FinancialSource], List[Tuple[date, Figure]]] = {
            key: sorted(points.items(), key=lambda point: point[0]) for key, points in by_source.items()
        }
        self.logger.debug("Book of %d flow series and %d balance series.", len(self.flows), len(self.balances))

    ############################
    # Internal Helpers Methods #
    ############################

    def _reconciled(self, values: Sequence[FinancialValue]) -> List[FinancialValue]:
        """Drop the researched figures a filed source already states (the same line within a few days).

        Args:
            values (Sequence[FinancialValue]): The stored lines, every source.

        Returns:
            List[FinancialValue]: The lines, the researched ones a filing covers left out.
        """
        filed: Dict[Tuple[FinancialMetric, bool], Set[date]] = {}
        for value in values:
            if value.source in self.FILED:
                instant = value.granularity is FinancialGranularity.INSTANT
                filed.setdefault((value.metric, instant), set()).add(value.period_end)
        kept: List[FinancialValue] = []
        dropped = 0
        for value in values:
            if value.source is FinancialSource.REPORTED:
                days = filed.get((value.metric, value.granularity is FinancialGranularity.INSTANT), set())
                if any(abs((day - value.period_end).days) <= self.RECONCILE_DAYS for day in days):
                    dropped += 1
                    continue
            kept.append(value)
        if dropped:
            self.logger.debug("%d researched figures left out: a filing states them.", dropped)
        return kept

    ############################
    # Publicly Exposed Methods #
    ############################

    def ends(self, granularity: FinancialGranularity, metrics: Sequence[FinancialMetric]) -> List[date]:
        """Get the period ends of some flows.

        Args:
            granularity (FinancialGranularity): A quarter or a year.
            metrics (Sequence[FinancialMetric]): The flows whose periods count.

        Returns:
            List[date]: The period ends, sorted.
        """
        return sorted({end for metric in metrics for end in self.flows.get((metric, granularity), {})})

    def ttm(self, metric: FinancialMetric, end: date) -> Optional[Figure]:
        """Get a flow over the twelve months ending on a quarter end: its four quarters, else its fiscal year.

        Args:
            metric (FinancialMetric): The line.
            end (date): The last day of the last quarter.

        Returns:
            Optional[Figure]: The sum of the four quarters, `None` when one lacks and no fiscal year ends then.
        """
        quarters = self.flows.get((metric, FinancialGranularity.QUARTER), {})
        ends = sorted(quarters)
        chain: List[date] = []
        current: Optional[date] = end if end in quarters else None
        while current is not None and len(chain) < 4:
            chain.append(current)
            index = bisect.bisect_left(ends, current)
            previous = ends[index - 1] if index else None
            low, high = self.QUARTER_GAP
            current = previous if previous and low <= (current - previous).days <= high else None
        if len(chain) == 4:
            figures = [quarters[day] for day in chain]
            return sum(figure[0] for figure in figures), figures[0][1], f"sum of 4 quarters ({figures[0][2]})"
        return self.flows.get((metric, FinancialGranularity.YEAR), {}).get(end)

    def flow(self, metric: FinancialMetric, granularity: FinancialGranularity, end: date) -> Optional[Figure]:
        """Get a flow of a period.

        Args:
            metric (FinancialMetric): The line.
            granularity (FinancialGranularity): A quarter, a year or the trailing twelve months.
            end (date): The period end.

        Returns:
            Optional[Figure]: The figure, `None` when not stated (or, for the twelve months, when a quarter lacks).
        """
        if granularity is FinancialGranularity.TTM:
            return self.ttm(metric, end)
        return self.flows.get((metric, granularity), {}).get(end)

    def balance(self, metric: FinancialMetric, day: date, tolerance: int = 15) -> Optional[Figure]:
        """Get a balance at a day: the nearest date within the tolerance.

        Args:
            metric (FinancialMetric): The line.
            day (date): The day.
            tolerance (int): The most days between the day and the balance's date.

        Returns:
            Optional[Figure]: The figure, `None` when no balance is dated near the day.
        """
        points = self.balances.get(metric, [])
        if not points:
            return None
        index = bisect.bisect_left(self.balance_days[metric], day)
        near = [points[i] for i in (index - 1, index) if 0 <= i < len(points)]
        near = [point for point in near if abs((point[0] - day).days) <= tolerance]
        return min(near, key=lambda point: abs((point[0] - day).days))[1] if near else None

    def latest_balance(self, metric: FinancialMetric, day: date, age: int) -> Optional[Tuple[date, Figure]]:
        """Get the last balance dated on or before a day.

        Args:
            metric (FinancialMetric): The line.
            day (date): The day.
            age (int): The most days the balance may be older than the day.

        Returns:
            Optional[Tuple[date, Figure]]: Its date and figure, `None` when none is recent enough.
        """
        points = self.balances.get(metric, [])
        index = bisect.bisect_right(self.balance_days.get(metric, []), day)
        if not index:
            return None
        found = points[index - 1]
        return found if (day - found[0]) <= timedelta(days=age) else None

    def latest_sourced(
        self, metric: FinancialMetric, source: FinancialSource, day: date, age: int
    ) -> Optional[Tuple[date, Figure]]:
        """Get the last balance a source dated on or before a day.

        Args:
            metric (FinancialMetric): The line.
            source (FinancialSource): The source.
            day (date): The day.
            age (int): The most days the balance may be older than the day.

        Returns:
            Optional[Tuple[date, Figure]]: Its date and figure, `None` when the source states none recent enough.
        """
        points = self.sourced.get((metric, source), [])
        index = bisect.bisect_right([point[0] for point in points], day)
        if not index:
            return None
        found = points[index - 1]
        return found if (day - found[0]) <= timedelta(days=age) else None

    def year_before(self, end: date, granularity: FinancialGranularity) -> Optional[date]:
        """Get the period end a year before another, among the periods of the revenue.

        Args:
            end (date): The period end.
            granularity (FinancialGranularity): A year or the trailing twelve months (quarter ends).

        Returns:
            Optional[date]: The period end 340 to 390 days before, `None` when there is none.
        """
        base = FinancialGranularity.YEAR if granularity is FinancialGranularity.YEAR else FinancialGranularity.QUARTER
        candidates = [day for day in self.ends(base, [FinancialMetric.REVENUE]) if 340 <= (end - day).days <= 390]
        return candidates[-1] if candidates else None

    def total(self, metrics: Sequence[FinancialMetric], day: date) -> Optional[Figure]:
        """Add up the balances of some lines at a day.

        Args:
            metrics (Sequence[FinancialMetric]): The lines.
            day (date): The day.

        Returns:
            Optional[Figure]: The sum of those stated, `None` when none is.
        """
        figures = [figure for figure in (self.balance(metric, day) for metric in metrics) if figure]
        if not figures:
            return None
        return (
            sum(figure[0] for figure in figures),
            figures[0][1],
            " + ".join(sorted({figure[2] for figure in figures})),
        )

    def debt(self, day: date) -> Optional[Figure]:
        """Get the total debt at a day: the current and long-term debt, and the bonds the IFRS filers state apart.

        Args:
            day (date): The day.

        Returns:
            Optional[Figure]: The debt, `None` when no debt line is stated.
        """
        return self.total(self.DEBT, day)

    def cash(self, day: date) -> Optional[Figure]:
        """Get the cash at a day: the cash and equivalents plus the short-term investments.

        Args:
            day (date): The day.

        Returns:
            Optional[Figure]: The cash, `None` when the cash is not stated.
        """
        cash = self.balance(FinancialMetric.CASH, day)
        if cash is None:
            return None
        investments = self.balance(FinancialMetric.SHORT_TERM_INVESTMENTS, day)
        return cash[0] + (investments[0] if investments else 0.0), cash[1], "cash + short-term-investments"

    def average(self, metric: FinancialMetric, end: date) -> Optional[float]:
        """Get the average of the balances of a line at the end of a year and a year before.

        Args:
            metric (FinancialMetric): The line.
            end (date): The end of the year.

        Returns:
            Optional[float]: The average, the closing balance alone when the opening one is not stated.
        """
        closing = self.balance(metric, end)
        if closing is None:
            return None
        opening = self.balance(metric, end - timedelta(days=365), tolerance=30)
        return (closing[0] + opening[0]) / 2 if opening else closing[0]

    def ebitda(self, granularity: FinancialGranularity, end: date) -> Optional[Figure]:
        """Get the EBITDA of a period: the operating income plus the depreciation, else as Google states it.

        Args:
            granularity (FinancialGranularity): The period.
            end (date): The period end.

        Returns:
            Optional[Figure]: The EBITDA, `None` when neither way gives it.
        """
        operating = self.flow(FinancialMetric.OPERATING_INCOME, granularity, end)
        depreciation = self.flow(FinancialMetric.DEPRECIATION, granularity, end)
        if operating and depreciation:
            return operating[0] + depreciation[0], operating[1], "operating-income + depreciation"
        return self.flow(FinancialMetric.EBITDA, granularity, end)

    def free_cash_flow(self, granularity: FinancialGranularity, end: date) -> Optional[Figure]:
        """Get the free cash flow of a period: the operating cash flow less the capital expenditure.

        Args:
            granularity (FinancialGranularity): The period.
            end (date): The period end.

        Returns:
            Optional[Figure]: The free cash flow (Google's own when the inputs lack), `None` otherwise.
        """
        operating = self.flow(FinancialMetric.OPERATING_CASH_FLOW, granularity, end)
        capex = self.flow(FinancialMetric.CAPEX, granularity, end)
        if operating and capex:
            return operating[0] - capex[0], operating[1], "operating-cash-flow - capex"
        return self.flow(FinancialMetric.FREE_CASH_FLOW, granularity, end)

    def liabilities(self, day: date) -> Optional[Figure]:
        """Get the total liabilities at a day: as stated, else the total assets less the equity.

        Args:
            day (date): The day.

        Returns:
            Optional[Figure]: The liabilities, `None` when neither way gives them.
        """
        stated = self.balance(FinancialMetric.TOTAL_LIABILITIES, day)
        if stated is not None:
            return stated
        assets = self.balance(FinancialMetric.TOTAL_ASSETS, day)
        equity = self.balance(FinancialMetric.TOTAL_EQUITY, day)
        if assets is None or equity is None:
            return None
        return assets[0] - equity[0], assets[1], "total-assets - total-equity"
