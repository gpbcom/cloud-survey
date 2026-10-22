from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter

# First Party Imports.
from gui.charts.base.chart_legend import LegendEntry
from gui.charts.base.metric_chart import MetricChart
from gui.charts.base.plot_frame import PlotFrame

Segment = Tuple[QRectF, str, str, float]


class MixBarChart(MetricChart):
    """Mix of a matrix: one 100% stacked bar per row, a coloured segment per column.

    Attributes:
        BAR_HEIGHT (ClassVar[int]): The height of a bar, in pixels.
        BAR_SPACING (ClassVar[int]): The space between two bars, in pixels.
        VALUE_WIDTH (ClassVar[int]): The smallest segment width showing its share, in pixels.
        HEADER_LIMIT (ClassVar[int]): The largest width of the row names of a chart fitted to the view, in pixels.

    Notes:
        - The cells are the share of each column in its row, in percent.
        - Hiding a column from the legend leaves its gap in the bars, so that the shares stay readable.
    """

    BAR_HEIGHT: ClassVar[int] = 22
    BAR_SPACING: ClassVar[int] = 10
    VALUE_WIDTH: ClassVar[int] = 36
    HEADER_LIMIT: ClassVar[int] = 180

    ############################
    # Internal Helpers Methods #
    ############################

    def _has_data(self) -> bool:
        """Tell whether there are bars to paint.

        Returns:
            bool: Whether the matrix has rows and columns.
        """
        return self.matrix is not None and bool(self.matrix.rows) and bool(self.matrix.columns)

    def _legend_entries(self) -> List[LegendEntry]:
        """Get the legend entries: one per column.

        Returns:
            List[LegendEntry]: The name and colour of each column.
        """
        if self.matrix is None or self.axes is None:
            return []
        grouping = self.axes.columns
        return [
            (
                self.labels.series_label(grouping, column),
                self.labels.series_color(grouping, column),
                Qt.PenStyle.SolidLine,
            )
            for column in self.matrix.columns
        ]

    def _legend_suffixes(self) -> Dict[str, str]:
        """Get the text after the legend labels: none for the columns.

        Returns:
            Dict[str, str]: No suffix.
        """
        return {}

    def _segments(self, plot: QRectF) -> List[Segment]:
        """Place the segments of the bars.

        Args:
            plot (QRectF): The area of the bars, right of the row names.

        Returns:
            List[Segment]: The rectangle, row, column and share of each segment.
        """
        if self.matrix is None or self.axes is None:
            return []
        full = (0.0, 100.0)
        frame = PlotFrame(plot, self.zoom.x_range(*full), (0.0, 1.0))
        self.zoom.zoom_y = False
        self.zoom.set_frame(frame, full, None)
        segments: List[Segment] = []
        for index, row in enumerate(self.matrix.rows):
            top = plot.top() + index * (self.BAR_HEIGHT + self.BAR_SPACING)
            start = 0.0
            cells = self.matrix.cells.get(row, {})
            total = sum(cells.get(column, 0.0) for column in self.matrix.columns) or 1.0
            for column in self.matrix.columns:
                share = cells.get(column, 0.0)
                end = start + 100.0 * share / max(total, 100.0)
                left, right = max(frame.map_x(start), plot.left()), min(frame.map_x(end), plot.right())
                segments.append((QRectF(left, top, max(right - left, 0.0), self.BAR_HEIGHT), row, column, share))
                start = end
        return segments

    def _paint_plot(self, painter: QPainter, plot: QRectF) -> None:
        """Paint the row names and the bars.

        Args:
            painter (QPainter): The painter.
            plot (QRectF): The plot area.
        """
        if self.matrix is None or self.axes is None:
            return
        axes = self.axes
        metrics = painter.fontMetrics()
        names = [self.labels.series_label(axes.series_by, row) for row in self.matrix.rows]
        header = max((metrics.horizontalAdvance(name) for name in names), default=60) + 16
        header = header if self.wide else min(header, self.HEADER_LIMIT)
        bars = QRectF(plot.left() - self.LEFT + header, plot.top(), plot.width() + self.LEFT - header, plot.height())
        self.plot_area = bars
        for index, name in enumerate(names):
            top = bars.top() + index * (self.BAR_HEIGHT + self.BAR_SPACING)
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            box = QRectF(bars.left() - header, top, header - 10, self.BAR_HEIGHT)
            elided = metrics.elidedText(name, Qt.TextElideMode.ElideRight, int(header - 12))
            painter.drawText(box, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, elided)
        for rect, _, column, share in self._segments(bars):
            label = self.labels.series_label(axes.columns, column)
            if label in self.hidden or rect.width() <= 0:
                continue
            painter.fillRect(
                rect.adjusted(0, 0, -1, 0), self._faded(self.labels.series_color(axes.columns, column), label)
            )
            if rect.width() >= self.VALUE_WIDTH:
                painter.setPen(QColor(self.theme.WINDOW))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{share:.0f}%")

    def _tooltip(self, position: QPointF) -> Optional[str]:
        """Describe the segment under the mouse.

        Args:
            position (QPointF): The mouse position.

        Returns:
            Optional[str]: The row, the column and its share, `None` outside the bars.
        """
        if self.matrix is None or self.axes is None or self.plot_area.isEmpty():
            return None
        for rect, row, column, share in self._segments(self.plot_area):
            if rect.contains(position):
                row_name = self.labels.series_label(self.axes.series_by, row)
                column_name = self.labels.series_label(self.axes.columns, column)
                return f"{row_name} · {column_name}\n{share:.1f}% of the row"
        return None

    ############################
    # Publicly Exposed Methods #
    ############################

    def preferred_height(self) -> int:
        """Get the height fitting every bar and the legend.

        Returns:
            int: The height, in pixels, at least the chart minimum.
        """
        rows = len(self.matrix.rows) if self.matrix is not None else 0
        return max(self.MIN_HEIGHT, self.TOP + rows * (self.BAR_HEIGHT + self.BAR_SPACING) + self.BOTTOM + 40)

    def needed_height(self) -> int:
        """Get the height fitting every bar and the legend.

        Returns:
            int: The height, in pixels, at least the chart minimum.
        """
        return self.preferred_height()

    def natural_width(self) -> int:
        """Get the width of the widened chart: the row names in full beside wide bars.

        Returns:
            int: The width, in pixels.
        """
        if self.matrix is None or self.axes is None:
            return 0
        metrics = self.fontMetrics()
        names = [self.labels.series_label(self.axes.series_by, row) for row in self.matrix.rows]
        header = max((metrics.horizontalAdvance(name) for name in names), default=60) + 16
        return header + self.WIDE_PLOT_WIDTH + self.RIGHT + self._legend_width()
