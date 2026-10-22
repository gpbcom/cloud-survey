from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.drivers.enums import DriverWarningKind, ProviderMetric


class DriverWarning(BaseModel):
    """What limits the conclusions of a driver analysis: its kind, the sentence of this run, the criteria concerned.

    Attributes:
        kind (DriverWarningKind): What limits the conclusions (its explanation is in `conf/metrics/drivers-help.yaml`).
        message (str): The warning of this run, with its figures.
        subjects (List[ProviderMetric]): The criteria concerned, if any.
    """

    model_config = ConfigDict(frozen=True)

    kind: DriverWarningKind = Field(description="What limits the conclusions.")
    message: str = Field(min_length=1, description="The warning of this run.")
    subjects: List[ProviderMetric] = Field(default_factory=list, description="The criteria concerned.")

    @field_validator("message", mode="before")
    def validate_message(cls, value: JsonValue) -> JsonValue:
        """Validate the raw message: trimmed.

        Args:
            value (JsonValue): The raw message.

        Returns:
            JsonValue: The message, trimmed.
        """
        return value.strip() if isinstance(value, str) else value

    @field_validator("subjects", mode="before")
    def validate_subjects(cls, value: JsonValue) -> JsonValue:
        """Validate the raw criteria: each once, in their order.

        Args:
            value (JsonValue): The raw criteria.

        Returns:
            JsonValue: The criteria, each once.
        """
        if not isinstance(value, list):
            return value
        unique: List[JsonValue] = [*dict.fromkeys(str(item) for item in value)]
        return unique
