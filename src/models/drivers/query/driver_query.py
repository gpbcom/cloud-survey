from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.drivers.enums import DriverScope, ProviderMetric
from models.drivers.exception import TargetAmongCriteriaError


class DriverQuery(BaseModel):
    """What a driver analysis explains, with which criteria, over which observations.

    Attributes:
        target (ProviderMetric): The measure of the rise to explain.
        criteria (List[ProviderMetric]): The candidate drivers.
        scope (DriverScope): One observation per provider (latest quarter), or per provider and quarter.
        lag (int): How many quarters the criteria lead the target (panel only).
        controls (List[ProviderMetric]): The criteria held constant in the partial correlations (e.g. the size).
        providers (List[CloudProvider]): Only these providers, every provider when empty.
        bootstrap (int): The bootstrap resamples of the confidence intervals (0 for none).
        seed (int): The seed of the resampling (the results are reproducible).
    """

    model_config = ConfigDict(frozen=True)

    target: ProviderMetric = Field(description="The measure of the rise to explain.")
    criteria: List[ProviderMetric] = Field(min_length=1, max_length=16, description="The candidate drivers.")
    scope: DriverScope = Field(default=DriverScope.CROSS_SECTION, description="Which observations are used.")
    lag: int = Field(default=0, ge=0, le=8, description="How many quarters the criteria lead the target.")
    controls: List[ProviderMetric] = Field(default_factory=list, max_length=4, description="The controls.")
    providers: List[CloudProvider] = Field(default_factory=list, description="Only these providers.")
    bootstrap: int = Field(default=400, ge=0, le=5000, description="The bootstrap resamples.")
    seed: int = Field(default=7, description="The seed of the resampling.")

    @field_validator("controls", "providers", mode="before")
    def validate_list(cls, value: JsonValue) -> JsonValue:
        """Validate a raw list: each value once, in its order.

        Args:
            value (JsonValue): The raw values.

        Returns:
            JsonValue: The values, each once (checked by pydantic afterwards).
        """
        if isinstance(value, list):
            unique: List[JsonValue] = [*dict.fromkeys(str(item) for item in value)]
            return unique
        return value

    @field_validator("criteria", mode="before")
    def validate_criteria(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate the raw criteria: each once, in their order, the target not among them.

        Args:
            value (JsonValue): The raw criteria.
            info (ValidationInfo): The fields validated so far (the target).

        Returns:
            JsonValue: The criteria, each once (checked by pydantic afterwards).

        Raises:
            TargetAmongCriteriaError: If the target is one of the criteria.
        """
        if not isinstance(value, list):
            return value
        unique: List[JsonValue] = [*dict.fromkeys(str(item) for item in value)]
        target = info.data.get("target")
        if target is not None and str(target) in unique:
            raise TargetAmongCriteriaError(str(target))
        return unique
