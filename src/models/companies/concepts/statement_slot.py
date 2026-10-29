from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.enums import FinancialMetric
from models.markets.field_check import MarketFieldCheck


class StatementSlot(BaseModel):
    """Where a statement line sits in the value list of a Google Finance period.

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        metric (FinancialMetric): The statement line.
        slot (int): Its position in the value list (Google moves them without notice: they are configuration).
        negate (bool): Whether Google states the opposite of the stored value (the capital expenditure is negative).
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: FinancialMetric = Field(description="The statement line.")
    slot: int = Field(ge=0, le=500, description="Its position in the value list.")
    negate: bool = Field(default=False, description="Whether Google states the opposite of the stored value.")

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
        return cls.CHECK.choice(value, "statement slot line", [metric.value for metric in FinancialMetric])

    @field_validator("slot", mode="before")
    def validate_slot(cls, value: JsonValue) -> JsonValue:
        """Validate the raw position: a whole number from 0 to 500.

        Args:
            value (JsonValue): The raw position.

        Returns:
            JsonValue: The position.

        Raises:
            InvalidMarketNumberError: If it is not a whole number from 0 to 500.
        """
        return cls.CHECK.number(value, "statement slot", low=0, high=500, integer=True)

    @field_validator("negate", mode="before")
    def validate_negate(cls, value: JsonValue) -> JsonValue:
        """Validate the raw sign flag: a boolean.

        Args:
            value (JsonValue): The raw flag.

        Returns:
            JsonValue: The flag.

        Raises:
            InvalidMarketFlagError: If it is not a boolean.
        """
        return cls.CHECK.flag(value, "negated slot")
