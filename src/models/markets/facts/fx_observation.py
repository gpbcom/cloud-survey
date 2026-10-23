from __future__ import annotations

# Standard Library Imports.
from datetime import date
from typing import ClassVar

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.markets.field_check import MarketFieldCheck


class FxObservation(BaseModel):
    """A value of a FRED exchange-rate series, quoted as the series is (US dollars per unit, or units per dollar).

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        series (str): The FRED series, e.g. `DEXUSEU`.
        day (date): The day (the first of the month for a monthly series).
        value (float): The rate.
        source_url (str): The CSV read.
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    series: str = Field(min_length=4, max_length=30, description="The FRED series.")
    day: date = Field(description="The day.")
    value: float = Field(gt=0, description="The rate.")
    source_url: str = Field(min_length=1, max_length=2048, description="The CSV read.")

    @field_validator("series", mode="before")
    def validate_series(cls, value: JsonValue) -> JsonValue:
        """Validate the raw series: a text of 4 to 30 characters, trimmed.

        Args:
            value (JsonValue): The raw series.

        Returns:
            JsonValue: The series.

        Raises:
            InvalidMarketTextError: If it is not a text of 4 to 30 characters.
        """
        return cls.CHECK.text(value, "FRED series", 30, minimum=4, collapse=False)

    @field_validator("day", mode="before")
    def validate_day(cls, value: JsonValue) -> JsonValue:
        """Validate the raw day: a date.

        Args:
            value (JsonValue): The raw day.

        Returns:
            JsonValue: The day.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        return cls.CHECK.iso_day(value, "rate day")

    @field_validator("value", mode="before")
    def validate_value(cls, value: JsonValue) -> JsonValue:
        """Validate the raw rate: a number above zero.

        Args:
            value (JsonValue): The raw rate.

        Returns:
            JsonValue: The rate.

        Raises:
            InvalidMarketNumberError: If it is not a number above zero.
        """
        return cls.CHECK.number(value, "exchange rate", low=0.0, strict_low=True)

    @field_validator("source_url", mode="before")
    def validate_source_url(cls, value: JsonValue) -> JsonValue:
        """Validate the raw document: a text of 1 to 2048 characters, trimmed.

        Args:
            value (JsonValue): The raw document.

        Returns:
            JsonValue: The document.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 2048 characters.
        """
        return cls.CHECK.text(value, "rate document", 2048, collapse=False)
