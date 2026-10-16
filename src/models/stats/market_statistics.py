from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import AwareDatetime, BaseModel, Field

# First Party Imports.
from models.stats.market_report import MarketReport


class MarketStatistics(BaseModel):
    """The cloud market figures published by a market research firm, as crawled at a given time.

    Attributes:
        source (str): The market research firm, e.g. `Synergy Research Group`.
        crawled_at (AwareDatetime): When the figures were crawled, timezone-aware.
        reports (List[MarketReport]): The published figures, one report per period, region and segment.
    """

    source: str = Field(min_length=1, description="The market research firm.")
    crawled_at: AwareDatetime = Field(description="When the figures were crawled, timezone-aware.")
    reports: List[MarketReport] = Field(default_factory=list, description="The published figures.")

    @property
    def size(self) -> int:
        """Get the number of reports.

        Returns:
            int: The number of reports, not serialized.
        """
        return len(self.reports)
