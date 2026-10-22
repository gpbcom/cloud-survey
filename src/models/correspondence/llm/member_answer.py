from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.correspondence.enums import MemberRole


class MemberAnswer(BaseModel):
    """The language model answer for one service of a concept.

    Attributes:
        id (int): The service identifier, as sent.
        role (MemberRole): Whether the service does what the concept stands for, or part of it only.
        confidence (int): How sure the model is, from 0 to 100.
    """

    model_config = ConfigDict(extra="forbid")

    id: int = Field(description="The service identifier, as sent.")
    role: MemberRole = Field(default=MemberRole.EQUIVALENT, description="Equivalent, or partial.")
    confidence: int = Field(default=80, description="How sure the model is, from 0 to 100.")

    @field_validator("confidence", mode="before")
    def validate_confidence(cls, value: JsonValue) -> JsonValue:
        """Validate the raw confidence: rounded and kept between 0 and 100.

        Args:
            value (JsonValue): The raw confidence.

        Returns:
            JsonValue: The confidence, 80 when missing (its type is checked by pydantic afterwards).
        """
        if value is None:
            return 80
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return max(0, min(100, round(value)))
        return value
