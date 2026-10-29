from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.catalog.market_cap_source import MarketCapSource
from models.companies.catalog.openalex_affiliation import OpenAlexAffiliation
from models.companies.catalog.patent_search import PatentSearch
from models.companies.enums import StatementKind
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class CompanyEntry(BaseModel):
    """Where the financial statements, the patents and the papers of a company of the chronology are found.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a company key: lower-case words joined by hyphens.
        CIK (ClassVar[Pattern[str]]): The format of an SEC filer: up to 10 digits.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        key (str): The company of the chronology, e.g. `nvidia`.
        sec_ciks (List[str]): Its SEC EDGAR filers, 10 digits, the current one first (a group that split or was
            renamed filed under several, e.g. Hewlett-Packard then HP Inc.).
        market_cap (Optional[MarketCapSource]): The listing it is valued on when it is not its primary listing at
            one share per unit.
        patents (Optional[PatentSearch]): How its patents are searched, `None` when not searched.
        openalex (OpenAlexAffiliation): Its OpenAlex institutions, none when not searched.
        statements (StatementKind): The shape of its statements (a bank's skip the scores and the liquidity ratios).
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    CIK: ClassVar[Pattern[str]] = re.compile(r"^\d{1,10}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(description="The company of the chronology.")
    sec_ciks: List[str] = Field(default_factory=list, description="Its SEC EDGAR filers.")
    market_cap: Optional[MarketCapSource] = Field(default=None, description="The listing it is valued on.")
    patents: Optional[PatentSearch] = Field(default=None, description="How its patents are searched.")
    openalex: OpenAlexAffiliation = Field(default_factory=OpenAlexAffiliation, description="Its institutions.")
    statements: StatementKind = Field(default=StatementKind.INDUSTRIAL, description="The shape of its statements.")

    @field_validator("key", mode="before")
    def validate_key(cls, value: JsonValue) -> JsonValue:
        """Validate the raw company key: lower-case words joined by hyphens.

        Args:
            value (JsonValue): The raw key.

        Returns:
            JsonValue: The key.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 40 characters.
            InvalidCompanyValueError: If it is not lower-case words joined by hyphens.
        """
        key = cls.CHECK.text(value, "company key", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidCompanyValueError("company key", key, "lower-case words joined by hyphens")
        return key

    @field_validator("sec_ciks", mode="before")
    def validate_sec_ciks(cls, value: JsonValue) -> JsonValue:
        """Validate the raw SEC filers: up to 10 digits each, padded to 10, each once.

        Args:
            value (JsonValue): The raw filers (texts or numbers).

        Returns:
            JsonValue: The filers, 10 digits, each once in their order.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketTextError: If a filer is not a text.
            InvalidCompanyValueError: If a filer is not up to 10 digits.
        """
        ciks: List[JsonValue] = []
        for item in cls.CHECK.items(value, "SEC filers", "identifiers"):
            cik = cls.CHECK.text(str(item) if isinstance(item, int) else item, "SEC filer", 10) or ""
            if not cls.CIK.match(cik):
                raise InvalidCompanyValueError("SEC filer", cik, "up to 10 digits")
            if cik.zfill(10) not in ciks:
                ciks.append(cik.zfill(10))
        return ciks

    @field_validator("market_cap", mode="before")
    def validate_market_cap(cls, value: JsonValue) -> JsonValue:
        """Validate the raw valued listing: a mapping, or none.

        Args:
            value (JsonValue): The raw listing.

        Returns:
            JsonValue: The listing (validated by its model afterwards).

        Raises:
            InvalidCompanyValueError: If it is neither missing nor a mapping.
        """
        if value is not None and not isinstance(value, (dict, MarketCapSource)):
            raise InvalidCompanyValueError("valued listing", repr(value), "a mapping of listing and shares_per_unit")
        return value

    @field_validator("patents", mode="before")
    def validate_patents(cls, value: JsonValue) -> JsonValue:
        """Validate the raw patents search: a mapping, or none.

        Args:
            value (JsonValue): The raw search.

        Returns:
            JsonValue: The search (validated by its model afterwards).

        Raises:
            InvalidCompanyValueError: If it is neither missing nor a mapping.
        """
        if value is not None and not isinstance(value, (dict, PatentSearch)):
            raise InvalidCompanyValueError("patents search", repr(value), "a mapping of assignees, since and exclude")
        return value

    @field_validator("openalex", mode="before")
    def validate_openalex(cls, value: JsonValue) -> JsonValue:
        """Validate the raw OpenAlex affiliation: a mapping, none meaning no institution.

        Args:
            value (JsonValue): The raw affiliation.

        Returns:
            JsonValue: The affiliation (validated by its model afterwards).

        Raises:
            InvalidCompanyValueError: If it is neither missing nor a mapping.
        """
        if value is None:
            return {}
        if not isinstance(value, (dict, OpenAlexAffiliation)):
            raise InvalidCompanyValueError("OpenAlex affiliation", repr(value), "a mapping of institutions")
        return value

    @field_validator("statements", mode="before")
    def validate_statements(cls, value: JsonValue) -> JsonValue:
        """Validate the raw shape of the statements: industrial or bank.

        Args:
            value (JsonValue): The raw shape.

        Returns:
            JsonValue: The shape.

        Raises:
            InvalidMarketChoiceError: If it is not a statement kind.
        """
        return cls.CHECK.choice(value, "statement kind", [kind.value for kind in StatementKind])
