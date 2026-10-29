from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.compounding.exception import InvalidCompoundingValueError
from models.markets.field_check import MarketFieldCheck


class FoundationLink(BaseModel):
    """A category a dependent category is built on, with the document showing it.

    Attributes:
        SLUG (ClassVar[Pattern[str]]): The format of a category slug.
        URL (ClassVar[Pattern[str]]): The format of a source.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        foundation (str): The foundation category (taxonomy slug).
        source (str): The document showing the link (a web address).
    """

    SLUG: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    URL: ClassVar[Pattern[str]] = re.compile(r"^https?://\S+$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    foundation: str = Field(description="The foundation category.")
    source: str = Field(description="The document showing the link.")

    @field_validator("foundation", mode="before")
    def validate_foundation(cls, value: JsonValue) -> JsonValue:
        """Validate the raw foundation: a kebab-case slug.

        Args:
            value (JsonValue): The raw slug.

        Returns:
            JsonValue: The slug.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompoundingValueError: If it is not a kebab-case slug.
        """
        slug = cls.CHECK.text(value, "foundation category", 60) or ""
        if not cls.SLUG.match(slug):
            raise InvalidCompoundingValueError("foundation category", slug, "a kebab-case slug")
        return slug

    @field_validator("source", mode="before")
    def validate_source(cls, value: JsonValue) -> JsonValue:
        """Validate the raw source: a web address.

        Args:
            value (JsonValue): The raw source.

        Returns:
            JsonValue: The source.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompoundingValueError: If it is not a web address.
        """
        source = cls.CHECK.text(value, "foundation source", 500) or ""
        if not cls.URL.match(source):
            raise InvalidCompoundingValueError("foundation source", source, "a web address")
        return source
