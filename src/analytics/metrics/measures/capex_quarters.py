from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

# First Party Imports.
from analytics.companies.financials.flow_quarters import FlowQuarters
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource, ProviderMetric
from models.drivers.facts.capex_fact import CapexFact
from models.drivers.metrics.provider_metric_value import ProviderMetricValue

type Duration = Tuple[date, date]


class CapexQuarters:
    """Turn the capex facts of the filings into the quarterly capex of each provider's group.

    Attributes:
        BILLION (ClassVar[float]): The dollars of a billion (the unit of the capex metric).
        flows (FlowQuarters): Derives the quarters of the year-to-date facts (shared with the companies' statements).
        logger (Logger): The measure logger.

    Notes:
        - The cash-flow facts of a 10-Q cover the fiscal year to date. A quarter is taken as published when a
          3-month fact exists, else derived from two year-to-date facts of the same fiscal year 3 months apart (the
          fourth quarter from the 10-K minus the nine months).
        - A quarter is dated by its last day (Oracle's quarter ending on 31 August is 2025Q3).
        - The concepts are read in the order of the facts, a later concept filling the quarters the first lacks
          (Amazon moved from `PaymentsToAcquirePropertyPlantAndEquipment` to `PaymentsToAcquireProductiveAssets`).
    """

    BILLION: ClassVar[float] = 1e9

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the measure.

        Args:
            logger (Optional[Logger]): The measure logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.flows = FlowQuarters(logger=self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _quarters(self, durations: Dict[Duration, float]) -> Dict[date, float]:
        """Get the value of each fiscal quarter, published or derived from the year-to-date facts.

        Args:
            durations (Dict[Duration, float]): The value of each period of a concept.

        Returns:
            Dict[date, float]: The value of each quarter, by its last day.
        """
        filed, derived = self.flows.quarters(durations)
        return {**derived, **filed}

    def _quarter(self, moment: date) -> str:
        """Write the quarter of a date.

        Args:
            moment (date): The date.

        Returns:
            str: Its quarter, written `YYYYQn`.
        """
        return f"{moment.year:04d}Q{(moment.month - 1) // 3 + 1}"

    ############################
    # Publicly Exposed Methods #
    ############################

    def measure(self, facts: List[CapexFact]) -> List[ProviderMetricValue]:
        """Measure the quarterly capex of every provider of the facts.

        Args:
            facts (List[CapexFact]): The capex facts, as filed.

        Returns:
            List[ProviderMetricValue]: One capex measure per provider and quarter, in USD bn, the oldest first.
        """
        by_concept: Dict[CloudProvider, Dict[str, Dict[Duration, float]]] = {}
        urls: Dict[CloudProvider, str] = {}
        for fact in facts:
            durations = by_concept.setdefault(fact.provider, {}).setdefault(fact.concept, {})
            durations.setdefault((fact.start, fact.end), fact.value)
            urls.setdefault(fact.provider, fact.source_url)
        values: List[ProviderMetricValue] = []
        for provider, concepts in by_concept.items():
            quarters: Dict[date, float] = {}
            for durations in concepts.values():
                for end, value in self._quarters(durations).items():
                    quarters.setdefault(end, value)
            values += [
                ProviderMetricValue(
                    provider=provider,
                    period=self._quarter(end),
                    metric=ProviderMetric.CAPEX,
                    value=value / self.BILLION,
                    source=MetricSource.EDGAR,
                    source_url=urls[provider],
                )
                for end, value in sorted(quarters.items())
                if value > 0
            ]
        self.logger.info("Quarterly capex of %d groups: %d measures.", len(by_concept), len(values))
        return values
