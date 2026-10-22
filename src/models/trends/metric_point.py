from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, Field


class MetricPoint(BaseModel):
    """A point of a chart series.

    Attributes:
        x (float): The x value: a measured value, or a month ordinal (`year * 12 + month - 1`, plus the elapsed
            fraction of the month for a date) for a time axis.
        y (float): The y value.
        size (Optional[float]): The bubble size value, `None` outside the bubble charts.
        label (Optional[str]): The name of the point, e.g. the period `2025H1`, `None` to name it from its x value.
        projected (bool): Whether the point is a forecast rather than an observation.
    """

    x: float = Field(description="The x value, a month ordinal for a time axis.")
    y: float = Field(description="The y value.")
    size: Optional[float] = Field(default=None, description="The bubble size value.")
    label: Optional[str] = Field(default=None, max_length=40, description="The name of the point.")
    projected: bool = Field(default=False, description="Whether the point is a forecast.")
