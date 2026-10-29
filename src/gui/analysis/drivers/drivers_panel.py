from __future__ import annotations

# Standard Library Imports.
import asyncio
import csv
import math
from datetime import UTC, datetime
from functools import partial
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
import numpy
from PyQt6 import sip
from PyQt6.QtCore import QItemSelectionModel, Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from analytics.drivers.catalog.driver_help_loader import DriverHelpLoader
from analytics.drivers.catalog.metric_catalog_loader import MetricCatalogLoader
from analytics.drivers.driver_analysis import DriverAnalysis
from analytics.drivers.exception import DriverHelpFileError, MetricCatalogFileError
from analytics.drivers.matrix.driver_matrix import DriverMatrix
from gui.analysis.drivers.charts.driver_bar_chart import DriverBar, DriverBarChart
from gui.analysis.drivers.charts.driver_scatter_chart import DriverPoint
from gui.analysis.drivers.charts.driver_scatter_grid import DriverScatterGrid, ScatterPanel
from gui.analysis.drivers.controls.driver_controls import DriverControls
from gui.analysis.drivers.controls.role_legend import RoleLegend
from gui.analysis.drivers.metrics.metrics_table import MetricsTable
from gui.analysis.drivers.notes.column_guide import ColumnGuide
from gui.analysis.drivers.notes.criterion_tooltip import CriterionTooltip
from gui.analysis.drivers.notes.warning_board import WarningBoard
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.drivers.enums import DriverColumn, DriverRole, DriverScope, MetricScale, ProviderMetric
from models.drivers.help.driver_help import DriverHelp
from models.drivers.metrics.metric_catalog import MetricCatalog
from models.drivers.metrics.metric_coverage import MetricCoverage
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from models.drivers.query.driver_query import DriverQuery
from models.drivers.results.driver_result import DriverResult
from storage.exception import StorageError
from storage.storage import Storage

type DriverOutcome = Tuple[DriverResult, DriverMatrix]


class DriversPanel(QWidget):
    """The "Rise drivers" analysis: which criteria are predominant in the rise of the providers.

    Attributes:
        SIGNIFICANT (ClassVar[float]): The q-value below which a correlation is called significant.
        EMPTY_TABLE_HEIGHT (ClassVar[int]): The height of the table before a run, in pixels.
        MAX_TABLE_ROWS (ClassVar[int]): The rows the table shows before it scrolls (it fits its rows otherwise).
        GUIDE_WIDTH (ClassVar[int]): The narrowest the guide of the columns gets, right of the table.
        COLUMNS (ClassVar[Tuple[DriverColumn, ...]]): The columns of the table of the criteria.
        theme (Theme): The application theme.
        loop (StorageLoop): The storage thread of the GUI.
        catalog (MetricCatalog): The definitions of the criteria and the targets.
        analysis (DriverAnalysis): The statistics.
        controls (DriverControls): The pickers.
        help (DriverHelp): The explanation of each role and each warning.
        tooltips (CriterionTooltip): Writes the tooltips of the criteria, the choices and the buttons.
        legend (RoleLegend): The role of each parameter picked, explained on hover.
        caveats (WarningBoard): The warnings of the last analysis, explained on hover.
        guide (ColumnGuide): What each column of the table shows, right of the table.
        summary (QLabel): The fit of the last analysis, or its progress.
        table (QTableWidget): Every figure of every criterion.
        correlation_chart (DriverBarChart): The correlation of each criterion with the target.
        importance_chart (DriverBarChart): The share of the explained variance of each criterion.
        scatters (DriverScatterGrid): The target against each criterion, a chart each, the most predominant first.
        scale_button (QToolButton): Switches the scatter between the logarithmic scale of the analysis and the
            natural values (checked: logarithmic).
        metrics_table (MetricsTable): Every stored provider metric with its source (a card of its own).
        measures (List[ProviderMetricValue]): The measures the last run read, shown in the table of the metrics.
        stale (bool): Whether the provider metrics must be computed again before the next run.
        generation (int): The number of the last run (a late answer of an older run is dropped).
        outcome (Optional[DriverOutcome]): The last result and its observations.
        logger (Logger): The panel logger.

    Notes:
        A run computes the provider metrics again when a dataset was written since the last one
        (`Storage.refresh_metrics`), reads them, and runs the statistics off the GUI thread. The method and its traps
        are explained in `docs/analysis/rise-drivers.md`.
    """

    SIGNIFICANT: ClassVar[float] = 0.05
    EMPTY_TABLE_HEIGHT: ClassVar[int] = 60
    MAX_TABLE_ROWS: ClassVar[int] = 12
    GUIDE_WIDTH: ClassVar[int] = 280
    COLUMNS: ClassVar[Tuple[DriverColumn, ...]] = (
        DriverColumn.CRITERION,
        DriverColumn.IMPORTANCE,
        DriverColumn.BETA,
        DriverColumn.BETA_INTERVAL,
        DriverColumn.BETA_P,
        DriverColumn.RHO,
        DriverColumn.RHO_Q,
        DriverColumn.PARTIAL,
        DriverColumn.OBSERVATIONS,
        DriverColumn.GRANGER,
    )

    def __init__(
        self, theme: Theme, loop: StorageLoop, catalog: Optional[MetricCatalog] = None, logger: Optional[Logger] = None
    ) -> None:
        """Build the panel, running nothing until asked.

        Args:
            theme (Theme): The application theme.
            loop (StorageLoop): The storage thread of the GUI.
            catalog (Optional[MetricCatalog]): The definitions, read from `conf/metrics/metrics.yaml` by default.
            logger (Optional[Logger]): The panel logger.
        """
        super().__init__()
        self.theme, self.loop = theme, loop
        self.logger = logger if logger else getLogger(__name__)
        message = ""
        if catalog is None:
            try:
                catalog = MetricCatalogLoader(self.logger).load()
            except MetricCatalogFileError as e:
                self.logger.error("The rise drivers cannot be analysed: %s", e.message)
                catalog, message = MetricCatalog(definitions=[]), e.message
        try:
            self.help = DriverHelpLoader(self.logger).load()
        except DriverHelpFileError as e:
            self.logger.error("The rise drivers are not explained: %s", e.message)
            self.help, message = DriverHelp(), message or e.message
        self.catalog = catalog
        self.analysis = DriverAnalysis(catalog, self.logger)
        self.tooltips = CriterionTooltip(theme, catalog, self.help, self.logger)
        self.controls = DriverControls(catalog, self.logger, self.tooltips)
        self.legend = RoleLegend(theme, self.help, self.logger)
        self.caveats = WarningBoard(theme, self.help, catalog, self.logger)
        if message:
            self.caveats.show_error(message)
        self.summary = QLabel("Pick a target and criteria, then Run.")
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        self.guide = ColumnGuide(theme, self.help, self.COLUMNS, self.logger)
        self.guide.setMinimumWidth(self.GUIDE_WIDTH)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([self.guide.title(column) for column in self.COLUMNS])
        for position, column in enumerate(self.COLUMNS):
            item = self.table.horizontalHeaderItem(position)
            if item is not None:
                item.setToolTip(self.guide.tooltip(column))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)  # type: ignore[union-attr]
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)  # type: ignore[union-attr]
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setFixedHeight(self.EMPTY_TABLE_HEIGHT)
        self.correlation_chart = DriverBarChart(theme, symmetric=True, logger=self.logger)
        self.importance_chart = DriverBarChart(theme, symmetric=False, logger=self.logger)
        self.scatters = DriverScatterGrid(theme, self.logger)
        self.scale_button = QToolButton()
        self.scale_button.setText("Log scale")
        self.scale_button.setObjectName("segment")
        self.scale_button.setCheckable(True)
        self.scale_button.setChecked(True)
        self.scale_button.setToolTip(
            "Checked: the logarithms the analysis works on (the counts and amounts). Unchecked: the natural values "
            "(and in a panel the yearly change in percent)."
        )
        self.metrics_table = MetricsTable(theme, catalog, self.help, self.logger)
        self.measures: List[ProviderMetricValue] = []
        self.stale = True
        self.generation = 0
        self.outcome: Optional[DriverOutcome] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.controls)
        layout.addWidget(self.legend)
        layout.addWidget(self.caveats)
        layout.addWidget(self.summary)
        figures = QHBoxLayout()
        figures.setSpacing(10)
        figures.addWidget(self.table, 0, Qt.AlignmentFlag.AlignTop)
        figures.addWidget(self.guide, 1, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(figures)
        layout.addStretch(1)
        self._fit_width()
        self.controls.run_requested.connect(self.run)
        self.controls.export_requested.connect(self.export)
        self.scale_button.toggled.connect(self._on_scale)
        self.controls.changed.connect(self._on_selection)
        self.legend.role_clicked.connect(self._on_role)
        self.caveats.subjects_picked.connect(self._on_subjects)
        self.guide.column_picked.connect(self._on_column)
        self._on_selection()
        self.logger.debug("Rise drivers panel built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _label(self, metric: ProviderMetric) -> str:
        """Get the display name of a metric.

        Args:
            metric (ProviderMetric): The metric.

        Returns:
            str: Its label.
        """
        return self.catalog.label(metric)

    def _figure(self, value: Optional[float], pattern: str = "{:.2f}") -> str:
        """Write a figure.

        Args:
            value (Optional[float]): The figure.
            pattern (str): Its format.

        Returns:
            str: The figure written, `-` when missing.
        """
        return pattern.format(value) if value is not None and math.isfinite(value) else "-"

    def _stars(self, q_value: float) -> str:
        """Mark the significance of a correlation.

        Args:
            q_value (float): Its q-value.

        Returns:
            str: `**` below 1%, `*` below 5%, nothing otherwise.
        """
        return "**" if q_value < 0.01 else "*" if q_value < self.SIGNIFICANT else ""

    async def _compute(self, query: DriverQuery, refresh: bool, storage: Storage) -> DriverOutcome:
        """Read the provider metrics (computed again if stale) and run the statistics, in the storage thread.

        Args:
            query (DriverQuery): The analysis.
            refresh (bool): Whether to compute the provider metrics again first.
            storage (Storage): The open storage.

        Returns:
            DriverOutcome: The result and its observations.
        """
        self.logger.debug("Computing the rise drivers of %s (refresh %s).", query.target.value, refresh)
        if refresh:
            written = await storage.refresh_metrics(datetime.now(UTC))
            self.logger.info("Provider metrics computed again: %d measures.", written)
        values = await storage.metrics.list()
        self.measures = values
        if not values:
            self.logger.warning("No provider metric stored: the rise drivers of %s have no data.", query.target.value)
        result = await asyncio.to_thread(self.analysis.run, query, values)
        matrix = await asyncio.to_thread(self.analysis.panel.build, query, values)
        self.logger.info(
            "Rise drivers of %s computed from %d measures: %d observations.",
            query.target.value,
            len(values),
            result.observations,
        )
        return result, matrix

    async def _read_coverage(self, storage: Storage) -> List[MetricCoverage]:
        """Read what the stored measures of each criterion cover, in the storage thread.

        Args:
            storage (Storage): The open storage.

        Returns:
            List[MetricCoverage]: One entry per stored criterion.
        """
        self.logger.debug("Reading the coverage of the criteria.")
        coverage = await storage.metrics.coverage()
        self.logger.debug("Coverage of %d criteria read.", len(coverage))
        return coverage

    def _on_coverage(self, coverage: List[MetricCoverage]) -> None:
        """Write the coverage into the tooltips (GUI thread).

        Args:
            coverage (List[MetricCoverage]): One entry per stored criterion.
        """
        if sip.isdeleted(self):
            self.logger.debug("Rise drivers panel closed: coverage of %d criteria dropped.", len(coverage))
            return
        self.tooltips.set_coverage(coverage)
        self.controls.refresh_tooltips()
        self.logger.info("Tooltips of the Rise drivers updated with the coverage of %d criteria.", len(coverage))

    def _on_coverage_error(self, error: StorageError) -> None:
        """Keep the tooltips without coverage when it cannot be read (the analysis itself is not affected).

        Args:
            error (StorageError): The error.
        """
        self.logger.warning("The coverage of the criteria cannot be read for the tooltips: %s", error)

    def _load_coverage(self) -> None:
        """Read the coverage of the criteria (storage thread), then write it into the tooltips."""
        self.logger.debug("Asking for the coverage of the criteria.")
        self.loop.submit(self._read_coverage, self._on_coverage, self._on_coverage_error)

    async def _read_metrics(self, storage: Storage) -> List[ProviderMetricValue]:
        """Read every stored provider metric for the table of the metrics, in the storage thread.

        Args:
            storage (Storage): The open storage.

        Returns:
            List[ProviderMetricValue]: The measures, by provider, quarter, metric and source.
        """
        self.logger.debug("Reading the stored provider metrics for their table.")
        values = await storage.metrics.list()
        self.logger.debug("%d stored provider metrics read for their table.", len(values))
        return values

    def _on_metrics(self, values: List[ProviderMetricValue]) -> None:
        """Show the stored provider metrics in their table (GUI thread).

        Args:
            values (List[ProviderMetricValue]): The measures.
        """
        if sip.isdeleted(self) or sip.isdeleted(self.metrics_table):
            self.logger.debug("Rise drivers panel closed: %d provider metrics dropped.", len(values))
            return
        self.metrics_table.load(values)
        self.logger.info("Table of the provider metrics refreshed: %d measures.", len(values))

    def _on_metrics_error(self, error: StorageError) -> None:
        """Report in the table of the metrics that they cannot be read.

        Args:
            error (StorageError): The error.
        """
        if sip.isdeleted(self) or sip.isdeleted(self.metrics_table):
            self.logger.warning("Rise drivers panel closed before the provider metrics error was shown: %s", error)
            return
        self.logger.warning("The stored provider metrics cannot be read for their table: %s", error)
        self.metrics_table.show_error(f"The provider metrics cannot be read: {error}")

    def _load_metrics(self) -> None:
        """Read every stored provider metric (storage thread), then show them in their table."""
        self.logger.debug("Asking for the stored provider metrics.")
        self.loop.submit(self._read_metrics, self._on_metrics, self._on_metrics_error)

    def _axis(self, metric: ProviderMetric, scope: DriverScope, logarithmic: bool) -> str:
        """Name an axis of the scatter by the values it shows.

        Args:
            metric (ProviderMetric): The metric.
            scope (DriverScope): The scope of the analysis.
            logarithmic (bool): Whether the scatter shows the logarithms of the analysis, or the natural values.

        Returns:
            str: Its label: `log` for the logarithms of the counts and amounts, `yearly change` in a panel, with its
                unit (% or points) on the natural scale.
        """
        definition = self.catalog.get(metric)
        logged = definition is not None and definition.scale in (MetricScale.COUNT, MetricScale.AMOUNT)
        name = self._label(metric)
        if logarithmic:
            value = f"log {name}" if logged else name
            return f"yearly change of {value}" if scope is DriverScope.PANEL else value
        if scope is DriverScope.PANEL:
            return f"yearly change of {name} ({'%' if logged else 'points'})"
        return name

    def _correlation_bars(self, result: DriverResult) -> List[DriverBar]:
        """Build the bars of the correlations.

        Args:
            result (DriverResult): The analysis.

        Returns:
            List[DriverBar]: A bar per criterion, the strongest first, coloured by its sign and significance.
        """
        bars: List[DriverBar] = []
        for cell in result.correlations:
            definition = self.catalog.get(cell.criterion)
            color = (
                self.theme.DRIVER_FAINT
                if cell.q_value >= self.SIGNIFICANT
                else self.theme.DRIVER_POSITIVE
                if cell.rho > 0
                else self.theme.DRIVER_NEGATIVE
            )
            tooltip = (
                f"<b>{self._label(cell.criterion)}</b><br>Spearman rho {cell.rho:+.2f}"
                f" (95% CI {self._figure(cell.low, '{:+.2f}')} to {self._figure(cell.high, '{:+.2f}')})<br>"
                f"p {cell.p_value:.3g}, q {cell.q_value:.3g} ({len(result.correlations)} criteria tested)<br>"
                f"Partial rho (controls held constant): {self._figure(cell.partial, '{:+.2f}')}<br>"
                f"{cell.observations} observations"
                + (f"<br>Granger p (it leads the target) {cell.granger_p:.3g}" if cell.granger_p is not None else "")
                + (f"<br><i>{definition.description}</i>" if definition and definition.description else "")
            )
            label = f"{self._label(cell.criterion)} {self._stars(cell.q_value)}".strip()
            bars.append((label, cell.rho, cell.low, cell.high, color, tooltip, cell.partial))
        self.logger.debug("%d correlation bars built.", len(bars))
        return bars

    def _importance_bars(self, result: DriverResult) -> List[DriverBar]:
        """Build the bars of the importances.

        Args:
            result (DriverResult): The analysis.

        Returns:
            List[DriverBar]: A bar per regressed criterion, the most important first.
        """
        explained = result.r2 or 0.0
        if explained <= 0 and result.coefficients:
            self.logger.warning("No explained variance: the %d importances are shown as 0%%.", len(result.coefficients))
        bars: List[DriverBar] = []
        for coefficient in result.coefficients:
            part = coefficient.importance / explained if explained > 0 else 0.0
            tooltip = (
                f"<b>{self._label(coefficient.criterion)}</b><br>Share of R² {coefficient.importance:.3f}"
                f" (95% CI {self._figure(coefficient.importance_low, '{:.3f}')} to "
                f"{self._figure(coefficient.importance_high, '{:.3f}')}), {part:.0%} of the explained variance<br>"
                f"β {coefficient.beta:+.2f} (95% CI {self._figure(coefficient.low, '{:+.2f}')} to "
                f"{self._figure(coefficient.high, '{:+.2f}')}), p {self._figure(coefficient.p_value, '{:.3g}')}"
                + (
                    f"<br>Granger p (it leads the target) {coefficient.granger_p:.3g}"
                    if coefficient.granger_p is not None
                    else ""
                )
            )
            bars.append(
                (
                    self._label(coefficient.criterion),
                    coefficient.importance,
                    coefficient.importance_low,
                    coefficient.importance_high,
                    self.theme.ACCENT,
                    tooltip,
                    None,
                )
            )
        self.logger.debug("%d importance bars built.", len(bars))
        return bars

    def _ranked(self, result: DriverResult, matrix: DriverMatrix) -> List[ProviderMetric]:
        """Order the criteria of the charts: by share of R², then by strength of correlation, then the others.

        Args:
            result (DriverResult): The analysis.
            matrix (DriverMatrix): Its observations.

        Returns:
            List[ProviderMetric]: Every criterion of the analysis, each once.
        """
        ranked = [coefficient.criterion for coefficient in result.coefficients]
        ranked += [cell.criterion for cell in result.correlations]
        ranked += list(matrix.criteria)
        ordered = [*dict.fromkeys(ranked)]
        self.logger.debug("%d criteria ranked for the charts.", len(ordered))
        return ordered

    def _points(
        self, result: DriverResult, matrix: DriverMatrix, criterion: ProviderMetric, logarithmic: bool
    ) -> List[DriverPoint]:
        """Get the dots of the target against a criterion.

        Args:
            result (DriverResult): The analysis.
            matrix (DriverMatrix): Its observations.
            criterion (ProviderMetric): The criterion.
            logarithmic (bool): Whether the dots keep the logarithms of the analysis, or the natural values.

        Returns:
            List[DriverPoint]: A dot per observation holding both.
        """
        if criterion not in matrix.criteria:
            self.logger.warning("The criterion %s has no observation in the matrix: no dot.", criterion.value)
            return []
        column = matrix.criteria.index(criterion)
        rows = numpy.flatnonzero(numpy.isfinite(matrix.y) & numpy.isfinite(matrix.x[:, column]))
        points: List[DriverPoint] = []
        scope, natural = result.query.scope, self.analysis.panel.natural
        for row in rows:
            x, y = float(matrix.x[row, column]), float(matrix.y[row])
            if not logarithmic:
                shown_x, shown_y = natural(criterion, x, scope), natural(result.query.target, y, scope)
                if shown_x is None or shown_y is None:
                    continue
                x, y = shown_x, shown_y
            points.append((matrix.providers[row], matrix.periods[row], x, y))
        if len(points) < len(rows):
            self.logger.debug(
                "%d of the %d observations of %s have no natural value: not plotted.",
                len(rows) - len(points),
                len(rows),
                criterion.value,
            )
        self.logger.debug("%d dots of %s against the target.", len(points), criterion.value)
        return points

    def _weight(self, result: DriverResult, criterion: ProviderMetric) -> str:
        """Write the title of a criterion chart: its name and its weight.

        Args:
            result (DriverResult): The analysis.
            criterion (ProviderMetric): The criterion.

        Returns:
            str: E.g. `SDK GitHub stars · 60% of R²`, or its correlation when it was not regressed.
        """
        name = self._label(criterion)
        coefficient = next((entry for entry in result.coefficients if entry.criterion is criterion), None)
        if coefficient is not None and result.r2:
            return f"{name}  ·  {coefficient.importance / result.r2:.0%} of R²"
        cell = next((entry for entry in result.correlations if entry.criterion is criterion), None)
        if cell is not None:
            return f"{name}  ·  rho {cell.rho:+.2f}{self._stars(cell.q_value)}"
        return f"{name}  ·  not correlated"

    def _show_scatter(self, result: DriverResult, matrix: DriverMatrix) -> None:
        """Show the target against each criterion, the most predominant first, on the scale picked.

        Args:
            result (DriverResult): The analysis.
            matrix (DriverMatrix): Its observations.
        """
        logarithmic = self.scale_button.isChecked()
        scope = result.query.scope
        self.logger.debug("Showing the rise drivers scatter of %s.", result.query.target.value)
        panels: List[ScatterPanel] = [
            (
                self._weight(result, criterion),
                self._axis(criterion, scope, logarithmic),
                self._points(result, matrix, criterion, logarithmic),
            )
            for criterion in self._ranked(result, matrix)
        ]
        self.scatters.set_panels(
            panels,
            self._axis(result.query.target, scope, logarithmic),
            self.theme.driver_role_color(DriverRole.CRITERION),
            self.theme.driver_role_color(DriverRole.TARGET),
            f"No criterion to plot against {self._label(result.query.target)}.",
        )
        self.logger.debug("Rise drivers scatter shows %d criteria.", len(panels))

    def _fit_width(self) -> None:
        """Size the table to its columns, the guide taking the rest of the width."""
        self.table.resizeColumnsToContents()
        columns = sum(self.table.columnWidth(column) for column in range(self.table.columnCount()))
        scroll_bar = self.table.verticalScrollBar()
        extra = (
            scroll_bar.sizeHint().width()
            if scroll_bar is not None and self.table.rowCount() > self.MAX_TABLE_ROWS
            else 0
        )
        self.table.setFixedWidth(columns + extra + 2 * self.table.frameWidth() + 2)
        self.logger.debug("Rise drivers table fitted to %d pixels.", self.table.width())

    def _fill_table(self, result: DriverResult) -> None:
        """Write every figure of every criterion in the table.

        Args:
            result (DriverResult): The analysis.
        """
        coefficients = {coefficient.criterion: coefficient for coefficient in result.coefficients}
        cells = {cell.criterion: cell for cell in result.correlations}
        order = [*coefficients, *(criterion for criterion in cells if criterion not in coefficients)]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(order))
        for row, criterion in enumerate(order):
            coefficient, cell = coefficients.get(criterion), cells.get(criterion)
            texts = [
                self._label(criterion),
                self._figure(coefficient.importance if coefficient else None, "{:.3f}"),
                self._figure(coefficient.beta if coefficient else None, "{:+.2f}"),
                (
                    f"{self._figure(coefficient.low, '{:+.2f}')} to {self._figure(coefficient.high, '{:+.2f}')}"
                    if coefficient
                    else "-"
                ),
                self._figure(coefficient.p_value if coefficient else None, "{:.3g}"),
                self._figure(cell.rho if cell else None, "{:+.2f}") + (self._stars(cell.q_value) if cell else ""),
                self._figure(cell.q_value if cell else None, "{:.3g}"),
                self._figure(cell.partial if cell else None, "{:+.2f}"),
                str(cell.observations) if cell else "-",
                self._figure(cell.granger_p if cell else coefficient.granger_p if coefficient else None, "{:.3g}"),
            ]
            for column, text in enumerate(texts):
                item = QTableWidgetItem(text)
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, item)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        rows = min(len(order), self.MAX_TABLE_ROWS)
        height = (header.height() if header else 24) + sum(self.table.rowHeight(row) for row in range(rows))
        self.table.setFixedHeight(height + 2 * self.table.frameWidth() + 2)
        self._fit_width()
        self.logger.debug("Rise drivers table filled: %d criteria, %d regressed.", len(order), len(coefficients))

    def _show(self, result: DriverResult, matrix: DriverMatrix) -> None:
        """Show a result in the charts, the table, the summary and the caveats.

        Args:
            result (DriverResult): The analysis.
            matrix (DriverMatrix): Its observations.
        """
        target = self._label(result.query.target)
        self.logger.debug(
            "Showing the rise drivers of %s: %d correlations, %d coefficients, %d warnings.",
            result.query.target.value,
            len(result.correlations),
            len(result.coefficients),
            len(result.warnings),
        )
        if result.r2 is None:
            self.logger.warning("No regression for the rise drivers of %s.", result.query.target.value)
        self.correlation_chart.set_bars(
            self._correlation_bars(result), 1.0, f"No criterion can be correlated with {target}."
        )
        self.importance_chart.set_bars(
            self._importance_bars(result), message="No regression: see the warnings (too few observations?)."
        )
        self._show_scatter(result, matrix)
        self._fill_table(result)
        fit = (
            f"R² {result.r2:.2f}, leave-one-out R² {self._figure(result.loo_r2)}."
            if result.r2 is not None
            else "No regression."
        )
        leader = (
            f" Predominant: {self._label(result.coefficients[0].criterion)}"
            f" ({result.coefficients[0].importance / result.r2:.0%} of the explained variance)."
            if result.coefficients and result.r2
            else ""
        )
        self.summary.setText(
            f"{target}: {result.observations} observations of {result.providers} providers. {fit}{leader}"
        )
        self.caveats.show_warnings(result.warnings)
        self.controls.export_button.setEnabled(bool(len(matrix.y)))

    def _on_scale(self, logarithmic: bool) -> None:
        """Draw the scatter again on the scale picked, from the last result.

        Args:
            logarithmic (bool): Whether the logarithmic scale is picked.
        """
        self.logger.debug("Rise drivers scatter on the %s scale.", "logarithmic" if logarithmic else "natural")
        if self.outcome is not None:
            self._show_scatter(*self.outcome)

    def _on_outcome(self, generation: int, outcome: DriverOutcome) -> None:
        """Show the outcome of a run, unless a later run was started.

        Args:
            generation (int): The number of the run.
            outcome (DriverOutcome): Its result and observations.
        """
        if sip.isdeleted(self) or generation != self.generation:
            self.logger.debug("Outcome of the rise drivers run %d dropped (last run %d).", generation, self.generation)
            return
        self.stale = False
        self.outcome = outcome
        self.controls.run_button.setEnabled(True)
        self._show(*outcome)
        self.metrics_table.load(self.measures)
        self._load_coverage()
        self.logger.info("Rise drivers of %s shown.", outcome[0].query.target)

    def _on_selection(self) -> None:
        """Show the role of each parameter picked in the legend."""
        target, criteria, controls, scope, lag = self.controls.selection()
        self.legend.show_selection(self.catalog, target, criteria, controls, scope, lag)

    def _on_role(self, role: str) -> None:
        """Open the picker of a role clicked in the legend.

        Args:
            role (str): The role (its value).
        """
        self.logger.debug("Role %s picked in the legend.", role)
        self.controls.open_picker(DriverRole(role))

    def _on_column(self, index: int) -> None:
        """Select in the table the column of an entry clicked in the guide.

        Args:
            index (int): The column, -1 to clear the selection.
        """
        self.table.clearSelection()
        selection = self.table.selectionModel()
        if index >= 0 and selection is not None:
            flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Columns
            selection.select(self.table.model().index(0, index), flags)  # type: ignore[union-attr]
            self.logger.debug("Column %s selected from the guide.", self.COLUMNS[index].value)
        else:
            self.logger.debug("Column selection of the rise drivers table cleared.")

    def _on_subjects(self, subjects: List[str]) -> None:
        """Highlight in the table the criteria of a warning clicked on the board.

        Args:
            subjects (List[str]): The criteria (their values), none to stop highlighting.
        """
        names = {self._label(ProviderMetric(subject)) for subject in subjects}
        self.guide.set_active(None)
        self.table.clearSelection()
        selection = self.table.selectionModel()
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.text() in names and selection is not None:
                selection.select(self.table.model().index(row, 0), flags)  # type: ignore[union-attr]
                self.table.scrollToItem(item)
        self.logger.debug("%d criteria highlighted in the table.", len(names))

    def _on_error(self, error: StorageError) -> None:
        """Report a storage error.

        Args:
            error (StorageError): The error.
        """
        if sip.isdeleted(self):
            self.logger.warning("Rise drivers panel closed before its error was shown: %s", error)
            return
        self.logger.error("The rise drivers cannot be analysed: %s", error)
        self.controls.run_button.setEnabled(True)
        self.summary.setText("The analysis failed.")
        self.caveats.show_error(str(error))

    def _write_csv(self, path: Path, matrix: DriverMatrix) -> None:
        """Write the observations of an analysis as CSV.

        Args:
            path (Path): The file.
            matrix (DriverMatrix): The observations.
        """
        self.logger.debug("Writing %d observations to %s.", len(matrix.providers), path)
        names = [self._label(metric) for metric in (matrix.target, *matrix.criteria, *matrix.controls)]
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["provider", "period", *names])
            for row, provider in enumerate(matrix.providers):
                values = [matrix.y[row], *matrix.x[row], *matrix.z[row]]
                writer.writerow(
                    [
                        provider.value,
                        matrix.periods[row],
                        *(f"{value:.6g}" if math.isfinite(value) else "" for value in values),
                    ]
                )
        self.logger.info("%d observations exported to %s.", len(matrix.providers), path)

    ############################
    # Publicly Exposed Methods #
    ############################

    def run(self) -> None:
        """Run the analysis picked (the provider metrics computed again first when stale)."""
        query = self.controls.query()
        if query is None:
            self.logger.warning("No rise drivers analysis without a target and a criterion.")
            self.summary.setText("Pick a target and at least one criterion.")
            return
        self.generation += 1
        self.controls.run_button.setEnabled(False)
        self.summary.setText(
            "Computing the provider metrics and running the analysis..." if self.stale else "Running the analysis..."
        )
        self.logger.debug("Running the rise drivers of %s (generation %d).", query.target, self.generation)
        self.loop.submit(
            partial(self._compute, query, self.stale), partial(self._on_outcome, self.generation), self._on_error
        )

    def refresh(self) -> None:
        """Mark the provider metrics stale (a dataset was written): the next run computes them again.

        Notes:
            The coverage shown in the tooltips and the table of the provider metrics are read again at once: a
            markets crawl writes new criteria.
        """
        self.stale = True
        self._load_metrics()
        self._load_coverage()
        self.logger.debug("Provider metrics marked stale.")

    def export(self, path: Optional[Path] = None) -> Optional[Path]:
        """Save the observations of the last analysis as CSV.

        Args:
            path (Optional[Path]): The file, asked for when `None`.

        Returns:
            Optional[Path]: The file written, `None` without a result or when the dialog is cancelled.
        """
        if self.outcome is None:
            self.logger.warning("No rise drivers analysis to export yet.")
            return None
        if path is None:
            name, _ = QFileDialog.getSaveFileName(self, "Export the observations", "rise-drivers.csv", "CSV (*.csv)")
            if not name:
                self.logger.warning("Export of the rise drivers observations cancelled.")
                return None
            path = Path(name)
        try:
            self._write_csv(path, self.outcome[1])
        except OSError as e:
            self.logger.error("The observations cannot be exported to %s: %s", path, e.strerror)
            self.caveats.show_error(f"The observations cannot be exported to {path}: {e.strerror}")
            return None
        self.logger.info("Rise drivers observations of %s exported to %s.", self.outcome[0].query.target.value, path)
        return path
