from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class OpenAlexAffiliation(BaseModel):
    """The OpenAlex institutions of a company: its researchers' papers are those affiliated with them.

    Attributes:
        INSTITUTION (ClassVar[Pattern[str]]): The format of an OpenAlex institution identifier, e.g. `I4210127875`.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        institutions (List[str]): The institutions, the top of their lineage (the group, not each laboratory).
        include_affiliations (List[str]): Regular expressions one of which the affiliation text OpenAlex resolved
            to one of the institutions must match, when the company's name is a common word (`SOM OPERA` is a
            Groningen research programme, not Opera Software), case-insensitive. None: every text is accepted.
        exclude_affiliations (List[str]): Regular expressions on the affiliation text OpenAlex resolved to one of
            the institutions: a match is another organisation it confused with the company (case-insensitive).

    Notes:
        - The papers are searched with the `authorships.institutions.lineage` filter, which also matches the child
          institutions of the lineage (Nvidia United Kingdom is a child of Nvidia United States).
        - OpenAlex resolves some homonyms to a company (the Amazon Environmental Research Institute to Amazon): an
          author whose every affiliation text resolved to the company is refused (an exclusion pattern matches it, or
          no inclusion pattern does) is not a member of the company, and a paper without a member is not the
          company's.
    """

    INSTITUTION: ClassVar[Pattern[str]] = re.compile(r"^I\d{3,12}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    institutions: List[str] = Field(default_factory=list, description="The OpenAlex institutions.")
    include_affiliations: List[str] = Field(default_factory=list, description="The company's affiliation patterns.")
    exclude_affiliations: List[str] = Field(default_factory=list, description="The homonyms' affiliation patterns.")

    @field_validator("institutions", mode="before")
    def validate_institutions(cls, value: JsonValue) -> JsonValue:
        """Validate the raw institutions: OpenAlex identifiers (`I…`, a full URL is shortened), each once.

        Args:
            value (JsonValue): The raw institutions.

        Returns:
            JsonValue: The identifiers, each once in their order.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketTextError: If an identifier is not a text.
            InvalidCompanyValueError: If an identifier is not `I` followed by digits.
        """
        identifiers: List[JsonValue] = []
        for item in cls.CHECK.items(value, "OpenAlex institutions", "identifiers"):
            identifier = (cls.CHECK.text(item, "OpenAlex institution", 80) or "").rsplit("/", 1)[-1].upper()
            if not cls.INSTITUTION.match(identifier):
                raise InvalidCompanyValueError("OpenAlex institution", identifier, "I followed by digits")
            if identifier not in identifiers:
                identifiers.append(identifier)
        return identifiers

    @field_validator("include_affiliations", "exclude_affiliations", mode="before")
    def validate_exclude_affiliations(cls, value: JsonValue) -> JsonValue:
        """Validate the raw affiliation patterns: regular expressions that compile.

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
        for item in cls.CHECK.items(value, "affiliation patterns", "regular expressions"):
            pattern = cls.CHECK.text(item, "affiliation pattern", 200, collapse=False) or ""
            try:
                re.compile(pattern)
            except re.error as e:
                raise InvalidCompanyValueError("affiliation pattern", pattern, f"a regular expression ({e})") from e
            patterns.append(pattern)
        return patterns

    ############################
    # Publicly Exposed Methods #
    ############################

    def excludes(self, affiliation: str) -> bool:
        """Tell whether an affiliation text names another organisation than the company.

        Args:
            affiliation (str): The affiliation text, as the paper prints it.

        Returns:
            bool: Whether one of the exclusion patterns matches it, or none of the inclusion patterns (when the
                company has some) does.
        """
        if self.include_affiliations and not any(
            re.search(pattern, affiliation, re.IGNORECASE) for pattern in self.include_affiliations
        ):
            return True
        return any(re.search(pattern, affiliation, re.IGNORECASE) for pattern in self.exclude_affiliations)
