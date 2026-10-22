from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class ResolvedLabel(BaseModel):
    """A source label as the categorization of the items sees it: its identity and the taxonomy nodes it tells.

    Attributes:
        id (int): The identifier of the label (`source_labels.id`).
        key (str): Its normalized key (see `LabelNormalizer.key`).
        group (str): The key shared by the label and its aliases (the same English name, or a merge).
        noise (bool): Whether the label is not a category: it tells no node.
        nodes (List[str]): The taxonomy slugs (categories or domains) the label and its aliases tell, without the
            excluded ones.
    """

    model_config = ConfigDict(frozen=True)

    id: int = Field(ge=1, description="The identifier of the label.")
    key: str = Field(description="Its normalized key.")
    group: str = Field(description="The key shared by the label and its aliases.")
    noise: bool = Field(default=False, description="Whether the label is not a category.")
    nodes: List[str] = Field(default_factory=list, description="The taxonomy slugs the label tells.")

    @field_validator("nodes", mode="before")
    def validate_nodes(cls, value: JsonValue) -> JsonValue:
        """Validate the raw nodes: duplicates dropped, a missing list read as empty.

        Args:
            value (JsonValue): The raw slugs.

        Returns:
            JsonValue: The slugs without duplicates, in their order (checked by pydantic afterwards).
        """
        if value is None:
            return []
        if isinstance(value, list):
            return list(dict.fromkeys(value))
        return value
