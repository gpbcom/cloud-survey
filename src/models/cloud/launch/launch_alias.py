from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.exception import InvalidLaunchFieldError


class LaunchAlias(BaseModel):
    """The name a provider's dated source gives a catalogue product, when it differs from the catalogue's.

    Attributes:
        CRAWLER (ClassVar[Pattern[str]]): The format of a crawler name: lower-case words joined by hyphens.
        NAME_LIMIT (ClassVar[int]): The longest product name.
        crawler (str): The crawler of the product, e.g. `azure`.
        name (str): The product, as the catalogue names it, e.g. `Azure OpenAI in Foundry Models`.
        feed_name (str): The product, as the dated source names it, e.g. `Azure OpenAI Service`.

    Notes:
        A product renamed after its launch keeps its former name in the provider's updates feed, e.g. the products
        Microsoft moved under Foundry in 2025.
    """

    CRAWLER: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    NAME_LIMIT: ClassVar[int] = 120

    model_config = ConfigDict(frozen=True, extra="forbid")

    crawler: str = Field(description="The crawler of the product.")
    name: str = Field(description="The product, as the catalogue names it.")
    feed_name: str = Field(description="The product, as the dated source names it.")

    @field_validator("crawler", mode="before")
    def validate_crawler(cls, value: JsonValue) -> JsonValue:
        """Validate the raw crawler name: lower-case words joined by hyphens.

        Args:
            value (JsonValue): The raw crawler name.

        Returns:
            JsonValue: The crawler name, trimmed.

        Raises:
            InvalidLaunchFieldError: If it is not lower-case words joined by hyphens.
        """
        crawler = value.strip() if isinstance(value, str) else ""
        if not cls.CRAWLER.match(crawler):
            raise InvalidLaunchFieldError("crawler", str(value), "lower-case words joined by hyphens")
        return crawler

    @field_validator("name", "feed_name", mode="before")
    def validate_names(cls, value: JsonValue) -> JsonValue:
        """Validate a raw product name: a text of 1 to 120 characters, spaces collapsed.

        Args:
            value (JsonValue): The raw product name.

        Returns:
            JsonValue: The product name.

        Raises:
            InvalidLaunchFieldError: If it is not a text of 1 to 120 characters.
        """
        name = " ".join(value.split()) if isinstance(value, str) else ""
        if not 0 < len(name) <= cls.NAME_LIMIT:
            raise InvalidLaunchFieldError("product name", str(value), f"a text of 1 to {cls.NAME_LIMIT} characters")
        return name
