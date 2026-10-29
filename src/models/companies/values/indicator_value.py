from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.enums import CompanyIndicator, FinancialGranularity, IndicatorUnit
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class IndicatorValue(BaseModel):
    """A point of an indicator's time series: the value of an indicator of a company for one period.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a company key.
        CURRENCY (ClassVar[Pattern[str]]): The format of a currency.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        company (str): The company.
        indicator (CompanyIndicator): The indicator.
        period_end (date): The last day of the period (the last trading day of a week, the 31 December of a
            calendar year for the patents and the papers).
        granularity (FinancialGranularity): The period: a week, a quarter, a year or the trailing twelve months.
        value (float): The value, in its unit.
        unit (IndicatorUnit): The unit.
        currency (Optional[str]): The currency of an amount, `None` otherwise.
        value_usd (Optional[float]): The amount in US dollars at the rate of the period's last day, `None` when not
            an amount or when no rate is stored.
        inputs (str): How it was computed, e.g. `net-income / avg(total-equity)` or `edgar us-gaap:Revenues`.
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    CURRENCY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{3}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(description="The company.")
    indicator: CompanyIndicator = Field(description="The indicator.")
    period_end: date = Field(description="The last day of the period.")
    granularity: FinancialGranularity = Field(description="The period.")
    value: float = Field(description="The value, in its unit.")
    unit: IndicatorUnit = Field(description="The unit.")
    currency: Optional[str] = Field(default=None, description="The currency of an amount.")
    value_usd: Optional[float] = Field(default=None, description="The amount in US dollars.")
    inputs: str = Field(min_length=1, max_length=300, description="How it was computed.")

    @field_validator("company", mode="before")
    def validate_company(cls, value: JsonValue) -> JsonValue:
        """Validate the raw company: a company key.

        Args:
            value (JsonValue): The raw company.

        Returns:
            JsonValue: The key.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 40 characters.
            InvalidCompanyValueError: If it is not lower-case words joined by hyphens.
        """
        key = cls.CHECK.text(value, "indicator company", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidCompanyValueError("indicator company", key, "lower-case words joined by hyphens")
        return key

    @field_validator("indicator", mode="before")
    def validate_indicator(cls, value: JsonValue) -> JsonValue:
        """Validate the raw indicator: one of the company indicators.

        Args:
            value (JsonValue): The raw indicator.

        Returns:
            JsonValue: The indicator.

        Raises:
            InvalidMarketChoiceError: If it is not a company indicator.
        """
        return cls.CHECK.choice(value, "indicator", [indicator.value for indicator in CompanyIndicator])

    @field_validator("period_end", mode="before")
    def validate_period_end(cls, value: JsonValue) -> JsonValue:
        """Validate the raw last day: a date.

        Args:
            value (JsonValue): The raw day.

        Returns:
            JsonValue: The day, `YYYY-MM-DD`.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        return cls.CHECK.iso_day(value, "indicator period end")

    @field_validator("granularity", mode="before")
    def validate_granularity(cls, value: JsonValue) -> JsonValue:
        """Validate the raw period: one of the granularities.

        Args:
            value (JsonValue): The raw period.

        Returns:
            JsonValue: The period.

        Raises:
            InvalidMarketChoiceError: If it is not a granularity.
        """
        return cls.CHECK.choice(value, "indicator period", [item.value for item in FinancialGranularity])

    @field_validator("value", mode="before")
    def validate_value(cls, value: JsonValue) -> JsonValue:
        """Validate the raw value: a finite number.

        Args:
            value (JsonValue): The raw value.

        Returns:
            JsonValue: The value.

        Raises:
            InvalidMarketNumberError: If it is not a finite number.
        """
        return cls.CHECK.number(value, "indicator value")

    @field_validator("unit", mode="before")
    def validate_unit(cls, value: JsonValue) -> JsonValue:
        """Validate the raw unit: one of the indicator units.

        Args:
            value (JsonValue): The raw unit.

        Returns:
            JsonValue: The unit.

        Raises:
            InvalidMarketChoiceError: If it is not an indicator unit.
        """
        return cls.CHECK.choice(value, "indicator unit", [unit.value for unit in IndicatorUnit])

    @field_validator("currency", mode="before")
    def validate_currency(cls, value: JsonValue) -> JsonValue:
        """Validate the raw currency: three letters, upper-cased, or none.

        Args:
            value (JsonValue): The raw currency.

        Returns:
            JsonValue: The currency, `None` when not an amount.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompanyValueError: If it is not three letters.
        """
        currency = cls.CHECK.text(value, "indicator currency", 3, optional=True)
        if currency is None:
            return None
        if not cls.CURRENCY.match(currency.upper()):
            raise InvalidCompanyValueError("indicator currency", currency, "three letters (ISO 4217)")
        return currency.upper()

    @field_validator("value_usd", mode="before")
    def validate_value_usd(cls, value: JsonValue) -> JsonValue:
        """Validate the raw amount in US dollars: a finite number, or none.

        Args:
            value (JsonValue): The raw amount.

        Returns:
            JsonValue: The amount, `None` when not converted.

        Raises:
            InvalidMarketNumberError: If it is not a finite number.
        """
        return cls.CHECK.number(value, "indicator value in US dollars", optional=True)

    @field_validator("inputs", mode="before")
    def validate_inputs(cls, value: JsonValue) -> JsonValue:
        """Validate the raw computation: a text of 1 to 300 characters.

        Args:
            value (JsonValue): The raw computation.

        Returns:
            JsonValue: The computation.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 300 characters.
        """
        return cls.CHECK.text(value, "indicator inputs", 300)
