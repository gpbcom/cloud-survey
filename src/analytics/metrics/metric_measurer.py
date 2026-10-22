from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger, getLogger
from typing import Dict, List, Optional, Type

# Third Party Imports.
from pydantic import BaseModel, JsonValue, ValidationError

# First Party Imports.
from analytics.metrics.measures.adoption_measures import AdoptionMeasures
from analytics.metrics.measures.capex_quarters import CapexQuarters
from analytics.metrics.measures.company_measures import CompanyMeasures
from analytics.metrics.measures.network_measures import NetworkMeasures
from models.drivers.enums import MetricSource
from models.drivers.facts.capex_fact import CapexFact
from models.drivers.facts.company_fact import CompanyFact
from models.drivers.facts.network_fact import NetworkFact
from models.drivers.facts.repository_fact import RepositoryFact
from models.drivers.metrics.provider_metric_value import ProviderMetricValue


class MetricMeasurer:
    """Turn the facts crawled from a metric source into the measures of the providers.

    Attributes:
        capex (CapexQuarters): The quarterly capex, from the SEC EDGAR facts.
        company (CompanyMeasures): The age and the employees, from the Wikidata facts.
        network (NetworkMeasures): The exchanges and the facilities, from the PeeringDB networks.
        adoption (AdoptionMeasures): The stars, from the GitHub repositories.
        logger (Logger): The measurer logger.

    Notes:
        The crawlers stream the facts as the sources state them. This is where they are computed into the metrics of
        `provider_metrics`, so that the crawl and the computation are tested and changed apart.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the measurer.

        Args:
            logger (Optional[Logger]): The measurer logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.capex = CapexQuarters(self.logger)
        self.company = CompanyMeasures(self.logger)
        self.network = NetworkMeasures(self.logger)
        self.adoption = AdoptionMeasures(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _facts[Fact: BaseModel](self, model: Type[Fact], items: List[Dict[str, JsonValue]]) -> List[Fact]:
        """Validate the crawled items of a source.

        Args:
            model (Type[Fact]): The fact model of the source.
            items (List[Dict[str, JsonValue]]): The crawled items.

        Returns:
            List[Fact]: The valid facts (an invalid item is logged and left out).
        """
        facts: List[Fact] = []
        for item in items:
            try:
                facts.append(model.model_validate(item))
            except ValidationError as e:
                self.logger.warning("Invalid %s item left out: %s", model.__name__, e.errors()[0]["msg"])
        return facts

    ############################
    # Publicly Exposed Methods #
    ############################

    def measure(
        self, source: MetricSource, items: List[Dict[str, JsonValue]], now: datetime
    ) -> List[ProviderMetricValue]:
        """Measure the providers from the items crawled at a source.

        Args:
            source (MetricSource): The source crawled.
            items (List[Dict[str, JsonValue]]): Its crawled facts.
            now (datetime): When the snapshots are taken.

        Returns:
            List[ProviderMetricValue]: The measures, none for a source without facts to measure.
        """
        match source:
            case MetricSource.EDGAR:
                values = self.capex.measure(self._facts(CapexFact, items))
            case MetricSource.WIKIDATA:
                values = self.company.measure(self._facts(CompanyFact, items), now)
            case MetricSource.PEERINGDB:
                values = self.network.measure(self._facts(NetworkFact, items), now)
            case MetricSource.GITHUB:
                values = self.adoption.measure(self._facts(RepositoryFact, items), now)
            case _:
                self.logger.warning("No measure of the %s facts.", source.value)
                values = []
        self.logger.debug("%d %s facts measured into %d values.", len(items), source.value, len(values))
        return values
