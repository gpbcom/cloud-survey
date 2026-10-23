from __future__ import annotations

# Standard Library Imports.
from datetime import date
from typing import ClassVar, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.enums import Granularity
from models.markets.field_check import MarketFieldCheck


class CoverageEntry(BaseModel):
    """How many points a series holds, and whether that is enough to correlate it.

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        key (str): What the series is, e.g. `search / US / all / google` or `NYSE:IBM`.
        granularity (Granularity): The period of its points.
        first (Optional[date]): Its first period.
        last (Optional[date]): Its last period.
        points (int): The periods with a value.
        longest_gap (int): The most consecutive periods missing between its first and last.
        enough (bool): Whether it meets the thresholds of a correlation (points and gaps).
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1, description="What the series is.")
    granularity: Granularity = Field(description="The period of its points.")
    first: Optional[date] = Field(default=None, description="Its first period.")
    last: Optional[date] = Field(default=None, description="Its last period.")
    points: int = Field(default=0, ge=0, description="The periods with a value.")
    longest_gap: int = Field(default=0, ge=0, description="The most consecutive periods missing.")
    enough: bool = Field(default=False, description="Whether it can be correlated.")

    @field_validator("key", mode="before")
    def validate_key(cls, value: JsonValue) -> JsonValue:
        """Validate the raw key: a text of 1 to 200 characters.

        Args:
            value (JsonValue): The raw key.

        Returns:
            JsonValue: The key, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 200 characters.
        """
        return cls.CHECK.text(value, "coverage key", 200)

    @field_validator("granularity", mode="before")
    def validate_granularity(cls, value: JsonValue) -> JsonValue:
        """Validate the raw granularity: a `Granularity` value.

        Args:
            value (JsonValue): The raw granularity.

        Returns:
            JsonValue: The granularity.

        Raises:
            InvalidMarketChoiceError: If it is not a known granularity.
        """
        return cls.CHECK.choice(value, "coverage granularity", [granularity.value for granularity in Granularity])

    @field_validator("first", "last", mode="before")
    def validate_period(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw first or last period: a date, `None` for an empty series.

        Args:
            value (JsonValue): The raw period.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The period.

        Raises:
            InvalidMarketDateError: If it is neither missing nor a date.
        """
        return cls.CHECK.iso_day(value, f"coverage {info.field_name} period", optional=True)

    @field_validator("points", "longest_gap", mode="before")
    def validate_count(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw count: a whole number of at least 0.

        Args:
            value (JsonValue): The raw count.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The count.

        Raises:
            InvalidMarketNumberError: If it is not a whole number of at least 0.
        """
        return cls.CHECK.number(value, f"coverage {info.field_name}", low=0, integer=True)

    @field_validator("enough", mode="before")
    def validate_enough(cls, value: JsonValue) -> JsonValue:
        """Validate the raw verdict: a boolean.

        Args:
            value (JsonValue): The raw verdict.

        Returns:
            JsonValue: The verdict.

        Raises:
            InvalidMarketFlagError: If it is not a boolean.
        """
        return cls.CHECK.flag(value, "coverage verdict")
