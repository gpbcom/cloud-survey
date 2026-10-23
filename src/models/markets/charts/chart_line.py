from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, List, Optional, Pattern, Tuple

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.exception import InvalidMarketValueError
from models.markets.field_check import MarketFieldCheck


class ChartLine(BaseModel):
    """A line of a time chart of the markets cards: a company's share, a listing's value or a region index.

    Attributes:
        COLOR (ClassVar[Pattern[str]]): The format of a colour: `#rrggbb`.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        key (str): What the line is, e.g. `google` or `NYSE:IBM` (the legend toggles it by key).
        label (str): Its name in the legend and the tooltips.
        color (str): Its colour, `#rrggbb`.
        dashed (bool): Whether it is drawn dashed (a secondary listing, an estimate).
        dots (bool): Whether each point is drawn as a dot (a quarterly or yearly source, never interpolated).
        points (List[Tuple[date, float]]): Its values by day, oldest first.
        note (Optional[str]): What its tooltip adds, e.g. its source labels or its listing.
    """

    COLOR: ClassVar[Pattern[str]] = re.compile(r"^#[0-9a-fA-F]{6}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1, description="What the line is.")
    label: str = Field(min_length=1, description="Its name.")
    color: str = Field(description="Its colour.")
    dashed: bool = Field(default=False, description="Whether it is dashed.")
    dots: bool = Field(default=False, description="Whether each point is a dot.")
    points: List[Tuple[date, float]] = Field(default_factory=list, description="Its values by day.")
    note: Optional[str] = Field(default=None, description="What its tooltip adds.")

    @field_validator("key", "label", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw key or name: a text of 1 to 120 characters.

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 120 characters.
        """
        return cls.CHECK.text(value, f"line {info.field_name}", 120)

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
        color = (cls.CHECK.text(value, "line colour", 7) or "").lower()
        if not cls.COLOR.match(color):
            raise InvalidMarketValueError("line colour", color, "#rrggbb")
        return color

    @field_validator("dashed", "dots", mode="before")
    def validate_flag(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw drawing flag: a boolean.

        Args:
            value (JsonValue): The raw flag.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The flag.

        Raises:
            InvalidMarketFlagError: If it is not a boolean.
        """
        return cls.CHECK.flag(value, f"line {info.field_name} flag")

    @field_validator("points", mode="before")
    def validate_points(cls, value: JsonValue) -> JsonValue:
        """Validate the raw points: `(date, number)` pairs, sorted by date.

        Args:
            value (JsonValue): The raw points.

        Returns:
            JsonValue: The points, oldest first.

        Raises:
            InvalidMarketListError: If they are not `(date, number)` pairs.
        """
        points: List[JsonValue] = [[day.isoformat(), number] for day, number in cls.CHECK.points(value, "line points")]
        return points

    @field_validator("note", mode="before")
    def validate_note(cls, value: JsonValue) -> JsonValue:
        """Validate the raw note: a text of at most 600 characters, `None` when blank.

        Args:
            value (JsonValue): The raw note.

        Returns:
            JsonValue: The note.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text of at most 600 characters.
        """
        return cls.CHECK.text(value, "line note", 600, optional=True)
