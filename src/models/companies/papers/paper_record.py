from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, List, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.exception import InvalidCompanyValueError
from models.companies.papers.paper_authorship import PaperAuthorship
from models.markets.field_check import MarketFieldCheck


class PaperRecord(BaseModel):
    """A research paper of a company's researchers, as OpenAlex describes the work.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a company key.
        WORK (ClassVar[Pattern[str]]): The format of an OpenAlex work, e.g. `W2741809807`.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        openalex_id (str): The OpenAlex work.
        company (str): The company whose institutions it is affiliated with.
        doi (Optional[str]): Its DOI, without the resolver prefix.
        title (Optional[str]): Its title.
        publication_year (Optional[int]): The year it was published.
        publication_date (Optional[date]): The day it was published.
        type (Optional[str]): Its type, e.g. `article`, `preprint`.
        venue (Optional[str]): The journal, the conference or the repository it appeared in.
        language (Optional[str]): Its language, ISO 639-1.
        cited_by_count (int): The citations it received.
        fwci (Optional[float]): Its field-weighted citation impact (1 is the world average of its field and year).
        is_oa (bool): Whether it is open access.
        topic (Optional[str]): Its main topic.
        authorships (List[PaperAuthorship]): Its authors.
        source_url (str): The OpenAlex request it was read from.
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    WORK: ClassVar[Pattern[str]] = re.compile(r"^W\d{3,14}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    openalex_id: str = Field(description="The OpenAlex work.")
    company: str = Field(description="The company whose institutions it is affiliated with.")
    doi: Optional[str] = Field(default=None, max_length=300, description="Its DOI.")
    title: Optional[str] = Field(default=None, max_length=1000, description="Its title.")
    publication_year: Optional[int] = Field(default=None, ge=1800, le=2200, description="The year it was published.")
    publication_date: Optional[date] = Field(default=None, description="The day it was published.")
    type: Optional[str] = Field(default=None, max_length=40, description="Its type.")
    venue: Optional[str] = Field(default=None, max_length=300, description="Where it appeared.")
    language: Optional[str] = Field(default=None, max_length=8, description="Its language.")
    cited_by_count: int = Field(default=0, ge=0, description="The citations it received.")
    fwci: Optional[float] = Field(default=None, ge=0, description="Its field-weighted citation impact.")
    is_oa: bool = Field(default=False, description="Whether it is open access.")
    topic: Optional[str] = Field(default=None, max_length=300, description="Its main topic.")
    authorships: List[PaperAuthorship] = Field(default_factory=list, description="Its authors.")
    source_url: str = Field(min_length=1, max_length=2048, description="The request it was read from.")

    @field_validator("openalex_id", mode="before")
    def validate_openalex_id(cls, value: JsonValue) -> JsonValue:
        """Validate the raw work: an OpenAlex work (a full URL is shortened).

        Args:
            value (JsonValue): The raw work.

        Returns:
            JsonValue: The identifier.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompanyValueError: If it is not `W` followed by digits.
        """
        identifier = (cls.CHECK.text(value, "OpenAlex work", 80) or "").rsplit("/", 1)[-1].upper()
        if not cls.WORK.match(identifier):
            raise InvalidCompanyValueError("OpenAlex work", identifier, "W followed by digits")
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
        key = cls.CHECK.text(value, "paper company", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidCompanyValueError("paper company", key, "lower-case words joined by hyphens")
        return key

    @field_validator("doi", mode="before")
    def validate_doi(cls, value: JsonValue) -> JsonValue:
        """Validate the raw DOI: a text, the resolver prefix removed, or none.

        Args:
            value (JsonValue): The raw DOI.

        Returns:
            JsonValue: The DOI, lower-cased, `None` when unknown.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text of at most 300 characters.
        """
        doi = cls.CHECK.text(value, "paper DOI", 300, optional=True, collapse=False)
        return doi.removeprefix("https://doi.org/").lower() if doi else None

    @field_validator("title", "type", "venue", "language", "topic", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw text: spaces collapsed, cut to its field's length, or none.

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text, `None` when blank.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text.
        """
        limits = {"title": 1000, "type": 40, "venue": 300, "language": 8, "topic": 300}
        limit = limits.get(info.field_name or "", 300)
        collapsed = " ".join(value.split())[:limit] if isinstance(value, str) else value
        return cls.CHECK.text(collapsed, f"paper {info.field_name}", limit, optional=True)

    @field_validator("publication_year", mode="before")
    def validate_publication_year(cls, value: JsonValue) -> JsonValue:
        """Validate the raw year: a whole number from 1800 to 2200, or none.

        Args:
            value (JsonValue): The raw year.

        Returns:
            JsonValue: The year, `None` when unknown.

        Raises:
            InvalidMarketNumberError: If it is not a whole number from 1800 to 2200.
        """
        return cls.CHECK.number(value, "paper year", low=1800, high=2200, optional=True, integer=True)

    @field_validator("publication_date", mode="before")
    def validate_publication_date(cls, value: JsonValue) -> JsonValue:
        """Validate the raw day: a date, or none.

        Args:
            value (JsonValue): The raw day.

        Returns:
            JsonValue: The day, `YYYY-MM-DD`, `None` when unknown.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        return cls.CHECK.iso_day(value, "paper day", optional=True)

    @field_validator("cited_by_count", mode="before")
    def validate_cited_by_count(cls, value: JsonValue) -> JsonValue:
        """Validate the raw citations: a whole number of at least 0 (none is 0).

        Args:
            value (JsonValue): The raw citations.

        Returns:
            JsonValue: The citations.

        Raises:
            InvalidMarketNumberError: If it is not a whole number of at least 0.
        """
        return cls.CHECK.number(0 if value is None else value, "paper citations", low=0, integer=True)

    @field_validator("fwci", mode="before")
    def validate_fwci(cls, value: JsonValue) -> JsonValue:
        """Validate the raw impact: a number of at least 0, or none.

        Args:
            value (JsonValue): The raw impact.

        Returns:
            JsonValue: The impact, `None` when unknown.

        Raises:
            InvalidMarketNumberError: If it is not a number of at least 0.
        """
        return cls.CHECK.number(value, "paper impact", low=0.0, optional=True)

    @field_validator("is_oa", mode="before")
    def validate_is_oa(cls, value: JsonValue) -> JsonValue:
        """Validate the raw open access flag: a boolean (none is false).

        Args:
            value (JsonValue): The raw flag.

        Returns:
            JsonValue: The flag.

        Raises:
            InvalidMarketFlagError: If it is not a boolean.
        """
        return cls.CHECK.flag(False if value is None else value, "paper open access")

    @field_validator("authorships", mode="before")
    def validate_authorships(cls, value: JsonValue) -> JsonValue:
        """Validate the raw authors: a list.

        Args:
            value (JsonValue): The raw authors.

        Returns:
            JsonValue: The authors (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
        """
        return cls.CHECK.items(value, "paper authors", "authorships")

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
        return cls.CHECK.text(value, "paper request", 2048, collapse=False)
