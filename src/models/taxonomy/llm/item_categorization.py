from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class ItemCategorization(BaseModel):
    """The language model answer for one item: the taxonomy categories it files the item under.

    Attributes:
        id (int): The item identifier, as sent.
        slugs (List[str]): One to three taxonomy category slugs, empty when none fits.
    """

    model_config = ConfigDict(extra="forbid")

    id: int = Field(description="The item identifier, as sent.")
    slugs: List[str] = Field(default_factory=list, description="One to three taxonomy category slugs.")

    @field_validator("slugs", mode="before")
    def validate_slugs(cls, value: JsonValue) -> JsonValue:
        """Validate the raw slugs: trimmed, lower-cased, each once, three at most.

        Args:
            value (JsonValue): The raw slugs.

        Returns:
            JsonValue: The cleaned slugs (checked by pydantic afterwards), an empty list when missing.
        """
        if value is None:
            return []
        if isinstance(value, list):
            cleaned: List[JsonValue] = [
                *dict.fromkeys(str(slug).strip().lower() for slug in value if str(slug).strip())
            ]
            return cleaned[:3]
        return value
