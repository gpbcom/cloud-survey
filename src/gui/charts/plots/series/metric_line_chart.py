from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen

# First Party Imports.
from gui.charts.base.metric_chart import ChartLine, MetricChart
from gui.charts.base.plot_frame import PlotFrame
from models.trends.enums import MetricKind, MetricUnit, ValueTransform
from models.trends.metric_point import MetricPoint


class MetricLineChart(MetricChart):
    """Line chart of any y metric over any x metric: time (periods, buckets, dates) or a measured value.

    Attributes:
        MARKER_LIMIT (ClassVar[int]): The number of points of a series above which its markers are not drawn.
        HOVER_DISTANCE (ClassVar[float]): How close the mouse must be to a point of a numeric x axis, in pixels.

    Notes:
        - The x spacing follows the real time (a half-year report sits six months after the previous quarter) or
          the real values.
        - The forecast is dashed, with hollow markers, after a vertical line at the latest observation.
        - A rank axis is inverted (1 at the top): with the rank transform, the chart is a bump chart.
        - Hovering a time axis shows a crosshair and every series value at the nearest x value.
    """

    MARKER_LIMIT: ClassVar[int] = 40
    HOVER_DISTANCE: ClassVar[float] = 24.0

    ############################
    # Internal Helpers Methods #
    ############################

    def _is_time(self) -> bool:
        """Tell whether the x axis counts time.

        Returns:
            bool: Whether the x metric is a time metric.
        """
        return self.axes is not None and self.axes.x.kind is MetricKind.TIME

    def _points(self) -> List[MetricPoint]:
        """Get every visible point.

        Returns:
            List[MetricPoint]: The points of the visible series.
        """
        return [point for series, _, _, _ in self._visible() for point in series.points]

    def _frame(self, plot: QRectF) -> Tuple[PlotFrame, List[float], Optional[float]]:
        """Fit the visible points in the plot.

        Args:
            plot (QRectF): The plot area.

        Returns:
            Tuple[PlotFrame, List[float], Optional[float]]: The frame, the y grid values and the y step.
        """
        points = self._points() or [point for series, _, _, _ in self.lines for point in series.points]
        xs, ys = [point.x for point in points], [point.y for point in points]
        x_low, x_high = min(xs), max(xs)
        if not self._is_time():
            x_low, x_high, _ = self.scale.linear(x_low, x_high, include_zero=False)
        elif x_low == x_high:
            x_low, x_high = x_low - 1, x_high + 1
        full_x = (x_low, x_high)
        shown_x = self.zoom.x_range(x_low, x_high)
        if self._y_unit() is MetricUnit.RANK:
            highest = max(max(ys), 2.0)
            step = 1.0 if highest <= 10 else self.scale.linear(1, highest)[2]
            ticks = [1.0, *[value for value in self.scale.ticks(0, highest, step) if value >= step]]
            full_y = (0.5, highest + 0.5)
            shown_y = self.zoom.y_range(*full_y)
            visible = [value for value in ticks if shown_y[0] <= value <= shown_y[1]]
            frame = PlotFrame(plot, shown_x, shown_y, invert_y=True)
            self.zoom.set_frame(frame, full_x, full_y)
            return frame, visible, step
        low, high, step = self.scale.linear(min(ys), max(ys), include_zero=min(ys) >= 0)
        shown_low, shown_high, ticks, step = self._zoomed_y(low, high, self.scale.ticks(low, high, step), step)
        frame = PlotFrame(plot, shown_x, (shown_low, shown_high))
        self.zoom.set_frame(frame, full_x, (low, high))
        return frame, ticks, step

    def _x_values(self) -> List[Tuple[float, str]]:
        """Get the x values of a time axis and their labels.

        Returns:
            List[Tuple[float, str]]: Each distinct x value of the visible points, with the name of its point.
        """
        if self.axes is None:
            return []
        names: Dict[float, str] = {}
        for point in self._points():
            names.setdefault(round(point.x, 6), self.formatter.x_label(self.axes.x, point.x, point.label))
        return list(names.items())

    def _paint_x_axis(self, painter: QPainter, frame: PlotFrame) -> None:
        """Paint the x values: the moments of a time axis, the grid values of a numeric one.

        Args:
            painter (QPainter): The painter.
            frame (PlotFrame): The plot frame.
        """
        if self.axes is None:
            return
        if self._is_time():
            self._paint_x_values(painter, frame, self._x_values())
            return
        step = self.scale.linear(frame.x_low, frame.x_high, include_zero=False)[2]
        values = [
            (value, self.formatter.value(self.axes.x.unit, value, self._currency(), step))
            for value in self.scale.ticks(frame.x_low, frame.x_high, step)
        ]
        self._paint_x_values(painter, frame, values, grid=True)

    def _paint_marks(self, painter: QPainter, frame: PlotFrame) -> None:
        """Paint the methodology changes and the start of the forecast.

        Args:
            painter (QPainter): The painter.
            frame (PlotFrame): The plot frame.
        """
        top, bottom = frame.area.top(), frame.area.bottom()
        painter.setPen(QPen(QColor(self.theme.WARNING), 1, Qt.PenStyle.DashLine))
        for value in self.breaks:
            if frame.x_low <= value <= frame.x_high:
                x = frame.map_x(value)
                painter.drawLine(QPointF(x, top), QPointF(x, bottom))
                painter.drawText(QRectF(x + 4, top, 160, 16), Qt.AlignmentFlag.AlignLeft, "methodology change")
        forecast = any(point.projected for point in self._points())
        if forecast and self.last_actual is not None:
            x = frame.map_x(self.last_actual)
            painter.setPen(QPen(QColor(self.theme.TEXT_MUTED), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))
            painter.drawText(QRectF(x + 4, top + 16, 120, 16), Qt.AlignmentFlag.AlignLeft, "forecast →")

    def _paint_series(self, painter: QPainter, frame: PlotFrame, line: ChartLine) -> None:
        """Paint a series: its observed points joined by a line, its forecast dashed.

        Args:
            painter (QPainter): The painter.
            frame (PlotFrame): The plot frame.
            line (ChartLine): The series.
        """
        series, label, color, style = line
        points = sorted(series.points, key=lambda point: point.x) if not self._is_time() else series.points
        shown = self._faded(color, label)
        markers = len(points) <= self.MARKER_LIMIT
        width = 3 if self.highlighted == label else 2
        previous: Optional[QPointF] = None
        for point in points:
            position = frame.map(point.x, point.y)
            if previous is not None:
                pen_style = Qt.PenStyle.DashLine if point.projected else style
                painter.setPen(QPen(shown, width, pen_style))
                painter.drawLine(previous, position)
            if markers or point.projected:
                painter.setPen(QPen(shown, 1.5))
                painter.setBrush(QColor(self.theme.SURFACE) if point.projected else shown)
                painter.drawEllipse(position, 3, 3)
            previous = position
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _nearest_x(self, frame: PlotFrame) -> Optional[float]:
        """Find the x value of the visible points nearest to the mouse.

        Args:
            frame (PlotFrame): The plot frame.

        Returns:
            Optional[float]: The x value, `None` when the mouse is outside the plot.
        """
        if self.hover is None or not frame.area.adjusted(-4, -4, 4, 4).contains(self.hover):
            return None
        xs = {round(point.x, 6) for point in self._points()}
        hover = self.hover
        return min(xs, key=lambda x: abs(frame.map_x(x) - hover.x()), default=None)

    def _paint_crosshair(self, painter: QPainter, frame: PlotFrame) -> None:
        """Paint a vertical line at the x value nearest to the mouse, and the points on it.

        Args:
            painter (QPainter): The painter.
            frame (PlotFrame): The plot frame.
        """
        nearest = self._nearest_x(frame) if self._is_time() else None
        if nearest is None:
            return
        x = frame.map_x(nearest)
        painter.setPen(QPen(QColor(self.theme.TEXT_MUTED), 1))
        painter.drawLine(QPointF(x, frame.area.top()), QPointF(x, frame.area.bottom()))
        for series, _, color, _ in self._visible():
            for point in series.points:
                if round(point.x, 6) == nearest:
                    painter.setPen(QPen(QColor(self.theme.SURFACE), 2))
                    painter.setBrush(color)
                    painter.drawEllipse(frame.map(point.x, point.y), 5, 5)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _value(self, value: float) -> str:
        """Write a y value with its unit.

        Args:
            value (float): The value.

        Returns:
            str: The written value.
        """
        return self.formatter.value(self._y_unit(), value, self._currency())

    def _paint_plot(self, painter: QPainter, plot: QRectF) -> None:
        """Paint the grid, the axes, the marks, the series and the crosshair.

        Args:
            painter (QPainter): The painter.
            plot (QRectF): The plot area.
        """
        if self.axes is None:
            return
        frame, ticks, step = self._frame(plot)
        self._paint_y_grid(painter, frame, ticks, self._y_unit(), step)
        self._paint_x_axis(painter, frame)
        x_title = "" if self._is_time() else self.labels.axis_title(self.axes.x, self.axes.scope)
        self._paint_titles(
            painter, plot, x_title, self.labels.axis_title(self.axes.y, self.axes.scope, self.axes.transform)
        )
        painter.save()
        painter.setClipRect(plot if self.zoom.is_zoomed() else plot.adjusted(-6, -6, 6, 6))
        self._paint_marks(painter, frame)
        for line in self._visible():
            if line[1] != self.highlighted:
                self._paint_series(painter, frame, line)
        for line in self._visible():
            if line[1] == self.highlighted:
                self._paint_series(painter, frame, line)
        self._paint_crosshair(painter, frame)
        painter.restore()

    def _tooltip(self, position: QPointF) -> Optional[str]:
        """Describe the series values at the x value nearest to the mouse, or the point under it.

        Args:
            position (QPointF): The mouse position.

        Returns:
            Optional[str]: The tooltip, `None` away from the data.
        """
        if self.axes is None or not self._has_data():
            return None
        if self.plot_area.isEmpty():
            return None
        frame = self._frame(self.plot_area)[0]
        self.hover = position
        axes = self.axes
        if self._is_time():
            nearest = self._nearest_x(frame)
            if nearest is None:
                return None
            rows: List[Tuple[float, str]] = []
            name = ""
            for series, label, _, _ in self._visible():
                for point in series.points:
                    if round(point.x, 6) == nearest:
                        name = self.formatter.x_label(axes.x, point.x, point.label)
                        forecast = " (forecast)" if point.projected else ""
                        rows.append((point.y, f"{label}: {self._value(point.y)}{forecast}"))
            ascending = self._y_unit() is MetricUnit.RANK
            ordered = [text for _, text in sorted(rows, key=lambda row: row[0], reverse=not ascending)]
            return "\n".join([name, *ordered]) if ordered else None
        candidates = [
            (
                abs(frame.map(point.x, point.y).x() - position.x())
                + abs(frame.map(point.x, point.y).y() - position.y()),
                label,
                point,
            )
            for series, label, _, _ in self._visible()
            for point in series.points
        ]
        if not candidates:
            return None
        distance, label, point = min(candidates, key=lambda candidate: candidate[0])
        if distance > self.HOVER_DISTANCE:
            return None
        x_name = self.labels.metric_label(axes.x, axes.scope)
        y_name = self.labels.metric_label(axes.y, axes.scope)
        x_value = self.formatter.value(axes.x.unit, point.x, self._currency())
        when = f" ({point.label})" if point.label else ""
        return f"{label}{when}\n{x_name}: {x_value}\n{y_name}: {self._value(point.y)}"

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_rank(self) -> bool:
        """Tell whether the chart shows ranks (an inverted y axis).

        Returns:
            bool: Whether the values are ranks.
        """
        return self.axes is not None and self.axes.transform is ValueTransform.RANK
