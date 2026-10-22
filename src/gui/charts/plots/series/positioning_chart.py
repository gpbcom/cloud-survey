from __future__ import annotations

# Standard Library Imports.
import math
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen

# First Party Imports.
from gui.charts.base.chart_legend import LegendEntry
from gui.charts.base.metric_chart import ChartLine, MetricChart
from gui.charts.base.plot_frame import PlotFrame
from models.trends.metric_point import MetricPoint

Bubble = Tuple[ChartLine, MetricPoint, QPointF, float]


class PositioningChart(MetricChart):
    """Competitive positioning: one bubble per provider, placed by two metrics, sized by a third, coloured by bloc.

    Attributes:
        MIN_RADIUS (ClassVar[float]): The radius of the smallest bubble, in pixels.
        MAX_RADIUS (ClassVar[float]): The radius of the largest bubble, in pixels.
        SAME_RADIUS (ClassVar[float]): The radius of every bubble without a size metric, in pixels.

    Notes:
        - The bubble area is proportional to its size value.
        - The legend lists the blocs: hiding a bloc hides its bubbles.
        - The bubble labels which would overlap a previous one are left to the tooltips.
    """

    MIN_RADIUS: ClassVar[float] = 6.0
    MAX_RADIUS: ClassVar[float] = 30.0
    SAME_RADIUS: ClassVar[float] = 9.0

    ############################
    # Internal Helpers Methods #
    ############################

    def _legend_key(self, line: ChartLine) -> str:
        """Get the legend entry of a bubble: its bloc.

        Args:
            line (ChartLine): The bubble series.

        Returns:
            str: The bloc name, the series label when it has no bloc.
        """
        if self.axes is None:
            return line[1]
        bloc = self.labels.bloc_of(self.axes.series_by, line[0].key)
        return self.theme.bloc_label(bloc) if bloc is not None else line[1]

    def _legend_entries(self) -> List[LegendEntry]:
        """Get the legend entries: one per bloc.

        Returns:
            List[LegendEntry]: The bloc name and colour of each bloc shown.
        """
        entries: Dict[str, LegendEntry] = {}
        for line in self.lines:
            entries.setdefault(self._legend_key(line), (self._legend_key(line), line[2], Qt.PenStyle.SolidLine))
        return list(entries.values())

    def _legend_suffixes(self) -> Dict[str, str]:
        """Get the text after the legend labels: none for the blocs.

        Returns:
            Dict[str, str]: No suffix.
        """
        return {}

    def _frame(self, plot: QRectF) -> Tuple[PlotFrame, List[float], List[float]]:
        """Fit the bubbles in the plot, with room for their radius.

        Args:
            plot (QRectF): The plot area.

        Returns:
            Tuple[PlotFrame, List[float], List[float]]: The frame and the x and y grid values.
        """
        points = [series.points[0] for series, _, _, _ in self._visible() if series.points] or [
            series.points[0] for series, _, _, _ in self.lines if series.points
        ]
        xs, ys = [point.x for point in points], [point.y for point in points]
        log = self.axes is not None and self.axes.log_scale and min(xs) > 0 and min(ys) > 0
        inner = plot.adjusted(self.MAX_RADIUS, self.MAX_RADIUS, -self.MAX_RADIUS, -self.MAX_RADIUS)
        if log:
            x_low, x_high, x_ticks = self.scale.log(min(xs), max(xs))
            y_low, y_high, y_ticks = self.scale.log(min(ys), max(ys))
        else:
            x_low, x_high, x_step = self.scale.linear(min(xs), max(xs))
            y_low, y_high, y_step = self.scale.linear(min(ys), max(ys))
            x_ticks, y_ticks = self.scale.ticks(x_low, x_high, x_step), self.scale.ticks(y_low, y_high, y_step)
        shown_x, shown_y = self.zoom.x_range(x_low, x_high, log), self.zoom.y_range(y_low, y_high, log)
        frame = PlotFrame(inner, shown_x, shown_y, log_x=log, log_y=log)
        self.zoom.wheel_y = True
        self.zoom.set_frame(frame, (x_low, x_high), (y_low, y_high))
        if self.zoom.is_zoomed():
            x_ticks = [value for value in x_ticks if shown_x[0] <= value <= shown_x[1]]
            y_ticks = [value for value in y_ticks if shown_y[0] <= value <= shown_y[1]]
        return frame, x_ticks, y_ticks

    def _bubbles(self, frame: PlotFrame) -> List[Bubble]:
        """Place and size the visible bubbles, the largest first (painted below the smaller ones).

        Args:
            frame (PlotFrame): The plot frame.

        Returns:
            List[Bubble]: The series, point, centre and radius of each bubble.
        """
        visible = [(line, line[0].points[0]) for line in self._visible() if line[0].points]
        largest = max((point.size or 0.0 for _, point in visible), default=0.0)
        bubbles: List[Bubble] = []
        for line, point in visible:
            if point.size is None or largest <= 0:
                radius = self.SAME_RADIUS
            else:
                radius = self.MIN_RADIUS + (self.MAX_RADIUS - self.MIN_RADIUS) * math.sqrt(
                    max(point.size, 0.0) / largest
                )
            bubbles.append((line, point, frame.map(point.x, point.y), radius))
        return sorted(bubbles, key=lambda bubble: -bubble[3])

    def _paint_plot(self, painter: QPainter, plot: QRectF) -> None:
        """Paint the grid, the axes and the labelled bubbles.

        Args:
            painter (QPainter): The painter.
            plot (QRectF): The plot area.
        """
        if self.axes is None:
            return
        frame, x_ticks, y_ticks = self._frame(plot)
        x_unit, y_unit = self.axes.x.unit, self.axes.y.unit
        y_step = y_ticks[1] - y_ticks[0] if len(y_ticks) > 1 and not frame.log_y else None
        self._paint_y_grid(painter, frame, y_ticks, y_unit, y_step)
        x_step = x_ticks[1] - x_ticks[0] if len(x_ticks) > 1 and not frame.log_x else None
        values = [(value, self.formatter.value(x_unit, value, self._currency(), x_step)) for value in x_ticks]
        self._paint_x_values(painter, frame, values, grid=True)
        self._paint_titles(
            painter,
            plot,
            self.labels.axis_title(self.axes.x, self.axes.scope),
            self.labels.axis_title(self.axes.y, self.axes.scope),
        )
        labelled: List[QRectF] = []
        metrics = painter.fontMetrics()
        painter.save()
        if self.zoom.is_zoomed():
            painter.setClipRect(plot)
        for (series, label, color, _), _point, center, radius in self._bubbles(frame):
            key = self._legend_key((series, label, color, Qt.PenStyle.SolidLine))
            painter.setPen(QPen(self._faded(color.lighter(120), key), 1.5))
            painter.setBrush(self._faded(color, key, 150))
            painter.drawEllipse(center, radius, radius)
            box = QRectF(center.x() + radius + 4, center.y() - 8, metrics.horizontalAdvance(label) + 4, 16)
            if not any(box.intersects(other) for other in labelled):
                painter.setPen(self._faded(QColor(self.theme.TEXT), key))
                painter.drawText(box, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
                labelled.append(box)
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _tooltip(self, position: QPointF) -> Optional[str]:
        """Describe the bubble under the mouse: its provider, bucket and three values.

        Args:
            position (QPointF): The mouse position.

        Returns:
            Optional[str]: The tooltip, `None` away from the bubbles.
        """
        if self.axes is None or self.plot_area.isEmpty() or not self._has_data():
            return None
        frame = self._frame(self.plot_area)[0]
        under = [
            bubble
            for bubble in self._bubbles(frame)
            if math.hypot(bubble[2].x() - position.x(), bubble[2].y() - position.y()) <= bubble[3] + 2
        ]
        if not under:
            return None
        (series, label, _, _), point, _, _ = min(under, key=lambda bubble: bubble[3])
        axes, currency = self.axes, series.currency
        rows = [
            f"{label} ({point.label})" if point.label else label,
            f"{self.labels.metric_label(axes.x, axes.scope)}: {self.formatter.value(axes.x.unit, point.x, currency)}",
            f"{self.labels.metric_label(axes.y, axes.scope)}: {self.formatter.value(axes.y.unit, point.y, currency)}",
        ]
        if axes.size is not None and point.size is not None:
            size = self.formatter.value(axes.size.unit, point.size, currency)
            rows.append(f"{self.labels.metric_label(axes.size, axes.scope)}: {size}")
        return "\n".join(rows)
