from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.enums import FinancialControl
from models.markets.field_check import MarketFieldCheck


class FinancialControlHelp(BaseModel):
    """What a control of the company financials card does, as its tooltip explains it (`conf/help.yaml`).

    Attributes:
        TEXTS (ClassVar[Dict[str, int]]): The longest text of each text field.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        control (FinancialControl): The control.
        title (str): Its name, the first line of the tooltip.
        summary (str): What it changes.
    """

    TEXTS: ClassVar[Dict[str, int]] = {"title": 60, "summary": 900}
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    control: FinancialControl = Field(description="The control.")
    title: str = Field(min_length=1, max_length=60, description="Its name.")
    summary: str = Field(min_length=1, max_length=900, description="What it changes.")

    @field_validator("control", mode="before")
    def validate_control(cls, value: JsonValue) -> JsonValue:
        """Validate the raw control: a `FinancialControl` value.

        Args:
            value (JsonValue): The raw control.

        Returns:
            JsonValue: The control.

        Raises:
            InvalidMarketChoiceError: If it is not a known control.
        """
        return cls.CHECK.choice(value, "financials help control", [control.value for control in FinancialControl])

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
        return cls.CHECK.text(value, f"financials help {name}", cls.TEXTS[name])
