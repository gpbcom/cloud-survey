from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Optional, Pattern, Tuple

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.enums import FigureBasis, FinancialMetric
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class ReportedEvent(BaseModel):
    """A dated figure a company makes public outside its fiscal years: a funding round, a run-rate, a headcount.

    Attributes:
        DATE (ClassVar[Pattern[str]]): The format of a date: `YYYY`, `YYYY-MM` or `YYYY-MM-DD`.
        CURRENCY (ClassVar[Pattern[str]]): The format of a currency.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        METRICS (ClassVar[Tuple[FinancialMetric, ...]]): The lines an event may state.
        date (str): When, `YYYY`, `YYYY-MM` or `YYYY-MM-DD`.
        metric (FinancialMetric): What it states: the capital raised, an annualized revenue or the employees.
        value (float): The figure, in the company's scale (the employees as a count).
        currency (Optional[str]): Its currency, when not the company's (none for the employees).
        basis (FigureBasis): What it was read from.
        source (str): The document read (`https://`).
        note (Optional[str]): What the document says (the round, the investors, the scope).
    """

    DATE: ClassVar[Pattern[str]] = re.compile(r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$")
    CURRENCY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{3}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()
    METRICS: ClassVar[Tuple[FinancialMetric, ...]] = (
        FinancialMetric.FUNDING_RAISED,
        FinancialMetric.REVENUE_RUN_RATE,
        FinancialMetric.EMPLOYEES,
    )

    model_config = ConfigDict(frozen=True, extra="forbid")

    date: str = Field(description="When.")
    metric: FinancialMetric = Field(description="What it states.")
    value: float = Field(ge=0, description="The figure.")
    currency: Optional[str] = Field(default=None, description="Its currency, when not the company's.")
    basis: FigureBasis = Field(description="What it was read from.")
    source: str = Field(description="The document read.")
    note: Optional[str] = Field(default=None, max_length=500, description="What the document says.")

    @field_validator("date", mode="before")
    def validate_date(cls, value: JsonValue) -> JsonValue:
        """Validate the raw date: `YYYY`, `YYYY-MM` or `YYYY-MM-DD` (a year may be a number).

        Args:
            value (JsonValue): The raw date.

        Returns:
            JsonValue: The date, as text.

        Raises:
            InvalidMarketTextError: If it is not a text nor a year.
            InvalidCompanyValueError: If it is not a valid partial date.
        """
        if isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        day = cls.CHECK.text(value, "reported event date", 10) or ""
        if not cls.DATE.match(day):
            raise InvalidCompanyValueError("reported event date", day, "YYYY, YYYY-MM or YYYY-MM-DD")
        return day

    @field_validator("metric", mode="before")
    def validate_metric(cls, value: JsonValue) -> JsonValue:
        """Validate the raw line: the capital raised, an annualized revenue or the employees.

        Args:
            value (JsonValue): The raw line.

        Returns:
            JsonValue: The line.

        Raises:
            InvalidMarketChoiceError: If it is not a line an event may state.
        """
        return cls.CHECK.choice(value, "reported event line", [metric.value for metric in cls.METRICS])

    @field_validator("value", mode="before")
    def validate_value(cls, value: JsonValue) -> JsonValue:
        """Validate the raw figure: a finite number, zero or more.

        Args:
            value (JsonValue): The raw figure.

        Returns:
            JsonValue: The figure.

        Raises:
            InvalidMarketNumberError: If it is not a finite number of zero or more.
        """
        return cls.CHECK.number(value, "reported event figure", low=0)

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
        currency = cls.CHECK.text(value, "reported event currency", 3, optional=True)
        if currency is None:
            return None
        if not cls.CURRENCY.match(currency.upper()):
            raise InvalidCompanyValueError("reported event currency", currency, "three letters (ISO 4217)")
        return currency.upper()

    @field_validator("basis", mode="before")
    def validate_basis(cls, value: JsonValue) -> JsonValue:
        """Validate the raw basis: one of the figure bases.

        Args:
            value (JsonValue): The raw basis.

        Returns:
            JsonValue: The basis.

        Raises:
            InvalidMarketChoiceError: If it is not a figure basis.
        """
        return cls.CHECK.choice(value, "reported event basis", [basis.value for basis in FigureBasis])

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
        source = cls.CHECK.text(value, "reported event source", 2048, collapse=False) or ""
        if not source.startswith("https://"):
            raise InvalidCompanyValueError("reported event source", source, "an https:// address")
        return source

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
        return cls.CHECK.text(value, "reported event note", 500, optional=True)
