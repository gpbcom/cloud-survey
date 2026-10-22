from __future__ import annotations

# Standard Library Imports.
import re
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.classification.exception import InvalidRulePatternError
from models.cloud.enums import SoftwareCategory


class AudienceHint(BaseModel):
    """Source labels directly telling who an item is meant for, whatever its categories.

    Attributes:
        pattern (str): The case-insensitive regular expression searched in the source labels.
        audiences (List[SoftwareCategory]): The audiences given to the items filed under a matching label.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pattern: str = Field(min_length=1, description="The case-insensitive regular expression searched in the labels.")
    audiences: List[SoftwareCategory] = Field(min_length=1, description="The audiences of a matching label.")

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
