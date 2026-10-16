from __future__ import annotations

# Third Party Imports.
from pydantic import Field, JsonValue, field_validator

# First Party Imports.
from models.configuration.logging.base.dict_config_model import DictConfigModel
from models.configuration.logging.enums import LogLevel


class LevelledModel(DictConfigModel):
    """Base model for `dictConfig` sections holding a case-insensitive logging level.

    Attributes:
        level (LogLevel): The minimum severity handled.
    """

    level: LogLevel = Field(default=LogLevel.NOTSET, description="The minimum severity handled.")

    @field_validator("level", mode="before")
    def normalize_level(cls, value: JsonValue) -> JsonValue:
        """Make the level case-insensitive.

        Args:
            value (JsonValue): The raw level.

        Returns:
            JsonValue: The upper-cased level when given a string, the raw value otherwise.
        """
        return value.upper() if isinstance(value, str) else value
