from __future__ import annotations

import re

# Standard Library Imports.
from datetime import datetime
from typing import ClassVar, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.drivers.exception import InvalidSourceIdentifierError


class CompanyFact(BaseModel):
    """What Wikidata states about a provider: its founding date, and its employees at a date.

    Attributes:
        ITEM (ClassVar[Pattern[str]]): The format of a Wikidata item.
        provider (CloudProvider): The provider.
        item (str): Its Wikidata item, e.g. `Q456157`.
        inception (Optional[datetime]): Its founding date (P571), if stated.
        employees (Optional[float]): Its employees (P1128), if stated.
        employees_at (Optional[datetime]): When the employees were counted (P585), if stated.
        source_url (str): The item page.
    """

    ITEM: ClassVar[Pattern[str]] = re.compile(r"^Q\d+$")

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: CloudProvider = Field(description="The provider.")
    item: str = Field(description="Its Wikidata item.")
    inception: Optional[datetime] = Field(default=None, description="Its founding date.")
    employees: Optional[float] = Field(default=None, ge=0, description="Its employees.")
    employees_at: Optional[datetime] = Field(default=None, description="When the employees were counted.")
    source_url: str = Field(min_length=1, max_length=2048, description="The item page.")

    @field_validator("item", mode="before")
    def validate_item(cls, value: JsonValue) -> JsonValue:
        """Validate the raw item: `Q` and digits, the last segment of an entity URL.

        Args:
            value (JsonValue): The raw item, or its entity URL.

        Returns:
            JsonValue: The item.

        Raises:
            InvalidSourceIdentifierError: If it is not `Q` followed by digits.
        """
        if not isinstance(value, str):
            return value
        item = value.strip().rsplit("/", 1)[-1].upper()
        if not cls.ITEM.match(item):
            raise InvalidSourceIdentifierError("Wikidata item", value, "Q followed by digits")
        return item

    @field_validator("source_url", mode="before")
    def validate_source_url(cls, value: JsonValue) -> JsonValue:
        """Validate the raw page: trimmed.

        Args:
            value (JsonValue): The raw page.

        Returns:
            JsonValue: The page, trimmed.
        """
        return value.strip() if isinstance(value, str) else value
