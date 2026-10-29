from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class PaperAuthorship(BaseModel):
    """An author of a research paper, with the institutions the paper gives for them.

    Attributes:
        AUTHOR (ClassVar[Pattern[str]]): The format of an OpenAlex author, e.g. `A5023888391`.
        INSTITUTION (ClassVar[Pattern[str]]): The format of an OpenAlex institution, e.g. `I4210127875`.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        position (int): The author's rank in the paper, from 0.
        author_id (Optional[str]): The OpenAlex author, `None` when OpenAlex did not identify them.
        name (str): The author's name.
        orcid (Optional[str]): The author's ORCID, when known.
        institutions (List[str]): The OpenAlex institutions of the author in this paper.
        company_affiliated (bool): Whether one of them belongs to the company searched.
    """

    AUTHOR: ClassVar[Pattern[str]] = re.compile(r"^A\d{1,15}$")
    INSTITUTION: ClassVar[Pattern[str]] = re.compile(r"^I\d{1,15}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    position: int = Field(ge=0, description="The author's rank in the paper.")
    author_id: Optional[str] = Field(default=None, description="The OpenAlex author.")
    name: str = Field(min_length=1, max_length=300, description="The author's name.")
    orcid: Optional[str] = Field(default=None, max_length=60, description="The author's ORCID.")
    institutions: List[str] = Field(default_factory=list, description="The author's institutions in the paper.")
    company_affiliated: bool = Field(default=False, description="Whether one belongs to the company searched.")

    @field_validator("position", mode="before")
    def validate_position(cls, value: JsonValue) -> JsonValue:
        """Validate the raw rank: a whole number of at least 0.

        Args:
            value (JsonValue): The raw rank.

        Returns:
            JsonValue: The rank.

        Raises:
            InvalidMarketNumberError: If it is not a whole number of at least 0.
        """
        return cls.CHECK.number(value, "author rank", low=0, integer=True)

    @field_validator("author_id", mode="before")
    def validate_author_id(cls, value: JsonValue) -> JsonValue:
        """Validate the raw author: an OpenAlex author (a full URL is shortened), or none.

        Args:
            value (JsonValue): The raw author.

        Returns:
            JsonValue: The identifier, `None` when unidentified.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text.
            InvalidCompanyValueError: If it is not `A` followed by digits.
        """
        author = cls.CHECK.text(value, "OpenAlex author", 80, optional=True)
        if author is None:
            return None
        identifier = author.rsplit("/", 1)[-1].upper()
        if not cls.AUTHOR.match(identifier):
            raise InvalidCompanyValueError("OpenAlex author", identifier, "A followed by digits")
        return identifier

    @field_validator("name", mode="before")
    def validate_name(cls, value: JsonValue) -> JsonValue:
        """Validate the raw name: a text of 1 to 300 characters.

        Args:
            value (JsonValue): The raw name.

        Returns:
            JsonValue: The name.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 300 characters.
        """
        return cls.CHECK.text(value[:300] if isinstance(value, str) else value, "author name", 300)

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
        orcid = cls.CHECK.text(value, "author ORCID", 60, optional=True)
        return orcid.rsplit("/", 1)[-1] if orcid else None

    @field_validator("institutions", mode="before")
    def validate_institutions(cls, value: JsonValue) -> JsonValue:
        """Validate the raw institutions: OpenAlex institutions (full URLs shortened), each once.

        Args:
            value (JsonValue): The raw institutions.

        Returns:
            JsonValue: The identifiers, each once in their order.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketTextError: If an institution is not a text.
            InvalidCompanyValueError: If an institution is not `I` followed by digits.
        """
        identifiers: List[JsonValue] = []
        for item in cls.CHECK.items(value, "author institutions", "identifiers"):
            identifier = (cls.CHECK.text(item, "author institution", 80) or "").rsplit("/", 1)[-1].upper()
            if not cls.INSTITUTION.match(identifier):
                raise InvalidCompanyValueError("author institution", identifier, "I followed by digits")
            if identifier not in identifiers:
                identifiers.append(identifier)
        return identifiers

    @field_validator("company_affiliated", mode="before")
    def validate_company_affiliated(cls, value: JsonValue) -> JsonValue:
        """Validate the raw affiliation flag: a boolean.

        Args:
            value (JsonValue): The raw flag.

        Returns:
            JsonValue: The flag.

        Raises:
            InvalidMarketFlagError: If it is not a boolean.
        """
        return cls.CHECK.flag(value, "company affiliation")
