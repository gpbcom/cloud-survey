from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger, getLogger
from typing import Dict, List, Optional, Set

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource, ProviderMetric
from models.drivers.facts.network_fact import NetworkFact
from models.drivers.metrics.provider_metric_value import ProviderMetricValue


class NetworkMeasures:
    """Turn the PeeringDB networks into the internet exchanges and facilities of each provider.

    Attributes:
        logger (Logger): The measure logger.

    Notes:
        A provider with several autonomous systems counts each exchange and each facility once. The counts are a
        snapshot, dated by the quarter of the collection.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the measure.

        Args:
            logger (Optional[Logger]): The measure logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def measure(self, facts: List[NetworkFact], now: datetime) -> List[ProviderMetricValue]:
        """Count the exchanges and facilities of every provider of the facts.

        Args:
            facts (List[NetworkFact]): The networks.
            now (datetime): When the snapshot is taken.

        Returns:
            List[ProviderMetricValue]: Two measures per provider.
        """
        exchanges: Dict[CloudProvider, Set[int]] = {}
        facilities: Dict[CloudProvider, Set[int]] = {}
        urls: Dict[CloudProvider, str] = {}
        for fact in facts:
            exchanges.setdefault(fact.provider, set()).update(fact.exchanges)
            facilities.setdefault(fact.provider, set()).update(fact.facilities)
            urls.setdefault(fact.provider, fact.source_url)
        period = f"{now.year:04d}Q{(now.month - 1) // 3 + 1}"
        values = [
            ProviderMetricValue(
                provider=provider,
                period=period,
                metric=metric,
                value=float(len(linked[provider])),
                source=MetricSource.PEERINGDB,
                source_url=urls[provider],
            )
            for provider in urls
            for metric, linked in (
                (ProviderMetric.NETWORK_EXCHANGES, exchanges),
                (ProviderMetric.FACILITIES, facilities),
            )
        ]
        self.logger.info("Network reach of %d providers: %d measures.", len(urls), len(values))
        return values
