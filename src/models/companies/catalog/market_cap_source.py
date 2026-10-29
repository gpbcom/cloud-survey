from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class MarketCapSource(BaseModel):
    """Which listing values a company, and how many shares one of its units stands for.

    Attributes:
        SYMBOL (ClassVar[Pattern[str]]): The format of a listing: `EXCHANGE:SYMBOL`.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        listing (str): The listing whose closes are multiplied by the shares, e.g. `NYSE:BABA`.
        shares_per_unit (float): The shares one traded unit stands for: 1 for a share, 8 for an Alibaba ADS (the
            market capitalisation is then the close times the shares divided by 8).
        since (Optional[date]): The first day the ratio holds (a share split changing it), the market capitalisation
            being computed from then only. `None` when it always held.

    Notes:
        By default a company is valued on its primary
        listing at one share per unit. This is only written when the
        primary listing trades depositary receipts standing for several shares.
    """

    SYMBOL: ClassVar[Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9]{0,14}:[A-Z0-9][A-Z0-9.\-]{0,11}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    listing: str = Field(description="The listing valued.")
    shares_per_unit: float = Field(default=1.0, gt=0, description="The shares one traded unit stands for.")
    since: Optional[date] = Field(default=None, description="The first day the ratio holds.")

    @field_validator("listing", mode="before")
    def validate_listing(cls, value: JsonValue) -> JsonValue:
        """Validate the raw listing: `EXCHANGE:SYMBOL`, upper-cased.

        Args:
            value (JsonValue): The raw listing.

        Returns:
            JsonValue: The listing.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompanyValueError: If it is not written `EXCHANGE:SYMBOL`.
        """
        symbol = (cls.CHECK.text(value, "valued listing", 30, minimum=3) or "").upper()
        if not cls.SYMBOL.match(symbol):
            raise InvalidCompanyValueError("valued listing", symbol, "EXCHANGE:SYMBOL")
        return symbol

    @field_validator("shares_per_unit", mode="before")
    def validate_shares_per_unit(cls, value: JsonValue) -> JsonValue:
        """Validate the raw shares per unit: a number above zero, at most 10000.

        Args:
            value (JsonValue): The raw ratio.

        Returns:
            JsonValue: The ratio.

        Raises:
            InvalidMarketNumberError: If it is not a number above zero and at most 10000.
        """
        return cls.CHECK.number(value, "shares per unit", low=0.0, high=10000.0, strict_low=True)

    @field_validator("since", mode="before")
    def validate_since(cls, value: JsonValue) -> JsonValue:
        """Validate the raw first day of the ratio: a date, or none.

        Args:
            value (JsonValue): The raw day.

        Returns:
            JsonValue: The day, `YYYY-MM-DD`, `None` when the ratio always held.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        return cls.CHECK.iso_day(value, "valued listing ratio start", optional=True)
