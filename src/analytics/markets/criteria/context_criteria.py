from __future__ import annotations

# Standard Library Imports.
from collections import defaultdict
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence

# First Party Imports.
from analytics.drivers.matrix.quarter_calendar import QuarterCalendar
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource, ProviderMetric
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from models.markets.enums import Granularity
from models.markets.values.market_share_value import MarketShareValue


class ContextCriteria:
    """Turn the chip supplier rankings (TrendForce) into a market context common to every provider.

    Attributes:
        METRICS (ClassVar[Dict[str, ProviderMetric]]): The criterion of each segment read.
        calendar (QuarterCalendar): Names the quarters.
        logger (Logger): The measurer logger.

    Notes:
        - The concentration of a quarter is the Herfindahl-Hirschman index of the suppliers the release ranks: the
          sum of their squared shares, as fractions (0 to 1, 1 being a monopoly). The unranked rest is not split, so the
          index is a lower bound.
        - TrendForce's companies (TSMC, Samsung, SK hynix…) run no cloud provider: the value is copied to every
          provider. Within a quarter it is the same for all of them, so it can only test timing (does the target
          move with the chip supply?), never a difference between providers: on the latest quarter it differs only
          where the providers' latest quarters differ, and the panel regression's quarter effects absorb it. The
          panel correlations and Granger tests use it.
    """

    METRICS: ClassVar[Dict[str, ProviderMetric]] = {
        "foundry": ProviderMetric.CONTEXT_FOUNDRY_HHI,
        "dram": ProviderMetric.CONTEXT_DRAM_HHI,
        "nand": ProviderMetric.CONTEXT_NAND_HHI,
    }

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the measurer.

        Args:
            logger (Optional[Logger]): The measurer logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.calendar = QuarterCalendar()

    ############################
    # Publicly Exposed Methods #
    ############################

    def concentration(self, values: Sequence[MarketShareValue]) -> Dict[date, float]:
        """Compute the concentration of each quarter.

        Args:
            values (Sequence[MarketShareValue]): The worldwide shares of a segment.

        Returns:
            Dict[date, float]: The index of each quarter, keyed by its first day (yearly totals left out).
        """
        squares: Dict[date, float] = defaultdict(float)
        for value in values:
            if value.granularity is Granularity.QUARTER:
                squares[value.period] += (value.value / 100.0) ** 2
        if not squares:
            self.logger.warning("No quarterly share among %d values: no concentration.", len(values))
        else:
            self.logger.debug("Concentration of %d quarters.", len(squares))
        return dict(sorted(squares.items()))

    def measure(
        self, segment: str, values: Sequence[MarketShareValue], providers: Sequence[CloudProvider]
    ) -> List[ProviderMetricValue]:
        """Measure a segment's concentration for every provider.

        Args:
            segment (str): The segment, a key of `METRICS`.
            values (Sequence[MarketShareValue]): Its worldwide shares.
            providers (Sequence[CloudProvider]): The providers the context is copied to.

        Returns:
            List[ProviderMetricValue]: One measure per provider and quarter, none for a segment without criterion.
        """
        metric = self.METRICS.get(segment)
        if metric is None:
            self.logger.warning("No context criterion for %s: left out.", segment)
            return []
        quarters = self.concentration(values)
        measures = [
            ProviderMetricValue(
                provider=provider,
                period=self.calendar.of_day(quarter),
                metric=metric,
                value=index,
                source=MetricSource.TRENDFORCE,
            )
            for provider in providers
            for quarter, index in quarters.items()
        ]
        self.logger.info(
            "%s concentration of %d quarters copied to %d providers.", segment, len(quarters), len(providers)
        )
        return measures
