from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.drivers.exception import InvalidSourceIdentifierError


class RepositoryFact(BaseModel):
    """A GitHub repository of a provider (its Terraform provider or an SDK) and its stars.

    Attributes:
        REPOSITORY (ClassVar[Pattern[str]]): The format of a repository (`owner/name`).
        provider (CloudProvider): The provider.
        repository (str): The repository, `owner/name`.
        stars (int): Its stars.
        source_url (str): The document read.
    """

    REPOSITORY: ClassVar[Pattern[str]] = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: CloudProvider = Field(description="The provider.")
    repository: str = Field(description="The repository.")
    stars: int = Field(ge=0, description="Its stars.")
    source_url: str = Field(min_length=1, max_length=2048, description="The document read.")

    @field_validator("repository", mode="before")
    def validate_repository(cls, value: JsonValue) -> JsonValue:
        """Validate the raw repository: `owner/name`.

        Args:
            value (JsonValue): The raw repository.

        Returns:
            JsonValue: The repository, trimmed.

        Raises:
            InvalidSourceIdentifierError: If it is not written `owner/name`.
        """
        if not isinstance(value, str):
            return value
        name = value.strip()
        if not cls.REPOSITORY.match(name):
            raise InvalidSourceIdentifierError("GitHub repository", value, "owner/name")
        return name

    @field_validator("source_url", mode="before")
    def validate_source_url(cls, value: JsonValue) -> JsonValue:
        """Validate the raw document: trimmed.

        Args:
            value (JsonValue): The raw document.

        Returns:
            JsonValue: The document, trimmed.
        """
        return value.strip() if isinstance(value, str) else value
