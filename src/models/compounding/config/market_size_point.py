from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.compounding.exception import InvalidCompoundingValueError
from models.markets.field_check import MarketFieldCheck


class MarketSizePoint(BaseModel):
    """A curated yearly size of the worldwide cloud infrastructure services market.

    Attributes:
        URL (ClassVar[Pattern[str]]): The format of a source.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        year (int): The year.
        size_bn (float): The market size, in billion USD.
        source (str): The document giving it (a web address).

    Notes:
        A curated size is used only for a year the Synergy crawl gives no figure for.
    """

    URL: ClassVar[Pattern[str]] = re.compile(r"^https?://\S+$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    year: int = Field(description="The year.")
    size_bn: float = Field(description="The market size, in billion USD.")
    source: str = Field(description="The document giving it.")

    @field_validator("year", mode="before")
    def validate_year(cls, value: JsonValue) -> JsonValue:
        """Validate the raw year: a year between 2000 and 2100.

        Args:
            value (JsonValue): The raw year.

        Returns:
            JsonValue: The year.

        Raises:
            InvalidMarketNumberError: If it is not a whole year in range.
        """
        return cls.CHECK.number(value, "market year", low=2000, high=2100, integer=True)

    @field_validator("size_bn", mode="before")
    def validate_size(cls, value: JsonValue) -> JsonValue:
        """Validate the raw size: a positive number of billions.

        Args:
            value (JsonValue): The raw size.

        Returns:
            JsonValue: The size.

        Raises:
            InvalidMarketNumberError: If it is not a positive number.
        """
        return cls.CHECK.number(value, "market size", low=0, high=10000, strict_low=True)

    @field_validator("source", mode="before")
    def validate_source(cls, value: JsonValue) -> JsonValue:
        """Validate the raw source: a web address.

        Args:
            value (JsonValue): The raw source.

        Returns:
            JsonValue: The source.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompoundingValueError: If it is not a web address.
        """
        source = cls.CHECK.text(value, "market size source", 500) or ""
        if not cls.URL.match(source):
            raise InvalidCompoundingValueError("market size source", source, "a web address")
        return source
