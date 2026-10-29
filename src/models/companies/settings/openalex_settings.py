from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class OpenAlexSettings(BaseModel):
    """How OpenAlex is read: the API keys (by the names of their environment variables) and the page sizes.

    Attributes:
        ENV (ClassVar[Pattern[str]]): The format of an environment variable name.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        key_envs (List[str]): The environment variables holding the API keys, rotated when one is rate limited
            (mega-trends' `OPENALEX_API_KEY_1` and `OPENALEX_API_KEY_2`).
        mailto_env (str): The environment variable holding the contact address sent without a key.
        per_page (int): The works asked per page (OpenAlex allows 200).
        author_batch (int): The authors asked per request.
        max_works (int): The most works read per company, 0 for all of them.
        delay_seconds (float): The seconds between two requests.
        min_affiliation_years (int): The years of a researcher's profile at the company that confirm a member who
            was last seen elsewhere.
        min_company_papers (int): The stored papers signed with the company that confirm such a member.

    Notes:
        A researcher is confirmed as a member of the company when the company is their last known institution, or
        their profile lists it for `min_affiliation_years` years, or they signed `min_company_papers` stored papers
        with it. The others (one paper, one year, now elsewhere) are mostly affiliations OpenAlex copied onto every
        author of a paper: they are kept out of the researchers shown and counted.
    """

    ENV: ClassVar[Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    key_envs: List[str] = Field(default_factory=list, description="The variables holding the API keys.")
    mailto_env: str = Field(default="CRAWLER_OPENALEX_MAILTO", description="The variable holding the contact.")
    per_page: int = Field(default=200, ge=1, le=200, description="The works asked per page.")
    author_batch: int = Field(default=50, ge=1, le=100, description="The authors asked per request.")
    max_works: int = Field(default=0, ge=0, description="The most works read per company, 0 for all.")
    delay_seconds: float = Field(default=0.2, ge=0, le=60, description="The seconds between two requests.")
    min_affiliation_years: int = Field(default=2, ge=1, description="The profile years confirming a member.")
    min_company_papers: int = Field(default=2, ge=1, description="The stored papers confirming a member.")

    @field_validator("key_envs", mode="before")
    def validate_key_envs(cls, value: JsonValue) -> JsonValue:
        """Validate the raw key variables: upper-case names, each once.

        Args:
            value (JsonValue): The raw names.

        Returns:
            JsonValue: The names, each once in their order.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketTextError: If a name is not a text.
            InvalidCompanyValueError: If a name is not an upper-case variable name.
        """
        names: List[JsonValue] = []
        for item in cls.CHECK.items(value, "OpenAlex key variables", "variable names"):
            name = cls.CHECK.text(item, "OpenAlex key variable", 64) or ""
            if not cls.ENV.match(name):
                raise InvalidCompanyValueError("OpenAlex key variable", name, "an upper-case variable name")
            if name not in names:
                names.append(name)
        return names

    @field_validator("mailto_env", mode="before")
    def validate_mailto_env(cls, value: JsonValue) -> JsonValue:
        """Validate the raw contact variable: an upper-case name.

        Args:
            value (JsonValue): The raw name.

        Returns:
            JsonValue: The name.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompanyValueError: If it is not an upper-case variable name.
        """
        name = cls.CHECK.text(value, "OpenAlex contact variable", 64) or ""
        if not cls.ENV.match(name):
            raise InvalidCompanyValueError("OpenAlex contact variable", name, "an upper-case variable name")
        return name

    @field_validator(
        "per_page", "author_batch", "max_works", "min_affiliation_years", "min_company_papers", mode="before"
    )
    def validate_count(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw count: a whole number of at least 0.

        Args:
            value (JsonValue): The raw count.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The count.

        Raises:
            InvalidMarketNumberError: If it is not a whole number of at least 0.
        """
        return cls.CHECK.number(value, f"OpenAlex {info.field_name}", low=0, integer=True)

    @field_validator("delay_seconds", mode="before")
    def validate_delay_seconds(cls, value: JsonValue) -> JsonValue:
        """Validate the raw delay: a number of seconds from 0 to 60.

        Args:
            value (JsonValue): The raw delay.

        Returns:
            JsonValue: The delay.

        Raises:
            InvalidMarketNumberError: If it is not a number from 0 to 60.
        """
        return cls.CHECK.number(value, "OpenAlex request delay", low=0.0, high=60.0)
