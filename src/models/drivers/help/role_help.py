from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.drivers.enums import DriverRole


class RoleHelp(BaseModel):
    """What a parameter does in a driver analysis, as the role legend explains it.

    Attributes:
        role (DriverRole): The role.
        title (str): Its name, e.g. `Target`.
        symbol (str): A short glyph drawn on its chip.
        summary (str): What it is, in one line.
        details (str): How the statistics use it, and how to pick it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: DriverRole = Field(description="The role.")
    title: str = Field(min_length=1, description="Its name.")
    symbol: str = Field(min_length=1, max_length=2, description="A short glyph drawn on its chip.")
    summary: str = Field(min_length=1, description="What it is, in one line.")
    details: str = Field(min_length=1, description="How the statistics use it.")

    @field_validator("title", "symbol", "summary", "details", mode="before")
    def validate_text(cls, value: JsonValue) -> JsonValue:
        """Validate a raw text: trimmed, its lines joined.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The text, trimmed.
        """
        return " ".join(value.split()) if isinstance(value, str) else value
