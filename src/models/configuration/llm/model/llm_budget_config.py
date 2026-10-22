from __future__ import annotations

# Standard Library Imports.
from decimal import Decimal

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class LLMBudgetConfig(BaseModel):
    """What the language model calls may spend in total, recorded in the storage.

    Attributes:
        ceiling (Decimal): The largest total cost of the calls.
        currency (str): The currency of the ceiling and of the rates (ISO 4217).
        enforce (bool): Whether a call is refused once the ceiling is reached (`False`: a warning only).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ceiling: Decimal = Field(default=Decimal(10), ge=0, description="The largest total cost of the calls.")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="The currency (ISO 4217).")
    enforce: bool = Field(default=True, description="Whether a call is refused once the ceiling is reached.")

    @field_validator("currency", mode="before")
    def validate_currency(cls, value: JsonValue) -> JsonValue:
        """Upper-case the currency code.

        Args:
            value (JsonValue): The raw code.

        Returns:
            JsonValue: The trimmed upper-case code.
        """
        return value.strip().upper() if isinstance(value, str) else value
