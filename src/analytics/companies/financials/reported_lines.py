from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

# First Party Imports.
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import FigureScale, FinancialGranularity, FinancialMetric, FinancialNature, FinancialSource
from models.companies.figures.reported_company import ReportedCompany
from models.companies.figures.reported_event import ReportedEvent
from models.companies.figures.reported_year import ReportedYear
from models.companies.values.financial_value import FinancialValue

type EventKey = Tuple[FinancialMetric, date]


class ReportedLines:
    """Turn the figures researched by hand (`data/curated/figures.json`) into stored statement lines.

    Attributes:
        SCALES (ClassVar[Dict[FigureScale, float]]): The factor of each scale.
        COUNTS (ClassVar[Tuple[FinancialMetric, ...]]): The lines counting people, never scaled nor in a currency.
        EVENT_NATURES (ClassVar[Tuple[FinancialMetric, ...]]): The lines dated by their event (a balance at a date).
        FISCAL_PERIOD (ClassVar[str]): The fiscal period of a researched fiscal year.
        concepts (FinancialConcepts): How the statement lines are read (their nature).
        logger (Logger): The converter logger.

    Notes:
        - A fiscal year's flows are yearly lines ending on its last day (the stated one, else the company's usual
          fiscal year end), its balances are dated that day.
        - An event is dated by the first day of its partial date (`2023-01` is the 1st of January). Two rounds of
          the same day are added up (one funding line per day), the other events of a day keep the last one.
        - The concept of a researched line is its basis (`annual-report`, `estimate`…): the indicators name it in
          their inputs, so an estimate stays recognisable.
    """

    SCALES: ClassVar[Dict[FigureScale, float]] = {
        FigureScale.UNITS: 1.0,
        FigureScale.THOUSANDS: 1e3,
        FigureScale.MILLIONS: 1e6,
        FigureScale.BILLIONS: 1e9,
    }
    COUNTS: ClassVar[Tuple[FinancialMetric, ...]] = (FinancialMetric.EMPLOYEES,)
    EVENT_NATURES: ClassVar[Tuple[FinancialMetric, ...]] = (
        FinancialMetric.EMPLOYEES,
        FinancialMetric.FUNDING_RAISED,
        FinancialMetric.REVENUE_RUN_RATE,
    )
    FISCAL_PERIOD: ClassVar[str] = "FY"

    def __init__(self, concepts: FinancialConcepts, logger: Optional[Logger] = None) -> None:
        """Initialize the converter.

        Args:
            concepts (FinancialConcepts): How the statement lines are read.
            logger (Optional[Logger]): The converter logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.concepts = concepts

    ############################
    # Internal Helpers Methods #
    ############################

    def _period_end(self, company: ReportedCompany, year: ReportedYear) -> date:
        """Get the last day of a researched fiscal year.

        Args:
            company (ReportedCompany): The company (its usual fiscal year end).
            year (ReportedYear): The fiscal year.

        Returns:
            date: The stated last day, else the usual one in the fiscal year (the 28th for a 29 February).
        """
        if year.period_end is not None:
            return year.period_end
        month, day = (int(part) for part in company.fiscal_year_end.split("-"))
        if (month, day) == (2, 29):
            try:
                return date(year.fiscal_year, 2, 29)
            except ValueError:
                return date(year.fiscal_year, 2, 28)
        return date(year.fiscal_year, month, day)

    def _event_day(self, event: ReportedEvent) -> date:
        """Get the day of an event: the first day of its partial date.

        Args:
            event (ReportedEvent): The event.

        Returns:
            date: Its day.
        """
        parts = [int(part) for part in event.date.split("-")]
        return date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)

    def _amount(self, company: ReportedCompany, metric: FinancialMetric, value: float) -> float:
        """Scale a researched amount (a count of people is not scaled).

        Args:
            company (ReportedCompany): The company (its scale).
            metric (FinancialMetric): The line.
            value (float): The figure, as written.

        Returns:
            float: The figure in units.
        """
        return value if metric in self.COUNTS else value * self.SCALES[company.scale]

    def _year_lines(self, company: ReportedCompany, year: ReportedYear) -> List[FinancialValue]:
        """Build the lines of a researched fiscal year.

        Args:
            company (ReportedCompany): The company.
            year (ReportedYear): The fiscal year.

        Returns:
            List[FinancialValue]: A yearly line per flow, a dated line per balance.
        """
        end = self._period_end(company, year)
        lines: List[FinancialValue] = []
        for metric, raw in year.figures.items():
            nature = self.concepts.nature(metric)
            instant = metric in self.EVENT_NATURES or nature is not FinancialNature.FLOW
            lines.append(
                FinancialValue(
                    company=company.company,
                    metric=metric,
                    period_end=end,
                    granularity=FinancialGranularity.INSTANT if instant else FinancialGranularity.YEAR,
                    source=FinancialSource.REPORTED,
                    value=self._amount(company, metric, raw),
                    currency=None if metric in self.COUNTS else company.currency,
                    concept=year.basis.value,
                    fiscal_year=year.fiscal_year,
                    fiscal_period=self.FISCAL_PERIOD,
                    filed=year.published,
                    source_url=year.source,
                    note=year.note,
                )
            )
        return lines

    def _event_lines(self, company: ReportedCompany) -> List[FinancialValue]:
        """Build the lines of a company's events, the rounds of a same day added up.

        Args:
            company (ReportedCompany): The company.

        Returns:
            List[FinancialValue]: A dated line per line and day.
        """
        lines: Dict[EventKey, FinancialValue] = {}
        for event in company.events:
            day = self._event_day(event)
            key = (event.metric, day)
            value = self._amount(company, event.metric, event.value)
            known = lines.get(key)
            if known is not None and event.metric is FinancialMetric.FUNDING_RAISED:
                value += known.value
            lines[key] = FinancialValue(
                company=company.company,
                metric=event.metric,
                period_end=day,
                granularity=FinancialGranularity.INSTANT,
                source=FinancialSource.REPORTED,
                value=value,
                currency=None if event.metric in self.COUNTS else (event.currency or company.currency),
                concept=event.basis.value,
                source_url=event.source,
                note=event.note,
            )
        return list(lines.values())

    ############################
    # Publicly Exposed Methods #
    ############################

    def lines(self, company: ReportedCompany) -> List[FinancialValue]:
        """Build every stored line of a researched company.

        Args:
            company (ReportedCompany): The company's researched figures.

        Returns:
            List[FinancialValue]: Its lines (fiscal years, then events).
        """
        lines = [line for year in company.years for line in self._year_lines(company, year)]
        lines += self._event_lines(company)
        if not lines:
            self.logger.warning("No researched figure for %s.", company.company)
        self.logger.debug(
            "%s: %d researched lines (%d fiscal years, %d events).",
            company.company,
            len(lines),
            len(company.years),
            len(company.events),
        )
        return lines
