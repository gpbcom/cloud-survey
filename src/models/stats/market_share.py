from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.cloud.enums import MarketPlayer
from models.stats.exception import InvalidShareBandError


class MarketShare(BaseModel):
    """The market share of a player (a provider or an aggregate) in a market report.

    Attributes:
        player (MarketPlayer): The provider or the aggregate.
        share_pct (float): The market share, in percent: the middle of the band when a band is published.
        share_low_pct (Optional[float]): The low bound of the published band, e.g. 32 for "32-34%".
        share_high_pct (Optional[float]): The high bound of the published band, e.g. 34 for "32-34%".
        approximate (bool): Whether the share is published as an approximation, e.g. "around 15%".
        computed (bool): Whether the share is computed rather than published (the others).
        part_of (Optional[MarketPlayer]): The aggregate including the player, e.g. the big three for Amazon. `None`
            for a top-level share.
    """

    player: MarketPlayer = Field(description="The provider or the aggregate.")
    share_pct: float = Field(ge=0, le=100, description="The market share, in percent.")
    share_low_pct: Optional[float] = Field(default=None, ge=0, le=100, description="The low bound of the band.")
    share_high_pct: Optional[float] = Field(default=None, ge=0, le=100, description="The high bound of the band.")
    approximate: bool = Field(default=False, description="Whether the share is published as an approximation.")
    computed: bool = Field(default=False, description="Whether the share is computed rather than published.")
    part_of: Optional[MarketPlayer] = Field(default=None, description="The aggregate including the player.")

    @field_validator("share_high_pct", mode="before")
    def validate_band(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate that the high bound of the band is not below its low bound.

        Args:
            value (JsonValue): The raw high bound.
            info (ValidationInfo): The fields validated so far.

        Returns:
            JsonValue: The unchanged high bound (its type is checked by pydantic afterwards).

        Raises:
            InvalidShareBandError: If the high bound is below the low bound.
        """
        low = info.data.get("share_low_pct")
        if isinstance(value, (int, float)) and isinstance(low, (int, float)) and value < low:
            raise InvalidShareBandError(low, value)
        return value
