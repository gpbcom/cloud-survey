from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.enums import CompanyIndicator, FinancialControl, IndicatorFamily
from models.companies.exception import DuplicateCompanyKeyError, InvalidCompanyValueError
from models.companies.help.financial_control_help import FinancialControlHelp
from models.companies.help.indicator_family_help import IndicatorFamilyHelp
from models.companies.help.indicator_help import IndicatorHelp
from models.markets.field_check import MarketFieldCheck


class FinancialsHelp(BaseModel):
    """The tooltips and the menu of the company financials card (the `financials` block of `conf/help.yaml`).

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        controls (List[FinancialControlHelp]): What each control does, each control once.
        families (List[IndicatorFamilyHelp]): The families, in the order of the menu, each once.
        indicators (List[IndicatorHelp]): Every indicator, once, in the order of the menu within its family.

    Notes:
        Every indicator is explained, so the menu lists them all: a new indicator without help fails the loading.
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    controls: List[FinancialControlHelp] = Field(default_factory=list, description="What each control does.")
    families: List[IndicatorFamilyHelp] = Field(default_factory=list, description="The families of the menu.")
    indicators: List[IndicatorHelp] = Field(default_factory=list, description="Every indicator.")

    @field_validator("controls", "families", mode="before")
    def validate_entries(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate raw controls or families: a list, each key once.

        Args:
            value (JsonValue): The raw entries.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The entries (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
            DuplicateCompanyKeyError: If a control or a family is explained twice.
        """
        key = "control" if info.field_name == "controls" else "family"
        items = cls.CHECK.items(value, f"financials help {info.field_name}", f"mappings of {key}, title, summary")
        seen: List[str] = []
        for item in items:
            name = item.get(key) if isinstance(item, dict) else None
            if isinstance(name, str):
                if name in seen:
                    raise DuplicateCompanyKeyError(f"financials help {key}", name)
                seen.append(name)
        return items

    @field_validator("indicators", mode="before")
    def validate_indicators(cls, value: JsonValue) -> JsonValue:
        """Validate the raw indicators: a list explaining every indicator exactly once.

        Args:
            value (JsonValue): The raw indicators.

        Returns:
            JsonValue: The indicators (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
            DuplicateCompanyKeyError: If an indicator is explained twice.
            InvalidCompanyValueError: If an indicator is not explained.
        """
        items = cls.CHECK.items(value, "financials help indicators", "mappings of indicator, family, title, formula")
        seen: List[str] = []
        for item in items:
            name = item.get("indicator") if isinstance(item, dict) else None
            if isinstance(name, str):
                if name in seen:
                    raise DuplicateCompanyKeyError("financials help indicator", name)
                seen.append(name)
        missing = [indicator.value for indicator in CompanyIndicator if indicator.value not in seen]
        if missing:
            raise InvalidCompanyValueError("financials help indicators", ", ".join(missing), "every indicator once")
        return items

    ############################
    # Publicly Exposed Methods #
    ############################

    def control(self, control: FinancialControl) -> Optional[FinancialControlHelp]:
        """Get the help of a control.

        Args:
            control (FinancialControl): The control.

        Returns:
            Optional[FinancialControlHelp]: Its help, `None` when it has none.
        """
        return next((item for item in self.controls if item.control is control), None)

    def indicator(self, indicator: CompanyIndicator) -> Optional[IndicatorHelp]:
        """Get the help of an indicator.

        Args:
            indicator (CompanyIndicator): The indicator.

        Returns:
            Optional[IndicatorHelp]: Its help, `None` when it has none.
        """
        return next((item for item in self.indicators if item.indicator is indicator), None)

    def family_of(self, family: IndicatorFamily) -> List[IndicatorHelp]:
        """Get the indicators of a family, in the order of the menu.

        Args:
            family (IndicatorFamily): The family.

        Returns:
            List[IndicatorHelp]: Its indicators.
        """
        return [item for item in self.indicators if item.family is family]
