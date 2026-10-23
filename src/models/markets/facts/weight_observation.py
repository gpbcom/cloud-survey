from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.markets.enums import WeightIndicator
from models.markets.exception import InvalidMarketValueError
from models.markets.field_check import MarketFieldCheck


class WeightObservation(BaseModel):
    """A World Bank indicator of a country for a year, weighting the country within a union (the EU-27 estimate).

    Attributes:
        COUNTRY (ClassVar[Pattern[str]]): The format of a country: ISO 3166-1 alpha-2, upper case.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        indicator (WeightIndicator): The indicator, internet users (% of the population) or the population.
        country (str): The country, ISO 3166-1 alpha-2.
        year (int): The year.
        value (float): The value.
        source_url (str): The document read.
    """

    COUNTRY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{2}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    indicator: WeightIndicator = Field(description="The indicator.")
    country: str = Field(pattern=r"^[A-Z]{2}$", description="The country.")
    year: int = Field(ge=1960, le=2100, description="The year.")
    value: float = Field(ge=0, description="The value.")
    source_url: str = Field(min_length=1, max_length=2048, description="The document read.")

    @field_validator("indicator", mode="before")
    def validate_indicator(cls, value: JsonValue) -> JsonValue:
        """Validate the raw indicator: a `WeightIndicator` value.

        Args:
            value (JsonValue): The raw indicator.

        Returns:
            JsonValue: The indicator.

        Raises:
            InvalidMarketChoiceError: If it is not a known indicator.
        """
        return cls.CHECK.choice(value, "World Bank indicator", [indicator.value for indicator in WeightIndicator])

    @field_validator("country", mode="before")
    def validate_country(cls, value: JsonValue) -> JsonValue:
        """Validate the raw country: a two-letter code, upper-cased.

        Args:
            value (JsonValue): The raw country.

        Returns:
            JsonValue: The country.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not a two-letter code.
        """
        country = (cls.CHECK.text(value, "weight country", 2) or "").upper()
        if not cls.COUNTRY.match(country):
            raise InvalidMarketValueError("weight country", country, "a two-letter country code")
        return country

    @field_validator("year", mode="before")
    def validate_year(cls, value: JsonValue) -> JsonValue:
        """Validate the raw year: a whole number from 1960 to 2100 (the World Bank writes it as a text).

        Args:
            value (JsonValue): The raw year.

        Returns:
            JsonValue: The year.

        Raises:
            InvalidMarketNumberError: If it is not a whole number from 1960 to 2100.
        """
        return cls.CHECK.number(value, "weight year", low=1960, high=2100, integer=True)

    @field_validator("value", mode="before")
    def validate_value(cls, value: JsonValue) -> JsonValue:
        """Validate the raw value: a number of at least 0.

        Args:
            value (JsonValue): The raw value.

        Returns:
            JsonValue: The value.

        Raises:
            InvalidMarketNumberError: If it is not a number of at least 0.
        """
        return cls.CHECK.number(value, "weight value", low=0)

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
        return cls.CHECK.text(value, "weight document", 2048, collapse=False)
