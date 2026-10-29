from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Optional

# Third Party Imports.
from PyQt6 import sip
from PyQt6.QtCore import QObject, QTimer

# First Party Imports.
from analytics.pipeline.matrix_loader import MatrixLoader
from analytics.pipeline.trend_loader import TrendLoader
from gui.charts.panels.chart_panel import ChartPanel
from gui.storage_bridge.storage_loop import StorageLoop
from models.storage.pages.item_query import ItemQuery
from models.trends.chart_axes import ChartAxes
from models.trends.matrix.metric_matrix import MetricMatrix
from models.trends.trend_result import TrendResult
from storage.exception import StorageError


class StoredChartController(QObject):
    """Feed a chart panel with the stored data: read in the storage thread when its axes or filters change.

    Attributes:
        DELAY_MS (ClassVar[int]): How long the axes and filters must stay unchanged before the data is read.
        panel (ChartPanel): The chart panel.
        loop (StorageLoop): The storage thread of the GUI.
        trends (TrendLoader): The loader of the series.
        matrices (MatrixLoader): The loader of the matrix cells.
        query (ItemQuery): The filters of the tab, applied to the chart data.
        request (int): The number of the latest request: the results of the earlier ones are dropped.
        timer (QTimer): Delays the requests while the axes or filters change.
        logger (Logger): The controller logger.

    Notes:
        - The GUI thread never waits for the database: the requests are queued to the storage thread, and only the
          result of the latest one is drawn.
        - A result arriving after its chart was closed (e.g. the window) is dropped.
    """

    DELAY_MS: ClassVar[int] = 400

    def __init__(
        self, panel: ChartPanel, loop: StorageLoop, statistics_source: str, logger: Optional[Logger] = None
    ) -> None:
        """Initialize the controller, reading nothing until `refresh` or `set_query`.

        Args:
            panel (ChartPanel): The chart panel.
            loop (StorageLoop): The storage thread of the GUI.
            statistics_source (str): The market statistics source compared with the providers.
            logger (Optional[Logger]): The controller logger.
        """
        super().__init__(panel)
        self.logger = logger if logger else getLogger(__name__)
        self.panel, self.loop = panel, loop
        self.trends = TrendLoader(statistics_source, self.logger)
        self.matrices = MatrixLoader(self.logger)
        self.query = ItemQuery()
        self.request = 0
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(self.DELAY_MS)
        self.timer.timeout.connect(self._request)
        panel.axes_changed.connect(lambda axes: self.refresh())
        panel.retry_requested.connect(self._request)

    ############################
    # Internal Helpers Methods #
    ############################

    def _is_current(self, request: int) -> bool:
        """Tell whether the result of a request should be drawn.

        Args:
            request (int): The request number.

        Returns:
            bool: Whether it is the latest request and its chart is still open.
        """
        if sip.isdeleted(self.panel):
            self.logger.debug("Result of the request %d dropped: its chart was closed.", request)
            return False
        if request != self.request:
            self.logger.debug("Result of the request %d dropped: request %d is pending.", request, self.request)
            return False
        return True

    def _on_series(self, request: int, axes: ChartAxes, result: TrendResult) -> None:
        """Draw the series read by a request, unless a later request was made.

        Args:
            request (int): The request number.
            axes (ChartAxes): The axes of the request.
            result (TrendResult): The series.
        """
        if self._is_current(request):
            self.panel.show_result(axes, result)

    def _on_matrix(self, request: int, axes: ChartAxes, matrix: MetricMatrix) -> None:
        """Draw the cells read by a request, unless a later request was made.

        Args:
            request (int): The request number.
            axes (ChartAxes): The axes of the request.
            matrix (MetricMatrix): The cells.
        """
        if self._is_current(request):
            self.panel.show_matrix(axes, matrix)

    def _on_error(self, request: int, error: StorageError) -> None:
        """Show that a request failed, unless a later request was made.

        Args:
            request (int): The request number.
            error (StorageError): The error.
        """
        if self._is_current(request):
            self.logger.warning("The chart %s could not be read: %s", self.panel.key, error)
            self.panel.show_error(str(error))

    def _request(self) -> None:
        """Read the data of the chosen axes and filters in the storage thread."""
        if sip.isdeleted(self.panel):
            self.logger.debug("Chart data not read: its chart was closed.")
            return
        self.timer.stop()
        self.request += 1
        request, axes, query = self.request, self.panel.axes(), self.query
        self.panel.show_loading()
        self.logger.debug("Chart %s request %d: %s %s.", self.panel.key, request, axes.chart.value, axes.y.value)
        if axes.chart.is_matrix:
            self.loop.submit(
                lambda storage: self.matrices.load(storage, axes, query),
                lambda matrix: self._on_matrix(request, axes, matrix),
                lambda error: self._on_error(request, error),
            )
        else:
            self.loop.submit(
                lambda storage: self.trends.load(storage, axes, query),
                lambda result: self._on_series(request, axes, result),
                lambda error: self._on_error(request, error),
            )

    ############################
    # Publicly Exposed Methods #
    ############################

    def refresh(self) -> None:
        """Read the chart data again once the changes stop (the data was written, or the axes changed)."""
        self.logger.debug("Chart data to read again in %d ms.", self.DELAY_MS)
        self.timer.start()

    def set_query(self, query: ItemQuery) -> None:
        """Apply the filters of the tab to the chart, once they stop changing.

        Args:
            query (ItemQuery): The filters of the tab.
        """
        self.query = query.model_copy(update={"offset": 0, "with_total": False})
        self.logger.debug("Filters of the tab applied to the chart: %d providers.", len(self.query.providers))
        self.refresh()
