from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.drivers.enums import MetricSource, ProviderMetric
from models.drivers.exception import InvalidPeriodError


class MetricCoverage(BaseModel):
    """What the stored measures of a criterion cover, as its tooltip in the Rise drivers card says.

    Attributes:
        PERIOD (ClassVar[Pattern[str]]): The format of a quarter.
        metric (ProviderMetric): The criterion.
        providers (int): The providers holding at least one measure.
        first (str): The first quarter measured, written `YYYYQn`.
        last (str): The last quarter measured, written `YYYYQn`.
        observations (int): The stored measures (provider-quarters, all sources).
        sources (List[MetricSource]): Where they come from.
    """

    PERIOD: ClassVar[Pattern[str]] = re.compile(r"^(19|20)\d{2}Q[1-4]$")

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: ProviderMetric = Field(description="The criterion.")
    providers: int = Field(ge=0, description="The providers holding a measure.")
    first: str = Field(description="The first quarter measured.")
    last: str = Field(description="The last quarter measured.")
    observations: int = Field(ge=0, description="The stored measures.")
    sources: List[MetricSource] = Field(default_factory=list, description="Where they come from.")

    @field_validator("first", "last", mode="before")
    def validate_period(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw first or last quarter: written `YYYYQn`.

        Args:
            value (JsonValue): The raw quarter.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The quarter, trimmed and upper-cased.

        Raises:
            InvalidPeriodError: If it is not a quarter written `YYYYQn`.
        """
        period = value.strip().upper() if isinstance(value, str) else repr(value)
        if not cls.PERIOD.match(period):
            raise InvalidPeriodError(period)
        return period
