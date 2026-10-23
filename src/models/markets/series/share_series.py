from __future__ import annotations

# Standard Library Imports.
from datetime import date
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.markets.field_check import MarketFieldCheck


class ShareSeries(BaseModel):
    """The share of a company (or of the others) over time, in a segment, an area and on a device: a chart line.

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        company (Optional[str]): The company of the chronology, `None` for the others.
        label (str): The name drawn, e.g. `Google` or `Others`.
        labels (List[str]): The source labels summed into it, e.g. `Chrome`, `Chromium`.
        points (List[Tuple[date, float]]): The share by period, in percent, oldest first.
        estimate (bool): Whether the shares are estimated (the EU-27).
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: Optional[str] = Field(default=None, description="The company, None for the others.")
    label: str = Field(min_length=1, description="The name drawn.")
    labels: List[str] = Field(default_factory=list, description="The source labels summed into it.")
    points: List[Tuple[date, float]] = Field(default_factory=list, description="The share by period.")
    estimate: bool = Field(default=False, description="Whether the shares are estimated.")

    @field_validator("company", mode="before")
    def validate_company(cls, value: JsonValue) -> JsonValue:
        """Validate the raw company: a text of at most 40 characters, `None` for the others.

        Args:
            value (JsonValue): The raw company.

        Returns:
            JsonValue: The company key.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text of at most 40 characters.
        """
        return cls.CHECK.text(value, "series company", 40, optional=True)

    @field_validator("label", mode="before")
    def validate_label(cls, value: JsonValue) -> JsonValue:
        """Validate the raw name: a text of 1 to 120 characters.

        Args:
            value (JsonValue): The raw name.

        Returns:
            JsonValue: The name, single-spaced.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 120 characters.
        """
        return cls.CHECK.text(value, "series name", 120)

    @field_validator("labels", mode="before")
    def validate_labels(cls, value: JsonValue) -> JsonValue:
        """Validate the raw source labels: texts of 1 to 80 characters.

        Args:
            value (JsonValue): The raw labels.

        Returns:
            JsonValue: The labels, trimmed.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketTextError: If a label is not a text of 1 to 80 characters.
        """
        labels: List[JsonValue] = [
            cls.CHECK.text(item, "source label", 80, collapse=False)
            for item in cls.CHECK.items(value, "source labels", "texts")
        ]
        return labels

    @field_validator("points", mode="before")
    def validate_points(cls, value: JsonValue) -> JsonValue:
        """Validate the raw points: `(date, share)` pairs, sorted by date.

        Args:
            value (JsonValue): The raw points.

        Returns:
            JsonValue: The points, oldest first.

        Raises:
            InvalidMarketListError: If they are not `(date, number)` pairs.
        """
        points: List[JsonValue] = [[day.isoformat(), share] for day, share in cls.CHECK.points(value, "share points")]
        return points

    @field_validator("estimate", mode="before")
    def validate_estimate(cls, value: JsonValue) -> JsonValue:
        """Validate the raw estimate flag: a boolean.

        Args:
            value (JsonValue): The raw flag.

        Returns:
            JsonValue: The flag.

        Raises:
            InvalidMarketFlagError: If it is not a boolean.
        """
        return cls.CHECK.flag(value, "series estimate")
