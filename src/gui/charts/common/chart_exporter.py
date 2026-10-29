from __future__ import annotations

# Standard Library Imports.
import csv
import io
from logging import Logger, getLogger
from pathlib import Path
from typing import List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtWidgets import QApplication, QFileDialog, QWidget

# First Party Imports.
from gui.charts.common.axis.axis_formatter import AxisFormatter
from models.trends.chart_axes import ChartAxes
from models.trends.matrix.metric_matrix import MetricMatrix
from models.trends.metric_series import MetricSeries


class ChartExporter:
    """Export a chart: its picture as a PNG file or to the clipboard, its data as CSV.

    Attributes:
        formatter (AxisFormatter): The value formatter, naming the x values.
        logger (Logger): The exporter logger.

    Notes:
        A file which cannot be written is reported in the logs: exporting never stops the application.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the exporter.

        Args:
            logger (Optional[Logger]): The exporter logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.formatter = AxisFormatter(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _write(self, path: str, data: bytes) -> bool:
        """Write a file.

        Args:
            path (str): The file path.
            data (bytes): The file content.

        Returns:
            bool: Whether the file was written (logged when not).
        """
        try:
            Path(path).write_bytes(data)
        except OSError as e:
            self.logger.warning("The chart could not be exported to %s: %s", path, e)
            return False
        self.logger.info("Chart exported to %s.", path)
        return True

    ############################
    # Publicly Exposed Methods #
    ############################

    def series_csv(self, axes: ChartAxes, series: List[Tuple[str, MetricSeries]]) -> str:
        """Write the points of the chart series as CSV.

        Args:
            axes (ChartAxes): The chart axes.
            series (List[Tuple[str, MetricSeries]]): The label and points of each series.

        Returns:
            str: One row per point: series, x label, x, y, size and whether it is a forecast.
        """
        self.logger.debug("Writing %d series of %s by %s as CSV.", len(series), axes.y.value, axes.x.value)
        if not series:
            self.logger.warning("No series to export: the CSV holds the header only.")
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["series", axes.x.value, "x", axes.y.value, "size", "forecast"])
        points = 0
        for label, one in series:
            for point in one.points:
                name = self.formatter.x_label(axes.x, point.x, point.label)
                size = "" if point.size is None else point.size
                writer.writerow([label, name, point.x, point.y, size, point.projected])
            points += len(one.points)
        self.logger.info("%d points of %d series written as CSV.", points, len(series))
        return buffer.getvalue()

    def matrix_csv(self, rows: List[Tuple[str, str]], columns: List[Tuple[str, str]], matrix: MetricMatrix) -> str:
        """Write the cells of a matrix chart as CSV.

        Args:
            rows (List[Tuple[str, str]]): The key and label of each row.
            columns (List[Tuple[str, str]]): The key and label of each column.
            matrix (MetricMatrix): The matrix.

        Returns:
            str: A header row of the column labels, then one row per row label and its cells.
        """
        self.logger.debug("Writing a matrix of %d rows by %d columns as CSV.", len(rows), len(columns))
        if not rows or not columns:
            self.logger.warning("Empty matrix to export: %d rows by %d columns.", len(rows), len(columns))
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["", *[label for _, label in columns]])
        for key, label in rows:
            cells = matrix.cells.get(key, {})
            writer.writerow([label, *[cells.get(column, 0.0) for column, _ in columns]])
        self.logger.info("Matrix of %d rows by %d columns written as CSV.", len(rows), len(columns))
        return buffer.getvalue()

    def save_png(self, widget: QWidget, name: str) -> bool:
        """Ask where to save the picture of a chart, and save it.

        Args:
            widget (QWidget): The chart.
            name (str): The suggested file name, without extension.

        Returns:
            bool: Whether the picture was saved (`False` when cancelled).
        """
        self.logger.debug("Asking where to save the picture of the chart %s.", name)
        path, _ = QFileDialog.getSaveFileName(widget, "Save the chart picture", f"{name}.png", "PNG images (*.png)")
        if not path:
            self.logger.debug("Saving the picture of the chart %s cancelled.", name)
            return False
        saved = widget.grab().save(path, "PNG")
        if not saved:
            self.logger.warning("The chart picture could not be saved to %s.", path)
        else:
            self.logger.info("Chart picture saved to %s.", path)
        return bool(saved)

    def save_csv(self, widget: QWidget, name: str, text: str) -> bool:
        """Ask where to save the data of a chart, and save it.

        Args:
            widget (QWidget): The chart, parent of the dialog.
            name (str): The suggested file name, without extension.
            text (str): The CSV data.

        Returns:
            bool: Whether the data was saved (`False` when cancelled).
        """
        self.logger.debug("Asking where to save the data of the chart %s (%d characters).", name, len(text))
        path, _ = QFileDialog.getSaveFileName(widget, "Save the chart data", f"{name}.csv", "CSV files (*.csv)")
        if not path:
            self.logger.debug("Saving the data of the chart %s cancelled.", name)
            return False
        return self._write(path, text.encode("utf-8"))

    def copy_image(self, widget: QWidget) -> None:
        """Copy the picture of a chart to the clipboard.

        Args:
            widget (QWidget): The chart.
        """
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setPixmap(widget.grab())
            self.logger.debug("Chart picture copied to the clipboard.")
        else:
            self.logger.warning("No clipboard: the chart picture was not copied.")

    def copy_text(self, text: str) -> None:
        """Copy the data of a chart to the clipboard.

        Args:
            text (str): The CSV data.
        """
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
            self.logger.debug("Chart data copied to the clipboard.")
        else:
            self.logger.warning("No clipboard: the chart data was not copied.")
