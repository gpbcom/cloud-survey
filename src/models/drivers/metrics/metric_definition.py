from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.drivers.enums import MetricFamily, MetricScale, ProviderMetric


class MetricDefinition(BaseModel):
    """What a criterion (or a target) of the driver analysis measures (`conf/metrics/metrics.yaml`).

    Attributes:
        metric (ProviderMetric): The criterion.
        label (str): Its display name.
        family (MetricFamily): Its family.
        scale (MetricScale): How it is transformed before the statistics.
        unit (str): Its unit (e.g. `products`, `USD bn`, `share`).
        description (str): What it measures, in one line.
        sources (List[str]): Where it comes from, or where to find it.
        target (bool): Whether it can be the target of an analysis (a measure of the rise).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: ProviderMetric = Field(description="The criterion.")
    label: str = Field(min_length=1, description="Its display name.")
    family: MetricFamily = Field(description="Its family.")
    scale: MetricScale = Field(description="How it is transformed.")
    unit: str = Field(default="", description="Its unit.")
    description: str = Field(default="", description="What it measures.")
    sources: List[str] = Field(default_factory=list, description="Where it comes from.")
    target: bool = Field(default=False, description="Whether it can be a target.")

    @field_validator("label", "unit", "description", mode="before")
    def validate_text(cls, value: JsonValue) -> JsonValue:
        """Validate a raw text: spaces collapsed and trimmed.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The cleaned text (its type is checked by pydantic afterwards), empty when missing.
        """
        if value is None:
            return ""
        return " ".join(value.split()) if isinstance(value, str) else value
