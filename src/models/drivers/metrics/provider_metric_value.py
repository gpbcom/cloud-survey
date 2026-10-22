from __future__ import annotations

# Standard Library Imports.
import re
from datetime import datetime
from typing import ClassVar, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource, ProviderMetric
from models.drivers.exception import InvalidPeriodError


class ProviderMetricValue(BaseModel):
    """A measure of a provider for a quarter, with where it comes from.

    Attributes:
        PERIOD (ClassVar[Pattern[str]]): The format of a quarter.
        provider (CloudProvider): The provider.
        period (str): The quarter, written `YYYYQn`.
        metric (ProviderMetric): What is measured.
        value (float): The measure.
        source (MetricSource): Where it comes from.
        source_url (Optional[str]): The page or document it was read from.
        fetched_at (Optional[datetime]): When it was read.
    """

    model_config = ConfigDict(frozen=True)

    PERIOD: ClassVar[Pattern[str]] = re.compile(r"^(19|20)\d{2}Q[1-4]$")

    provider: CloudProvider = Field(description="The provider.")
    period: str = Field(description="The quarter, written YYYYQn.")
    metric: ProviderMetric = Field(description="What is measured.")
    value: float = Field(description="The measure.")
    source: MetricSource = Field(default=MetricSource.DERIVED, description="Where it comes from.")
    source_url: Optional[str] = Field(default=None, max_length=2048, description="Where it was read.")
    fetched_at: Optional[datetime] = Field(default=None, description="When it was read.")

    @field_validator("period", mode="before")
    def validate_period(cls, value: JsonValue) -> JsonValue:
        """Validate the raw quarter: trimmed, upper-cased, written `YYYYQn`.

        Args:
            value (JsonValue): The raw quarter.

        Returns:
            JsonValue: The quarter.

        Raises:
            InvalidPeriodError: If it is not a quarter written `YYYYQn`.
        """
        if not isinstance(value, str):
            return value
        period = value.strip().upper()
        if not cls.PERIOD.match(period):
            raise InvalidPeriodError(value)
        return period
