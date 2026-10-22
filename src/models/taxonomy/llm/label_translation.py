from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class LabelTranslation(BaseModel):
    """The language model answer for one source label: its English name, its taxonomy nodes, or noise.

    Attributes:
        id (int): The label identifier, as sent.
        english (str): The English name of the label, as a short category name.
        slugs (List[str]): Up to three taxonomy slugs (categories, or a domain) the label files its items under.
        noise (bool): Whether the label is not a category (a tab, a vendor, a promotion, "Other").
    """

    model_config = ConfigDict(extra="forbid")

    id: int = Field(description="The label identifier, as sent.")
    english: str = Field(description="The English name of the label.")
    slugs: List[str] = Field(default_factory=list, description="Up to three taxonomy slugs.")
    noise: bool = Field(default=False, description="Whether the label is not a category.")

    @field_validator("english", mode="before")
    def validate_english(cls, value: JsonValue) -> JsonValue:
        """Validate the raw English name: spaces collapsed and trimmed.

        Args:
            value (JsonValue): The raw name.

        Returns:
            JsonValue: The cleaned name (checked by pydantic afterwards).
        """
        return " ".join(value.split()) if isinstance(value, str) else value

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
