from __future__ import annotations

# Standard Library Imports.
import math
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen

# First Party Imports.
from gui.charts.base.chart_legend import LegendEntry
from gui.charts.base.metric_chart import MetricChart
from gui.charts.base.plot_frame import PlotFrame
from models.trends.enums import MetricUnit

Cell = Tuple[QRectF, str, str, float]


class HeatmapChart(MetricChart):
    """Heatmap of a matrix: one coloured cell per row and column, the darker the larger.

    Attributes:
        ROW_HEIGHT (ClassVar[int]): The smallest height of a row, in pixels.
        HEADER_HEIGHT (ClassVar[int]): The height of the column headers, in pixels.
        SCALE_HEIGHT (ClassVar[int]): The height of the colour scale below the cells, in pixels.
        VALUE_WIDTH (ClassVar[int]): The smallest cell width showing its value, in pixels.
        HEADER_LIMIT (ClassVar[int]): The largest width of the row headers of a chart fitted to the view, in pixels.
        COLUMN_PADDING (ClassVar[int]): The room around a column header of a widened chart, in pixels.

    Notes:
        - The colour runs from the panel colour (zero) to the accent colour (the largest cell).
        - The diagonal of a marketplace by marketplace matrix holds each marketplace's own figure.
        - Fitted to the view, the long headers are shortened (in full in the tooltips). Widened, every column is as
          wide as its header and the row headers are in full, the chart scrolling sideways.
    """

    ROW_HEIGHT: ClassVar[int] = 26
    HEADER_HEIGHT: ClassVar[int] = 44
    SCALE_HEIGHT: ClassVar[int] = 34
    VALUE_WIDTH: ClassVar[int] = 40
    HEADER_LIMIT: ClassVar[int] = 200
    COLUMN_PADDING: ClassVar[int] = 16

    ############################
    # Internal Helpers Methods #
    ############################

    def _has_data(self) -> bool:
        """Tell whether there are cells to paint.

        Returns:
            bool: Whether the matrix has rows and columns.
        """
        return self.matrix is not None and bool(self.matrix.rows) and bool(self.matrix.columns)

    def _legend_entries(self) -> List[LegendEntry]:
        """Get the legend entries: none, the colour scale stands for the legend.

        Returns:
            List[LegendEntry]: No entry.
        """
        return []

    def _unit(self) -> MetricUnit:
        """Get the unit of the cells.

        Returns:
            MetricUnit: The unit of the cell metric.
        """
        return self.axes.cell.unit if self.axes is not None else MetricUnit.COUNT

    def _mix(self, ratio: float) -> QColor:
        """Get the colour of a cell.

        Args:
            ratio (float): The cell value over the largest one, 0 to 1.

        Returns:
            QColor: A blend of the panel and accent colours.
        """
        low, high = QColor(self.theme.SURFACE_ALT), QColor(self.theme.ACCENT)
        ratio = min(max(ratio, 0.0), 1.0)
        return QColor(
            round(low.red() + (high.red() - low.red()) * ratio),
            round(low.green() + (high.green() - low.green()) * ratio),
            round(low.blue() + (high.blue() - low.blue()) * ratio),
        )

    def _index_frame(self, area: QRectF) -> PlotFrame:
        """Map the column and row indexes to the cell area, through the zoom.

        Args:
            area (QRectF): The area of the cells.

        Returns:
            PlotFrame: The frame: column `c` spans x `c` to `c + 1`, row `r` spans y `r` to `r + 1` (from the top).
        """
        columns = len(self.matrix.columns) if self.matrix is not None else 1
        rows = len(self.matrix.rows) if self.matrix is not None else 1
        full_x, full_y = (0.0, float(max(columns, 1))), (0.0, float(max(rows, 1)))
        frame = PlotFrame(area, self.zoom.x_range(*full_x), self.zoom.y_range(*full_y), invert_y=True)
        self.zoom.wheel_y = True
        self.zoom.set_frame(frame, full_x, full_y)
        return frame

    def _shown_indexes(self, low: float, high: float, count: int) -> range:
        """Get the indexes of the rows (or columns) shown in a zoom window.

        Args:
            low (float): The low bound of the window.
            high (float): The high bound of the window.
            count (int): The number of rows (or columns).

        Returns:
            range: The indexes at least partly inside the window.
        """
        return range(max(math.floor(low), 0), min(math.ceil(high), count))

    def _cells(self, area: QRectF) -> Tuple[List[Cell], float]:
        """Place the cells shown by the zoom (every cell when not zoomed).

        Args:
            area (QRectF): The area of the cells, right of the row headers and below the column headers.

        Returns:
            Tuple[List[Cell], float]: The rectangle, row, column and value of each shown cell, and the largest value
                of every cell (the colour scale does not change with the zoom).
        """
        if self.matrix is None or self.axes is None:
            return [], 0.0
        matrix = self.matrix
        frame = self._index_frame(area)
        cells: List[Cell] = []
        for row_index in self._shown_indexes(frame.y_low, frame.y_high, len(matrix.rows)):
            row = matrix.rows[row_index]
            for column_index in self._shown_indexes(frame.x_low, frame.x_high, len(matrix.columns)):
                column = matrix.columns[column_index]
                corner = QPointF(frame.map_x(column_index), frame.map_y(row_index))
                rect = QRectF(corner, QPointF(frame.map_x(column_index + 1), frame.map_y(row_index + 1)))
                rect = rect.normalized().intersected(area)
                cells.append((rect.adjusted(1, 1, -1, -1), row, column, matrix.cells.get(row, {}).get(column, 0.0)))
        values = [(row, column, value) for row, found in matrix.cells.items() for column, value in found.items()]
        largest = max(
            (value for row, column, value in values if not (row == column and self.axes.cell.publisher_pairs)),
            default=0.0,
        )
        return cells, largest or max((value for *_, value in values), default=1.0) or 1.0

    def _header_width(self) -> int:
        """Get the width of the row headers.

        Returns:
            int: The width of the longest row name, at most `HEADER_LIMIT` unless the chart is widened, in pixels.
        """
        metrics = self.fontMetrics()
        rows = self.matrix.rows if self.matrix is not None else []
        grouping = self.axes.series_by if self.axes is not None else None
        names = [self.labels.series_label(grouping, row) for row in rows] if grouping is not None else []
        header = max((metrics.horizontalAdvance(name) for name in names), default=60) + 16
        return header if self.wide else min(header, self.HEADER_LIMIT)

    def _areas(self) -> Tuple[QRectF, float]:
        """Split the chart between the row headers and the cells.

        Returns:
            Tuple[QRectF, float]: The area of the cells and the width of the row headers.
        """
        header = self._header_width()
        area = QRectF(
            header,
            self.HEADER_HEIGHT,
            max(self.width() - header - self.RIGHT, 10),
            max(self.height() - self.HEADER_HEIGHT - self.SCALE_HEIGHT - 8, 10),
        )
        return area, header

    def _paint_plot(self, painter: QPainter, plot: QRectF) -> None:
        """Paint the headers, the cells and the colour scale.

        Args:
            painter (QPainter): The painter.
            plot (QRectF): The chart area (the matrix lays itself out).
        """
        if self.matrix is None or self.axes is None:
            return
        axes = self.axes
        area, header = self._areas()
        self.plot_area = area
        cells, largest = self._cells(area)
        metrics = painter.fontMetrics()
        for rect, row, _column, value in cells:
            label = self.labels.series_label(axes.series_by, row)
            painter.fillRect(rect, self._faded(self._mix(value / largest), label))
            if rect.width() >= self.VALUE_WIDTH and rect.height() >= 16:
                painter.setPen(QColor(self.theme.TEXT))
                text = self.formatter.value(self._unit(), value, compact=True)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.setPen(QColor(self.theme.TEXT_MUTED))
        frame = self._index_frame(area)
        for index in self._shown_indexes(frame.y_low, frame.y_high, len(self.matrix.rows)):
            name = metrics.elidedText(
                self.labels.series_label(axes.series_by, self.matrix.rows[index]),
                Qt.TextElideMode.ElideRight,
                int(header - 12),
            )
            row_top, row_bottom = max(frame.map_y(index), area.top()), min(frame.map_y(index + 1), area.bottom())
            box = QRectF(4, row_top, header - 10, row_bottom - row_top)
            painter.drawText(box, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, name)
        for index in self._shown_indexes(frame.x_low, frame.x_high, len(self.matrix.columns)):
            left, right = max(frame.map_x(index), area.left()), min(frame.map_x(index + 1), area.right())
            name = self.labels.series_label(axes.columns, self.matrix.columns[index])
            elided = metrics.elidedText(name, Qt.TextElideMode.ElideRight, int(max(right - left - 4, 12)))
            box = QRectF(left, area.top() - 22, right - left, 18)
            painter.drawText(box, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, elided)
        scale = QRectF(area.left(), area.bottom() + 12, min(area.width(), 240), 10)
        gradient = QLinearGradient(scale.topLeft(), scale.topRight())
        gradient.setColorAt(0, self._mix(0))
        gradient.setColorAt(1, self._mix(1))
        painter.fillRect(scale, gradient)
        painter.setPen(QColor(self.theme.TEXT_MUTED))
        painter.drawText(QRectF(scale.left(), scale.bottom() + 2, 80, 14), Qt.AlignmentFlag.AlignLeft, "0")
        top = self.formatter.value(self._unit(), largest, compact=True)
        painter.drawText(QRectF(scale.right() - 80, scale.bottom() + 2, 80, 14), Qt.AlignmentFlag.AlignRight, top)
        painter.drawText(
            QRectF(scale.right() + 12, scale.top() - 3, 260, 16),
            Qt.AlignmentFlag.AlignLeft,
            self.labels.CELL_LABELS[axes.cell],
        )
        painter.setPen(QPen(QColor(self.theme.BORDER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(area)

    def _tooltip(self, position: QPointF) -> Optional[str]:
        """Describe the cell (or the header) under the mouse.

        Args:
            position (QPointF): The mouse position.

        Returns:
            Optional[str]: The row, the column and the value, the full name of a header, `None` elsewhere.
        """
        if self.matrix is None or self.axes is None:
            return None
        area, _ = self._areas()
        rows, columns = self.matrix.rows, self.matrix.columns
        frame = self._index_frame(area)
        if area.top() <= position.y() < area.bottom() and position.x() < area.left() and rows:
            row = rows[min(max(int(frame.value_y(position.y())), 0), len(rows) - 1)]
            return self.labels.series_label(self.axes.series_by, row)
        if area.left() <= position.x() < area.right() and position.y() < area.top() and columns:
            column = columns[min(max(int(frame.value_x(position.x())), 0), len(columns) - 1)]
            return self.labels.series_label(self.axes.columns, column)
        cells, _ = self._cells(area)
        for rect, row, column, value in cells:
            if rect.contains(position):
                row_name = self.labels.series_label(self.axes.series_by, row)
                column_name = self.labels.series_label(self.axes.columns, column)
                cell = self.labels.CELL_LABELS[self.axes.cell]
                return f"{row_name} × {column_name}\n{cell}: {self.formatter.value(self._unit(), value, compact=False)}"
        return None

    ############################
    # Publicly Exposed Methods #
    ############################

    def needed_height(self) -> int:
        """Get the height fitting every row.

        Returns:
            int: The height, in pixels, at least `MIN_HEIGHT`.
        """
        rows = len(self.matrix.rows) if self.matrix is not None and self._has_data() else 0
        return max(self.MIN_HEIGHT, self.HEADER_HEIGHT + rows * self.ROW_HEIGHT + self.SCALE_HEIGHT + 8)

    def natural_width(self) -> int:
        """Get the width of the widened chart: every column as wide as its header.

        Returns:
            int: The width, in pixels.
        """
        if self.matrix is None or self.axes is None:
            return 0
        metrics = self.fontMetrics()
        widths = [
            metrics.horizontalAdvance(self.labels.series_label(self.axes.columns, column)) + self.COLUMN_PADDING
            for column in self.matrix.columns
        ]
        cell = max(max(widths, default=self.VALUE_WIDTH), self.VALUE_WIDTH)
        return self._header_width() + cell * len(self.matrix.columns) + self.RIGHT
