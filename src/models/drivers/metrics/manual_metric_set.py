from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.drivers.metrics.provider_metric_value import ProviderMetricValue


class ManualMetricSet(BaseModel):
    """The measures typed in from annual reports and analyst publications (`conf/metrics/manual-metrics.yaml`).

    Attributes:
        values (List[ProviderMetricValue]): The measures, each with the document it was read from.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    values: List[ProviderMetricValue] = Field(default_factory=list, description="The measures.")
