from __future__ import annotations

# Standard Library Imports.
from datetime import date
from typing import ClassVar

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.markets.enums import Device, StatCounterStat
from models.markets.field_check import MarketFieldCheck


class ShareObservation(BaseModel):
    """A usage share as StatCounter prints it: a label's share of a statistic, in an area, on a device, for a month.

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        stat (StatCounterStat): The statistic, e.g. search engines.
        area (str): The StatCounter region, e.g. `ww` or `US`.
        device (Device): The devices measured.
        month (date): The first day of the month.
        label (str): The label, as printed (`bing`, `Chrome`).
        value (float): The share, in percent of the page views.
        source_url (str): The CSV read.
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    stat: StatCounterStat = Field(description="The statistic.")
    area: str = Field(min_length=2, max_length=12, description="The StatCounter region.")
    device: Device = Field(description="The devices measured.")
    month: date = Field(description="The first day of the month.")
    label: str = Field(min_length=1, max_length=80, description="The label, as printed.")
    value: float = Field(ge=0, le=100, description="The share, in percent.")
    source_url: str = Field(min_length=1, max_length=2048, description="The CSV read.")

    @field_validator("stat", mode="before")
    def validate_stat(cls, value: JsonValue) -> JsonValue:
        """Validate the raw statistic: a `StatCounterStat` value.

        Args:
            value (JsonValue): The raw statistic.

        Returns:
            JsonValue: The statistic.

        Raises:
            InvalidMarketChoiceError: If it is not a known statistic.
        """
        return cls.CHECK.choice(value, "StatCounter statistic", [stat.value for stat in StatCounterStat])

    @field_validator("area", mode="before")
    def validate_area(cls, value: JsonValue) -> JsonValue:
        """Validate the raw region: a text of 2 to 12 characters.

        Args:
            value (JsonValue): The raw region.

        Returns:
            JsonValue: The region, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text of 2 to 12 characters.
        """
        return cls.CHECK.text(value, "StatCounter region", 12, minimum=2)

    @field_validator("device", mode="before")
    def validate_device(cls, value: JsonValue) -> JsonValue:
        """Validate the raw devices: a `Device` value.

        Args:
            value (JsonValue): The raw devices.

        Returns:
            JsonValue: The devices.

        Raises:
            InvalidMarketChoiceError: If it is not a known device choice.
        """
        return cls.CHECK.choice(value, "device", [device.value for device in Device])

    @field_validator("month", mode="before")
    def validate_month(cls, value: JsonValue) -> JsonValue:
        """Validate the raw month: `YYYY-MM` (read as its first day) or a date.

        Args:
            value (JsonValue): The raw month.

        Returns:
            JsonValue: The first day of the month.

        Raises:
            InvalidMarketDateError: If it is not a month nor a date.
        """
        if isinstance(value, str) and len(value.strip()) == 7:
            value = f"{value.strip()}-01"
        day = cls.CHECK.day(value, "StatCounter month")
        return day.replace(day=1).isoformat() if day else None

    @field_validator("label", mode="before")
    def validate_label(cls, value: JsonValue) -> JsonValue:
        """Validate the raw label: a text of 1 to 80 characters, trimmed (labels are matched exactly).

        Args:
            value (JsonValue): The raw label.

        Returns:
            JsonValue: The label.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 80 characters.
        """
        return cls.CHECK.text(value, "StatCounter label", 80, collapse=False)

    @field_validator("value", mode="before")
    def validate_value(cls, value: JsonValue) -> JsonValue:
        """Validate the raw share: a number from 0 to 100.

        Args:
            value (JsonValue): The raw share.

        Returns:
            JsonValue: The share.

        Raises:
            InvalidMarketNumberError: If it is not a number from 0 to 100.
        """
        return cls.CHECK.number(value, "StatCounter share", low=0, high=100)

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
        return cls.CHECK.text(value, "StatCounter document", 2048, collapse=False)
