from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Set, Tuple

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

# First Party Imports.
from gui.charts.base.metric_chart import ChartLine, MetricChart
from gui.charts.plots.series.metric_line_chart import MetricLineChart
from gui.charts.plots.series.stacked_area_chart import StackedAreaChart
from gui.layout.flow_layout import FlowLayout
from gui.theme import Theme
from models.trends.chart_axes import ChartAxes
from models.trends.enums import ChartKind

Facet = Tuple[str, List[ChartLine]]


class FacetGrid(QWidget):
    """Small multiples: one compact chart per facet (e.g. per provider), sharing the series, the axes and the zoom.

    Attributes:
        FACET_WIDTH (ClassVar[int]): The smallest width of a small chart: the grid has as many columns as fit.
        WIDE_FACTOR (ClassVar[int]): How much wider the small charts of a widened grid are.
        SPACING (ClassVar[int]): The space between two small charts, in pixels.
        menu_requested (pyqtSignal): Emitted with a small chart and the position of its context menu.
        theme (Theme): The application theme.
        kind (Optional[ChartKind]): The kind of the small charts, `None` before the first facets.
        charts (List[MetricChart]): The small charts, the largest facet first.
        titles (List[QLabel]): The title of each small chart (its facet).
        cards (List[QWidget]): The title and chart of each facet.
        legend (QWidget): The series shared by every small chart, with their colour.
        legend_layout (FlowLayout): Lays the legend entries out, wrapping.
        message (QLabel): Why there is no facet (empty or failed), shown instead of the grid.
        grid (QGridLayout): Lays the cards out in columns.
        columns (int): The number of columns of the latest layout.
        wide (bool): Whether the grid is widened: larger small charts, fewer per row, scrolling sideways.
        logger (Logger): The grid logger.

    Notes:
        - Every small chart draws the same series (same colours), so that the facets can be compared: one legend
          shows them for all.
        - Zooming the time axis of one small chart zooms every other one, their time axes being shared.
    """

    FACET_WIDTH: ClassVar[int] = 440
    WIDE_FACTOR: ClassVar[int] = 2
    SPACING: ClassVar[int] = 14

    menu_requested = pyqtSignal(object, object)

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build an empty grid.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The grid logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.theme = theme
        self.kind: Optional[ChartKind] = None
        self.charts: List[MetricChart] = []
        self.titles: List[QLabel] = []
        self.cards: List[QWidget] = []
        self.columns = 0
        self.wide = False
        self.legend = QWidget()
        self.legend_layout = FlowLayout(self.legend, gap=12, logger=self.logger)
        self.message = QLabel()
        self.message.setObjectName("muted")
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.message.setVisible(False)
        self.grid = QGridLayout()
        self.grid.setSpacing(self.SPACING)
        self.grid.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.legend)
        layout.addWidget(self.message)
        layout.addLayout(self.grid)
        layout.addStretch(1)
        self.logger.debug("Facet grid built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _share_x_window(self, source: MetricChart, window: Optional[Tuple[float, float]]) -> None:
        """Zoom the time axis of every small chart like the one the user zoomed.

        Args:
            source (MetricChart): The zoomed chart.
            window (Optional[Tuple[float, float]]): Its x window, `None` for the full range.
        """
        self.logger.debug("Facet x zoom shared: %s.", window)
        for chart in self.charts:
            if chart is not source:
                chart.zoom.set_x_window(window)

    def _chart_of(self, kind: ChartKind) -> MetricChart:
        """Build a small chart.

        Args:
            kind (ChartKind): The chart kind: areas, lines otherwise.

        Returns:
            MetricChart: The compact chart, its context menu and zoom wired to the grid.
        """
        chart: MetricChart = (
            StackedAreaChart(self.theme, self.logger)
            if kind is ChartKind.AREA
            else MetricLineChart(self.theme, self.logger)
        )
        chart.set_compact(True)
        chart.customContextMenuRequested.connect(
            lambda position, shown=chart: self.menu_requested.emit(shown, position)
        )
        chart.zoom.x_window_changed.connect(lambda window, source=chart: self._share_x_window(source, window))
        return chart

    def _clear(self) -> None:
        """Remove every small chart."""
        for card in self.cards:
            self.grid.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self.charts, self.titles, self.cards = [], [], []
        self.columns = 0
        self.logger.debug("Facet grid cleared.")

    def _ensure(self, kind: ChartKind, count: int) -> None:
        """Keep one small chart of a kind per facet, building or removing charts as needed.

        Args:
            kind (ChartKind): The chart kind.
            count (int): The number of facets.
        """
        if kind is not self.kind:
            self._clear()
            self.kind = kind
        while len(self.cards) > count:
            card = self.cards.pop()
            self.charts.pop()
            self.titles.pop()
            self.grid.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        while len(self.cards) < count:
            title = QLabel()
            title.setObjectName("chartSubtitle")
            chart = self._chart_of(kind)
            card = QWidget()
            column = QVBoxLayout(card)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(2)
            column.addWidget(title)
            column.addWidget(chart)
            self.titles.append(title)
            self.charts.append(chart)
            self.cards.append(card)
        self.columns = 0
        self.logger.debug("%d small %s charts kept.", count, kind.value)

    def _facet_width(self) -> int:
        """Get the smallest width of a small chart.

        Returns:
            int: `FACET_WIDTH`, `WIDE_FACTOR` times larger once widened, in pixels.
        """
        return self.FACET_WIDTH * (self.WIDE_FACTOR if self.wide else 1)

    def _needed_height(self) -> int:
        """Get the height fitting every small chart.

        Returns:
            int: The height of the legend and of the rows of small charts, in pixels.
        """
        if not self.cards:
            return MetricChart.COMPACT_HEIGHT
        columns = self.columns or max(1, min(self.width() // self._facet_width(), len(self.cards)))
        rows = -(-len(self.cards) // columns)
        card = MetricChart.COMPACT_HEIGHT + self.fontMetrics().height() + 8
        legend = self.legend.sizeHint().height() if self.legend.isVisible() else 0
        return legend + 10 + rows * card + (rows - 1) * self.SPACING

    def _relayout(self) -> None:
        """Lay the cards out in as many columns as fit the width (never more than cards), sharing the whole width."""
        columns = max(1, min(self.width() // self._facet_width(), len(self.cards)))
        if columns == self.columns:
            return
        self.columns = columns
        for card in self.cards:
            self.grid.removeWidget(card)
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns)
        for column in range(max(self.grid.columnCount(), columns)):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        self.setMinimumHeight(self._needed_height())
        self.logger.debug("Facet grid laid out in %d columns.", columns)

    def _fill_legend(self, lines: List[ChartLine]) -> None:
        """Show the series shared by the small charts, with their colour.

        Args:
            lines (List[ChartLine]): The series of the first facet carrying each label.
        """
        while (item := self.legend_layout.takeAt(0)) is not None:
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for _, label, color, _ in lines:
            entry = QLabel(f'<span style="color:{color.name()}">■</span> {label}')
            entry.setObjectName("muted")
            self.legend_layout.addWidget(entry)
        self.legend.setVisible(bool(lines))
        self.logger.debug("Facet legend of %d series.", len(lines))

    ############################
    # Publicly Exposed Methods #
    ############################

    def needed_height(self) -> int:
        """Get the height fitting every small chart.

        Returns:
            int: The height of the legend and of the rows of small charts, in pixels.
        """
        return self._needed_height()

    def set_facets(
        self,
        axes: ChartAxes,
        facets: List[Facet],
        breaks: Optional[List[float]] = None,
        last_actual: Optional[float] = None,
    ) -> None:
        """Show one small chart per facet.

        Args:
            axes (ChartAxes): The chart axes (a line or area chart).
            facets (List[Facet]): The title and series of each facet, the largest first.
            breaks (Optional[List[float]]): The x values of the methodology changes.
            last_actual (Optional[float]): The x value of the latest observation.
        """
        self._ensure(axes.chart, len(facets))
        legend: List[ChartLine] = []
        seen: Set[str] = set()
        for (title, lines), label, chart in zip(facets, self.titles, self.charts, strict=True):
            label.setText(title)
            chart.set_lines(axes, lines, breaks, last_actual)
            for line in lines:
                if line[1] not in seen:
                    seen.add(line[1])
                    legend.append(line)
        self._fill_legend(legend)
        self.message.setVisible(False)
        self._relayout()
        self.setMinimumHeight(self.needed_height())
        self.logger.debug("%d facets shown.", len(facets))

    def set_message(self, message: str) -> None:
        """Show why there is no facet, instead of the grid.

        Args:
            message (str): The explanation.
        """
        self._clear()
        self._fill_legend([])
        self.message.setText(message)
        self.message.setVisible(True)
        self.setMinimumHeight(MetricChart.COMPACT_HEIGHT)
        self.logger.debug("Facet grid message: %s", message)

    def set_wide(self, wide: bool) -> None:
        """Widen the small charts (fewer per row, the grid scrolling sideways), or fit them to the view again.

        Args:
            wide (bool): Whether the grid is widened.
        """
        if wide == self.wide:
            return
        self.wide = wide
        self.columns = 0
        self._relayout()
        self.logger.debug("Facet grid %s.", "widened" if wide else "fitted to the view")

    def set_loading(self, loading: bool) -> None:
        """Show (or stop showing) that new data is being read, on every small chart.

        Args:
            loading (bool): Whether the data is being read.
        """
        for chart in self.charts:
            chart.set_loading(loading)

    def resizeEvent(self, event: Optional[QResizeEvent]) -> None:
        """Lay the cards out again for the new width (Qt override).

        Args:
            event (Optional[QResizeEvent]): The resize event.
        """
        super().resizeEvent(event)
        self._relayout()
