from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.markets.enums import FxQuote
from models.markets.exception import InvalidMarketValueError
from models.markets.field_check import MarketFieldCheck


class CurrencySeries(BaseModel):
    """The FRED series giving the exchange rate of a currency against the US dollar.

    Attributes:
        CURRENCY (ClassVar[Pattern[str]]): The format of a currency: ISO 4217, three upper-case letters.
        SERIES (ClassVar[Pattern[str]]): The format of a FRED series identifier.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        currency (str): The currency, e.g. `EUR`.
        series (str): The FRED series, e.g. `DEXUSEU`.
        quote (FxQuote): Whether the series gives US dollars per unit or units per US dollar.

    Notes:
        The US dollar is the pivot of every conversion: a price in a listing currency becomes US dollars, then euros
        or pounds through their own series. FRED's daily series start in 1971 (1999 for the euro), so a price older
        than its series is shown in its listing currency only.
    """

    CURRENCY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{3}$")
    SERIES: ClassVar[Pattern[str]] = re.compile(r"^[A-Z0-9]{4,30}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    currency: str = Field(description="The currency.")
    series: str = Field(description="The FRED series.")
    quote: FxQuote = Field(description="How the series is quoted.")

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

    @field_validator("series", mode="before")
    def validate_series(cls, value: JsonValue) -> JsonValue:
        """Validate the raw FRED series: upper-case letters and digits.

        Args:
            value (JsonValue): The raw series.

        Returns:
            JsonValue: The series, upper-cased.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not 4 to 30 letters or digits.
        """
        series = (cls.CHECK.text(value, "FRED series", 30) or "").upper()
        if not cls.SERIES.match(series):
            raise InvalidMarketValueError("FRED series", series, "4 to 30 letters or digits")
        return series

    @field_validator("quote", mode="before")
    def validate_quote(cls, value: JsonValue) -> JsonValue:
        """Validate the raw quotation: a `FxQuote` value.

        Args:
            value (JsonValue): The raw quotation.

        Returns:
            JsonValue: The quotation.

        Raises:
            InvalidMarketChoiceError: If it is not a known quotation.
        """
        return cls.CHECK.choice(value, "FRED quotation", [quote.value for quote in FxQuote])
