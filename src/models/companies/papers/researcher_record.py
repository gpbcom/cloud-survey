from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class ResearcherRecord(BaseModel):
    """The OpenAlex profile of a researcher who wrote a paper as a member of a company.

    Attributes:
        AUTHOR (ClassVar[Pattern[str]]): The format of an OpenAlex author.
        KEY (ClassVar[Pattern[str]]): The format of a company key.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        author_id (str): The OpenAlex author.
        company (str): The company they wrote for.
        name (str): Their name.
        orcid (Optional[str]): Their ORCID, when known.
        works_count (int): The works OpenAlex counts for them (all affiliations).
        cited_by_count (int): The citations their works received.
        h_index (Optional[int]): Their h-index.
        institution (Optional[str]): The institution they were last seen at.
        current_affiliation (bool): Whether one of their last known institutions belongs to the company.
        affiliation_years (int): The years their profile lists at one of the company's institutions.
        source_url (str): The OpenAlex request it was read from.
    """

    AUTHOR: ClassVar[Pattern[str]] = re.compile(r"^A\d{3,14}$")
    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    author_id: str = Field(description="The OpenAlex author.")
    company: str = Field(description="The company they wrote for.")
    name: str = Field(min_length=1, max_length=300, description="Their name.")
    orcid: Optional[str] = Field(default=None, max_length=60, description="Their ORCID.")
    works_count: int = Field(default=0, ge=0, description="The works OpenAlex counts for them.")
    cited_by_count: int = Field(default=0, ge=0, description="The citations their works received.")
    h_index: Optional[int] = Field(default=None, ge=0, description="Their h-index.")
    institution: Optional[str] = Field(default=None, max_length=300, description="Where they were last seen.")
    current_affiliation: bool = Field(default=False, description="Whether they are last seen at the company.")
    affiliation_years: int = Field(default=0, ge=0, le=200, description="Their profile years at the company.")
    source_url: str = Field(min_length=1, max_length=2048, description="The request it was read from.")

    @field_validator("author_id", mode="before")
    def validate_author_id(cls, value: JsonValue) -> JsonValue:
        """Validate the raw author: an OpenAlex author (a full URL is shortened).

        Args:
            value (JsonValue): The raw author.

        Returns:
            JsonValue: The identifier.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompanyValueError: If it is not `A` followed by digits.
        """
        identifier = (cls.CHECK.text(value, "researcher", 80) or "").rsplit("/", 1)[-1].upper()
        if not cls.AUTHOR.match(identifier):
            raise InvalidCompanyValueError("researcher", identifier, "A followed by digits")
        return identifier

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
        key = cls.CHECK.text(value, "researcher company", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidCompanyValueError("researcher company", key, "lower-case words joined by hyphens")
        return key

    @field_validator("name", "institution", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw text: cut to 300 characters (the institution may be missing).

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text, `None` for a missing institution.

        Raises:
            InvalidMarketTextError: If it is not a text of at most 300 characters (or a missing name).
        """
        clipped = value[:300] if isinstance(value, str) else value
        return cls.CHECK.text(clipped, f"researcher {info.field_name}", 300, optional=info.field_name == "institution")

    @field_validator("orcid", mode="before")
    def validate_orcid(cls, value: JsonValue) -> JsonValue:
        """Validate the raw ORCID: a text (a full URL is shortened), or none.

        Args:
            value (JsonValue): The raw ORCID.

        Returns:
            JsonValue: The ORCID, `None` when unknown.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text of at most 60 characters.
        """
        orcid = cls.CHECK.text(value, "researcher ORCID", 60, optional=True)
        return orcid.rsplit("/", 1)[-1] if orcid else None

    @field_validator("works_count", "cited_by_count", "h_index", "affiliation_years", mode="before")
    def validate_count(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw count: a whole number of at least 0 (the h-index may be missing, the counts are 0).

        Args:
            value (JsonValue): The raw count.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The count.

        Raises:
            InvalidMarketNumberError: If it is not a whole number of at least 0.
        """
        if value is None and info.field_name != "h_index":
            value = 0
        return cls.CHECK.number(value, f"researcher {info.field_name}", low=0, optional=True, integer=True)

    @field_validator("current_affiliation", mode="before")
    def validate_current_affiliation(cls, value: JsonValue) -> JsonValue:
        """Validate the raw current affiliation flag: a boolean.

        Args:
            value (JsonValue): The raw flag.

        Returns:
            JsonValue: The flag.

        Raises:
            InvalidMarketFlagError: If it is not a boolean.
        """
        return cls.CHECK.flag(value, "researcher current affiliation")

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
        return cls.CHECK.text(value, "researcher request", 2048, collapse=False)
