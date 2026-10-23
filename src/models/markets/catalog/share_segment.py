from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.enums import Device, ShareMetric, ShareSource, StatCounterStat
from models.markets.exception import InvalidMarketListError, InvalidMarketValueError
from models.markets.field_check import MarketFieldCheck


class ShareSegment(BaseModel):
    """A market whose shares are followed over time, e.g. web search or smartphone operating systems.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a key: lower-case words joined by hyphens.
        MONTH (ClassVar[Pattern[str]]): The format of a month: `YYYY-MM`.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        key (str): Its key, e.g. `search`.
        label (str): Its name, e.g. `Web search`.
        chronology (Optional[str]): The segment of the leaders chronology it measures, if any (a click on a leader
            band of that segment opens it).
        source (ShareSource): Where its shares come from.
        stat (Optional[StatCounterStat]): The StatCounter statistic read, for a StatCounter segment.
        metric (ShareMetric): What the shares are a share of.
        devices (List[Device]): The devices its shares are measured on, the default one first.
        first_month (Optional[str]): The first month the source publishes, `YYYY-MM`, when later than the
            catalogue's start (e.g. the AI chatbots, from 2025-04).
        description (str): Its definition: what is measured, and how it differs from units or revenue.
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    MONTH: ClassVar[Pattern[str]] = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(description="Its key.")
    label: str = Field(min_length=1, description="Its name.")
    chronology: Optional[str] = Field(default=None, description="The chronology segment it measures.")
    source: ShareSource = Field(description="Where its shares come from.")
    stat: Optional[StatCounterStat] = Field(default=None, description="The StatCounter statistic read.")
    metric: ShareMetric = Field(description="What the shares are a share of.")
    devices: List[Device] = Field(default_factory=lambda: [Device.ALL], min_length=1, description="The devices.")
    first_month: Optional[str] = Field(default=None, description="The first month published, YYYY-MM.")
    description: str = Field(default="", description="Its definition.")

    @field_validator("key", "chronology", mode="before")
    def validate_key(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw key: lower-case words joined by hyphens (the chronology segment may be missing).

        Args:
            value (JsonValue): The raw key.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The key, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not lower-case words joined by hyphens.
        """
        optional = info.field_name == "chronology"
        key = cls.CHECK.text(value, "segment key", 40, optional=optional)
        if key is None:
            return None
        if not cls.KEY.match(key):
            raise InvalidMarketValueError("segment key", key, "lower-case words joined by hyphens")
        return key

    @field_validator("label", mode="before")
    def validate_label(cls, value: JsonValue) -> JsonValue:
        """Validate the raw name: a text of 1 to 80 characters, single-spaced.

        Args:
            value (JsonValue): The raw name.

        Returns:
            JsonValue: The name.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 80 characters.
        """
        return cls.CHECK.text(value, "segment name", 80)

    @field_validator("description", mode="before")
    def validate_description(cls, value: JsonValue) -> JsonValue:
        """Validate the raw definition: a text of at most 600 characters, single-spaced.

        Args:
            value (JsonValue): The raw definition.

        Returns:
            JsonValue: The definition, empty when missing.

        Raises:
            InvalidMarketTextError: If it is not a text of at most 600 characters.
        """
        return cls.CHECK.text(value, "segment definition", 600, minimum=0, optional=True) or ""

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
        return cls.CHECK.choice(value, "segment source", [source.value for source in ShareSource])

    @field_validator("stat", mode="before")
    def validate_stat(cls, value: JsonValue) -> JsonValue:
        """Validate the raw StatCounter statistic: a `StatCounterStat` value, or none.

        Args:
            value (JsonValue): The raw statistic.

        Returns:
            JsonValue: The statistic, `None` when missing.

        Raises:
            InvalidMarketChoiceError: If it is not a known statistic.
        """
        return cls.CHECK.choice(value, "StatCounter statistic", [stat.value for stat in StatCounterStat], optional=True)

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
        return cls.CHECK.choice(value, "segment metric", [metric.value for metric in ShareMetric])

    @field_validator("devices", mode="before")
    def validate_devices(cls, value: JsonValue) -> JsonValue:
        """Validate the raw devices: at least one `Device` value, each once, in their order.

        Args:
            value (JsonValue): The raw devices.

        Returns:
            JsonValue: The devices, each once.

        Raises:
            InvalidMarketListError: If it is not a non-empty list.
            InvalidMarketChoiceError: If a device is unknown.
        """
        choices = [device.value for device in Device]
        devices = [cls.CHECK.choice(item, "device", choices) for item in cls.CHECK.items(value, "devices", "devices")]
        if not devices:
            raise InvalidMarketListError("devices", "at least one device")
        unique: List[JsonValue] = [*dict.fromkeys(devices)]
        return unique

    @field_validator("first_month", mode="before")
    def validate_first_month(cls, value: JsonValue) -> JsonValue:
        """Validate the raw first month: `YYYY-MM`, or none.

        Args:
            value (JsonValue): The raw month.

        Returns:
            JsonValue: The month, trimmed, `None` when missing.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not written `YYYY-MM`.
        """
        month = cls.CHECK.text(value, "first month", 7, optional=True)
        if month is not None and not cls.MONTH.match(month):
            raise InvalidMarketValueError("first month", month, "YYYY-MM")
        return month
