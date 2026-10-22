from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, Field

# First Party Imports.
from models.trends.enums import ChartNote
from models.trends.metric_series import MetricSeries


class TrendResult(BaseModel):
    """The series of a chart, ready to be drawn, with what the chart must say about them.

    Attributes:
        series (List[MetricSeries]): The shown series, the largest first.
        breaks (List[float]): The x values where the figures stop being comparable (methodology changes).
        notes (List[ChartNote]): The caveats of the figures, for the footnote.
        total_count (int): The number of series before the largest ones were kept.
        last_actual (Optional[float]): The x value of the latest observation, `None` without observation.
        as_of (Optional[float]): The month ordinal the bubbles are positioned at, `None` outside the bubble charts.
    """

    series: List[MetricSeries] = Field(default_factory=list, description="The shown series.")
    breaks: List[float] = Field(default_factory=list, description="The x values of the methodology changes.")
    notes: List[ChartNote] = Field(default_factory=list, description="The caveats of the figures.")
    total_count: int = Field(default=0, ge=0, description="The number of series before the largest were kept.")
    last_actual: Optional[float] = Field(default=None, description="The x value of the latest observation.")
    as_of: Optional[float] = Field(default=None, description="The month ordinal of the bubbles.")
