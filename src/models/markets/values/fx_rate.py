from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.markets.enums import MarketFeed
from models.markets.exception import InvalidMarketValueError
from models.markets.field_check import MarketFieldCheck


class FxRate(BaseModel):
    """A stored exchange rate: the US dollars one unit of a currency was worth on a day.

    Attributes:
        CURRENCY (ClassVar[Pattern[str]]): The format of a currency: three upper-case letters.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        currency (str): The currency, e.g. `EUR`.
        day (date): The day.
        usd_per_unit (float): The US dollars for one unit of the currency.
        source (MarketFeed): Where it comes from (FRED).
    """

    CURRENCY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{3}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    currency: str = Field(description="The currency.")
    day: date = Field(description="The day.")
    usd_per_unit: float = Field(gt=0, description="The US dollars for one unit.")
    source: MarketFeed = Field(default=MarketFeed.FRED, description="Where it comes from.")

    @field_validator("currency", mode="before")
    def validate_currency(cls, value: JsonValue) -> JsonValue:
        """Validate the raw currency: three letters, upper-cased.

        Args:
            value (JsonValue): The raw currency.

        Returns:
            JsonValue: The currency.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not three letters.
        """
        currency = (cls.CHECK.text(value, "currency", 3) or "").upper()
        if not cls.CURRENCY.match(currency):
            raise InvalidMarketValueError("currency", currency, "three letters (ISO 4217)")
        return currency

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

    @field_validator("usd_per_unit", mode="before")
    def validate_usd_per_unit(cls, value: JsonValue) -> JsonValue:
        """Validate the raw rate: a number above zero.

        Args:
            value (JsonValue): The raw rate.

        Returns:
            JsonValue: The rate.

        Raises:
            InvalidMarketNumberError: If it is not a number above zero.
        """
        return cls.CHECK.number(value, "US dollars per unit", low=0.0, strict_low=True)

    @field_validator("source", mode="before")
    def validate_source(cls, value: JsonValue) -> JsonValue:
        """Validate the raw source: a `MarketFeed` value.

        Args:
            value (JsonValue): The raw source.

        Returns:
            JsonValue: The source.

        Raises:
            InvalidMarketChoiceError: If it is not a known feed.
        """
        return cls.CHECK.choice(value, "rate source", [feed.value for feed in MarketFeed])
