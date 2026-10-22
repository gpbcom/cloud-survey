from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.configuration.llm.enums import LLMEffort


class LLMTaskRoute(BaseModel):
    """Which profile answers a task, and the two settings a task may override.

    Attributes:
        profile (str): The profile (tier) answering the task.
        effort (Optional[LLMEffort]): The effort of the task, that of the profile when not given.
        max_tokens (Optional[int]): The largest output of the task, that of the profile when not given.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: str = Field(min_length=1, description="The profile answering the task.")
    effort: Optional[LLMEffort] = Field(default=None, description="The effort of the task.")
    max_tokens: Optional[int] = Field(default=None, gt=0, le=128_000, description="The largest output.")

    @field_validator("profile", mode="before")
    def validate_profile(cls, value: JsonValue) -> JsonValue:
        """Trim the profile name.

        Args:
            value (JsonValue): The raw name.

        Returns:
            JsonValue: The trimmed name.
        """
        return value.strip() if isinstance(value, str) else value
