from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Optional, Pattern, Sequence

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.catalog.company_entry import CompanyEntry
from models.companies.exception import DuplicateCompanyKeyError, InvalidCompanyValueError
from models.companies.settings.openalex_settings import OpenAlexSettings
from models.companies.settings.patents_settings import PatentsSettings
from models.markets.field_check import MarketFieldCheck


class CompaniesCatalog(BaseModel):
    """Where the financial statements, the patents and the papers of the chronology's companies are read.

    Attributes:
        ENV (ClassVar[Pattern[str]]): The format of an environment variable name.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        sec_user_agent_env (str): The environment variable holding the user agent SEC EDGAR asks for (a contact).
        patents (PatentsSettings): How Google Patents is read.
        openalex (OpenAlexSettings): How OpenAlex is read.
        companies (List[CompanyEntry]): The companies, each once.

    Notes:
        - The catalogue is `data/curated/companies.json`, every company being a company of the chronology.
        - Secrets are never written in the catalogue: only the names of the environment variables holding them.
    """

    ENV: ClassVar[Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    sec_user_agent_env: str = Field(default="CRAWLER_SEC_USER_AGENT", description="The SEC user agent variable.")
    patents: PatentsSettings = Field(default_factory=PatentsSettings, description="How Google Patents is read.")
    openalex: OpenAlexSettings = Field(default_factory=OpenAlexSettings, description="How OpenAlex is read.")
    companies: List[CompanyEntry] = Field(default_factory=list, description="The companies.")

    @field_validator("sec_user_agent_env", mode="before")
    def validate_sec_user_agent_env(cls, value: JsonValue) -> JsonValue:
        """Validate the raw user agent variable: an upper-case name.

        Args:
            value (JsonValue): The raw name.

        Returns:
            JsonValue: The name.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompanyValueError: If it is not an upper-case variable name.
        """
        name = cls.CHECK.text(value, "SEC user agent variable", 64) or ""
        if not cls.ENV.match(name):
            raise InvalidCompanyValueError("SEC user agent variable", name, "an upper-case variable name")
        return name

    @field_validator("patents", "openalex", mode="before")
    def validate_settings(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate raw settings: a mapping, none meaning the defaults.

        Args:
            value (JsonValue): The raw settings.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The settings (validated by their model afterwards).

        Raises:
            InvalidCompanyValueError: If they are neither missing nor a mapping.
        """
        if value is None:
            return {}
        if not isinstance(value, (dict, PatentsSettings, OpenAlexSettings)):
            raise InvalidCompanyValueError(f"{info.field_name} settings", repr(value), "a mapping")
        return value

    @field_validator("companies", mode="before")
    def validate_companies(cls, value: JsonValue) -> JsonValue:
        """Validate the raw companies: a list, each company once.

        Args:
            value (JsonValue): The raw companies.

        Returns:
            JsonValue: The companies (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
            DuplicateCompanyKeyError: If a company is defined twice.
        """
        items = cls.CHECK.items(value, "companies", "mappings with a key")
        keys: List[str] = []
        for item in items:
            key = item.get("key") if isinstance(item, dict) else None
            if isinstance(key, str):
                if key in keys:
                    raise DuplicateCompanyKeyError("company", key)
                keys.append(key)
        return items

    ############################
    # Publicly Exposed Methods #
    ############################

    def entry(self, key: str) -> Optional[CompanyEntry]:
        """Get a company.

        Args:
            key (str): The company key.

        Returns:
            Optional[CompanyEntry]: The company, `None` when unknown.
        """
        return next((entry for entry in self.companies if entry.key == key), None)

    def entries(self, keys: Sequence[str]) -> List[CompanyEntry]:
        """Get the companies of a crawl scope.

        Args:
            keys (Sequence[str]): Only these companies, every one when empty.

        Returns:
            List[CompanyEntry]: The companies, in the catalogue order.
        """
        return [entry for entry in self.companies if not keys or entry.key in keys]
