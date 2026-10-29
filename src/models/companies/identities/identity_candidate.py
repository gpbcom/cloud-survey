from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.exception import InvalidCompanyValueError
from models.curated.enums import IdentifierKind
from models.markets.field_check import MarketFieldCheck


class IdentityCandidate(BaseModel):
    """An identifier a resolver found for a company at a source: a SEC filer, an OpenAlex institution, an assignee.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a company key.
        URL (ClassVar[Pattern[str]]): The format of the evidence.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        company (str): The company it identifies.
        identifier_kind (IdentifierKind): What it identifies the company at.
        value (str): The identifier, as the catalogue writes it.
        label (str): What the source names it.
        evidence_url (str): The page that shows it.
        reason (str): Why the resolver proposes it.
        verified (bool): Whether it is unambiguous and passed its check (it is then confirmed at once).

    Notes:
        A candidate is written as a proposed identifier (`company_identifiers`, status `candidate`, origin
        `resolver`), which a person accepts or rejects in the Catalogues manager. An identifier already stored, in
        any status, is never proposed again.
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    URL: ClassVar[Pattern[str]] = re.compile(r"^https://\S+$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(description="The company it identifies.")
    identifier_kind: IdentifierKind = Field(description="What it identifies the company at.")
    value: str = Field(description="The identifier.")
    label: str = Field(description="What the source names it.")
    evidence_url: str = Field(description="The page that shows it.")
    reason: str = Field(description="Why it is proposed.")
    verified: bool = Field(default=False, description="Whether it is unambiguous and checked.")

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
        key = cls.CHECK.text(value, "candidate company", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidCompanyValueError("candidate company", key, "lower-case words joined by hyphens")
        return key

    @field_validator("value", mode="before")
    def validate_value(cls, value: JsonValue) -> JsonValue:
        """Validate the raw identifier: a text of 1 to 300 characters.

        Args:
            value (JsonValue): The raw identifier.

        Returns:
            JsonValue: The identifier, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 300 characters.
        """
        return cls.CHECK.text(value, "candidate identifier", 300, collapse=False)

    @field_validator("label", mode="before")
    def validate_label(cls, value: JsonValue) -> JsonValue:
        """Validate the raw name: a text of 1 to 300 characters.

        Args:
            value (JsonValue): The raw name.

        Returns:
            JsonValue: The name, its spaces collapsed.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 300 characters.
        """
        return cls.CHECK.text(value, "candidate name", 300)

    @field_validator("evidence_url", mode="before")
    def validate_evidence_url(cls, value: JsonValue) -> JsonValue:
        """Validate the raw evidence: an https URL.

        Args:
            value (JsonValue): The raw URL.

        Returns:
            JsonValue: The URL.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 2048 characters.
            InvalidCompanyValueError: If it is not an https URL.
        """
        url = cls.CHECK.text(value, "candidate evidence", 2048) or ""
        if not cls.URL.match(url):
            raise InvalidCompanyValueError("candidate evidence", url, "an https URL")
        return url

    @field_validator("reason", mode="before")
    def validate_reason(cls, value: JsonValue) -> JsonValue:
        """Validate the raw reason: a text of 1 to 300 characters.

        Args:
            value (JsonValue): The raw reason.

        Returns:
            JsonValue: The reason, its spaces collapsed.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 300 characters.
        """
        return cls.CHECK.text(value, "candidate reason", 300)
