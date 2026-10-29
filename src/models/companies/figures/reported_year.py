from __future__ import annotations

# Standard Library Imports.
from datetime import date
from typing import ClassVar, Dict, Optional, Tuple

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.enums import FigureBasis, FinancialMetric
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class ReportedYear(BaseModel):
    """The figures of a company's fiscal year, researched by hand from one source (an annual report, a filing).

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        METRICS (ClassVar[Tuple[FinancialMetric, ...]]): The statement lines a fiscal year may state.
        NON_NEGATIVE (ClassVar[Tuple[FinancialMetric, ...]]): The lines stated as positive amounts (spent or paid).
        BASES (ClassVar[Tuple[FigureBasis, ...]]): The sources a fiscal year may be read from (a run-rate is not
            a fiscal year).
        fiscal_year (int): The fiscal year, the calendar year its last day falls in.
        period_end (Optional[date]): Its last day, when it differs from the company's usual fiscal year end.
        basis (FigureBasis): What the figures were read from.
        source (str): The document read (`https://`).
        published (Optional[date]): When the document was published.
        note (Optional[str]): What the document says about the figures (a restatement, a scope change).
        figures (Dict[FinancialMetric, float]): The figures, in the company's scale (the employees as a count).

    Notes:
        A fiscal year ending in the first ten days of January (a 52 or 53-week year) belongs to the year before.
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()
    METRICS: ClassVar[Tuple[FinancialMetric, ...]] = (
        FinancialMetric.REVENUE,
        FinancialMetric.COST_OF_REVENUE,
        FinancialMetric.GROSS_PROFIT,
        FinancialMetric.RD_EXPENSE,
        FinancialMetric.SGA_EXPENSE,
        FinancialMetric.OPERATING_INCOME,
        FinancialMetric.DEPRECIATION,
        FinancialMetric.INTEREST_EXPENSE,
        FinancialMetric.PRETAX_INCOME,
        FinancialMetric.INCOME_TAX,
        FinancialMetric.NET_INCOME,
        FinancialMetric.TOTAL_ASSETS,
        FinancialMetric.CURRENT_ASSETS,
        FinancialMetric.CASH,
        FinancialMetric.INVENTORY,
        FinancialMetric.TOTAL_LIABILITIES,
        FinancialMetric.CURRENT_LIABILITIES,
        FinancialMetric.CURRENT_DEBT,
        FinancialMetric.LONG_TERM_DEBT,
        FinancialMetric.TOTAL_EQUITY,
        FinancialMetric.RETAINED_EARNINGS,
        FinancialMetric.OPERATING_CASH_FLOW,
        FinancialMetric.CAPEX,
        FinancialMetric.DIVIDENDS_PAID,
        FinancialMetric.BUYBACKS,
        FinancialMetric.EMPLOYEES,
    )
    NON_NEGATIVE: ClassVar[Tuple[FinancialMetric, ...]] = (
        FinancialMetric.REVENUE,
        FinancialMetric.RD_EXPENSE,
        FinancialMetric.INTEREST_EXPENSE,
        FinancialMetric.TOTAL_ASSETS,
        FinancialMetric.CURRENT_ASSETS,
        FinancialMetric.CASH,
        FinancialMetric.CAPEX,
        FinancialMetric.DIVIDENDS_PAID,
        FinancialMetric.BUYBACKS,
        FinancialMetric.EMPLOYEES,
    )
    BASES: ClassVar[Tuple[FigureBasis, ...]] = (
        FigureBasis.ANNUAL_REPORT,
        FigureBasis.FILING,
        FigureBasis.PRESS,
        FigureBasis.ESTIMATE,
    )

    model_config = ConfigDict(frozen=True, extra="forbid")

    fiscal_year: int = Field(ge=1950, le=2100, description="The fiscal year.")
    period_end: Optional[date] = Field(default=None, description="Its last day, when unusual.")
    basis: FigureBasis = Field(description="What the figures were read from.")
    source: str = Field(description="The document read.")
    published: Optional[date] = Field(default=None, description="When the document was published.")
    note: Optional[str] = Field(default=None, max_length=500, description="What the document says.")
    figures: Dict[FinancialMetric, float] = Field(description="The figures.")

    @field_validator("fiscal_year", mode="before")
    def validate_fiscal_year(cls, value: JsonValue) -> JsonValue:
        """Validate the raw fiscal year: a whole number from 1950 to 2100.

        Args:
            value (JsonValue): The raw year.

        Returns:
            JsonValue: The year.

        Raises:
            InvalidMarketNumberError: If it is not a whole number from 1950 to 2100.
        """
        return cls.CHECK.number(value, "reported fiscal year", low=1950, high=2100, integer=True)

    @field_validator("period_end", mode="before")
    def validate_period_end(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate the raw last day: a date within its fiscal year (or the first ten days of the next), or none.

        Args:
            value (JsonValue): The raw day.
            info (ValidationInfo): The fields validated before (the fiscal year).

        Returns:
            JsonValue: The day, `YYYY-MM-DD`, `None` when not stated.

        Raises:
            InvalidMarketDateError: If it is not a date.
            InvalidCompanyValueError: If it falls outside its fiscal year.
        """
        day = cls.CHECK.day(value, "reported period end", optional=True)
        year = info.data.get("fiscal_year")
        if day is None or not isinstance(year, int):
            return day.isoformat() if day else None
        if not date(year, 1, 1) <= day <= date(year + 1, 1, 10):
            raise InvalidCompanyValueError("reported period end", day.isoformat(), f"a day of {year}")
        return day.isoformat()

    @field_validator("basis", mode="before")
    def validate_basis(cls, value: JsonValue) -> JsonValue:
        """Validate the raw basis: an annual report, a filing, the press or an estimate.

        Args:
            value (JsonValue): The raw basis.

        Returns:
            JsonValue: The basis.

        Raises:
            InvalidMarketChoiceError: If it is not a basis of a fiscal year.
        """
        return cls.CHECK.choice(value, "reported basis", [basis.value for basis in cls.BASES])

    @field_validator("source", mode="before")
    def validate_source(cls, value: JsonValue) -> JsonValue:
        """Validate the raw source: an `https://` address.

        Args:
            value (JsonValue): The raw address.

        Returns:
            JsonValue: The address.

        Raises:
            InvalidMarketTextError: If it is not a text of at most 2048 characters.
            InvalidCompanyValueError: If it is not an `https://` address.
        """
        source = cls.CHECK.text(value, "reported source", 2048, collapse=False) or ""
        if not source.startswith("https://"):
            raise InvalidCompanyValueError("reported source", source, "an https:// address")
        return source

    @field_validator("published", mode="before")
    def validate_published(cls, value: JsonValue) -> JsonValue:
        """Validate the raw publication day: a date, or none.

        Args:
            value (JsonValue): The raw day.

        Returns:
            JsonValue: The day, `YYYY-MM-DD`, `None` when not stated.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        return cls.CHECK.iso_day(value, "reported publication day", optional=True)

    @field_validator("note", mode="before")
    def validate_note(cls, value: JsonValue) -> JsonValue:
        """Validate the raw note: a text of at most 500 characters, or none.

        Args:
            value (JsonValue): The raw note.

        Returns:
            JsonValue: The note, `None` when blank.

        Raises:
            InvalidMarketTextError: If it is not a text of at most 500 characters.
        """
        return cls.CHECK.text(value, "reported note", 500, optional=True)

    @field_validator("figures", mode="before")
    def validate_figures(cls, value: JsonValue) -> JsonValue:
        """Validate the raw figures: at least one line of a fiscal year, each a finite number (signs checked).

        Args:
            value (JsonValue): The raw figures, by statement line.

        Returns:
            JsonValue: The figures.

        Raises:
            InvalidCompanyValueError: If it is not a mapping, is empty, or holds a line a fiscal year cannot state.
            InvalidMarketNumberError: If a figure is not a finite number, an amount spent is negative, or the
                employees are not a whole number.
        """
        if not isinstance(value, dict) or not value:
            raise InvalidCompanyValueError("reported figures", repr(value), "a mapping of statement lines to numbers")
        allowed = [metric.value for metric in cls.METRICS]
        figures: Dict[str, JsonValue] = {}
        for raw, number in value.items():
            metric = cls.CHECK.choice(str(raw), "reported line", allowed) or ""
            low = 0.0 if FinancialMetric(metric) in cls.NON_NEGATIVE else None
            integer = metric == FinancialMetric.EMPLOYEES
            figures[metric] = cls.CHECK.number(number, f"reported {metric}", low=low, integer=integer)
        return figures
