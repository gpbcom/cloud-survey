from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.drivers.enums import DriverColumn


class ColumnHelp(BaseModel):
    """What a column of the driver table shows, and how to read it.

    Attributes:
        column (DriverColumn): The column.
        title (str): Its header, e.g. `Share of R²`.
        summary (str): What it shows, in a sentence.
        reading (str): How to read it: which values matter.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    column: DriverColumn = Field(description="The column.")
    title: str = Field(min_length=1, max_length=24, description="Its header.")
    summary: str = Field(min_length=1, description="What it shows.")
    reading: str = Field(min_length=1, description="How to read it.")

    @field_validator("title", "summary", "reading", mode="before")
    def validate_text(cls, value: JsonValue) -> JsonValue:
        """Validate a raw text: trimmed, its lines joined.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The text, trimmed.
        """
        return " ".join(value.split()) if isinstance(value, str) else value
