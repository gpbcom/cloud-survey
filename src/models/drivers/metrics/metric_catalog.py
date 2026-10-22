from __future__ import annotations

# Standard Library Imports.
from typing import Dict, List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

# First Party Imports.
from models.drivers.enums import MetricFamily, ProviderMetric
from models.drivers.metrics.metric_definition import MetricDefinition


class MetricCatalog(BaseModel):
    """Every criterion and target of the driver analysis, in display order.

    Attributes:
        definitions (List[MetricDefinition]): The definitions, in display order.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    definitions: List[MetricDefinition] = Field(default_factory=list, description="The definitions.")

    _by_metric: Dict[ProviderMetric, MetricDefinition] = PrivateAttr(default_factory=dict)

    ############################
    # Internal Helpers Methods #
    ############################

    def _index(self) -> Dict[ProviderMetric, MetricDefinition]:
        """Index the definitions by metric, once.

        Returns:
            Dict[ProviderMetric, MetricDefinition]: The definitions, by metric.
        """
        if not self._by_metric and self.definitions:
            self._by_metric.update({definition.metric: definition for definition in self.definitions})
        return self._by_metric

    ############################
    # Publicly Exposed Methods #
    ############################

    def get(self, metric: ProviderMetric) -> Optional[MetricDefinition]:
        """Get the definition of a metric.

        Args:
            metric (ProviderMetric): The metric.

        Returns:
            Optional[MetricDefinition]: Its definition, `None` when the catalogue has none.
        """
        return self._index().get(metric)

    def label(self, metric: ProviderMetric) -> str:
        """Get the display name of a metric.

        Args:
            metric (ProviderMetric): The metric.

        Returns:
            str: Its label, its value when the catalogue has no definition.
        """
        definition = self.get(metric)
        return definition.label if definition is not None else metric.value

    def targets(self) -> List[MetricDefinition]:
        """List the metrics measuring the rise.

        Returns:
            List[MetricDefinition]: The targets, in display order.
        """
        return [definition for definition in self.definitions if definition.target]

    def of_family(self, family: MetricFamily) -> List[MetricDefinition]:
        """List the metrics of a family.

        Args:
            family (MetricFamily): The family.

        Returns:
            List[MetricDefinition]: Its metrics, in display order.
        """
        return [definition for definition in self.definitions if definition.family is family]
