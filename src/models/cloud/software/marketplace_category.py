from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class MarketplaceCategory(BaseModel):
    """A category of the marketplace of a cloud provider, in its own taxonomy, with the categories above it.

    Attributes:
        SEPARATOR (ClassVar[str]): The separator of the levels in a readable label.
        path (List[str]): The category labels from the root of the taxonomy to the category, as labelled by the
            marketplace (e.g. `["AI Agents & Tools", "Content Creation"]`).
        id (Optional[str]): The identifier (or slug) of the category in the marketplace, when it gives one.
    """

    model_config = ConfigDict(frozen=True)

    SEPARATOR: ClassVar[str] = " > "

    path: List[str] = Field(
        min_length=1, max_length=6, description="The category labels, from the root of the taxonomy to the category."
    )
    id: Optional[str] = Field(
        default=None, max_length=200, description="The identifier of the category in the marketplace."
    )

    @field_validator("path", mode="before")
    def validate_path(cls, value: JsonValue) -> JsonValue:
        """Validate the raw category path.

        The labels are trimmed, the blank ones and the repeated levels are dropped.

        Args:
            value (JsonValue): The raw labels, from the root to the category.

        Returns:
            JsonValue: The cleaned labels (their types and count are checked by pydantic afterwards).
        """
        if not isinstance(value, list):
            return value
        labels = [" ".join(label.split()) if isinstance(label, str) else label for label in value]
        path: List[JsonValue] = []
        for label in labels:
            if label != "" and (not path or path[-1] != label):
                path.append(label)
        return path

    @field_validator("id", mode="before")
    def validate_id(cls, value: JsonValue) -> JsonValue:
        """Validate the raw category identifier: numbers are kept as text.

        Args:
            value (JsonValue): The raw identifier.

        Returns:
            JsonValue: The trimmed identifier, `None` when missing or blank.
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            return value.strip() or None
        return value

    def label(self) -> str:
        """Get a readable label of the category, with the categories above it.

        Returns:
            str: The labels of the path, from the root, e.g.
                `AI Agents & Tools > Content Creation`.
        """
        return self.SEPARATOR.join(self.path)

    def is_above(self, other: MarketplaceCategory) -> bool:
        """Tell whether this category is above another one.

        It is above when it is its parent, or a further ancestor.

        Args:
            other (MarketplaceCategory): The other category.

        Returns:
            bool: Whether its path is a strict
                prefix of the path of the other category.
        """
        return len(self.path) < len(other.path) and other.path[: len(self.path)] == self.path
