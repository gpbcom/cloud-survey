from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import Qt

# First Party Imports.
from gui.charts.base.metric_chart import ChartLine
from gui.charts.common.chart_labels import ChartLabels
from models.cloud.enums import MarketRegion, MarketSegment
from models.trends.chart_axes import ChartAxes
from models.trends.enums import ChartKind
from models.trends.metric_series import MetricSeries


class SeriesStyler:
    """Turn series into chart lines: their label, colour and line style.

    Attributes:
        REGION_TAGS (ClassVar[Dict[MarketRegion, str]]): The short tag of each market region.
        SEGMENT_TAGS (ClassVar[Dict[MarketSegment, str]]): The short tag of each market segment.
        LINE_STYLES (ClassVar[Tuple[Qt.PenStyle, ...]]): The line style of each region and segment, in order.
        labels (ChartLabels): The names and colours of the series.
        logger (Logger): The styler logger.

    Notes:
        - A series keeps its provider, player or bloc colour in every chart.
        - The statistics of several regions or segments are told apart by a tag and a line style.
        - The bubbles are coloured by bloc: the geopolitical reading of a competitive chart.
    """

    REGION_TAGS: ClassVar[Dict[MarketRegion, str]] = {MarketRegion.WORLDWIDE: "WW", MarketRegion.EUROPE: "EU"}
    SEGMENT_TAGS: ClassVar[Dict[MarketSegment, str]] = {
        MarketSegment.CLOUD_INFRASTRUCTURE: "CIS",
        MarketSegment.PUBLIC_IAAS_PAAS: "public",
    }
    LINE_STYLES: ClassVar[Tuple[Qt.PenStyle, ...]] = (
        Qt.PenStyle.SolidLine,
        Qt.PenStyle.DashLine,
        Qt.PenStyle.DotLine,
        Qt.PenStyle.DashDotLine,
    )

    def __init__(self, labels: ChartLabels, logger: Optional[Logger] = None) -> None:
        """Initialize the styler.

        Args:
            labels (ChartLabels): The names and colours of the series.
            logger (Optional[Logger]): The styler logger.
        """
        self.labels = labels
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def lines(self, axes: ChartAxes, series: List[MetricSeries]) -> List[ChartLine]:
        """Style the series of a chart.

        Args:
            axes (ChartAxes): The chart axes.
            series (List[MetricSeries]): The series.

        Returns:
            List[ChartLine]: The series, their label, colour and line style.
        """
        region_order, segment_order = list(MarketRegion), list(MarketSegment)
        groups = sorted(
            {(one.region, one.segment) for one in series},
            key=lambda group: (
                -1 if group[0] is None else region_order.index(group[0]),
                -1 if group[1] is None else segment_order.index(group[1]),
            ),
        )
        several = len(groups) > 1
        several_segments = len({segment for _, segment in groups}) > 1
        currencies = len({one.currency for one in series if one.currency}) > 1
        lines: List[ChartLine] = []
        for one in series:
            label = (
                self.labels.series_label(axes.series_by, one.key)
                if one.key
                else self.labels.metric_label(axes.y, axes.scope)
            )
            if several and one.region is not None:
                label = f"{label} · {self.REGION_TAGS[one.region]}"
                if several_segments and one.segment is not None:
                    label = f"{label} · {self.SEGMENT_TAGS[one.segment]}"
            if currencies and one.currency:
                label = f"{label} ({one.currency})"
            color = self.labels.series_color(axes.series_by, one.key)
            if axes.chart is ChartKind.BUBBLE:
                bloc = self.labels.bloc_of(axes.series_by, one.key)
                color = self.labels.theme.bloc_color(bloc) if bloc is not None else color
            style = self.LINE_STYLES[groups.index((one.region, one.segment)) % len(self.LINE_STYLES)]
            lines.append((one, label, color, style))
        self.logger.debug("%d chart lines styled.", len(lines))
        return lines
