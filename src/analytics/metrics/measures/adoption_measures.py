from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger, getLogger
from typing import Dict, List, Optional

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource, ProviderMetric
from models.drivers.facts.repository_fact import RepositoryFact
from models.drivers.metrics.provider_metric_value import ProviderMetricValue


class AdoptionMeasures:
    """Turn the GitHub repositories into the developer adoption of each provider: the stars of its repositories.

    Attributes:
        logger (Logger): The measure logger.

    Notes:
        The stars are summed over the repositories of a provider (each repository once) and dated by the quarter
        of the collection.
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

    def measure(self, facts: List[RepositoryFact], now: datetime) -> List[ProviderMetricValue]:
        """Sum the stars of every provider of the facts.

        Args:
            facts (List[RepositoryFact]): The repositories.
            now (datetime): When the snapshot is taken.

        Returns:
            List[ProviderMetricValue]: One measure per provider.
        """
        stars: Dict[CloudProvider, Dict[str, int]] = {}
        urls: Dict[CloudProvider, str] = {}
        for fact in facts:
            stars.setdefault(fact.provider, {})[fact.repository] = fact.stars
            urls.setdefault(fact.provider, f"https://github.com/{fact.repository}")
        period = f"{now.year:04d}Q{(now.month - 1) // 3 + 1}"
        values = [
            ProviderMetricValue(
                provider=provider,
                period=period,
                metric=ProviderMetric.SDK_STARS,
                value=float(sum(repositories.values())),
                source=MetricSource.GITHUB,
                source_url=urls[provider],
            )
            for provider, repositories in stars.items()
        ]
        self.logger.info("Developer adoption of %d providers: %d measures.", len(stars), len(values))
        return values
