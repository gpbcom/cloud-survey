from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.enums import MarketControl
from models.markets.field_check import MarketFieldCheck


class OptionHelp(BaseModel):
    """What one choice of a markets control means, as the tooltip of its list item explains it.

    Attributes:
        TEXTS (ClassVar[Dict[str, int]]): The longest text of each text field.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        control (MarketControl): The control offering the choice.
        option (str): The value of the choice, e.g. `mobile`, `union` or `stock`.
        summary (str): What it shows, from which source, transformed how.
    """

    TEXTS: ClassVar[Dict[str, int]] = {"option": 40, "summary": 900}
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    control: MarketControl = Field(description="The control offering the choice.")
    option: str = Field(min_length=1, max_length=40, description="The value of the choice.")
    summary: str = Field(min_length=1, max_length=900, description="What it shows, from where, how.")

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
        return cls.CHECK.choice(value, "help option control", [control.value for control in MarketControl])

    @field_validator("option", "summary", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw option or summary: a text within its length, its lines joined.

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text, its spaces collapsed.

        Raises:
            InvalidMarketTextError: If it is not a text of the right length.
        """
        name = str(info.field_name)
        return cls.CHECK.text(value, f"help option {name}", cls.TEXTS[name])
