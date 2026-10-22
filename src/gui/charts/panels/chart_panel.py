from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, FrozenSet, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from analytics.series.axis_rules import AxisRules
from analytics.series.chart_presets import ChartPresets
from gui.charts.base.chart_zoom import ChartZoom
from gui.charts.base.metric_chart import ChartLine, MetricChart
from gui.charts.common.chart_exporter import ChartExporter
from gui.charts.common.chart_labels import ChartLabels
from gui.charts.panels.styling.chart_titles import ChartTitles
from gui.charts.panels.styling.series_styler import SeriesStyler
from gui.charts.picker.axis_picker import AxisPicker
from gui.charts.plots.facets.facet_grid import Facet, FacetGrid
from gui.charts.plots.matrix.heatmap_chart import HeatmapChart
from gui.charts.plots.matrix.mix_bar_chart import MixBarChart
from gui.charts.plots.series.metric_line_chart import MetricLineChart
from gui.charts.plots.series.positioning_chart import PositioningChart
from gui.charts.plots.series.stacked_area_chart import StackedAreaChart
from gui.charts.sections.chart_state_store import ChartStateStore
from gui.theme import Theme
from models.storage.enums import DatasetKind
from models.trends.chart_axes import ChartAxes
from models.trends.enums import ChartKind, ChartPreset, ChartScope, MetricKind, PresetFamily
from models.trends.matrix.metric_matrix import MetricMatrix
from models.trends.trend_result import TrendResult


class ChartPanel(QWidget):
    """A configurable chart: its pickers, its chart (one per kind, stacked) and its footnote, with header tools.

    Attributes:
        WIDE_FACTOR (ClassVar[float]): How much wider than the view a widened chart is, at least.
        axes_changed (pyqtSignal): Emitted with the new `ChartAxes` when the user (or a ready-made chart) changes them.
        heading_changed (pyqtSignal): Emitted with the new title and subtitle of the chart.
        retry_requested (pyqtSignal): Emitted when the user asks to read the data again after an error.
        theme (Theme): The application theme.
        scope (ChartScope): Where the chart is shown.
        key (str): The chart key, remembering its axes.
        store (ChartStateStore): The store of the chart states.
        labels (ChartLabels): The names of the options.
        rules (AxisRules): The chart rules.
        presets (ChartPresets): The ready-made charts.
        titles (ChartTitles): The writer of the titles and footnotes.
        styler (SeriesStyler): The styler of the series.
        exporter (ChartExporter): The exporter of the pictures and data.
        default_preset (ChartPreset): The ready-made chart the reset shows.
        available (Optional[FrozenSet[DatasetKind]]): The stored datasets, `None` when unknown.
        picker (AxisPicker): The pickers.
        charts (Dict[ChartKind, MetricChart]): The chart of each kind of the scope.
        facets (FacetGrid): The small charts of a chart split into facets (e.g. one per provider).
        stack (QStackedWidget): Shows the chart of the chosen kind.
        chart_area (QScrollArea): Scrolls the chart sideways once widened.
        footnote (QLabel): The caveats of the figures.
        tools (QWidget): The header tools: ready-made charts, export and reset.
        views_button (QToolButton): Lists the ready-made charts.
        zoom_buttons (List[QToolButton]): Zoom in, zoom out and show everything again (the shown chart, or every
            small chart of a split chart).
        wide_button (QToolButton): Widens the chart (every label in full, scrolling sideways), or fits it back.
        export_menu (QMenu): Saves or copies the chart picture and data.
        error (str): The latest read error, empty when the data was read.
        logger (Logger): The panel logger.

    Notes:
        - The panel draws the data it is given: in memory (statistics) or through a `StoredChartController`.
        - Results for other axes than the chosen ones (a slower earlier request) are ignored.
        - The chart is as tall as its legend or rows need, the page scrolling rather than the chart. Widened (the
          choice is remembered per chart), it is at least `WIDE_FACTOR` times as wide as the view (and as wide as its
          names need), and scrolls sideways. The small charts of a split chart grow and scroll sideways the same way.
    """

    WIDE_FACTOR: ClassVar[float] = 1.5

    axes_changed = pyqtSignal(object)
    heading_changed = pyqtSignal(str, str)
    retry_requested = pyqtSignal()

    def __init__(
        self,
        theme: Theme,
        scope: ChartScope,
        key: str,
        store: ChartStateStore,
        default_preset: Optional[ChartPreset] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Build the panel, showing the saved axes or the default ready-made chart.

        Args:
            theme (Theme): The application theme.
            scope (ChartScope): Where the chart is shown.
            key (str): The chart key, e.g. `marketplace/trends`.
            store (ChartStateStore): The store of the chart states.
            default_preset (Optional[ChartPreset]): The ready-made chart shown first, the scope default otherwise.
            logger (Optional[Logger]): The panel logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.theme, self.scope, self.key, self.store = theme, scope, key, store
        self.labels = ChartLabels(theme, self.logger)
        self.rules = AxisRules(self.logger)
        self.presets = ChartPresets(self.logger)
        self.titles = ChartTitles(self.labels, self.logger)
        self.styler = SeriesStyler(self.labels, self.logger)
        self.exporter = ChartExporter(self.logger)
        self.default_preset = default_preset or self.presets.DEFAULTS[scope]
        self.available: Optional[FrozenSet[DatasetKind]] = None
        self.error = ""
        self.picker = AxisPicker(self.labels, scope, self.logger)
        self.charts: Dict[ChartKind, MetricChart] = {}
        self.stack = QStackedWidget()
        for kind in self.rules.kinds(scope):
            chart = self._chart_of(kind)
            chart.customContextMenuRequested.connect(lambda position, shown=chart: self._show_menu(shown, position))
            self.charts[kind] = chart
            self.stack.addWidget(chart)
        self.facets = FacetGrid(theme, self.logger)
        self.facets.menu_requested.connect(self._show_menu)
        self.stack.addWidget(self.facets)
        self.chart_area = QScrollArea()
        self.chart_area.setWidget(self.stack)
        self.chart_area.setWidgetResizable(True)
        self.chart_area.setFrameShape(QFrame.Shape.NoFrame)
        self.chart_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.footnote = QLabel()
        self.footnote.setObjectName("footnote")
        self.footnote.setWordWrap(True)
        self.views_button = QToolButton()
        self.wide_button = self._tool("\u2922 Widen", "Widen the chart: every name in full, scroll sideways to read it")
        self.wide_button.setCheckable(True)
        self.wide_button.setChecked(store.expanded(f"{key}/wide", False))
        self.export_menu = QMenu()
        self.tools = self._build_tools()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.picker)
        layout.addWidget(self.chart_area, 1)
        layout.addWidget(self.footnote)
        self.picker.set_axes(self.store.axes(key) or self.presets.axes(self.default_preset))
        self.stack.setCurrentWidget(self._shown())
        self.picker.axes_changed.connect(self._on_axes)
        self.wide_button.toggled.connect(self.set_wide)
        self._fit()

    ############################
    # Internal Helpers Methods #
    ############################

    def _chart_of(self, kind: ChartKind) -> MetricChart:
        """Build the chart of a kind.

        Args:
            kind (ChartKind): The chart kind.

        Returns:
            MetricChart: The chart.
        """
        match kind:
            case ChartKind.AREA:
                return StackedAreaChart(self.theme, self.logger)
            case ChartKind.BUBBLE:
                return PositioningChart(self.theme, self.logger)
            case ChartKind.HEATMAP:
                return HeatmapChart(self.theme, self.logger)
            case ChartKind.MIX:
                return MixBarChart(self.theme, self.logger)
            case _:
                return MetricLineChart(self.theme, self.logger)

    def _tool(self, text: str, tip: str) -> QToolButton:
        """Build a header tool button.

        Args:
            text (str): The button text.
            tip (str): What the button does.

        Returns:
            QToolButton: The button.
        """
        button = QToolButton()
        button.setObjectName("chartTool")
        button.setText(text)
        button.setToolTip(tip)
        button.setAccessibleName(tip)
        return button

    def _chart(self) -> MetricChart:
        """Get the shown chart.

        Returns:
            MetricChart: The chart of the chosen kind.
        """
        return self.charts[self.picker.axes().chart]

    def _shown(self) -> QWidget:
        """Get the shown widget: the chart of the chosen kind, or its small charts when split into facets.

        Returns:
            QWidget: The chart or the facet grid.
        """
        return self.facets if self.picker.axes().facet_by is not None else self._chart()

    def _fit(self) -> None:
        """Size the shown chart (widened or not) and its area, the other charts taking no room."""
        shown = self._shown()
        wide = self.wide_button.isChecked()
        bar, viewport = self.chart_area.horizontalScrollBar(), self.chart_area.viewport()
        view_width = viewport.width() if viewport is not None else 0
        for chart in self.charts.values():
            if chart is shown:
                chart.set_wide(wide)
            else:
                chart.setMinimumSize(0, 0)
        self.facets.set_wide(wide and shown is self.facets)
        if shown is not self.facets:
            self.facets.setMinimumSize(0, 0)
        width = max(shown.minimumWidth(), round(view_width * self.WIDE_FACTOR)) if wide else 0
        shown.setMinimumWidth(width)
        self.stack.setMinimumWidth(width)
        scrolls = wide and width > view_width
        extra = bar.sizeHint().height() if bar is not None and scrolls else 0
        self.chart_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if wide else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.chart_area.setMinimumHeight(shown.minimumHeight() + extra)
        self.logger.debug("Chart %s fitted: %d px tall, wide %s.", self.key, shown.minimumHeight(), wide)

    def _on_axes(self, axes: ChartAxes) -> None:
        """Show the chart of new axes and report them.

        Args:
            axes (ChartAxes): The axes.
        """
        self.store.set_axes(self.key, axes)
        self.stack.setCurrentWidget(self.facets if axes.facet_by is not None else self.charts[axes.chart])
        self._fit()
        self.footnote.clear()
        self.heading_changed.emit(self.titles.title(axes), self.titles.subtitle(axes))
        self.axes_changed.emit(axes)

    def _apply(self, preset: ChartPreset) -> None:
        """Show a ready-made chart.

        Args:
            preset (ChartPreset): The ready-made chart.
        """
        self.logger.info("Ready-made chart %s shown in %s.", preset.value, self.key)
        self.picker.set_axes(self.presets.axes(preset))
        self._on_axes(self.picker.axes())

    def _zoomed_charts(self) -> List[MetricChart]:
        """Get the charts the zoom buttons act on.

        Returns:
            List[MetricChart]: The small charts of a split chart, the shown chart otherwise.
        """
        return list(self.facets.charts) if self.picker.axes().facet_by is not None else [self._chart()]

    def _zoom(self, factor: Optional[float]) -> None:
        """Zoom the shown chart around its middle, or show everything again.

        Args:
            factor (Optional[float]): The share of the span kept (below 1 zooms in), `None` to reset the zoom.
        """
        self.logger.debug("Zoom button of %s: %s.", self.key, factor if factor is not None else "reset")
        for chart in self._zoomed_charts():
            if factor is None:
                chart.zoom.reset()
            else:
                chart.zoom.zoom_center(factor)

    def _export_data(self) -> str:
        """Get the data of the shown chart as CSV.

        Returns:
            str: The series points or the matrix cells.
        """
        chart, axes = self._chart(), self.picker.axes()
        if axes.facet_by is not None:
            facet_grouping = axes.facet_by
            faceted_rows = [
                (f"{title.text()} · {label}", series)
                for title, small in zip(self.facets.titles, self.facets.charts, strict=True)
                for series, label, _, _ in small.lines
            ]
            self.logger.debug("Exporting %d faceted series by %s.", len(faceted_rows), facet_grouping.value)
            return self.exporter.series_csv(axes, faceted_rows)
        if chart.matrix is not None:
            matrix = chart.matrix
            rows = [(row, self.labels.series_label(axes.series_by, row)) for row in matrix.rows]
            columns = [(column, self.labels.series_label(axes.columns, column)) for column in matrix.columns]
            return self.exporter.matrix_csv(rows, columns, matrix)
        return self.exporter.series_csv(axes, [(label, series) for series, label, _, _ in chart.lines])

    def _file_name(self) -> str:
        """Name the exported files after the chart.

        Returns:
            str: The chart title, in lower case with dashes.
        """
        title = self.titles.title(self.picker.axes())
        return "".join(character if character.isalnum() else "-" for character in title.lower()).strip("-")

    def _build_tools(self) -> QWidget:
        """Build the header tools: the ready-made charts, the export menu and the reset.

        Returns:
            QWidget: The tools, to put in the header of the chart section.
        """
        views = QMenu(self)
        views.setToolTipsVisible(True)
        chosen = self.presets.for_scope(self.scope)
        for family in PresetFamily:
            presets = [preset for preset in chosen if self.presets.family(preset) is family]
            if presets:
                views.addSection(self.labels.FAMILY_LABELS[family])
            for preset in presets:
                action = views.addAction(self.labels.PRESET_LABELS[preset])
                if action is not None:
                    action.triggered.connect(lambda checked, picked=preset: self._apply(picked))
        self.views_button.setObjectName("chartTool")
        self.views_button.setText("Views ▾")
        self.views_button.setToolTip("Ready-made charts: competitive analysis, forecast and geopolitics")
        self.views_button.setAccessibleName("Ready-made charts")
        self.views_button.setMenu(views)
        self.views_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        for text, handler in (
            ("Save picture…", lambda: self.exporter.save_png(self._shown(), self._file_name())),
            ("Save data (CSV)…", lambda: self.exporter.save_csv(self._shown(), self._file_name(), self._export_data())),
            ("Copy picture", lambda: self.exporter.copy_image(self._shown())),
            ("Copy data", lambda: self.exporter.copy_text(self._export_data())),
        ):
            action = self.export_menu.addAction(text)
            if action is not None:
                action.triggered.connect(handler)
        export = self._tool("Export ▾", "Save or copy the chart picture or data")
        export.setMenu(self.export_menu)
        export.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.zoom_buttons = [
            self._tool("\uff0b", "Zoom in (or Ctrl + wheel, or drag a rectangle on the chart)"),
            self._tool("\uff0d", "Zoom out (or Ctrl + wheel)"),
            self._tool("\u27f2", "Show the whole chart again (or double-click it, or press Esc)"),
        ]
        for button, factor in zip(
            self.zoom_buttons, (ChartZoom.ZOOM_IN**2, 1 / ChartZoom.ZOOM_IN**2, None), strict=True
        ):
            button.clicked.connect(lambda checked, chosen=factor: self._zoom(chosen))
        reset = self._tool("Reset", "Show the default chart of this section again")
        reset.clicked.connect(lambda: self._apply(self.default_preset))
        tools = QWidget()
        row = QHBoxLayout(tools)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        for button in (*self.zoom_buttons, self.views_button, export, reset):
            row.addWidget(button)
        return tools

    def _show_menu(self, chart: MetricChart, position: QPoint) -> None:
        """Show the context menu of a chart: the export actions, and the retry after an error.

        Args:
            chart (MetricChart): The chart.
            position (QPoint): Where the menu was asked, in chart pixels.
        """
        menu = QMenu(self)
        for action in self.export_menu.actions():
            menu.addAction(action)
        if self.error:
            menu.addSeparator()
            retry = menu.addAction("Retry")
            if retry is not None:
                retry.triggered.connect(self.retry_requested.emit)
        menu.exec(chart.mapToGlobal(position))

    def _empty_message(self, axes: ChartAxes) -> str:
        """Explain why a chart has no data.

        Args:
            axes (ChartAxes): The chart axes.

        Returns:
            str: What to crawl first, or that nothing matches the axes and filters.
        """
        metrics = [axes.y, axes.x] + ([axes.size] if axes.size else [])
        datasets: List[DatasetKind] = []
        if axes.chart.is_matrix:
            datasets = [DatasetKind.MARKETPLACE]
        else:
            for metric in metrics:
                dataset = metric.source or self.scope.dataset
                if dataset is not None and (metric.kind is not MetricKind.TIME or metric.source is not None):
                    datasets.append(dataset)
        missing = [dataset for dataset in datasets if self.available is not None and dataset not in self.available]
        if missing:
            return self.labels.BLOCK_LABELS[self.rules.DATA_BLOCKS[missing[0]]]
        return "Nothing matches these axes and filters yet."

    def _show_facets(self, axes: ChartAxes, result: TrendResult, lines: List[ChartLine]) -> None:
        """Draw the small charts of a chart split into facets, the largest facet first.

        Args:
            axes (ChartAxes): The chart axes, with a facet grouping.
            result (TrendResult): The series, tagged with their facet.
            lines (List[ChartLine]): The styled series, in the order of the result.
        """
        facet_grouping = axes.facet_by
        if facet_grouping is None:
            return
        grouped: Dict[str, List[ChartLine]] = {}
        for line in lines:
            if line[0].facet is not None and line[0].points:
                grouped.setdefault(line[0].facet, []).append(line)
        facets: List[Facet] = [
            (self.labels.series_label(facet_grouping, facet), found) for facet, found in grouped.items()
        ]
        if facets:
            self.facets.set_facets(axes, facets, result.breaks, result.last_actual)
        else:
            self.facets.set_message(self._empty_message(axes))
        self.logger.debug("%d facets drawn in %s.", len(facets), self.key)

    ############################
    # Publicly Exposed Methods #
    ############################

    def axes(self) -> ChartAxes:
        """Get the chosen axes.

        Returns:
            ChartAxes: The axes.
        """
        return self.picker.axes()

    def chart(self) -> MetricChart:
        """Get the shown chart.

        Returns:
            MetricChart: The chart of the chosen kind.
        """
        return self._chart()

    def heading(self) -> Tuple[str, str]:
        """Get the title and subtitle of the chart.

        Returns:
            Tuple[str, str]: The title and the subtitle.
        """
        axes = self.picker.axes()
        return self.titles.title(axes), self.titles.subtitle(axes)

    def apply_preset(self, preset: ChartPreset) -> None:
        """Show a ready-made chart.

        Args:
            preset (ChartPreset): The ready-made chart.
        """
        self._apply(preset)

    def set_available(self, available: Optional[FrozenSet[DatasetKind]]) -> None:
        """Tell which datasets are stored, blocking the options needing the others.

        Args:
            available (Optional[FrozenSet[DatasetKind]]): The stored datasets, `None` when unknown.
        """
        changed = available != self.available
        self.available = available
        self.picker.set_available(available)
        if changed:
            self._on_axes(self.picker.axes())

    def show_loading(self) -> None:
        """Show that the chart data is being read."""
        if self.picker.axes().facet_by is not None:
            self.facets.set_loading(True)
            return
        self._chart().set_loading(True)

    def show_result(self, axes: ChartAxes, result: TrendResult) -> None:
        """Draw the series of a chart.

        Args:
            axes (ChartAxes): The axes the series were read for (ignored when they are no longer chosen).
            result (TrendResult): The series.
        """
        if axes != self.picker.axes():
            self.logger.debug("Series of former axes ignored in %s.", self.key)
            return
        self.error = ""
        chart = self.charts[axes.chart]
        lines = self.styler.lines(axes, result.series)
        if axes.facet_by is not None:
            self._show_facets(axes, result, lines)
        elif any(series.points for series, _, _, _ in lines):
            chart.set_lines(axes, lines, result.breaks, result.last_actual, result.as_of)
        else:
            chart.set_message(self._empty_message(axes))
        self._fit()
        self.footnote.setText(self.titles.footnote(result.notes))
        self.footnote.setVisible(bool(result.notes))
        self.heading_changed.emit(self.titles.title(axes), self.titles.subtitle(axes, result=result))

    def show_matrix(self, axes: ChartAxes, matrix: MetricMatrix) -> None:
        """Draw the cells of a matrix chart.

        Args:
            axes (ChartAxes): The axes the cells were read for (ignored when they are no longer chosen).
            matrix (MetricMatrix): The cells.
        """
        if axes != self.picker.axes():
            self.logger.debug("Cells of former axes ignored in %s.", self.key)
            return
        self.error = ""
        chart = self.charts[axes.chart]
        if matrix.rows and matrix.columns:
            chart.set_matrix(axes, matrix)
        else:
            chart.set_message(self._empty_message(axes))
        self._fit()
        self.footnote.setText(self.titles.footnote(matrix.notes))
        self.footnote.setVisible(bool(matrix.notes))
        self.heading_changed.emit(self.titles.title(axes), self.titles.subtitle(axes, matrix=matrix))

    def set_wide(self, wide: bool) -> None:
        """Widen the chart (every name in full, scrolling sideways), or fit it to the view, and remember it.

        Args:
            wide (bool): Whether the chart is widened.
        """
        self.logger.info("Chart %s %s.", self.key, "widened" if wide else "fitted to the view")
        self.store.set_expanded(f"{self.key}/wide", wide)
        if self.wide_button.isChecked() != wide:
            self.wide_button.setChecked(wide)
        self._fit()

    def show_error(self, message: str) -> None:
        """Show that the chart data could not be read.

        Args:
            message (str): Why the data could not be read.
        """
        self.error = message
        text = f"The chart data could not be read: {message}\nRight-click to retry."
        if self.picker.axes().facet_by is not None:
            self.facets.set_message(text)
            return
        self._chart().set_message(text)

    def resizeEvent(self, event: Optional[QResizeEvent]) -> None:
        """Keep a widened chart wider than the view after a resize (Qt override).

        Args:
            event (Optional[QResizeEvent]): The resize event.
        """
        super().resizeEvent(event)
        if self.wide_button.isChecked():
            self._fit()
