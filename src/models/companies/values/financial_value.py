from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.enums import FinancialGranularity, FinancialMetric, FinancialSource
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class FinancialValue(BaseModel):
    """A statement line of a company for one period, as stored: one per source, the quarters derived when needed.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a company key.
        CURRENCY (ClassVar[Pattern[str]]): The format of a currency.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        company (str): The company.
        metric (FinancialMetric): The statement line.
        period_end (date): The last day of the period, or the date of the balance.
        granularity (FinancialGranularity): The period (a quarter, a year, a balance at a date).
        source (FinancialSource): Where it was read.
        value (float): The figure, signed.
        currency (Optional[str]): Its currency, `None` for shares.
        concept (str): The concept or position it was read from (`derived` when computed from year-to-date facts).
        form (Optional[str]): The filing form.
        fiscal_year (Optional[int]): The fiscal year the filing states.
        fiscal_period (Optional[str]): The fiscal period the filing states.
        filed (Optional[date]): The day of the filing.
        source_url (Optional[str]): The document read.
        note (Optional[str]): What the source says about the figure (a researched figure's restatement, scope).
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    CURRENCY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{3}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(description="The company.")
    metric: FinancialMetric = Field(description="The statement line.")
    period_end: date = Field(description="The last day of the period.")
    granularity: FinancialGranularity = Field(description="The period.")
    source: FinancialSource = Field(description="Where it was read.")
    value: float = Field(description="The figure, signed.")
    currency: Optional[str] = Field(default=None, description="Its currency.")
    concept: str = Field(min_length=1, max_length=160, description="The concept or position it was read from.")
    form: Optional[str] = Field(default=None, max_length=12, description="The filing form.")
    fiscal_year: Optional[int] = Field(default=None, ge=1900, le=2200, description="The fiscal year.")
    fiscal_period: Optional[str] = Field(default=None, max_length=4, description="The fiscal period.")
    filed: Optional[date] = Field(default=None, description="The day of the filing.")
    source_url: Optional[str] = Field(default=None, max_length=2048, description="The document read.")
    note: Optional[str] = Field(default=None, max_length=500, description="What the source says about the figure.")

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
        key = cls.CHECK.text(value, "stored financial company", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidCompanyValueError("stored financial company", key, "lower-case words joined by hyphens")
        return key

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
        return cls.CHECK.choice(value, "stored financial line", [metric.value for metric in FinancialMetric])

    @field_validator("period_end", "filed", mode="before")
    def validate_day(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw day: a date (the filing day may be missing).

        Args:
            value (JsonValue): The raw day.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The day, `YYYY-MM-DD`.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        return cls.CHECK.iso_day(value, f"stored financial {info.field_name}", optional=info.field_name == "filed")

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
        return cls.CHECK.choice(value, "stored financial period", [item.value for item in FinancialGranularity])

    @field_validator("source", mode="before")
    def validate_source(cls, value: JsonValue) -> JsonValue:
        """Validate the raw source: one of the financial sources.

        Args:
            value (JsonValue): The raw source.

        Returns:
            JsonValue: The source.

        Raises:
            InvalidMarketChoiceError: If it is not a financial source.
        """
        return cls.CHECK.choice(value, "stored financial source", [source.value for source in FinancialSource])

    @field_validator("value", mode="before")
    def validate_value(cls, value: JsonValue) -> JsonValue:
        """Validate the raw figure: a finite number.

        Args:
            value (JsonValue): The raw figure.

        Returns:
            JsonValue: The figure.

        Raises:
            InvalidMarketNumberError: If it is not a finite number.
        """
        return cls.CHECK.number(value, "stored financial figure")

    @field_validator("currency", mode="before")
    def validate_currency(cls, value: JsonValue) -> JsonValue:
        """Validate the raw currency: three letters, upper-cased, or none.

        Args:
            value (JsonValue): The raw currency.

        Returns:
            JsonValue: The currency, `None` when not stated.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompanyValueError: If it is not three letters.
        """
        currency = cls.CHECK.text(value, "stored financial currency", 3, optional=True)
        if currency is None:
            return None
        if not cls.CURRENCY.match(currency.upper()):
            raise InvalidCompanyValueError("stored financial currency", currency, "three letters (ISO 4217)")
        return currency.upper()

    @field_validator("concept", "form", "fiscal_period", "source_url", "note", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw text: trimmed, at most 2048 characters (500 for a note, only the concept is required).

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text, `None` when an optional text is blank.

        Raises:
            InvalidMarketTextError: If it is not a text of at most 2048 characters, 500 for a note (or a missing
                concept).
        """
        optional = info.field_name != "concept"
        limit = 500 if info.field_name == "note" else 2048
        return cls.CHECK.text(value, f"stored financial {info.field_name}", limit, optional=optional, collapse=False)

    @field_validator("fiscal_year", mode="before")
    def validate_fiscal_year(cls, value: JsonValue) -> JsonValue:
        """Validate the raw fiscal year: a whole number from 1900 to 2200, or none.

        Args:
            value (JsonValue): The raw year.

        Returns:
            JsonValue: The year, `None` when not stated.

        Raises:
            InvalidMarketNumberError: If it is not a whole number from 1900 to 2200.
        """
        return cls.CHECK.number(value, "stored fiscal year", low=1900, high=2200, optional=True, integer=True)
