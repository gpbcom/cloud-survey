from __future__ import annotations

# Standard Library Imports.
import re
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.classification.exception import InvalidRulePatternError
from models.cloud.enums import SoftwareType


class TypeRule(BaseModel):
    """Rule giving software types to the texts matching a pattern.

    Attributes:
        pattern (str): The case-insensitive regular expression searched in the texts.
        types (List[SoftwareType]): The types given to a matching text, at least one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pattern: str = Field(min_length=1, description="The case-insensitive regular expression searched in the texts.")
    types: List[SoftwareType] = Field(min_length=1, description="The types given to a matching text.")

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
