from __future__ import annotations

# Standard Library Imports.
from datetime import date
from typing import ClassVar, Dict, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.enums import Device, Granularity, ShareMetric, ShareSource
from models.markets.field_check import MarketFieldCheck


class MarketShareValue(BaseModel):
    """A stored market share: a label's share of a segment, in an area, on a device, for a period, from a source.

    Attributes:
        TEXTS (ClassVar[Dict[str, int]]): The longest text of each text field.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        segment (str): The segment, e.g. `search`.
        area (str): The area, e.g. `ww`, `US` or `eu27`.
        period (date): The first day of the period.
        granularity (Granularity): Whether the period is a month, a quarter or a year.
        metric (ShareMetric): What the share is a share of.
        device (Device): The devices measured (`all` for the sources that do not split them).
        source (ShareSource): Where it comes from.
        label (str): The label, as the source prints it.
        company (Optional[str]): The company of the chronology behind the label, `None` for the others.
        value (float): The share, in percent.
        estimate (bool): Whether it is estimated rather than published (the EU-27 from its members).
        source_url (Optional[str]): The document read.
    """

    TEXTS: ClassVar[Dict[str, int]] = {"segment": 40, "area": 12, "label": 80, "company": 40, "source_url": 2048}
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    segment: str = Field(min_length=1, max_length=40, description="The segment.")
    area: str = Field(min_length=2, max_length=12, description="The area.")
    period: date = Field(description="The first day of the period.")
    granularity: Granularity = Field(default=Granularity.MONTH, description="The kind of period.")
    metric: ShareMetric = Field(description="What the share is a share of.")
    device: Device = Field(default=Device.ALL, description="The devices measured.")
    source: ShareSource = Field(description="Where it comes from.")
    label: str = Field(min_length=1, max_length=80, description="The label, as printed.")
    company: Optional[str] = Field(default=None, max_length=40, description="The company behind the label.")
    value: float = Field(ge=0, le=100, description="The share, in percent.")
    estimate: bool = Field(default=False, description="Whether it is estimated.")
    source_url: Optional[str] = Field(default=None, max_length=2048, description="The document read.")

    @field_validator("segment", "area", "label", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw text: trimmed, within its length (an area has at least 2 characters).

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text.

        Raises:
            InvalidMarketTextError: If it is not a text of the right length.
        """
        name = str(info.field_name)
        minimum = 2 if name == "area" else 1
        return cls.CHECK.text(value, f"share {name}", cls.TEXTS[name], minimum=minimum, collapse=False)

    @field_validator("company", "source_url", mode="before")
    def validate_optional_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw optional text: trimmed, within its length, `None` when blank.

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text of the right length.
        """
        name = str(info.field_name)
        return cls.CHECK.text(value, f"share {name}", cls.TEXTS[name], optional=True, collapse=False)

    @field_validator("period", mode="before")
    def validate_period(cls, value: JsonValue) -> JsonValue:
        """Validate the raw period: its first day.

        Args:
            value (JsonValue): The raw period.

        Returns:
            JsonValue: The day.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        return cls.CHECK.iso_day(value, "share period")

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
        return cls.CHECK.choice(value, "share granularity", [granularity.value for granularity in Granularity])

    @field_validator("metric", mode="before")
    def validate_metric(cls, value: JsonValue) -> JsonValue:
        """Validate the raw metric: a `ShareMetric` value.

        Args:
            value (JsonValue): The raw metric.

        Returns:
            JsonValue: The metric.

        Raises:
            InvalidMarketChoiceError: If it is not a known metric.
        """
        return cls.CHECK.choice(value, "share metric", [metric.value for metric in ShareMetric])

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
        return cls.CHECK.choice(value, "share device", [device.value for device in Device])

    @field_validator("source", mode="before")
    def validate_source(cls, value: JsonValue) -> JsonValue:
        """Validate the raw source: a `ShareSource` value.

        Args:
            value (JsonValue): The raw source.

        Returns:
            JsonValue: The source.

        Raises:
            InvalidMarketChoiceError: If it is not a known share source.
        """
        return cls.CHECK.choice(value, "share source", [source.value for source in ShareSource])

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
        return cls.CHECK.number(value, "share value", low=0, high=100)

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
        return cls.CHECK.flag(value, "share estimate")
