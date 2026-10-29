from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.enums import FinancialMetric
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class ScheduleTag(BaseModel):
    """The statement line a tag of the SEC financial data schedules (EX-27, 1993 to 2001) stands for.

    Attributes:
        TAG (ClassVar[Pattern[str]]): The format of a tag: upper-case words joined by hyphens.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        tag (str): The tag, e.g. `TOTAL-REVENUES`.
        metric (FinancialMetric): The statement line.
        rank (int): Its preference among the tags of the line (0 first: `TOTAL-REVENUES` before `SALES`).
        sum (bool): Whether the line is the sum of its tags (the equity is the common stock, the other equity and
            the preferred stock) rather than the first one stated.
        per_share (bool): Whether the figure is per share (the schedule's multiplier does not apply).
    """

    TAG: ClassVar[Pattern[str]] = re.compile(r"^[A-Z0-9&]+(?:-[A-Z0-9&]+)*$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    tag: str = Field(description="The tag.")
    metric: FinancialMetric = Field(description="The statement line.")
    rank: int = Field(default=0, ge=0, le=20, description="Its preference among the tags of the line.")
    sum: bool = Field(default=False, description="Whether the line is the sum of its tags.")
    per_share: bool = Field(default=False, description="Whether the figure is per share.")

    @field_validator("tag", mode="before")
    def validate_tag(cls, value: JsonValue) -> JsonValue:
        """Validate the raw tag: upper-case words joined by hyphens.

        Args:
            value (JsonValue): The raw tag.

        Returns:
            JsonValue: The tag.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 40 characters.
            InvalidCompanyValueError: If it is not upper-case words joined by hyphens.
        """
        tag = cls.CHECK.text(value, "schedule tag", 40) or ""
        if not cls.TAG.match(tag):
            raise InvalidCompanyValueError("schedule tag", tag, "upper-case words joined by hyphens")
        return tag

    @field_validator("metric", mode="before")
    def validate_metric(cls, value: JsonValue) -> JsonValue:
        """Validate the raw statement line: one of the financial metrics.

        Args:
            value (JsonValue): The raw line.

        Returns:
            JsonValue: The line.

        Raises:
            InvalidMarketChoiceError: If it is not a financial metric.
        """
        return cls.CHECK.choice(value, "schedule tag line", [metric.value for metric in FinancialMetric])

    @field_validator("rank", mode="before")
    def validate_rank(cls, value: JsonValue) -> JsonValue:
        """Validate the raw preference: a whole number from 0 to 20.

        Args:
            value (JsonValue): The raw preference.

        Returns:
            JsonValue: The preference.

        Raises:
            InvalidMarketNumberError: If it is not a whole number from 0 to 20.
        """
        return cls.CHECK.number(value, "schedule tag rank", low=0, high=20, integer=True)

    @field_validator("sum", "per_share", mode="before")
    def validate_flag(cls, value: JsonValue) -> JsonValue:
        """Validate a raw flag: a boolean.

        Args:
            value (JsonValue): The raw flag.

        Returns:
            JsonValue: The flag.

        Raises:
            InvalidMarketFlagError: If it is not a boolean.
        """
        return cls.CHECK.flag(value, "schedule tag flag")
