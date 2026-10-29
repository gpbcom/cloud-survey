from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.drivers.enums import MetricValueColumn
from models.drivers.exception import InvalidHelpTextError


class ValueColumnHelp(BaseModel):
    """What a column of the table of the stored provider metrics shows, as its header tooltip explains it.

    Attributes:
        column (MetricValueColumn): The column.
        title (str): Its header, e.g. `Fetched`.
        summary (str): What it shows, and how to use it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    column: MetricValueColumn = Field(description="The column.")
    title: str = Field(min_length=1, max_length=24, description="Its header.")
    summary: str = Field(min_length=1, description="What it shows.")

    @field_validator("title", "summary", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw text: a non-empty text, its lines joined.

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text, its spaces collapsed.

        Raises:
            InvalidHelpTextError: If it is missing or not a text.
        """
        text = " ".join(value.split()) if isinstance(value, str) else ""
        if not text:
            raise InvalidHelpTextError(str(info.field_name))
        return text
