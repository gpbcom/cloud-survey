from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.enums import MarketControl
from models.markets.field_check import MarketFieldCheck


class ControlHelp(BaseModel):
    """What a control of the markets cards does, as its tooltip explains it (the `markets` block of `conf/help.yaml`).

    Attributes:
        TEXTS (ClassVar[Dict[str, int]]): The longest text of each text field.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        control (MarketControl): The control.
        title (str): Its name, the first line of the tooltip.
        summary (str): What it changes and how the figures are computed.
    """

    TEXTS: ClassVar[Dict[str, int]] = {"title": 60, "summary": 900}
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    control: MarketControl = Field(description="The control.")
    title: str = Field(min_length=1, max_length=60, description="Its name.")
    summary: str = Field(min_length=1, max_length=900, description="What it changes and how.")

    @field_validator("control", mode="before")
    def validate_control(cls, value: JsonValue) -> JsonValue:
        """Validate the raw control: a `MarketControl` value.

        Args:
            value (JsonValue): The raw control.

        Returns:
            JsonValue: The control.

        Raises:
            InvalidMarketChoiceError: If it is not a known control.
        """
        return cls.CHECK.choice(value, "help control", [control.value for control in MarketControl])

    @field_validator("title", "summary", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw title or summary: a text within its length, its lines joined.

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text, its spaces collapsed.

        Raises:
            InvalidMarketTextError: If it is not a text of the right length.
        """
        name = str(info.field_name)
        return cls.CHECK.text(value, f"help {name}", cls.TEXTS[name])
