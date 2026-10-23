from __future__ import annotations

# Standard Library Imports.
from datetime import date
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.field_check import MarketFieldCheck


class StockSeries(BaseModel):
    """The value of a listing (or of a region index) over time, in a currency: a chart line.

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        key (str): The listing `EXCHANGE:SYMBOL`, or `region:<key>` for a region index.
        company (Optional[str]): The company of the chronology, `None` for a region index.
        label (str): The name drawn, e.g. `TSMC (TPE:2330)`.
        currency (str): The currency of the values, or `index` for a series rebased to 100.
        primary (bool): Whether it is the company's main listing (a secondary one is drawn dashed).
        points (List[Tuple[date, float]]): The value by day, oldest first.
        note (Optional[str]): What the listing stands for, or why some points are missing.
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1, description="The listing or the region index.")
    company: Optional[str] = Field(default=None, description="The company.")
    label: str = Field(min_length=1, description="The name drawn.")
    currency: str = Field(min_length=1, description="The currency of the values.")
    primary: bool = Field(default=True, description="Whether it is the main listing.")
    points: List[Tuple[date, float]] = Field(default_factory=list, description="The value by day.")
    note: Optional[str] = Field(default=None, description="What the listing stands for.")

    @field_validator("key", "label", "currency", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw key, name or currency: a text of 1 to 120 characters.

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 120 characters.
        """
        return cls.CHECK.text(value, f"stock series {info.field_name}", 120)

    @field_validator("company", mode="before")
    def validate_company(cls, value: JsonValue) -> JsonValue:
        """Validate the raw company: a text of at most 40 characters, `None` for a region index.

        Args:
            value (JsonValue): The raw company.

        Returns:
            JsonValue: The company key.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text of at most 40 characters.
        """
        return cls.CHECK.text(value, "stock series company", 40, optional=True)

    @field_validator("primary", mode="before")
    def validate_primary(cls, value: JsonValue) -> JsonValue:
        """Validate the raw primary flag: a boolean.

        Args:
            value (JsonValue): The raw flag.

        Returns:
            JsonValue: The flag.

        Raises:
            InvalidMarketFlagError: If it is not a boolean.
        """
        return cls.CHECK.flag(value, "primary listing")

    @field_validator("points", mode="before")
    def validate_points(cls, value: JsonValue) -> JsonValue:
        """Validate the raw points: `(date, value)` pairs, the values above zero, sorted by date.

        Args:
            value (JsonValue): The raw points.

        Returns:
            JsonValue: The points, oldest first.

        Raises:
            InvalidMarketListError: If they are not `(date, number)` pairs with numbers above zero.
        """
        pairs = cls.CHECK.points(value, "stock points", positive=True)
        points: List[JsonValue] = [[day.isoformat(), number] for day, number in pairs]
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
        return cls.CHECK.text(value, "stock series note", 600, optional=True)
