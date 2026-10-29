from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, List, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.exception import InvalidCompanyValueError
from models.companies.patents.patent_citation import PatentCitation
from models.markets.field_check import MarketFieldCheck


class PatentDetail(BaseModel):
    """What a Google Patents publication page states: its family, assignees, inventors, classes and citations.

    Attributes:
        PUBLICATION (ClassVar[Pattern[str]]): The format of a publication number.
        FAMILY (ClassVar[Pattern[str]]): The format of a DOCDB family: digits.
        CPC (ClassVar[Pattern[str]]): The format of a CPC class, e.g. `G06N3/08`.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        publication_number (str): The publication.
        family_id (Optional[str]): Its DOCDB family (the publications of one invention in every office).
        title (Optional[str]): Its title.
        abstract (Optional[str]): Its abstract.
        assignees_original (List[str]): The assignees it was filed by.
        assignees_current (List[str]): The assignees holding it now (after a sale or a merger).
        inventors (List[str]): Its inventors.
        cpc (List[str]): Its CPC classes, the first one being the main class.
        claims (Optional[int]): The number of its claims.
        priority_date (Optional[date]): The date of its first filing.
        filing_date (Optional[date]): The date it was filed.
        publication_date (Optional[date]): The date it was published.
        grant_date (Optional[date]): The date it was granted.
        citations (List[PatentCitation]): The publications it cites and those citing it.
        source_url (str): The page read.
    """

    PUBLICATION: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{2}[A-Z0-9]{1,24}$")
    FAMILY: ClassVar[Pattern[str]] = re.compile(r"^\d{1,20}$")
    CPC: ClassVar[Pattern[str]] = re.compile(r"^[A-HY]\d{2}[A-Z](?:\d{1,4}/\d{1,6})?$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    publication_number: str = Field(description="The publication.")
    family_id: Optional[str] = Field(default=None, description="Its DOCDB family.")
    title: Optional[str] = Field(default=None, max_length=1000, description="Its title.")
    abstract: Optional[str] = Field(default=None, max_length=20000, description="Its abstract.")
    assignees_original: List[str] = Field(default_factory=list, description="The assignees it was filed by.")
    assignees_current: List[str] = Field(default_factory=list, description="The assignees holding it now.")
    inventors: List[str] = Field(default_factory=list, description="Its inventors.")
    cpc: List[str] = Field(default_factory=list, description="Its CPC classes, the main one first.")
    claims: Optional[int] = Field(default=None, ge=0, description="The number of its claims.")
    priority_date: Optional[date] = Field(default=None, description="The date of its first filing.")
    filing_date: Optional[date] = Field(default=None, description="The date it was filed.")
    publication_date: Optional[date] = Field(default=None, description="The date it was published.")
    grant_date: Optional[date] = Field(default=None, description="The date it was granted.")
    citations: List[PatentCitation] = Field(default_factory=list, description="Its citations.")
    source_url: str = Field(min_length=1, max_length=2048, description="The page read.")

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
        number = (cls.CHECK.text(value, "detailed publication", 40) or "").replace("-", "").upper()
        if not cls.PUBLICATION.match(number):
            raise InvalidCompanyValueError(
                "detailed publication", number, "an office code followed by letters and digits"
            )
        return number

    @field_validator("family_id", mode="before")
    def validate_family_id(cls, value: JsonValue) -> JsonValue:
        """Validate the raw family: digits, or none.

        Args:
            value (JsonValue): The raw family.

        Returns:
            JsonValue: The family, `None` when not stated.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text.
            InvalidCompanyValueError: If it is not digits.
        """
        family = cls.CHECK.text(str(value) if isinstance(value, int) else value, "patent family", 20, optional=True)
        if family is not None and not cls.FAMILY.match(family):
            raise InvalidCompanyValueError("patent family", family, "digits")
        return family

    @field_validator("title", "abstract", mode="before")
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
        limit = 1000 if info.field_name == "title" else 20000
        collapsed = " ".join(value.split())[:limit] if isinstance(value, str) else value
        return cls.CHECK.text(collapsed, f"patent {info.field_name}", limit, optional=True)

    @field_validator("assignees_original", "assignees_current", "inventors", mode="before")
    def validate_names(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate raw names: texts of at most 300 characters, each once, blanks left out.

        Args:
            value (JsonValue): The raw names.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The names, each once in their order.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketTextError: If a name is not a text of at most 300 characters.
        """
        names = [
            cls.CHECK.text(item, f"patent {info.field_name} name", 300, optional=True)
            for item in cls.CHECK.items(value, f"patent {info.field_name}", "names")
        ]
        unique: List[JsonValue] = [*dict.fromkeys(name for name in names if name)]
        return unique

    @field_validator("cpc", mode="before")
    def validate_cpc(cls, value: JsonValue) -> JsonValue:
        """Validate the raw CPC classes: `G06N3/08` codes, each once (spaces removed).

        Args:
            value (JsonValue): The raw classes.

        Returns:
            JsonValue: The classes, each once in their order.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketTextError: If a class is not a text.
            InvalidCompanyValueError: If a class is not a CPC code.
        """
        codes: List[JsonValue] = []
        for item in cls.CHECK.items(value, "CPC classes", "CPC codes"):
            code = (cls.CHECK.text(item, "CPC class", 20) or "").replace(" ", "").upper()
            if not cls.CPC.match(code):
                raise InvalidCompanyValueError("CPC class", code, "a CPC code such as G06N3/08")
            if code not in codes:
                codes.append(code)
        return codes

    @field_validator("claims", mode="before")
    def validate_claims(cls, value: JsonValue) -> JsonValue:
        """Validate the raw number of claims: a whole number of at least 0, or none.

        Args:
            value (JsonValue): The raw number.

        Returns:
            JsonValue: The number, `None` when not stated.

        Raises:
            InvalidMarketNumberError: If it is not a whole number of at least 0.
        """
        return cls.CHECK.number(value, "patent claims", low=0, optional=True, integer=True)

    @field_validator("priority_date", "filing_date", "publication_date", "grant_date", mode="before")
    def validate_day(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw date: a date, or none.

        Args:
            value (JsonValue): The raw date.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The date, `YYYY-MM-DD`, `None` when missing.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        blank = isinstance(value, str) and not value.strip()
        return None if blank else cls.CHECK.iso_day(value, f"detailed {info.field_name}", optional=True)

    @field_validator("citations", mode="before")
    def validate_citations(cls, value: JsonValue) -> JsonValue:
        """Validate the raw citations: a list.

        Args:
            value (JsonValue): The raw citations.

        Returns:
            JsonValue: The citations (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
        """
        return cls.CHECK.items(value, "patent citations", "citations")

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
        return cls.CHECK.text(value, "detailed patent page", 2048, collapse=False)
