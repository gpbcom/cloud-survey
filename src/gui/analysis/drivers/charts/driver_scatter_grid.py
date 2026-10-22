from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QResizeEvent
from PyQt6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QWidget

# First Party Imports.
from gui.analysis.drivers.charts.driver_scatter_chart import DriverPoint, DriverScatterChart
from gui.theme import Theme

type ScatterPanel = Tuple[str, str, List[DriverPoint]]


class DriverScatterGrid(QWidget):
    """The target against each criterion: one small scatter per criterion, side by side, sharing the target axis.

    Attributes:
        CHART_WIDTH (ClassVar[int]): The narrowest a chart gets: the grid puts as many per row as fit.
        CHART_HEIGHT (ClassVar[int]): The height of a chart.
        MAX_COLUMNS (ClassVar[int]): The most charts per row.
        theme (Theme): The application theme.
        charts (List[DriverScatterChart]): The charts, the most predominant criterion first.
        columns (int): The charts per row of the current layout.
        grid (QGridLayout): The layout of the charts.
        message (QLabel): What the grid says without charts.
        logger (Logger): The grid logger.

    Notes:
        The charts share the range of the target axis, so their slopes compare at a glance. The grid flows again
        when its width changes (more charts per row in a widened window).
    """

    CHART_WIDTH: ClassVar[int] = 360
    CHART_HEIGHT: ClassVar[int] = 260
    MAX_COLUMNS: ClassVar[int] = 4

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build an empty grid.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The grid logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.charts: List[DriverScatterChart] = []
        self.columns = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.message = QLabel("Run the analysis to see the target against each criterion.")
        self.message.setObjectName("muted")
        self.message.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.message.setWordWrap(True)
        self.grid.addWidget(self.message, 0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    ############################
    # Internal Helpers Methods #
    ############################

    def _columns_for(self, width: int) -> int:
        """Count the charts fitting a row.

        Args:
            width (int): The width of the grid.

        Returns:
            int: From 1 to `MAX_COLUMNS`, at most the number of charts.
        """
        fitting = max(1, (width + self.grid.spacing()) // (self.CHART_WIDTH + self.grid.spacing()))
        return max(1, min(fitting, self.MAX_COLUMNS, len(self.charts) or 1))

    def _shared_range(self, panels: List[ScatterPanel]) -> Optional[Tuple[float, float]]:
        """Get the target axis of every chart: the range of the target over all of them, padded.

        Args:
            panels (List[ScatterPanel]): The charts to draw.

        Returns:
            Optional[Tuple[float, float]]: The lowest and highest target, `None` without a dot.
        """
        values = [y for _, _, points in panels for _, _, _, y in points]
        if not values:
            return None
        pad = (max(values) - min(values)) * 0.06 or 0.5
        low = max(min(values) - pad, 0.0) if min(values) > 0 else min(values) - pad
        return low, max(values) + pad

    def _relayout(self) -> None:
        """Place the charts in rows of as many as fit the width."""
        for chart in self.charts:
            self.grid.removeWidget(chart)
        self.grid.removeWidget(self.message)
        for position in range(self.MAX_COLUMNS):
            self.grid.setColumnStretch(position, 0)
        self.message.setVisible(not self.charts)
        if not self.charts:
            self.grid.addWidget(self.message, 0, 0)
            self.columns = 0
            return
        self.columns = self._columns_for(self.width())
        for index, chart in enumerate(self.charts):
            self.grid.addWidget(chart, index // self.columns, index % self.columns)
        for position in range(self.columns):
            self.grid.setColumnStretch(position, 1)
        self.updateGeometry()
        self.logger.debug("Scatter grid laid out: %d charts, %d per row.", len(self.charts), self.columns)

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_panels(
        self, panels: List[ScatterPanel], y_label: str, x_color: QColor, y_color: QColor, message: str = ""
    ) -> None:
        """Show a chart per criterion.

        Args:
            panels (List[ScatterPanel]): The title, the criterion name and the dots of each chart, in order.
            y_label (str): The name of the target, shared by the charts.
            x_color (QColor): The colour of the criterion titles (their role).
            y_color (QColor): The colour of the target axis titles (its role).
            message (str): What the grid says without charts.
        """
        for chart in self.charts:
            self.grid.removeWidget(chart)
            chart.deleteLater()
        if message:
            self.message.setText(message)
        shared = self._shared_range(panels)
        self.charts = []
        for title, x_label, points in panels:
            chart = DriverScatterChart(self.theme, self.logger)
            chart.setMinimumSize(self.CHART_WIDTH - 60, self.CHART_HEIGHT)
            chart.set_points(points, x_label, y_label, f"No observation of {x_label}.", x_color, y_color, title, shared)
            self.charts.append(chart)
        self._relayout()
        self.logger.debug("Scatter grid shows %d criteria.", len(self.charts))

    def sizeHint(self) -> QSize:
        """Get the preferred size: the rows of charts (Qt override).

        Returns:
            QSize: The preferred size.
        """
        columns = max(self.columns, 1)
        rows = -(-len(self.charts) // columns) if self.charts else 1
        return QSize(columns * self.CHART_WIDTH, rows * (self.CHART_HEIGHT + self.grid.spacing()))

    def resizeEvent(self, event: Optional[QResizeEvent]) -> None:
        """Flow the charts again when the width changes the charts per row (Qt override).

        Args:
            event (Optional[QResizeEvent]): The resize event.
        """
        super().resizeEvent(event)
        if self.charts and self._columns_for(self.width()) != self.columns:
            self._relayout()
