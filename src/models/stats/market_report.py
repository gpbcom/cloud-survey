from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import Final, FrozenSet, List, Optional, Tuple

# Third Party Imports.
from pydantic import BaseModel, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import MarketPlayer, MarketRegion, MarketSegment
from models.stats.exception import SharesOverflowError
from models.stats.market_share import MarketShare
from models.stats.provider_mention import ProviderMention

LEADERS: Final[FrozenSet[MarketPlayer]] = frozenset({MarketPlayer.AMAZON, MarketPlayer.MICROSOFT, MarketPlayer.GOOGLE})


class MarketReport(BaseModel):
    """The figures published for a cloud market (a period, a region and a segment) by a market research firm.

    Attributes:
        period (str): The period: a quarter (`2026Q2`), a half-year (`2025H1`) or a year (`2024`).
        region (MarketRegion): The market region.
        segment (MarketSegment): The market segment.
        currency (str): The currency of the amounts, `USD` or `EUR`.
        market_size_bn (Optional[float]): The market size over the period, in billions.
        twelve_month_bn (Optional[float]): The market size over the twelve months ending with the period, in billions.
        growth_pct (Optional[float]): The year-on-year growth of the market, in percent.
        shares (List[MarketShare]): The published market shares.
        mentions (List[ProviderMention]): The providers named without a market share.
        methodology_break (bool): Whether the figures are not comparable with the previous periods (reclassification).
        source_url (str): The article publishing the figures.
        title (str): The article title.
        published (date): When the article was published.
    """

    period: str = Field(pattern=r"^\d{4}(Q[1-4]|H[12])?$", description="The quarter, half-year or year.")
    region: MarketRegion = Field(description="The market region.")
    segment: MarketSegment = Field(description="The market segment.")
    currency: str = Field(default="USD", pattern=r"^(USD|EUR)$", description="The currency of the amounts.")
    market_size_bn: Optional[float] = Field(default=None, gt=0, description="The market size, in billions.")
    twelve_month_bn: Optional[float] = Field(default=None, gt=0, description="The twelve-month market size.")
    growth_pct: Optional[float] = Field(default=None, description="The year-on-year growth, in percent.")
    shares: List[MarketShare] = Field(default_factory=list, description="The published market shares.")
    mentions: List[ProviderMention] = Field(default_factory=list, description="The providers named without share.")
    methodology_break: bool = Field(default=False, description="Whether the figures are not comparable.")
    source_url: str = Field(pattern=r"^https?://", description="The article publishing the figures.")
    title: str = Field(min_length=1, description="The article title.")
    published: date = Field(description="When the article was published.")

    @field_validator("shares", mode="before")
    def validate_shares(cls, value: JsonValue) -> JsonValue:
        """Validate that the top-level shares (not part of an aggregate) sum to 100% at most.

        Args:
            value (JsonValue): The raw shares.

        Returns:
            JsonValue: The unchanged shares (their content is checked by pydantic afterwards).

        Raises:
            SharesOverflowError: If the top-level shares sum to more than 100%.
        """
        if not isinstance(value, list):
            return value
        total = 0.0
        for share in value:
            raw = share.model_dump() if isinstance(share, MarketShare) else share
            pct = raw.get("share_pct") if isinstance(raw, dict) else None
            if isinstance(raw, dict) and raw.get("part_of") is None and isinstance(pct, (int, float)):
                total += float(pct)
        if total > 100:
            raise SharesOverflowError(total)
        return value

    def others(self) -> Optional[MarketShare]:
        """Compute the share of every other player: 100% minus the top-level shares.

        It is only meaningful when the market leaders are quantified, together (the big three) or each of them:
        otherwise the rest would include a leader.

        Returns:
            Optional[MarketShare]: The computed others share, `None` when the report does not quantify the leaders.
        """
        players = {share.player for share in self.shares}
        if MarketPlayer.BIG_THREE not in players and not LEADERS.issubset(players):
            return None
        top = [share for share in self.shares if share.part_of is None]
        rest = max(0.0, 100.0 - sum(share.share_pct for share in top))
        approximate = any(share.approximate or share.share_low_pct is not None for share in top)
        return MarketShare(player=MarketPlayer.OTHERS, share_pct=rest, approximate=approximate, computed=True)

    def share_of(self, player: MarketPlayer) -> Optional[MarketShare]:
        """Get the share of a player, the computed one for the others.

        Args:
            player (MarketPlayer): The player.

        Returns:
            Optional[MarketShare]: Its share, `None` when the report does not publish it.
        """
        if player is MarketPlayer.OTHERS:
            return self.others()
        return next((share for share in self.shares if share.player is player), None)

    def sort_key(self) -> Tuple[int, int]:
        """Get the chronological sort key of the period: its year, then the last month it covers.

        Returns:
            Tuple[int, int]: The year and the last month of the period, e.g. `(2026, 6)` for `2026Q2`.
        """
        match = re.fullmatch(r"(\d{4})(?:([QH])([1-4]))?", self.period)
        if match is None or match.group(2) is None:
            return int(self.period[:4]), 12
        months = 3 if match.group(2) == "Q" else 6
        return int(match.group(1)), int(match.group(3)) * months
