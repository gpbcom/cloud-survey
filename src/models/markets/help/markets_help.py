from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.enums import MarketControl
from models.markets.exception import InvalidMarketListError
from models.markets.field_check import MarketFieldCheck
from models.markets.help.control_help import ControlHelp
from models.markets.help.option_help import OptionHelp


class MarketsHelp(BaseModel):
    """The tooltips of the markets cards: each control, each choice of a list, and the correlation method.

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        controls (List[ControlHelp]): The explanation of each control.
        options (List[OptionHelp]): The explanation of each choice of a list.
        method (str): The template of the correlation method, filled with the figures of a correlation (`{lags}`,
            `{block}`, `{resamples}`, `{granger}`, `{points}`, `{gap}`, `{unit}`).
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    controls: List[ControlHelp] = Field(default_factory=list, description="The explanation of each control.")
    options: List[OptionHelp] = Field(default_factory=list, description="The explanation of each choice.")
    method: str = Field(default="", max_length=1200, description="The template of the correlation method.")

    @field_validator("controls", "options", mode="before")
    def validate_entries(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate the raw controls or options: a list of mappings (or of explanations).

        Args:
            value (JsonValue): The raw entries.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The entries (checked by pydantic afterwards).

        Raises:
            InvalidMarketListError: If it is not a list of mappings.
        """
        entries = cls.CHECK.items(value, f"help {info.field_name}", "explanations")
        if not all(isinstance(entry, (dict, ControlHelp, OptionHelp)) for entry in entries):
            raise InvalidMarketListError(f"help {info.field_name}", "a list of mappings")
        return entries

    @field_validator("method", mode="before")
    def validate_method(cls, value: JsonValue) -> JsonValue:
        """Validate the raw method template: a text of at most 1200 characters, its lines joined.

        Args:
            value (JsonValue): The raw template.

        Returns:
            JsonValue: The template, empty when missing.

        Raises:
            InvalidMarketTextError: If it is not a text of the right length.
        """
        return cls.CHECK.text(value, "help method", 1200, optional=True) or ""

    ############################
    # Publicly Exposed Methods #
    ############################

    def control(self, control: MarketControl) -> Optional[ControlHelp]:
        """Get the explanation of a control.

        Args:
            control (MarketControl): The control.

        Returns:
            Optional[ControlHelp]: Its explanation, `None` when there is none.
        """
        return next((entry for entry in self.controls if entry.control is control), None)

    def option(self, control: MarketControl, option: str) -> Optional[OptionHelp]:
        """Get the explanation of a choice of a control.

        Args:
            control (MarketControl): The control.
            option (str): The value of the choice.

        Returns:
            Optional[OptionHelp]: Its explanation, `None` when there is none.
        """
        return next((entry for entry in self.options if entry.control is control and entry.option == option), None)
