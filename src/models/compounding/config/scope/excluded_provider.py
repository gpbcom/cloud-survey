from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.markets.field_check import MarketFieldCheck


class ExcludedProvider(BaseModel):
    """A provider with dated launches left out of the main fits.

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        provider (CloudProvider): The catalogue provider.
        reason (str): Why it is outside the public-cloud scope.

    Notes:
        An excluded provider is still fitted on its own and shown flagged, as a robustness check.
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: CloudProvider = Field(description="The catalogue provider.")
    reason: str = Field(description="Why it is left out.")

    @field_validator("reason", mode="before")
    def validate_reason(cls, value: JsonValue) -> JsonValue:
        """Validate the raw reason: a text of 10 to 300 characters.

        Args:
            value (JsonValue): The raw reason.

        Returns:
            JsonValue: The reason.

        Raises:
            InvalidMarketTextError: If it is not a text of that length.
        """
        return cls.CHECK.text(value, "exclusion reason", 300, minimum=10)
