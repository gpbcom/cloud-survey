from __future__ import annotations

# Standard Library Imports.
from datetime import date
from typing import ClassVar, Dict

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.enums import Granularity, ShareSource
from models.markets.field_check import MarketFieldCheck


class ReleaseShare(BaseModel):
    """A share as an analyst press release states it: a company's share of a segment, in an area, for a period.

    Attributes:
        TEXTS (ClassVar[Dict[str, int]]): The longest text of each text field.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        source (ShareSource): The firm, e.g. IDC.
        segment (str): The segment of the release family.
        area (str): The area of the release family.
        period (date): The first day of the period.
        granularity (Granularity): Whether the period is a quarter or a year.
        label (str): The company as the release names it, e.g. `HP Inc`.
        value (float): The share, in percent.
        title (str): The title of the release.
        published (date): When the release was published.
        source_url (str): The release.
    """

    TEXTS: ClassVar[Dict[str, int]] = {"segment": 40, "area": 12, "label": 80, "title": 400, "source_url": 2048}
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: ShareSource = Field(description="The firm.")
    segment: str = Field(min_length=1, max_length=40, description="The segment.")
    area: str = Field(min_length=2, max_length=12, description="The area.")
    period: date = Field(description="The first day of the period.")
    granularity: Granularity = Field(description="Whether the period is a quarter or a year.")
    label: str = Field(min_length=1, max_length=80, description="The company, as named.")
    value: float = Field(ge=0, le=100, description="The share, in percent.")
    title: str = Field(min_length=1, max_length=400, description="The title of the release.")
    published: date = Field(description="When it was published.")
    source_url: str = Field(min_length=1, max_length=2048, description="The release.")

    @field_validator("source", mode="before")
    def validate_source(cls, value: JsonValue) -> JsonValue:
        """Validate the raw firm: a `ShareSource` value.

        Args:
            value (JsonValue): The raw firm.

        Returns:
            JsonValue: The firm.

        Raises:
            InvalidMarketChoiceError: If it is not a known share source.
        """
        return cls.CHECK.choice(value, "release firm", [source.value for source in ShareSource])

    @field_validator("segment", "area", "label", "title", "source_url", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw text: single-spaced, within its length (an area has at least 2 characters).

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text.

        Raises:
            InvalidMarketTextError: If it is not a text of the right length.
        """
        name = str(info.field_name)
        return cls.CHECK.text(value, f"release {name}", cls.TEXTS[name], minimum=2 if name == "area" else 1)

    @field_validator("period", "published", mode="before")
    def validate_day(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw date: the first day of the period, or the publication day.

        Args:
            value (JsonValue): The raw date.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The date.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        return cls.CHECK.iso_day(value, f"release {info.field_name}")

    @field_validator("granularity", mode="before")
    def validate_granularity(cls, value: JsonValue) -> JsonValue:
        """Validate the raw granularity: a `Granularity` value.

        Args:
            value (JsonValue): The raw granularity.

        Returns:
            JsonValue: The granularity.

        Raises:
            InvalidMarketChoiceError: If it is not a known granularity.
        """
        return cls.CHECK.choice(value, "release granularity", [granularity.value for granularity in Granularity])

    @field_validator("value", mode="before")
    def validate_value(cls, value: JsonValue) -> JsonValue:
        """Validate the raw share: a number from 0 to 100 (a `%` sign is allowed).

        Args:
            value (JsonValue): The raw share.

        Returns:
            JsonValue: The share.

        Raises:
            InvalidMarketNumberError: If it is not a number from 0 to 100.
        """
        return cls.CHECK.number(value, "release share", low=0, high=100)
