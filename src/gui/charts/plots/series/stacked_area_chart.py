from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF

# First Party Imports.
from gui.charts.base.metric_chart import MetricChart
from gui.charts.base.plot_frame import PlotFrame
from models.trends.enums import MetricUnit, ValueTransform

Stack = Tuple[str, QColor, List[Tuple[float, float, float]]]


class StackedAreaChart(MetricChart):
    """Stacked area chart over time: the series pile up, the total (or 100% for the shares) on top.

    Attributes:
        COLUMN_WIDTH (ClassVar[int]): The width of the column drawn for a single x value, in pixels.

    Notes:
        - The series are stacked in their order: the largest at the bottom, the merged smallest ones on top.
        - A single x value (e.g. items all dated by the same crawl) is drawn as a stacked column.
        - The forecast part of each band is lighter, after a vertical line at the latest observation.
        - Hovering shows the value of every band at the nearest x value, and the total.
    """

    COLUMN_WIDTH: ClassVar[int] = 64

    ############################
    # Internal Helpers Methods #
    ############################

    def _stacks(self) -> List[Stack]:
        """Pile the visible series up.

        Returns:
            List[Stack]: The label, colour and (x, low, high) bounds of each band, from the bottom.
        """
        totals: Dict[float, float] = {}
        stacks: List[Stack] = []
        for series, label, color, _ in self._visible():
            bounds: List[Tuple[float, float, float]] = []
            for point in sorted(series.points, key=lambda point: point.x):
                x = round(point.x, 6)
                low = totals.get(x, 0.0)
                totals[x] = low + max(point.y, 0.0)
                bounds.append((point.x, low, totals[x]))
            stacks.append((label, color, bounds))
        return stacks

    def _frame(self, plot: QRectF, stacks: List[Stack]) -> Tuple[PlotFrame, List[float], float]:
        """Fit the stacked bands in the plot.

        Args:
            plot (QRectF): The plot area.
            stacks (List[Stack]): The bands.

        Returns:
            Tuple[PlotFrame, List[float], float]: The frame, the y grid values and the y step.
        """
        xs = [x for _, _, bounds in stacks for x, _, _ in bounds] or [0.0, 1.0]
        tops = [high for _, _, bounds in stacks for _, _, high in bounds] or [1.0]
        x_low, x_high = min(xs), max(xs)
        if x_low == x_high:
            x_low, x_high = x_low - 1, x_high + 1
        if self.axes is not None and self.axes.transform is ValueTransform.SHARE_OF_TOTAL:
            low, high, step = 0.0, 100.0, 20.0
        else:
            low, high, step = self.scale.linear(0.0, max(tops))
        shown_low, shown_high, ticks, step = self._zoomed_y(low, high, self.scale.ticks(low, high, step), step)
        frame = PlotFrame(plot, self.zoom.x_range(x_low, x_high), (shown_low, shown_high))
        self.zoom.set_frame(frame, (x_low, x_high), (low, high))
        return frame, ticks, step

    def _band(self, frame: PlotFrame, bounds: List[Tuple[float, float, float]]) -> QPolygonF:
        """Draw the outline of a band.

        Args:
            frame (PlotFrame): The plot frame.
            bounds (List[Tuple[float, float, float]]): The x, low and high values of the band.

        Returns:
            QPolygonF: Its top edge left to right, then its bottom edge right to left, or a column centred on its x for
                a band of a single x (e.g. items all dated by the same crawl).
        """
        if len(bounds) == 1:
            x, low, high = bounds[0]
            half = min(self.COLUMN_WIDTH, frame.area.width() / 3) / 2
            center = frame.map_x(x)
            return QPolygonF(
                [
                    QPointF(center - half, frame.map_y(high)),
                    QPointF(center + half, frame.map_y(high)),
                    QPointF(center + half, frame.map_y(low)),
                    QPointF(center - half, frame.map_y(low)),
                ]
            )
        top = [frame.map(x, high) for x, _, high in bounds]
        bottom = [frame.map(x, low) for x, low, _ in reversed(bounds)]
        return QPolygonF(top + bottom)

    def _nearest(self, frame: PlotFrame, stacks: List[Stack]) -> Optional[float]:
        """Find the x value nearest to the mouse.

        Args:
            frame (PlotFrame): The plot frame.
            stacks (List[Stack]): The bands.

        Returns:
            Optional[float]: The x value, `None` when the mouse is outside the plot.
        """
        if self.hover is None or not frame.area.contains(self.hover):
            return None
        hover = self.hover
        xs = {x for _, _, bounds in stacks for x, _, _ in bounds}
        return min(xs, key=lambda x: abs(frame.map_x(x) - hover.x()), default=None)

    def _paint_plot(self, painter: QPainter, plot: QRectF) -> None:
        """Paint the grid, the bands, the forecast boundary and the crosshair.

        Args:
            painter (QPainter): The painter.
            plot (QRectF): The plot area.
        """
        if self.axes is None:
            return
        stacks = self._stacks()
        frame, ticks, step = self._frame(plot, stacks)
        unit = self._y_unit()
        self._paint_y_grid(painter, frame, ticks, unit, step)
        names: Dict[float, str] = {}
        for series, _, _, _ in self._visible():
            for point in series.points:
                names.setdefault(round(point.x, 6), self.formatter.x_label(self.axes.x, point.x, point.label))
        self._paint_x_values(painter, frame, list(names.items()))
        self._paint_titles(painter, plot, "", self.labels.axis_title(self.axes.y, self.axes.scope, self.axes.transform))
        projected = any(point.projected for series, _, _, _ in self._visible() for point in series.points)
        boundary = frame.map_x(self.last_actual) if self.last_actual is not None and projected else plot.right()
        boundary = min(max(boundary, plot.left()), plot.right())
        for label, color, bounds in stacks:
            if not bounds:
                continue
            band = self._band(frame, bounds)
            for clip, alpha in (
                (QRectF(plot.left(), plot.top(), boundary - plot.left(), plot.height()), 190),
                (QRectF(boundary, plot.top(), plot.right() - boundary, plot.height()), 80),
            ):
                painter.save()
                painter.setClipRect(clip)
                painter.setPen(QPen(self._faded(color.darker(130), label), 1))
                painter.setBrush(self._faded(color, label, alpha))
                painter.drawPolygon(band)
                painter.restore()
        if projected and self.last_actual is not None:
            painter.setPen(QPen(QColor(self.theme.TEXT), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(boundary, plot.top()), QPointF(boundary, plot.bottom()))
            painter.drawText(QRectF(boundary + 4, plot.top(), 120, 16), Qt.AlignmentFlag.AlignLeft, "forecast →")
        painter.setPen(QPen(QColor(self.theme.WARNING), 1, Qt.PenStyle.DashLine))
        for value in self.breaks:
            if frame.x_low <= value <= frame.x_high:
                painter.drawLine(QPointF(frame.map_x(value), plot.top()), QPointF(frame.map_x(value), plot.bottom()))
        nearest = self._nearest(frame, stacks)
        if nearest is not None:
            painter.setPen(QPen(QColor(self.theme.TEXT), 1))
            painter.drawLine(QPointF(frame.map_x(nearest), plot.top()), QPointF(frame.map_x(nearest), plot.bottom()))
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _tooltip(self, position: QPointF) -> Optional[str]:
        """Describe every band at the x value nearest to the mouse, the top band first, and the total.

        Args:
            position (QPointF): The mouse position.

        Returns:
            Optional[str]: The tooltip, `None` outside the plot.
        """
        if self.axes is None or self.plot_area.isEmpty():
            return None
        self.hover = position
        stacks = self._stacks()
        frame = self._frame(self.plot_area, stacks)[0]
        nearest = self._nearest(frame, stacks)
        if nearest is None:
            return None
        unit, currency = self._y_unit(), self._currency()
        rows: List[str] = []
        total = 0.0
        name = ""
        projected = False
        for series, label, _, _ in self._visible():
            for point in series.points:
                if round(point.x, 6) == round(nearest, 6):
                    name = self.formatter.x_label(self.axes.x, point.x, point.label)
                    projected = projected or point.projected
                    rows.append(f"{label}: {self.formatter.value(unit, point.y, currency)}")
                    total += point.y
        if not rows:
            return None
        header = f"{name} (forecast)" if projected else name
        footer = [] if unit is MetricUnit.PERCENT else [f"Total: {self.formatter.value(unit, total, currency)}"]
        return "\n".join([header, *reversed(rows), *footer])
