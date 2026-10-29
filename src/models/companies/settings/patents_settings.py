from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class PatentsSettings(BaseModel):
    """How Google Patents is read: the size of a search window, the pace and what a run may fetch.

    Attributes:
        ENV (ClassVar[Pattern[str]]): The format of an environment variable name.
        COUNTRY (ClassVar[Pattern[str]]): The format of a patent office code, e.g. `US`, `EP`, `WO`.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        window_cap (int): The most publications a window may count to be read in one export (Google returns
            at most about a thousand results per query, so a larger window is split).
        refresh_years (int): The windows whose priority dates are this recent are searched again on each run (a
            publication appears about 18 months after its priority date).
        delay_seconds (float): The seconds between two requests to Google Patents.
        max_blocks (int): The refusals (HTTP 429 or 503, the `Sorry` page) a run accepts before it stops, the
            remaining windows and pages being left for the next run.
        page_budget (int): The publication pages a run reads by default.
        page_budget_env (str): The environment variable overriding the page budget.
        split_countries (List[str]): The patent offices a single day still counting too many publications is split
            by, the rest being searched without them.
        resume_minutes (int): The minutes the explorer waits after Google Patents refused a search before resuming
            it by itself (when asked to).
        browser (bool): Whether Google Patents is read in a visible browser (its search page, as a person sees it)
            rather than by HTTP requests.
    """

    ENV: ClassVar[Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
    COUNTRY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{2}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    window_cap: int = Field(default=900, ge=10, le=1000, description="The most publications of a window.")
    refresh_years: int = Field(default=3, ge=0, le=30, description="The recent years searched again.")
    delay_seconds: float = Field(default=6.0, ge=0, le=600, description="The seconds between two requests.")
    max_blocks: int = Field(default=1, ge=0, le=100, description="The refusals a run accepts before stopping.")
    page_budget: int = Field(default=2000, ge=0, le=10_000_000, description="The pages a run reads by default.")
    page_budget_env: str = Field(default="CRAWLER_PATENT_PAGES", description="The variable overriding the budget.")
    split_countries: List[str] = Field(default_factory=list, description="The offices a crowded day is split by.")
    resume_minutes: int = Field(default=60, ge=1, le=1440, description="The minutes before a refused search resumes.")
    browser: bool = Field(default=True, description="Whether Google Patents is read in a visible browser.")

    @field_validator("window_cap", "refresh_years", "max_blocks", "page_budget", "resume_minutes", mode="before")
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
        return cls.CHECK.number(value, f"patents {info.field_name}", low=0, integer=True)

    @field_validator("delay_seconds", mode="before")
    def validate_delay_seconds(cls, value: JsonValue) -> JsonValue:
        """Validate the raw delay: a number of seconds from 0 to 600.

        Args:
            value (JsonValue): The raw delay.

        Returns:
            JsonValue: The delay.

        Raises:
            InvalidMarketNumberError: If it is not a number from 0 to 600.
        """
        return cls.CHECK.number(value, "patents request delay", low=0.0, high=600.0)

    @field_validator("page_budget_env", mode="before")
    def validate_page_budget_env(cls, value: JsonValue) -> JsonValue:
        """Validate the raw environment variable: an upper-case name.

        Args:
            value (JsonValue): The raw name.

        Returns:
            JsonValue: The name.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompanyValueError: If it is not an upper-case variable name.
        """
        name = cls.CHECK.text(value, "page budget variable", 64) or ""
        if not cls.ENV.match(name):
            raise InvalidCompanyValueError("page budget variable", name, "an upper-case variable name")
        return name

    @field_validator("split_countries", mode="before")
    def validate_split_countries(cls, value: JsonValue) -> JsonValue:
        """Validate the raw patent offices: two upper-case letters each, each once.

        Args:
            value (JsonValue): The raw offices.

        Returns:
            JsonValue: The offices, each once in their order.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketTextError: If an office is not a text.
            InvalidCompanyValueError: If an office is not two letters.
        """
        countries: List[JsonValue] = []
        for item in cls.CHECK.items(value, "split patent offices", "two-letter codes"):
            country = (cls.CHECK.text(item, "patent office", 2) or "").upper()
            if not cls.COUNTRY.match(country):
                raise InvalidCompanyValueError("patent office", country, "two letters")
            if country not in countries:
                countries.append(country)
        return countries

    @field_validator("browser", mode="before")
    def validate_browser(cls, value: JsonValue) -> JsonValue:
        """Validate the raw browser flag: a boolean.

        Args:
            value (JsonValue): The raw flag.

        Returns:
            JsonValue: The flag.

        Raises:
            InvalidMarketFlagError: If it is not a boolean.
        """
        return cls.CHECK.flag(value, "patents browser")
