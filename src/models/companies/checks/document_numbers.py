from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class DocumentNumbers(BaseModel):
    """The numbers a document cited by researched fiscal years states, read to check the researched figures.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a company key.
        URL (ClassVar[Pattern[str]]): The format of the document's URL.
        MAX_NUMBERS (ClassVar[int]): The most numbers kept of a document.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        company (str): The company whose fiscal years cite the document.
        fiscal_years (List[int]): Those fiscal years.
        source_url (str): The document, as the fiscal years cite it.
        numbers (List[float]): The distinct numbers it states, as written (no scale applied), without sign, empty
            when it could not be read.

    Notes:
        A crawler only reads: the numbers are compared with the researched figures by `FigureChecker`, which marks
        each fiscal year as matching its document or not, never changing a figure.
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    URL: ClassVar[Pattern[str]] = re.compile(r"^https://\S+$")
    MAX_NUMBERS: ClassVar[int] = 100_000
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(description="The company whose fiscal years cite the document.")
    fiscal_years: List[int] = Field(min_length=1, description="The fiscal years citing it.")
    source_url: str = Field(description="The document.")
    numbers: List[float] = Field(default_factory=list, description="The distinct numbers it states.")

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
        key = cls.CHECK.text(value, "document company", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidCompanyValueError("document company", key, "lower-case words joined by hyphens")
        return key

    @field_validator("fiscal_years", mode="before")
    def validate_fiscal_years(cls, value: JsonValue) -> JsonValue:
        """Validate the raw fiscal years: years from 1950 to 2100, without duplicates.

        Args:
            value (JsonValue): The raw years.

        Returns:
            JsonValue: The years, sorted.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidCompanyValueError: If a year is not a whole number from 1950 to 2100.
        """
        years: List[JsonValue] = []
        for item in cls.CHECK.items(value, "document years", "a list of fiscal years"):
            if isinstance(item, bool) or not isinstance(item, int) or not 1950 <= item <= 2100:
                raise InvalidCompanyValueError("document year", repr(item), "a year from 1950 to 2100")
            years.append(item)
        unique: List[JsonValue] = [*sorted({year for year in years if isinstance(year, int)})]
        return unique

    @field_validator("source_url", mode="before")
    def validate_source_url(cls, value: JsonValue) -> JsonValue:
        """Validate the raw document: an https URL.

        Args:
            value (JsonValue): The raw URL.

        Returns:
            JsonValue: The URL.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 2048 characters.
            InvalidCompanyValueError: If it is not an https URL.
        """
        url = cls.CHECK.text(value, "document URL", 2048) or ""
        if not cls.URL.match(url):
            raise InvalidCompanyValueError("document URL", url, "an https URL")
        return url

    @field_validator("numbers", mode="before")
    def validate_numbers(cls, value: JsonValue) -> JsonValue:
        """Validate the raw numbers: at most `MAX_NUMBERS` non-negative numbers.

        Args:
            value (JsonValue): The raw numbers.

        Returns:
            JsonValue: The numbers, distinct and sorted.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidCompanyValueError: If a number is negative or not a number, or there are too many.
        """
        numbers: List[float] = []
        for item in cls.CHECK.items(value, "document numbers", "a list of numbers"):
            if isinstance(item, bool) or not isinstance(item, (int, float)) or item < 0:
                raise InvalidCompanyValueError("document number", repr(item), "a non-negative number")
            numbers.append(float(item))
        unique = sorted(set(numbers))
        if len(unique) > cls.MAX_NUMBERS:
            raise InvalidCompanyValueError("document numbers", str(len(unique)), f"at most {cls.MAX_NUMBERS} numbers")
        return [*unique]
