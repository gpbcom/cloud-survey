from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.compounding.config.foundations.foundation_link import FoundationLink
from models.compounding.exception import DuplicateCompoundingEntryError, InvalidCompoundingValueError
from models.markets.field_check import MarketFieldCheck


class CategoryFoundations(BaseModel):
    """The foundation set of a dependent category (R_s of the hazard model).

    Attributes:
        SLUG (ClassVar[Pattern[str]]): The format of a category slug.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        category (str): The dependent category (taxonomy slug).
        links (List[FoundationLink]): Its foundations, each once, never itself.
    """

    SLUG: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str = Field(description="The dependent category.")
    links: List[FoundationLink] = Field(min_length=1, description="Its foundations.")

    @field_validator("category", mode="before")
    def validate_category(cls, value: JsonValue) -> JsonValue:
        """Validate the raw category: a kebab-case slug.

        Args:
            value (JsonValue): The raw slug.

        Returns:
            JsonValue: The slug.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompoundingValueError: If it is not a kebab-case slug.
        """
        slug = cls.CHECK.text(value, "dependent category", 60) or ""
        if not cls.SLUG.match(slug):
            raise InvalidCompoundingValueError("dependent category", slug, "a kebab-case slug")
        return slug

    @field_validator("links", mode="before")
    def validate_links(cls, value: JsonValue) -> JsonValue:
        """Validate the raw links: a list, each foundation once.

        Args:
            value (JsonValue): The raw links.

        Returns:
            JsonValue: The links (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
            DuplicateCompoundingEntryError: If a foundation is listed twice.
        """
        items = cls.CHECK.items(value, "foundation links", "mappings with a foundation and a source")
        seen: List[str] = []
        for item in items:
            foundation = item.get("foundation") if isinstance(item, dict) else None
            if isinstance(foundation, str):
                if foundation in seen:
                    raise DuplicateCompoundingEntryError("foundation", foundation)
                seen.append(foundation)
        return items

    ############################
    # Publicly Exposed Methods #
    ############################

    def foundations(self) -> List[str]:
        """Get the foundation slugs.

        Returns:
            List[str]: The foundations, in their order.
        """
        return [link.foundation for link in self.links]
