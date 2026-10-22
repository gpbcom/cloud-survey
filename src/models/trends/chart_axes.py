from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.trends.enums import (
    ChartKind,
    ChartMetric,
    ChartPreset,
    ChartScope,
    MatrixCell,
    SeriesGrouping,
    ValueTransform,
)


class ChartAxes(BaseModel):
    """What a chart shows: its kind, its axes, its series and how their values are transformed.

    Attributes:
        scope (ChartScope): Where the chart is shown, which sets the data it reads.
        chart (ChartKind): The kind of chart.
        x (ChartMetric): The metric of the x axis (unused by the matrix charts).
        y (ChartMetric): The metric of the y axis (unused by the matrix charts).
        size (Optional[ChartMetric]): The metric sizing the bubbles, `None` outside the bubble charts.
        series_by (SeriesGrouping): What each series stands for, the rows of the matrix charts.
        facet_by (Optional[SeriesGrouping]): One small chart per value of this grouping (e.g. per provider), sharing
            the series, the axes and the transform, `None` for one chart.
        columns (SeriesGrouping): The columns of the matrix charts.
        cell (MatrixCell): What the cells of the matrix charts count.
        transform (ValueTransform): How the values are transformed.
        forecast (bool): Whether the trend of each series is extrapolated.
        log_scale (bool): Whether the bubble chart axes are logarithmic.
        top (Optional[int]): The largest number of series (or matrix rows and columns) shown, the largest first,
            `None` to show every one of them.
        preset (Optional[ChartPreset]): The ready-made chart these axes come from, `None` once customized.

    Notes:
        - The axes are not validated against each other here: `AxisRules` tells which combinations are valid, and
          repairs the others.
        - Axes saved before the software types were replaced by the taxonomy are read with the categories instead
          (`type` groupings) and the domain trends preset instead of the type mix one.
    """

    model_config = ConfigDict(frozen=True)

    RENAMED_GROUPINGS: ClassVar[Dict[str, str]] = {"type": SeriesGrouping.CATEGORY.value}
    RENAMED_PRESETS: ClassVar[Dict[str, str]] = {"type-mix-by-provider": ChartPreset.DOMAIN_TRENDS_BY_PROVIDER.value}

    scope: ChartScope = Field(description="Where the chart is shown.")
    chart: ChartKind = Field(default=ChartKind.LINE, description="The kind of chart.")
    x: ChartMetric = Field(default=ChartMetric.QUARTER, description="The metric of the x axis.")
    y: ChartMetric = Field(default=ChartMetric.LISTED, description="The metric of the y axis.")
    size: Optional[ChartMetric] = Field(default=None, description="The metric sizing the bubbles.")
    series_by: SeriesGrouping = Field(default=SeriesGrouping.PROVIDER, description="What each series stands for.")
    facet_by: Optional[SeriesGrouping] = Field(default=None, description="One small chart per value of this grouping.")
    columns: SeriesGrouping = Field(default=SeriesGrouping.DELIVERY, description="The columns of the matrix charts.")
    cell: MatrixCell = Field(default=MatrixCell.LISTED, description="What the matrix cells count.")
    transform: ValueTransform = Field(default=ValueTransform.RAW, description="How the values are transformed.")
    forecast: bool = Field(default=False, description="Whether the trends are extrapolated.")
    log_scale: bool = Field(default=False, description="Whether the bubble chart axes are logarithmic.")
    top: Optional[int] = Field(default=None, ge=1, le=20, description="The largest number of series, `None` for all.")
    preset: Optional[ChartPreset] = Field(default=None, description="The ready-made chart of the axes.")

    @field_validator("series_by", "facet_by", "columns", mode="before")
    def validate_grouping(cls, value: JsonValue) -> JsonValue:
        """Validate a raw grouping, a former one read as its replacement.

        Args:
            value (JsonValue): The raw grouping.

        Returns:
            JsonValue: The grouping, `category` for the former `type` (its value is checked by pydantic afterwards).
        """
        if isinstance(value, str):
            return cls.RENAMED_GROUPINGS.get(value, value)
        return value

    @field_validator("preset", mode="before")
    def validate_preset(cls, value: JsonValue) -> JsonValue:
        """Validate a raw preset, a former one read as its replacement.

        Args:
            value (JsonValue): The raw preset.

        Returns:
            JsonValue: The preset, the domain trends one for the former type mix (checked by pydantic afterwards).
        """
        if isinstance(value, str):
            return cls.RENAMED_PRESETS.get(value, value)
        return value
