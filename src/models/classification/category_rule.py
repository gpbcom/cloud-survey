from __future__ import annotations

# Standard Library Imports.
import re
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.classification.exception import InvalidRulePatternError, InvalidRuleSlugError


class CategoryRule(BaseModel):
    """Rule giving taxonomy categories to the texts matching a pattern.

    Attributes:
        pattern (str): The case-insensitive regular expression searched in the texts.
        categories (List[str]): The taxonomy slugs given to a matching text, at least one: categories, or domains
            when a text only tells the domain.

    Notes:
        The slugs are checked against the taxonomy when the classifier is built (`TaxonomySeedLoader.check`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pattern: str = Field(min_length=1, description="The case-insensitive regular expression searched in the texts.")
    categories: List[str] = Field(min_length=1, description="The taxonomy slugs given to a matching text.")

    @field_validator("pattern", mode="before")
    def validate_pattern(cls, value: JsonValue) -> JsonValue:
        """Validate the raw pattern.

        Args:
            value (JsonValue): The raw pattern.

        Returns:
            JsonValue: The unchanged pattern (its type is checked by pydantic afterwards).

        Raises:
            InvalidRulePatternError: If the pattern is not a valid regular expression.
        """
        if isinstance(value, str):
            try:
                re.compile(value)
            except re.error as e:
                raise InvalidRulePatternError(value, str(e)) from e
        return value

    @field_validator("categories", mode="before")
    def validate_categories(cls, value: JsonValue) -> JsonValue:
        """Validate the raw slugs: kebab-case, duplicates dropped.

        Args:
            value (JsonValue): The raw slugs.

        Returns:
            JsonValue: The slugs without duplicates (their type is checked by pydantic afterwards).

        Raises:
            InvalidRuleSlugError: If a slug is not kebab-case.
        """
        if not isinstance(value, list):
            return value
        for slug in value:
            if isinstance(slug, str) and not re.fullmatch(r"^[a-z0-9]+(-[a-z0-9]+)*$", slug):
                raise InvalidRuleSlugError(slug)
        return list(dict.fromkeys(slug for slug in value if isinstance(slug, str)))
