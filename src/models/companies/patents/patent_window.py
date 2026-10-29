from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.enums import PatentWindowStatus
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class PatentWindow(BaseModel):
    """A window of the patents search: an assignee search over a span of priority dates, maybe one office only.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a company key.
        COUNTRY (ClassVar[Pattern[str]]): The format of a patent office code.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        company (str): The company searched.
        query (str): The assignee search.
        after (date): The first priority date of the window.
        before (date): The day after its last priority date (Google's `before:` is exclusive).
        country (Optional[str]): The patent office searched, every office when `None`.
        expected (int): The publications Google counts in the window.
        fetched (int): The publications read from it.
        status (PatentWindowStatus): Whether it was read whole, split, read in part or not read yet.

    Notes:
        The windows are stored: a run resumes from those not complete, an audit compares what Google counts with
        what was read, and the recent ones are searched again on each run to catch the new publications.
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    COUNTRY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{2}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(description="The company searched.")
    query: str = Field(min_length=1, max_length=120, description="The assignee search.")
    after: date = Field(description="The first priority date of the window.")
    before: date = Field(description="The day after its last priority date.")
    country: Optional[str] = Field(default=None, description="The patent office searched.")
    expected: int = Field(ge=0, description="The publications Google counts.")
    fetched: int = Field(default=0, ge=0, description="The publications read.")
    status: PatentWindowStatus = Field(default=PatentWindowStatus.PENDING, description="Its state.")

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
        key = cls.CHECK.text(value, "window company", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidCompanyValueError("window company", key, "lower-case words joined by hyphens")
        return key

    @field_validator("query", mode="before")
    def validate_query(cls, value: JsonValue) -> JsonValue:
        """Validate the raw assignee search: a text of 1 to 120 characters.

        Args:
            value (JsonValue): The raw search.

        Returns:
            JsonValue: The search.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 120 characters.
        """
        return cls.CHECK.text(value, "window search", 120)

    @field_validator("after", mode="before")
    def validate_after(cls, value: JsonValue) -> JsonValue:
        """Validate the raw first priority date: a date.

        Args:
            value (JsonValue): The raw date.

        Returns:
            JsonValue: The date, `YYYY-MM-DD`.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        return cls.CHECK.iso_day(value, "window start")

    @field_validator("before", mode="before")
    def validate_before(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate the raw end: a date after the first priority date.

        Args:
            value (JsonValue): The raw date.
            info (ValidationInfo): The fields validated so far (the first date).

        Returns:
            JsonValue: The date, `YYYY-MM-DD`.

        Raises:
            InvalidMarketDateError: If it is not a date.
            InvalidCompanyValueError: If it is not after the first priority date.
        """
        before = cls.CHECK.day(value, "window end")
        after = info.data.get("after")
        if before is not None and isinstance(after, date) and before <= after:
            raise InvalidCompanyValueError("window end", before.isoformat(), f"a day after {after.isoformat()}")
        return before.isoformat() if before else None

    @field_validator("country", mode="before")
    def validate_country(cls, value: JsonValue) -> JsonValue:
        """Validate the raw patent office: two letters, or none.

        Args:
            value (JsonValue): The raw office.

        Returns:
            JsonValue: The office, `None` for every office.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text.
            InvalidCompanyValueError: If it is not two letters.
        """
        country = cls.CHECK.text(value, "window office", 2, optional=True)
        if country is not None and not cls.COUNTRY.match(country.upper()):
            raise InvalidCompanyValueError("window office", country, "two letters")
        return country.upper() if country else None

    @field_validator("expected", "fetched", mode="before")
    def validate_count(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw count: a whole number of at least 0.

        Args:
            value (JsonValue): The raw count.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The count.

        Raises:
            InvalidMarketNumberError: If it is not a whole number of at least 0.
        """
        return cls.CHECK.number(value, f"window {info.field_name}", low=0, integer=True)

    @field_validator("status", mode="before")
    def validate_status(cls, value: JsonValue) -> JsonValue:
        """Validate the raw state: one of the window states.

        Args:
            value (JsonValue): The raw state.

        Returns:
            JsonValue: The state.

        Raises:
            InvalidMarketChoiceError: If it is not a window state.
        """
        return cls.CHECK.choice(value, "window state", [status.value for status in PatentWindowStatus])

    ############################
    # Publicly Exposed Methods #
    ############################

    def days(self) -> int:
        """Get the length of the window.

        Returns:
            int: Its days (1 for a single day).
        """
        return (self.before - self.after).days
