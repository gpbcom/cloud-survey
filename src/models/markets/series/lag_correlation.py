from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.field_check import MarketFieldCheck


class LagCorrelation(BaseModel):
    """The rank correlation of the share changes with the stock returns some periods later (or earlier).

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        lag (int): The periods the returns follow the share changes (negative: the returns come first).
        rho (Optional[float]): The Spearman correlation, `None` when it cannot be computed.
        low (Optional[float]): The low end of its 95% block-bootstrap interval.
        high (Optional[float]): The high end of its 95% block-bootstrap interval.
        p_value (Optional[float]): Its two-sided p-value.
        q_value (Optional[float]): Its Benjamini-Hochberg q-value over the lags tested.
        months (int): The periods paired.
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    lag: int = Field(ge=-24, le=24, description="The periods the returns follow the share changes.")
    rho: Optional[float] = Field(default=None, ge=-1, le=1, description="The Spearman correlation.")
    low: Optional[float] = Field(default=None, ge=-1, le=1, description="The low end of its interval.")
    high: Optional[float] = Field(default=None, ge=-1, le=1, description="The high end of its interval.")
    p_value: Optional[float] = Field(default=None, ge=0, le=1, description="Its p-value.")
    q_value: Optional[float] = Field(default=None, ge=0, le=1, description="Its q-value.")
    months: int = Field(default=0, ge=0, description="The periods paired.")

    @field_validator("lag", mode="before")
    def validate_lag(cls, value: JsonValue) -> JsonValue:
        """Validate the raw lag: a whole number from -24 to 24.

        Args:
            value (JsonValue): The raw lag.

        Returns:
            JsonValue: The lag.

        Raises:
            InvalidMarketNumberError: If it is not a whole number from -24 to 24.
        """
        return cls.CHECK.number(value, "correlation lag", low=-24, high=24, integer=True)

    @field_validator("rho", "low", "high", mode="before")
    def validate_correlation(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw correlation or interval end: a number from -1 to 1, or none.

        Args:
            value (JsonValue): The raw value.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The value.

        Raises:
            InvalidMarketNumberError: If it is neither missing nor a number from -1 to 1.
        """
        return cls.CHECK.number(value, f"correlation {info.field_name}", low=-1, high=1, optional=True)

    @field_validator("p_value", "q_value", mode="before")
    def validate_probability(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw p-value or q-value: a number from 0 to 1, or none.

        Args:
            value (JsonValue): The raw value.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The value.

        Raises:
            InvalidMarketNumberError: If it is neither missing nor a number from 0 to 1.
        """
        return cls.CHECK.number(value, f"correlation {info.field_name}", low=0, high=1, optional=True)

    @field_validator("months", mode="before")
    def validate_months(cls, value: JsonValue) -> JsonValue:
        """Validate the raw count of pairs: a whole number of at least 0.

        Args:
            value (JsonValue): The raw count.

        Returns:
            JsonValue: The count.

        Raises:
            InvalidMarketNumberError: If it is not a whole number of at least 0.
        """
        return cls.CHECK.number(value, "correlation pairs", low=0, integer=True)
