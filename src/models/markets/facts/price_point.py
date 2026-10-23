from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.markets.exception import InvalidMarketValueError
from models.markets.field_check import MarketFieldCheck


class PricePoint(BaseModel):
    """A closing price of a listing, as Google Finance's chart gives it (one point a week over the whole history).

    Attributes:
        CURRENCY (ClassVar[Pattern[str]]): The format of a currency: three upper-case letters.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        listing (str): The listing, `EXCHANGE:SYMBOL` as the catalogue writes it.
        day (date): The trading day, in the exchange's time zone.
        close (float): The closing price, in the listing currency (split-adjusted, dividends not reinvested).
        volume (Optional[int]): The shares traded, when given.
        currency (str): The listing currency, as Google Finance states it.
        source_url (str): The page or RPC read.
    """

    CURRENCY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{3}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    listing: str = Field(min_length=3, max_length=30, description="The listing.")
    day: date = Field(description="The trading day.")
    close: float = Field(gt=0, description="The closing price.")
    volume: Optional[int] = Field(default=None, ge=0, description="The shares traded.")
    currency: str = Field(description="The listing currency.")
    source_url: str = Field(min_length=1, max_length=2048, description="The page or RPC read.")

    @field_validator("listing", mode="before")
    def validate_listing(cls, value: JsonValue) -> JsonValue:
        """Validate the raw listing: a text of 3 to 30 characters, trimmed.

        Args:
            value (JsonValue): The raw listing.

        Returns:
            JsonValue: The listing.

        Raises:
            InvalidMarketTextError: If it is not a text of 3 to 30 characters.
        """
        return cls.CHECK.text(value, "price listing", 30, minimum=3, collapse=False)

    @field_validator("day", mode="before")
    def validate_day(cls, value: JsonValue) -> JsonValue:
        """Validate the raw trading day: a date.

        Args:
            value (JsonValue): The raw day.

        Returns:
            JsonValue: The day.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        return cls.CHECK.iso_day(value, "trading day")

    @field_validator("close", mode="before")
    def validate_close(cls, value: JsonValue) -> JsonValue:
        """Validate the raw closing price: a number above zero.

        Args:
            value (JsonValue): The raw price.

        Returns:
            JsonValue: The price.

        Raises:
            InvalidMarketNumberError: If it is not a number above zero.
        """
        return cls.CHECK.number(value, "closing price", low=0.0, strict_low=True)

    @field_validator("volume", mode="before")
    def validate_volume(cls, value: JsonValue) -> JsonValue:
        """Validate the raw volume: a whole number of at least 0, or none.

        Args:
            value (JsonValue): The raw volume.

        Returns:
            JsonValue: The volume, `None` when not given.

        Raises:
            InvalidMarketNumberError: If it is not a whole number of at least 0.
        """
        return cls.CHECK.number(value, "traded volume", low=0, optional=True, integer=True)

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
        return cls.CHECK.text(value, "price document", 2048, collapse=False)
