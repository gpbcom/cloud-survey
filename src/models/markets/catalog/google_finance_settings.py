from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.markets.exception import InvalidMarketListError
from models.markets.field_check import MarketFieldCheck


class GoogleFinanceSettings(BaseModel):
    """How the price history of a listing is asked from Google Finance (the chart's own RPC).

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        rpc_id (str): The `batchexecute` RPC the chart calls for its history, `c2u4wc` when measured (2026-10).
        period (int): The window argument of that RPC, `8` being the longest (Max).
        consent_cookies (Dict[str, str]): The Google consent cookies (`CONSENT`, `SOCS`) sent with every request, so
            that Google answers instead of redirecting to its consent wall.

    Notes:
        These values belong to Google and change without notice: they live in the catalogue, not in the code, as in
        mega-trends' `GoogleFinanceConfig`. The cookies only record a consent choice, they identify nobody.
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    rpc_id: str = Field(default="c2u4wc", min_length=1, max_length=20, description="The chart RPC.")
    period: int = Field(default=8, ge=1, le=20, description="The window argument, 8 is Max.")
    consent_cookies: Dict[str, str] = Field(default_factory=dict, description="The Google consent cookies.")

    @field_validator("rpc_id", mode="before")
    def validate_rpc_id(cls, value: JsonValue) -> JsonValue:
        """Validate the raw RPC identifier: a text of 1 to 20 characters.

        Args:
            value (JsonValue): The raw identifier.

        Returns:
            JsonValue: The identifier, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 20 characters.
        """
        return cls.CHECK.text(value, "chart RPC identifier", 20)

    @field_validator("period", mode="before")
    def validate_period(cls, value: JsonValue) -> JsonValue:
        """Validate the raw window argument: a whole number from 1 to 20.

        Args:
            value (JsonValue): The raw argument.

        Returns:
            JsonValue: The argument.

        Raises:
            InvalidMarketNumberError: If it is not a whole number from 1 to 20.
        """
        return cls.CHECK.number(value, "chart RPC window", low=1, high=20, integer=True)

    @field_validator("consent_cookies", mode="before")
    def validate_consent_cookies(cls, value: JsonValue) -> JsonValue:
        """Validate the raw cookies: a mapping of names to texts, the empty ones left out.

        Args:
            value (JsonValue): The raw cookies.

        Returns:
            JsonValue: The cookies, trimmed.

        Raises:
            InvalidMarketListError: If it is not a mapping of names to texts.
        """
        if not isinstance(value, dict) or not all(isinstance(cookie, str) for cookie in value.values()):
            raise InvalidMarketListError("consent cookies", "a mapping of cookie names to texts")
        return {
            name.strip(): cookie.strip()
            for name, cookie in value.items()
            if isinstance(cookie, str) and name.strip() and cookie.strip()
        }
