from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, FrozenSet

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.drivers.enums import DriverScope, MetricScale
from models.drivers.exception import InvalidHelpTextError, UnknownHelpChoiceError


class ChoiceHelp(BaseModel):
    """What a scale or a scope of the driver analysis means, as its tooltip explains it.

    Attributes:
        CHOICES (ClassVar[FrozenSet[str]]): The choices that can be explained: the scale and the scope values.
        choice (str): The choice, e.g. `count` or `panel`.
        summary (str): What it does to the figures.

    Notes:
        A scale says how a criterion is transformed before the statistics, a scope which observations are compared.
    """

    CHOICES: ClassVar[FrozenSet[str]] = frozenset(
        [scale.value for scale in MetricScale] + [scope.value for scope in DriverScope]
    )

    model_config = ConfigDict(frozen=True, extra="forbid")

    choice: str = Field(min_length=1, description="The choice.")
    summary: str = Field(min_length=1, description="What it does to the figures.")

    @field_validator("choice", mode="before")
    def validate_choice(cls, value: JsonValue) -> JsonValue:
        """Validate the raw choice: a metric scale or a driver scope value.

        Args:
            value (JsonValue): The raw choice.

        Returns:
            JsonValue: The choice, trimmed.

        Raises:
            UnknownHelpChoiceError: If it is not a scale or a scope value.
        """
        choice = value.strip() if isinstance(value, str) else repr(value)
        if choice not in cls.CHOICES:
            raise UnknownHelpChoiceError(choice)
        return choice

    @field_validator("summary", mode="before")
    def validate_summary(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate the raw summary: a non-empty text, its lines joined.

        Args:
            value (JsonValue): The raw summary.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The summary, its spaces collapsed.

        Raises:
            InvalidHelpTextError: If it is missing or not a text.
        """
        text = " ".join(value.split()) if isinstance(value, str) else ""
        if not text:
            raise InvalidHelpTextError(str(info.field_name))
        return text
