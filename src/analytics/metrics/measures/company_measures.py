from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource, ProviderMetric
from models.drivers.facts.company_fact import CompanyFact
from models.drivers.metrics.provider_metric_value import ProviderMetricValue


class CompanyMeasures:
    """Turn the company facts of Wikidata into the age and the employees of each provider.

    Attributes:
        YEAR_DAYS (ClassVar[float]): The days of a year, for the age.
        logger (Logger): The measure logger.

    Notes:
        - The age is measured at the collection, its quarter, from the earliest founding date stated.
        - The employees are dated by the date they were counted when Wikidata states it (a series for the panel),
          else by the quarter of the collection. Two counts of a quarter keep the largest.
    """

    YEAR_DAYS: ClassVar[float] = 365.25

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the measure.

        Args:
            logger (Optional[Logger]): The measure logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _quarter(self, moment: datetime) -> str:
        """Write the quarter of a date.

        Args:
            moment (datetime): The date.

        Returns:
            str: Its quarter, written `YYYYQn`.
        """
        return f"{moment.year:04d}Q{(moment.month - 1) // 3 + 1}"

    ############################
    # Publicly Exposed Methods #
    ############################

    def measure(self, facts: List[CompanyFact], now: datetime) -> List[ProviderMetricValue]:
        """Measure the age and the employees of every provider of the facts.

        Args:
            facts (List[CompanyFact]): The facts, a row of Wikidata each.
            now (datetime): When the facts are measured (the age, the undated employees).

        Returns:
            List[ProviderMetricValue]: The age of each provider, and its employees by quarter.
        """
        founded: Dict[CloudProvider, datetime] = {}
        staff: Dict[CloudProvider, Dict[str, float]] = {}
        pages: Dict[CloudProvider, str] = {}
        for fact in facts:
            pages.setdefault(fact.provider, fact.source_url)
            if fact.inception is not None and (fact.provider not in founded or fact.inception < founded[fact.provider]):
                founded[fact.provider] = fact.inception
            if fact.employees is not None and fact.employees > 0:
                period = self._quarter(fact.employees_at or now)
                counts = staff.setdefault(fact.provider, {})
                counts[period] = max(fact.employees, counts.get(period, 0.0))
        period = self._quarter(now)
        values = [
            ProviderMetricValue(
                provider=provider,
                period=period,
                metric=ProviderMetric.AGE,
                value=(now - inception).days / self.YEAR_DAYS,
                source=MetricSource.WIKIDATA,
                source_url=pages[provider],
            )
            for provider, inception in founded.items()
            if now > inception
        ]
        values += [
            ProviderMetricValue(
                provider=provider,
                period=quarter,
                metric=ProviderMetric.EMPLOYEES,
                value=count,
                source=MetricSource.WIKIDATA,
                source_url=pages[provider],
            )
            for provider, counts in staff.items()
            for quarter, count in sorted(counts.items())
        ]
        self.logger.info("Company facts of %d providers: %d measures.", len(pages), len(values))
        return values
