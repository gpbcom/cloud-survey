from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.enums import IndicatorFamily
from models.markets.field_check import MarketFieldCheck


class IndicatorFamilyHelp(BaseModel):
    """A family of indicators as the company financials card groups them (`financials` block of `conf/help.yaml`).

    Attributes:
        TEXTS (ClassVar[Dict[str, int]]): The longest text of each text field.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        family (IndicatorFamily): The family.
        title (str): Its name, the heading of its indicators in the menu.
        summary (str): What its indicators tell about the company.
    """

    TEXTS: ClassVar[Dict[str, int]] = {"title": 60, "summary": 600}
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    family: IndicatorFamily = Field(description="The family.")
    title: str = Field(min_length=1, max_length=60, description="Its name.")
    summary: str = Field(min_length=1, max_length=600, description="What its indicators tell.")

    @field_validator("family", mode="before")
    def validate_family(cls, value: JsonValue) -> JsonValue:
        """Validate the raw family: an `IndicatorFamily` value.

        Args:
            value (JsonValue): The raw family.

        Returns:
            JsonValue: The family.

        Raises:
            InvalidMarketChoiceError: If it is not a known family.
        """
        return cls.CHECK.choice(value, "financials help family", [family.value for family in IndicatorFamily])

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
        return cls.CHECK.text(value, f"financials family {name}", cls.TEXTS[name])
