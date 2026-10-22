from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.correspondence.llm.member_answer import MemberAnswer


class ConceptAnswer(BaseModel):
    """The language model answer for one service concept: its name and its services.

    Attributes:
        concept_id (Optional[int]): The identifier of an existing concept, as sent, `None` for a new one.
        name (str): The short English name of the concept (e.g. "Managed Kubernetes").
        description (str): What the concept stands for, in one line.
        members (List[MemberAnswer]): The services filed under it.
    """

    model_config = ConfigDict(extra="forbid")

    concept_id: Optional[int] = Field(default=None, description="An existing concept identifier, or null.")
    name: str = Field(description="The short English name of the concept.")
    description: str = Field(default="", description="What the concept stands for, in one line.")
    members: List[MemberAnswer] = Field(default_factory=list, description="The services filed under it.")

    @field_validator("name", "description", mode="before")
    def validate_text(cls, value: JsonValue) -> JsonValue:
        """Validate a raw text: spaces collapsed and trimmed.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The cleaned text (its type is checked by pydantic afterwards), empty when missing.
        """
        if value is None:
            return ""
        return " ".join(value.split())[:300] if isinstance(value, str) else value
