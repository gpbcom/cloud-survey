from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, Field

# First Party Imports.
from models.cloud.enums import MarketRegion, MarketSegment
from models.trends.metric_point import MetricPoint


class MetricSeries(BaseModel):
    """A series of a chart: the points of a provider, a player, a bloc, a delivery method or a software type.

    Attributes:
        key (str): The value of the grouping enum the series stands for (e.g. `amazon-web-services` or `eu`), `*` for
            the series merged together, empty for a series of the whole market.
        facet (Optional[str]): The value of the facet grouping of the chart (`ChartAxes.facet_by`) the series belongs
            to, e.g. a provider: one small chart per facet. `None` without facets.
        region (Optional[MarketRegion]): The market region of a market statistics series.
        segment (Optional[MarketSegment]): The market segment of a market statistics series.
        currency (Optional[str]): The currency of the amounts, `USD` or `EUR`, `None` without amounts.
        points (List[MetricPoint]): The points, in increasing x order.
        trend_pct (Optional[float]): The annual growth of the forecast trend, in percent, `None` without forecast.
    """

    key: str = Field(max_length=100, description="The value of the grouping enum the series stands for.")
    facet: Optional[str] = Field(
        default=None, max_length=100, description="The value of the facet grouping (the small chart of the series)."
    )
    region: Optional[MarketRegion] = Field(default=None, description="The market region of a statistics series.")
    segment: Optional[MarketSegment] = Field(default=None, description="The market segment of a statistics series.")
    currency: Optional[str] = Field(default=None, pattern=r"^(USD|EUR)$", description="The currency of the amounts.")
    points: List[MetricPoint] = Field(default_factory=list, description="The points, in increasing x order.")
    trend_pct: Optional[float] = Field(default=None, description="The annual growth of the forecast trend, in percent.")
