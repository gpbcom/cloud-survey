from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.history.exception import InvalidHistoryKeyError


class SegmentDefinition(BaseModel):
    """A market segment of the computing chronology: a swimlane of the leaders chart.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a key: lower-case words joined by hyphens.
        key (str): Its key, e.g. `mainframes`.
        label (str): Its name, e.g. `Mainframes`.
        description (str): Its market definition (what the shares measure).
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(description="Its key.")
    label: str = Field(min_length=1, description="Its name.")
    description: str = Field(default="", description="Its market definition.")

    @field_validator("key", mode="before")
    def validate_key(cls, value: JsonValue) -> JsonValue:
        """Validate the raw key: lower-case words joined by hyphens.

        Args:
            value (JsonValue): The raw key.

        Returns:
            JsonValue: The key, trimmed.

        Raises:
            InvalidHistoryKeyError: If it is not lower-case words joined by hyphens.
        """
        if not isinstance(value, str):
            return value
        key = value.strip()
        if not cls.KEY.match(key):
            raise InvalidHistoryKeyError("segment key", value, "lower-case words joined by hyphens")
        return key

    @field_validator("label", "description", mode="before")
    def validate_text(cls, value: JsonValue) -> JsonValue:
        """Validate a raw text: trimmed, its lines joined.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The text.
        """
        return " ".join(value.split()) if isinstance(value, str) else value
