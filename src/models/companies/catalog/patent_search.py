from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class PatentSearch(BaseModel):
    """How the patents of a company are searched on Google Patents: the assignee names it files under.

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        assignees (List[str]): The assignee searches, each a name the group files under (subsidiaries, former names
            and names in the local script included), e.g. `Nvidia Corp`, `Mellanox Technologies`.
        since (date): The first priority date searched (the founding of the company).
        exclude (List[str]): Regular expressions on the assignee of a result: a match is another company with a
            similar name (a homonym), and the result is left out.

    Notes:
        Google Patents matches an assignee search against the harmonised names of the assignees, so a search for
        `Nvidia` also returns the publications filed as `NVIDIA Corporation` or `辉达公司`. A name shared by other
        companies (`Sun`, `Lotus`, `Apollo`) is searched under its full legal name, and the homonyms that still
        match are excluded.
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    assignees: List[str] = Field(min_length=1, description="The assignee searches.")
    since: date = Field(description="The first priority date searched.")
    exclude: List[str] = Field(default_factory=list, description="The patterns of the homonyms left out.")

    @field_validator("assignees", mode="before")
    def validate_assignees(cls, value: JsonValue) -> JsonValue:
        """Validate the raw assignee searches: texts of 2 to 120 characters, each once.

        Args:
            value (JsonValue): The raw searches.

        Returns:
            JsonValue: The searches, trimmed, each once in their order.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketTextError: If a search is not a text of 2 to 120 characters.
        """
        names = [
            cls.CHECK.text(item, "patent assignee", 120, minimum=2)
            for item in cls.CHECK.items(value, "patent assignees", "names")
        ]
        unique: List[JsonValue] = [*dict.fromkeys(names)]
        return unique

    @field_validator("since", mode="before")
    def validate_since(cls, value: JsonValue) -> JsonValue:
        """Validate the raw first priority date: a date.

        Args:
            value (JsonValue): The raw date.

        Returns:
            JsonValue: The date, `YYYY-MM-DD`.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        return cls.CHECK.iso_day(value, "first priority date")

    @field_validator("exclude", mode="before")
    def validate_exclude(cls, value: JsonValue) -> JsonValue:
        """Validate the raw homonym patterns: regular expressions that compile.

        Args:
            value (JsonValue): The raw patterns.

        Returns:
            JsonValue: The patterns.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketTextError: If a pattern is not a text of 1 to 200 characters.
            InvalidCompanyValueError: If a pattern is not a valid regular expression.
        """
        patterns: List[JsonValue] = []
        for item in cls.CHECK.items(value, "homonym patterns", "regular expressions"):
            pattern = cls.CHECK.text(item, "homonym pattern", 200, collapse=False) or ""
            try:
                re.compile(pattern)
            except re.error as e:
                raise InvalidCompanyValueError("homonym pattern", pattern, f"a regular expression ({e})") from e
            patterns.append(pattern)
        return patterns
