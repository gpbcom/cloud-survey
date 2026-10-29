from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional

# First Party Imports.
from gui.charts.common.axis.axis_formatter import AxisFormatter
from gui.charts.common.chart_labels import ChartLabels
from models.trends.chart_axes import ChartAxes
from models.trends.enums import ChartKind, ChartMetric, ChartNote, ChartScope, MetricKind, ValueTransform
from models.trends.matrix.metric_matrix import MetricMatrix
from models.trends.trend_result import TrendResult


class ChartTitles:
    """Write the title, subtitle and footnote of a chart from what it shows.

    Attributes:
        GRAINS (ClassVar[Dict[ChartMetric, str]]): How each time axis counts time, in the subtitle.
        labels (ChartLabels): The names of the options.
        formatter (AxisFormatter): The value formatter, naming the moments.
        logger (Logger): The titles logger.
    """

    GRAINS: ClassVar[Dict[ChartMetric, str]] = {
        ChartMetric.PERIOD: "Per report period",
        ChartMetric.PUBLISHED: "By publication date",
        ChartMetric.YEAR: "Yearly",
        ChartMetric.QUARTER: "Quarterly",
        ChartMetric.MONTH: "Monthly",
        ChartMetric.CRAWL_DATE: "Per crawl",
    }

    def __init__(self, labels: ChartLabels, logger: Optional[Logger] = None) -> None:
        """Initialize the titles.

        Args:
            labels (ChartLabels): The names of the options.
            logger (Optional[Logger]): The titles logger.
        """
        self.labels = labels
        self.logger = logger if logger else getLogger(__name__)
        self.formatter = AxisFormatter(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _by(self, axes: ChartAxes) -> str:
        """Name the series grouping of a title.

        Args:
            axes (ChartAxes): The chart axes.

        Returns:
            str: e.g. ` by provider`, empty for a metric of the whole market.
        """
        market = axes.scope is ChartScope.STATISTICS and not axes.y.player_scoped
        return "" if market else f" by {self.labels.GROUPING_PLURALS[axes.series_by]}"

    ############################
    # Publicly Exposed Methods #
    ############################

    def title(self, axes: ChartAxes) -> str:
        """Title a chart.

        Args:
            axes (ChartAxes): The chart axes.

        Returns:
            str: e.g. `Listed products by provider`, `Market share vs marketplace size` or `Delivery mix by bloc`.
        """
        if axes.preset is not None:
            self.logger.debug("Chart titled after the ready-made chart %s.", axes.preset.value)
            return self.labels.PRESET_LABELS[axes.preset]
        self.logger.debug("Titling a %s chart of %s.", axes.chart.value, axes.y.value)
        y = self.labels.metric_label(axes.y, axes.scope)
        x = self.labels.metric_label(axes.x, axes.scope).lower()
        match axes.chart:
            case ChartKind.HEATMAP:
                rows, columns = (self.labels.GROUPING_PLURALS[grouping] for grouping in (axes.series_by, axes.columns))
                return f"{self.labels.CELL_LABELS[axes.cell]}: {rows} × {columns}"
            case ChartKind.MIX:
                columns = self.labels.GROUPING_LABELS[axes.columns]
                return f"{columns} mix by {self.labels.GROUPING_PLURALS[axes.series_by]}"
            case ChartKind.BUBBLE:
                size = f", sized by {self.labels.metric_label(axes.size, axes.scope).lower()}" if axes.size else ""
                return f"{y} vs {x}{size}"
            case _ if axes.x.kind is not MetricKind.TIME:
                return f"{y} vs {x}{self._by(axes)}"
            case _ if axes.facet_by is not None:
                return f"{y}{self._by(axes)}, per {self.labels.GROUPING_LABELS[axes.facet_by].lower()}"
            case _:
                return f"{y}{self._by(axes)}"

    def subtitle(
        self, axes: ChartAxes, result: Optional[TrendResult] = None, matrix: Optional[MetricMatrix] = None
    ) -> str:
        """Say exactly what a chart shows: its grain, transform, forecast, date and selection.

        Args:
            axes (ChartAxes): The chart axes.
            result (Optional[TrendResult]): The drawn series, `None` before they are read.
            matrix (Optional[MetricMatrix]): The drawn matrix, `None` before it is read.

        Returns:
            str: e.g. `Quarterly · share of total · forecast to 2027Q4 · top 8 of 23`.
        """
        self.logger.debug(
            "Subtitling a %s chart, series read %s, matrix read %s.",
            axes.chart.value,
            result is not None,
            matrix is not None,
        )
        parts: List[str] = []
        if axes.chart.is_matrix:
            parts.append("Listed software")
            if matrix is not None and (
                matrix.total_rows > len(matrix.rows) or matrix.total_columns > len(matrix.columns)
            ):
                parts.append(f"largest {len(matrix.rows)} of {matrix.total_rows} rows")
            return " · ".join(parts)
        if axes.x.kind is MetricKind.TIME and axes.chart is not ChartKind.BUBBLE:
            parts.append(self.GRAINS[axes.x])
        else:
            parts.append(f"x: {self.labels.metric_label(axes.x, axes.scope).lower()}")
            if axes.chart is ChartKind.BUBBLE and axes.size is not None:
                parts.append(f"size: {self.labels.metric_label(axes.size, axes.scope).lower()}")
                parts.append("colour: bloc")
        if axes.transform is not ValueTransform.RAW:
            parts.append(self.labels.TRANSFORM_LABELS[axes.transform].lower())
        if result is not None:
            projected = [point.x for one in result.series for point in one.points if point.projected]
            if projected:
                parts.append(f"forecast to {self.formatter.x_label(axes.x, max(projected))}")
            if result.as_of is not None:
                parts.append(f"as of {self.formatter.x_label(ChartMetric.QUARTER, result.as_of)}")
            shown = len({one.key for one in result.series if one.key and one.key != "*"})
            if result.total_count > shown:
                parts.append(f"top {shown} of {result.total_count}")
            if axes.facet_by is not None:
                facets = len({one.facet for one in result.series if one.facet})
                parts.append(f"{facets} charts per {self.labels.GROUPING_LABELS[axes.facet_by].lower()}")
        return " · ".join(parts)

    def footnote(self, notes: List[ChartNote]) -> str:
        """Write the caveats of a chart.

        Args:
            notes (List[ChartNote]): The caveats.

        Returns:
            str: One sentence per caveat, separated by middle dots, empty without caveat.
        """
        return " · ".join(self.labels.NOTE_LABELS[note] for note in notes)
