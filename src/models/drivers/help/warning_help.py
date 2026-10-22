from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.drivers.enums import DriverWarningKind, WarningSeverity


class WarningHelp(BaseModel):
    """What a warning of a driver analysis means, and what to do about it.

    Attributes:
        kind (DriverWarningKind): The warning.
        severity (WarningSeverity): How much it limits the conclusions.
        title (str): Its name, e.g. `Collinear criteria`.
        meaning (str): What it means for the results.
        remedy (str): What to do about it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: DriverWarningKind = Field(description="The warning.")
    severity: WarningSeverity = Field(description="How much it limits the conclusions.")
    title: str = Field(min_length=1, description="Its name.")
    meaning: str = Field(min_length=1, description="What it means for the results.")
    remedy: str = Field(min_length=1, description="What to do about it.")

    @field_validator("title", "meaning", "remedy", mode="before")
    def validate_text(cls, value: JsonValue) -> JsonValue:
        """Validate a raw text: trimmed, its lines joined.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The text, trimmed.
        """
        return " ".join(value.split()) if isinstance(value, str) else value
