from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.markets.exception import InvalidMarketValueError
from models.markets.field_check import MarketFieldCheck


class ChartDot(BaseModel):
    """A lone point of a time chart: a sourced valuation of a company without a price history.

    Attributes:
        COLOR (ClassVar[Pattern[str]]): The format of a colour: `#rrggbb`.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        day (date): When.
        value (float): The value.
        color (str): Its colour, `#rrggbb` (its company's).
        label (str): Its caption, e.g. `DEC: to Compaq`.
        tooltip (str): What hovering it explains (its source and its tag).
    """

    COLOR: ClassVar[Pattern[str]] = re.compile(r"^#[0-9a-fA-F]{6}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: date = Field(description="When.")
    value: float = Field(gt=0, description="The value.")
    color: str = Field(description="Its colour.")
    label: str = Field(min_length=1, description="Its caption.")
    tooltip: str = Field(default="", description="What hovering it explains.")

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
        return cls.CHECK.iso_day(value, "dot day")

    @field_validator("value", mode="before")
    def validate_value(cls, value: JsonValue) -> JsonValue:
        """Validate the raw value: a number above zero (the dots sit on a logarithmic axis).

        Args:
            value (JsonValue): The raw value.

        Returns:
            JsonValue: The value.

        Raises:
            InvalidMarketNumberError: If it is not a number above zero.
        """
        return cls.CHECK.number(value, "dot value", low=0.0, strict_low=True)

    @field_validator("color", mode="before")
    def validate_color(cls, value: JsonValue) -> JsonValue:
        """Validate the raw colour: `#rrggbb`, lower-cased.

        Args:
            value (JsonValue): The raw colour.

        Returns:
            JsonValue: The colour.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not written `#rrggbb`.
        """
        color = (cls.CHECK.text(value, "dot colour", 7) or "").lower()
        if not cls.COLOR.match(color):
            raise InvalidMarketValueError("dot colour", color, "#rrggbb")
        return color

    @field_validator("label", mode="before")
    def validate_label(cls, value: JsonValue) -> JsonValue:
        """Validate the raw caption: a text of 1 to 200 characters.

        Args:
            value (JsonValue): The raw caption.

        Returns:
            JsonValue: The caption, single-spaced.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 200 characters.
        """
        return cls.CHECK.text(value, "dot caption", 200)

    @field_validator("tooltip", mode="before")
    def validate_tooltip(cls, value: JsonValue) -> JsonValue:
        """Validate the raw tooltip: a rich text of at most 2000 characters, empty when missing.

        Args:
            value (JsonValue): The raw tooltip.

        Returns:
            JsonValue: The tooltip.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text of at most 2000 characters.
        """
        return cls.CHECK.text(value, "dot tooltip", 2000, optional=True) or ""
