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


class FinancialFact(BaseModel):
    """A figure of a company's statements as its source states it: an XBRL fact of a filing or a Google Finance cell.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a company key.
        CURRENCY (ClassVar[Pattern[str]]): The format of a currency: three upper-case letters.
        CIK (ClassVar[Pattern[str]]): The format of an SEC filer: 10 digits.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        company (str): The company of the chronology.
        source (FinancialSource): Where the figure was read.
        metric (FinancialMetric): The statement line.
        concept (str): The XBRL concept (`us-gaap:Revenues`) or the Google position (`gfinance:0`).
        filer (Optional[str]): The SEC filer (10 digits) of an XBRL fact, `None` for Google Finance.
        start (Optional[date]): The first day of the period, `None` for a balance at a date.
        end (date): The last day of the period, or the date of the balance.
        granularity (Optional[FinancialGranularity]): The period, when the source states it (Google Finance), else
            derived from the dates (the XBRL facts).
        value (float): The figure, signed (a loss is negative, an amount spent is positive).
        currency (Optional[str]): Its currency, `None` for shares.
        form (Optional[str]): The filing form, e.g. `10-K`, `20-F`.
        fiscal_year (Optional[int]): The fiscal year the filing states.
        fiscal_period (Optional[str]): The fiscal period the filing states, e.g. `FY`, `Q2`.
        filed (Optional[date]): The day the filing was made (a later filing restating the figure wins).
        source_url (str): The document read.
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    CURRENCY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{3}$")
    CIK: ClassVar[Pattern[str]] = re.compile(r"^\d{10}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(description="The company of the chronology.")
    source: FinancialSource = Field(description="Where the figure was read.")
    metric: FinancialMetric = Field(description="The statement line.")
    concept: str = Field(min_length=1, max_length=160, description="The XBRL concept or the Google position.")
    filer: Optional[str] = Field(default=None, description="The SEC filer of an XBRL fact.")
    start: Optional[date] = Field(default=None, description="The first day of the period.")
    end: date = Field(description="The last day of the period.")
    granularity: Optional[FinancialGranularity] = Field(default=None, description="The period, when stated.")
    value: float = Field(description="The figure, signed.")
    currency: Optional[str] = Field(default=None, description="Its currency.")
    form: Optional[str] = Field(default=None, max_length=12, description="The filing form.")
    fiscal_year: Optional[int] = Field(default=None, ge=1900, le=2200, description="The fiscal year.")
    fiscal_period: Optional[str] = Field(default=None, max_length=4, description="The fiscal period.")
    filed: Optional[date] = Field(default=None, description="The day the filing was made.")
    source_url: str = Field(min_length=1, max_length=2048, description="The document read.")

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
        key = cls.CHECK.text(value, "financial company", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidCompanyValueError("financial company", key, "lower-case words joined by hyphens")
        return key

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
        return cls.CHECK.choice(value, "financial source", [source.value for source in FinancialSource])

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
        return cls.CHECK.choice(value, "financial line", [metric.value for metric in FinancialMetric])

    @field_validator("concept", "source_url", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw text: trimmed, not empty.

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 2048 characters.
        """
        return cls.CHECK.text(value, f"financial {info.field_name}", 2048, collapse=False)

    @field_validator("filer", mode="before")
    def validate_filer(cls, value: JsonValue) -> JsonValue:
        """Validate the raw SEC filer: 10 digits, or none.

        Args:
            value (JsonValue): The raw filer.

        Returns:
            JsonValue: The filer, `None` for a figure not filed with the SEC.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text.
            InvalidCompanyValueError: If it is not 10 digits.
        """
        filer = cls.CHECK.text(value, "financial filer", 10, optional=True)
        if filer is not None and not cls.CIK.match(filer):
            raise InvalidCompanyValueError("financial filer", filer, "10 digits")
        return filer

    @field_validator("start", "filed", mode="before")
    def validate_optional_day(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw optional day: a date, or none.

        Args:
            value (JsonValue): The raw day.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The day, `YYYY-MM-DD`, `None` when missing.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        return cls.CHECK.iso_day(value, f"financial {info.field_name} day", optional=True)

    @field_validator("end", mode="before")
    def validate_end(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate the raw last day: a date, not before the first day.

        Args:
            value (JsonValue): The raw day.
            info (ValidationInfo): The fields validated so far (the first day).

        Returns:
            JsonValue: The day, `YYYY-MM-DD`.

        Raises:
            InvalidMarketDateError: If it is not a date.
            InvalidCompanyValueError: If it is before the first day.
        """
        end = cls.CHECK.day(value, "financial end day")
        start = info.data.get("start")
        if end is not None and isinstance(start, date) and end < start:
            raise InvalidCompanyValueError("financial end day", end.isoformat(), f"a day from {start.isoformat()}")
        return end.isoformat() if end else None

    @field_validator("granularity", mode="before")
    def validate_granularity(cls, value: JsonValue) -> JsonValue:
        """Validate the raw period: one of the granularities, or none.

        Args:
            value (JsonValue): The raw period.

        Returns:
            JsonValue: The period, `None` when not stated.

        Raises:
            InvalidMarketChoiceError: If it is not a granularity.
        """
        return cls.CHECK.choice(
            value, "financial granularity", [item.value for item in FinancialGranularity], optional=True
        )

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
        return cls.CHECK.number(value, "financial figure")

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
        currency = cls.CHECK.text(value, "financial currency", 3, optional=True)
        if currency is None:
            return None
        if not cls.CURRENCY.match(currency.upper()):
            raise InvalidCompanyValueError("financial currency", currency, "three letters (ISO 4217)")
        return currency.upper()

    @field_validator("form", "fiscal_period", mode="before")
    def validate_code(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw filing code: a short text, or none.

        Args:
            value (JsonValue): The raw code.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The code, upper-cased, `None` when not stated.

        Raises:
            InvalidMarketTextError: If it is not a text of at most 12 characters.
        """
        code = cls.CHECK.text(value, f"financial {info.field_name}", 12, optional=True)
        return code.upper() if code else None

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
        return cls.CHECK.number(value, "fiscal year", low=1900, high=2200, optional=True, integer=True)
