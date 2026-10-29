from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, List, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class PatentRecord(BaseModel):
    """A publication returned by a Google Patents search of a company's assignee (a row of the CSV export).

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a company key.
        PUBLICATION (ClassVar[Pattern[str]]): The format of a publication number, e.g. `US20230214654A1`.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        company (str): The company searched.
        query (str): The assignee search that returned it.
        publication_number (str): The publication, as its Google Patents page names it.
        title (Optional[str]): Its title.
        assignee (Optional[str]): Its assignee, as the search writes it.
        inventors (List[str]): Its inventors, in the filing order.
        priority_date (Optional[date]): The date of its first filing (the priority).
        filing_date (Optional[date]): The date it was filed.
        publication_date (Optional[date]): The date it was published.
        grant_date (Optional[date]): The date it was granted, `None` for an application.
        source_url (str): Its Google Patents page.
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    PUBLICATION: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{2}[A-Z0-9]{1,24}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(description="The company searched.")
    query: str = Field(min_length=1, max_length=120, description="The assignee search.")
    publication_number: str = Field(description="The publication.")
    title: Optional[str] = Field(default=None, max_length=1000, description="Its title.")
    assignee: Optional[str] = Field(default=None, max_length=300, description="Its assignee.")
    inventors: List[str] = Field(default_factory=list, description="Its inventors.")
    priority_date: Optional[date] = Field(default=None, description="The date of its first filing.")
    filing_date: Optional[date] = Field(default=None, description="The date it was filed.")
    publication_date: Optional[date] = Field(default=None, description="The date it was published.")
    grant_date: Optional[date] = Field(default=None, description="The date it was granted.")
    source_url: str = Field(min_length=1, max_length=2048, description="Its Google Patents page.")

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
        key = cls.CHECK.text(value, "patent company", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidCompanyValueError("patent company", key, "lower-case words joined by hyphens")
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
        return cls.CHECK.text(value, "patent search", 120)

    @field_validator("publication_number", mode="before")
    def validate_publication_number(cls, value: JsonValue) -> JsonValue:
        """Validate the raw publication: an office code then letters and digits, separators removed.

        Args:
            value (JsonValue): The raw publication.

        Returns:
            JsonValue: The publication.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompanyValueError: If it is not an office code followed by letters and digits.
        """
        number = (cls.CHECK.text(value, "publication", 40) or "").replace("-", "").replace(" ", "").upper()
        if not cls.PUBLICATION.match(number):
            raise InvalidCompanyValueError("publication", number, "an office code followed by letters and digits")
        return number

    @field_validator("title", "assignee", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw text: trimmed, cut to its field's length, or none.

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text, `None` when blank.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text.
        """
        limit = 300 if info.field_name == "assignee" else 1000
        clipped = value[:limit] if isinstance(value, str) else value
        return cls.CHECK.text(clipped, f"patent {info.field_name}", limit, optional=True)

    @field_validator("inventors", mode="before")
    def validate_inventors(cls, value: JsonValue) -> JsonValue:
        """Validate the raw inventors: names of at most 200 characters, each once, blanks left out.

        Args:
            value (JsonValue): The raw inventors, a list or a comma-separated text.

        Returns:
            JsonValue: The names, each once in their order.

        Raises:
            InvalidMarketListError: If it is neither a list nor a text.
            InvalidMarketTextError: If a name is not a text of at most 200 characters.
        """
        parts: List[JsonValue] = [*value.split(",")] if isinstance(value, str) else []
        items = parts if isinstance(value, str) else value
        names = [
            cls.CHECK.text(item, "inventor", 200, optional=True)
            for item in cls.CHECK.items(items, "patent inventors", "names")
        ]
        unique: List[JsonValue] = [*dict.fromkeys(name for name in names if name)]
        return unique

    @field_validator("priority_date", "filing_date", "publication_date", "grant_date", mode="before")
    def validate_day(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw date: a date, or none (a blank cell of the export).

        Args:
            value (JsonValue): The raw date.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The date, `YYYY-MM-DD`, `None` when missing.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        blank = isinstance(value, str) and not value.strip()
        return None if blank else cls.CHECK.iso_day(value, f"patent {info.field_name}", optional=True)

    @field_validator("source_url", mode="before")
    def validate_source_url(cls, value: JsonValue) -> JsonValue:
        """Validate the raw page: a text of 1 to 2048 characters.

        Args:
            value (JsonValue): The raw page.

        Returns:
            JsonValue: The page.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 2048 characters.
        """
        return cls.CHECK.text(value, "patent page", 2048, collapse=False)
