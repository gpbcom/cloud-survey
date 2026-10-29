from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, List, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.enums import FigureScale
from models.companies.exception import DuplicateCompanyKeyError, InvalidCompanyValueError
from models.companies.figures.reported_event import ReportedEvent
from models.companies.figures.reported_year import ReportedYear
from models.markets.field_check import MarketFieldCheck


class ReportedCompany(BaseModel):
    """The figures researched by hand for a company: its fiscal years and its dated events.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a company key.
        CURRENCY (ClassVar[Pattern[str]]): The format of a currency.
        YEAR_END (ClassVar[Pattern[str]]): The format of a fiscal year end: `MM-DD`.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        company (str): The company of the chronology.
        currency (str): The currency of its amounts (an event may state another).
        fiscal_year_end (str): The usual last day of its fiscal years, `MM-DD`.
        scale (FigureScale): The unit its amounts are written in (not the employees, a count).
        years (List[ReportedYear]): Its fiscal years, each once.
        events (List[ReportedEvent]): Its dated events.
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    CURRENCY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{3}$")
    YEAR_END: ClassVar[Pattern[str]] = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(description="The company of the chronology.")
    currency: str = Field(description="The currency of its amounts.")
    fiscal_year_end: str = Field(default="12-31", description="The usual last day of its fiscal years.")
    scale: FigureScale = Field(default=FigureScale.MILLIONS, description="The unit its amounts are written in.")
    years: List[ReportedYear] = Field(default_factory=list, description="Its fiscal years.")
    events: List[ReportedEvent] = Field(default_factory=list, description="Its dated events.")

    @field_validator("company", mode="before")
    def validate_company(cls, value: JsonValue) -> JsonValue:
        """Validate the raw company: a company key.

        Args:
            value (JsonValue): The raw key.

        Returns:
            JsonValue: The key.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 40 characters.
            InvalidCompanyValueError: If it is not lower-case words joined by hyphens.
        """
        key = cls.CHECK.text(value, "reported company", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidCompanyValueError("reported company", key, "lower-case words joined by hyphens")
        return key

    @field_validator("currency", mode="before")
    def validate_currency(cls, value: JsonValue) -> JsonValue:
        """Validate the raw currency: three letters, upper-cased.

        Args:
            value (JsonValue): The raw currency.

        Returns:
            JsonValue: The currency.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompanyValueError: If it is not three letters.
        """
        currency = cls.CHECK.text(value, "reported currency", 3) or ""
        if not cls.CURRENCY.match(currency.upper()):
            raise InvalidCompanyValueError("reported currency", currency, "three letters (ISO 4217)")
        return currency.upper()

    @field_validator("fiscal_year_end", mode="before")
    def validate_fiscal_year_end(cls, value: JsonValue) -> JsonValue:
        """Validate the raw fiscal year end: a day of the year, `MM-DD`.

        Args:
            value (JsonValue): The raw day.

        Returns:
            JsonValue: The day, `MM-DD`.

        Raises:
            InvalidMarketTextError: If it is not a text of 5 characters.
            InvalidCompanyValueError: If it is not a day of a leap year.
        """
        day = cls.CHECK.text(value, "reported fiscal year end", 5, minimum=5) or ""
        try:
            valid = bool(cls.YEAR_END.match(day)) and date.fromisoformat(f"2000-{day}") is not None
        except ValueError:
            valid = False
        if not valid:
            raise InvalidCompanyValueError("reported fiscal year end", day, "a day of the year, MM-DD")
        return day

    @field_validator("scale", mode="before")
    def validate_scale(cls, value: JsonValue) -> JsonValue:
        """Validate the raw scale: units, thousands, millions or billions.

        Args:
            value (JsonValue): The raw scale.

        Returns:
            JsonValue: The scale.

        Raises:
            InvalidMarketChoiceError: If it is not a scale.
        """
        return cls.CHECK.choice(value, "reported scale", [scale.value for scale in FigureScale])

    @field_validator("years", mode="before")
    def validate_years(cls, value: JsonValue) -> JsonValue:
        """Validate the raw fiscal years: a list, each fiscal year once.

        Args:
            value (JsonValue): The raw fiscal years.

        Returns:
            JsonValue: The fiscal years (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
            DuplicateCompanyKeyError: If a fiscal year is stated twice.
        """
        items = cls.CHECK.items(value, "reported fiscal years", "mappings of fiscal year, basis, source and figures")
        seen: List[str] = []
        for item in items:
            year = item.get("fiscal_year") if isinstance(item, dict) else None
            if year is None:
                continue
            if str(year) in seen:
                raise DuplicateCompanyKeyError("reported fiscal year", str(year))
            seen.append(str(year))
        return items

    @field_validator("events", mode="before")
    def validate_events(cls, value: JsonValue) -> JsonValue:
        """Validate the raw events: a list (none when missing).

        Args:
            value (JsonValue): The raw events.

        Returns:
            JsonValue: The events (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
        """
        if value is None:
            return []
        return cls.CHECK.items(value, "reported events", "mappings of date, line, value, basis and source")
