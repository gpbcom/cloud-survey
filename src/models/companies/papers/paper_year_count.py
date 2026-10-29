from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class PaperYearCount(BaseModel):
    """The papers OpenAlex counts for a company's institutions in a publication year (its `group_by` answer).

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a company key.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        company (str): The company.
        year (int): The publication year.
        papers (int): The papers of the year.
        source_url (str): The OpenAlex request.

    Notes:
        The count is the exact one of OpenAlex, whatever the papers read (a run may read only part of them).
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(description="The company.")
    year: int = Field(ge=1800, le=2200, description="The publication year.")
    papers: int = Field(ge=0, description="The papers of the year.")
    source_url: str = Field(min_length=1, max_length=2048, description="The OpenAlex request.")

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
        key = cls.CHECK.text(value, "paper count company", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidCompanyValueError("paper count company", key, "lower-case words joined by hyphens")
        return key

    @field_validator("year", "papers", mode="before")
    def validate_number(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw year or count: a whole number (a text holding one is read).

        Args:
            value (JsonValue): The raw number.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The number.

        Raises:
            InvalidMarketNumberError: If it is not a whole number of at least 0.
        """
        return cls.CHECK.number(value, f"paper count {info.field_name}", low=0, integer=True)

    @field_validator("source_url", mode="before")
    def validate_source_url(cls, value: JsonValue) -> JsonValue:
        """Validate the raw request: a text of 1 to 2048 characters.

        Args:
            value (JsonValue): The raw request.

        Returns:
            JsonValue: The request.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 2048 characters.
        """
        return cls.CHECK.text(value, "paper count request", 2048, collapse=False)
