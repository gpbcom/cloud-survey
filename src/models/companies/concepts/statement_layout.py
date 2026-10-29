from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.concepts.statement_slot import StatementSlot
from models.companies.exception import DuplicateCompanyKeyError
from models.markets.field_check import MarketFieldCheck


class StatementLayout(BaseModel):
    """Where Google Finance's quote page puts the figures of its statements and of its quote row.

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        width (int): The fewest values of a period's list (106 measured on 2026-10-24).
        currency_slot (int): The position of the reporting currency in a period's list.
        period_end_slot (int): The position of the last day of the period (`[year, month, day]`).
        quote_market_cap_slot (int): The position of the market capitalisation in the quote row.
        quote_currency_slot (int): The position of the trading currency in the quote row.
        slots (List[StatementSlot]): The statement lines read, each at its position.

    Notes:
        The positions were pinned on 2026-10-24 against the SEC filings of Nvidia (quarter ending 27 July 2025,
        fiscal year ending 26 January 2025) and Microsoft (fiscal year ending 30 June 2025): every pinned value
        equals the filed one. The other positions (estimates, ratios Google computes itself) are not read.
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    width: int = Field(default=106, ge=20, le=1000, description="The fewest values of a period's list.")
    currency_slot: int = Field(default=16, ge=0, le=1000, description="The position of the reporting currency.")
    period_end_slot: int = Field(default=17, ge=0, le=1000, description="The position of the last day.")
    quote_market_cap_slot: int = Field(default=16, ge=0, le=1000, description="The position of the market cap.")
    quote_currency_slot: int = Field(default=12, ge=0, le=1000, description="The position of the trading currency.")
    slots: List[StatementSlot] = Field(default_factory=list, description="The statement lines read.")

    @field_validator(
        "width", "currency_slot", "period_end_slot", "quote_market_cap_slot", "quote_currency_slot", mode="before"
    )
    def validate_position(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw position or width: a whole number from 0 to 1000.

        Args:
            value (JsonValue): The raw number.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The number.

        Raises:
            InvalidMarketNumberError: If it is not a whole number from 0 to 1000.
        """
        return cls.CHECK.number(value, f"statement layout {info.field_name}", low=0, high=1000, integer=True)

    @field_validator("slots", mode="before")
    def validate_slots(cls, value: JsonValue) -> JsonValue:
        """Validate the raw slots: a list, each statement line once.

        Args:
            value (JsonValue): The raw slots.

        Returns:
            JsonValue: The slots (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
            DuplicateCompanyKeyError: If a statement line is read twice.
        """
        items = cls.CHECK.items(value, "statement slots", "mappings of metric and slot")
        seen: List[str] = []
        for item in items:
            metric = item.get("metric") if isinstance(item, dict) else None
            if isinstance(metric, str):
                if metric in seen:
                    raise DuplicateCompanyKeyError("statement slot", metric)
                seen.append(metric)
        return items
