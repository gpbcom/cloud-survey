from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class SeedLabel(BaseModel):
    """A source label of the label seed file (`conf/taxonomy/label-seed.yaml`): its translation and categories.

    Attributes:
        text (str): The label as the providers write it (any language).
        en (Optional[str]): Its English name, `None` to keep the text (English labels).
        links (List[str]): The taxonomy slugs (categories or domains) it files its items under.
        same_as (Optional[str]): Another label (its text) it is a synonym of: it becomes its alias.
        noise (bool): Whether the label is not a category (a tab, a vendor name, "Other").
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1, description="The label as the providers write it.")
    en: Optional[str] = Field(default=None, min_length=1, description="Its English name.")
    links: List[str] = Field(default_factory=list, description="The taxonomy slugs it files its items under.")
    same_as: Optional[str] = Field(default=None, min_length=1, description="The label it is a synonym of.")
    noise: bool = Field(default=False, description="Whether the label is not a category.")

    @field_validator("text", "en", "same_as", mode="before")
    def validate_text(cls, value: JsonValue) -> JsonValue:
        """Validate a raw text: spaces collapsed and trimmed.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The cleaned text (its type is checked by pydantic afterwards).
        """
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("links", mode="before")
    def validate_links(cls, value: JsonValue) -> JsonValue:
        """Validate the raw links: duplicates dropped, a missing list read as empty.

        Args:
            value (JsonValue): The raw links.

        Returns:
            JsonValue: The links without duplicates (checked by pydantic afterwards).
        """
        if value is None:
            return []
        if isinstance(value, list):
            return list(dict.fromkeys(item for item in value if isinstance(item, str)))
        return value
