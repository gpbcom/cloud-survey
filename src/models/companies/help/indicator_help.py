from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.enums import CompanyIndicator, IndicatorFamily
from models.markets.field_check import MarketFieldCheck


class IndicatorHelp(BaseModel):
    """What an indicator measures and how it is computed, as the company financials card explains it.

    Attributes:
        TEXTS (ClassVar[Dict[str, int]]): The longest text of each text field.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        indicator (CompanyIndicator): The indicator.
        family (IndicatorFamily): The family it is listed under.
        title (str): Its name in the menu and on the chart.
        formula (str): How it is computed, from the statement lines.
        summary (str): What it tells about the company.
        caveat (Optional[str]): When it misleads or is missing (a loss year, a bank, a currency change).
    """

    TEXTS: ClassVar[Dict[str, int]] = {"title": 60, "formula": 300, "summary": 600, "caveat": 600}
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    indicator: CompanyIndicator = Field(description="The indicator.")
    family: IndicatorFamily = Field(description="The family it is listed under.")
    title: str = Field(min_length=1, max_length=60, description="Its name.")
    formula: str = Field(min_length=1, max_length=300, description="How it is computed.")
    summary: str = Field(min_length=1, max_length=600, description="What it tells.")
    caveat: Optional[str] = Field(default=None, max_length=600, description="When it misleads or is missing.")

    @field_validator("indicator", mode="before")
    def validate_indicator(cls, value: JsonValue) -> JsonValue:
        """Validate the raw indicator: a `CompanyIndicator` value.

        Args:
            value (JsonValue): The raw indicator.

        Returns:
            JsonValue: The indicator.

        Raises:
            InvalidMarketChoiceError: If it is not a known indicator.
        """
        return cls.CHECK.choice(value, "financials help indicator", [item.value for item in CompanyIndicator])

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
        return cls.CHECK.choice(value, "financials help indicator family", [item.value for item in IndicatorFamily])

    @field_validator("title", "formula", "summary", "caveat", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw text: a text within its length, its lines joined (the caveat may be missing).

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text, its spaces collapsed, `None` for a missing caveat.

        Raises:
            InvalidMarketTextError: If it is not a text of the right length.
        """
        name = str(info.field_name)
        return cls.CHECK.text(value, f"financials help {name}", cls.TEXTS[name], optional=name == "caveat")
