from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.drivers.exception import InvalidSourceIdentifierError


class MetricSourceEntry(BaseModel):
    """Where a provider is found at the metric sources: its SEC filer, Wikidata item, networks and repositories.

    Attributes:
        CIK (ClassVar[Pattern[str]]): The format of an SEC Central Index Key (up to 10 digits).
        WIKIDATA (ClassVar[Pattern[str]]): The format of a Wikidata item (`Q` and digits).
        REPOSITORY (ClassVar[Pattern[str]]): The format of a GitHub repository (`owner/name`).
        provider (CloudProvider): The provider.
        cik (Optional[str]): The SEC filer of its group (the capex is the group's), zero-padded to 10 digits.
        wikidata (Optional[str]): The Wikidata item of the provider (its founding date, its employees).
        asns (List[int]): Its autonomous systems at PeeringDB.
        repositories (List[str]): Its SDK and Terraform provider repositories at GitHub.
    """

    CIK: ClassVar[Pattern[str]] = re.compile(r"^\d{1,10}$")
    WIKIDATA: ClassVar[Pattern[str]] = re.compile(r"^Q\d+$")
    REPOSITORY: ClassVar[Pattern[str]] = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: CloudProvider = Field(description="The provider.")
    cik: Optional[str] = Field(default=None, description="The SEC filer of its group.")
    wikidata: Optional[str] = Field(default=None, description="Its Wikidata item.")
    asns: List[int] = Field(default_factory=list, description="Its autonomous systems.")
    repositories: List[str] = Field(default_factory=list, description="Its GitHub repositories.")

    @field_validator("cik", mode="before")
    def validate_cik(cls, value: JsonValue) -> JsonValue:
        """Validate the raw CIK: digits, zero-padded to 10.

        Args:
            value (JsonValue): The raw CIK (a string or a number).

        Returns:
            JsonValue: The CIK, 10 digits.

        Raises:
            InvalidSourceIdentifierError: If it is not made of up to 10 digits.
        """
        if value is None or isinstance(value, bool) or not isinstance(value, (str, int)):
            return value
        cik = str(value).strip()
        if not cls.CIK.match(cik):
            raise InvalidSourceIdentifierError("SEC CIK", cik, "up to 10 digits")
        return cik.zfill(10)

    @field_validator("wikidata", mode="before")
    def validate_wikidata(cls, value: JsonValue) -> JsonValue:
        """Validate the raw Wikidata item: `Q` and digits.

        Args:
            value (JsonValue): The raw item.

        Returns:
            JsonValue: The item, upper-cased.

        Raises:
            InvalidSourceIdentifierError: If it is not `Q` followed by digits.
        """
        if not isinstance(value, str):
            return value
        item = value.strip().upper()
        if not cls.WIKIDATA.match(item):
            raise InvalidSourceIdentifierError("Wikidata item", value, "Q followed by digits")
        return item

    @field_validator("asns", mode="before")
    def validate_asns(cls, value: JsonValue) -> JsonValue:
        """Validate the raw autonomous systems: positive numbers, each once.

        Args:
            value (JsonValue): The raw numbers.

        Returns:
            JsonValue: The numbers, each once, in their order.

        Raises:
            InvalidSourceIdentifierError: If one is not a positive number.
        """
        if not isinstance(value, list):
            return value
        numbers: List[JsonValue] = []
        for item in value:
            if isinstance(item, bool) or not isinstance(item, (int, str)) or not str(item).strip().isdigit():
                raise InvalidSourceIdentifierError("autonomous system", str(item), "a positive number")
            number = int(str(item).strip())
            if number <= 0:
                raise InvalidSourceIdentifierError("autonomous system", str(item), "a positive number")
            if number not in numbers:
                numbers.append(number)
        return numbers

    @field_validator("repositories", mode="before")
    def validate_repositories(cls, value: JsonValue) -> JsonValue:
        """Validate the raw repositories: `owner/name`, each once.

        Args:
            value (JsonValue): The raw repositories.

        Returns:
            JsonValue: The repositories, each once, in their order.

        Raises:
            InvalidSourceIdentifierError: If one is not written `owner/name`.
        """
        if not isinstance(value, list):
            return value
        repositories: List[JsonValue] = []
        for item in value:
            name = str(item).strip()
            if not cls.REPOSITORY.match(name):
                raise InvalidSourceIdentifierError("GitHub repository", name, "owner/name")
            if name not in repositories:
                repositories.append(name)
        return repositories
