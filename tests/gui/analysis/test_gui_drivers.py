from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock

import numpy
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from pytestqt.qtbot import QtBot

from analytics.drivers.catalog.metric_catalog_loader import MetricCatalogLoader
from analytics.drivers.driver_analysis import DriverAnalysis
from gui.analysis.analysis_view import AnalysisView
from gui.analysis.drivers.charts.driver_scatter_grid import DriverScatterGrid
from gui.analysis.drivers.controls.driver_controls import DriverControls
from gui.analysis.drivers.drivers_panel import DriversPanel
from gui.analysis.drivers.notes.help_chip import HelpChip
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.drivers.enums import (
    DriverRole,
    DriverScope,
    DriverWarningKind,
    MetricSource,
    ProviderMetric,
    WarningSeverity,
)
from models.drivers.metrics.metric_catalog import MetricCatalog
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from models.drivers.query.driver_query import DriverQuery
from storage.exception import StorageReadError
from storage.storage import Storage

PROVIDERS: List[CloudProvider] = list(CloudProvider)


@pytest.fixture(scope="module")
def catalog() -> MetricCatalog:
    return MetricCatalogLoader().load()


def planted(source: MetricSource = MetricSource.DERIVED) -> List[ProviderMetricValue]:
    """Revenue following the capital expenditure, the regions unrelated, for 30 providers."""
    generator = numpy.random.default_rng(9)
    values: List[ProviderMetricValue] = []
    for provider in PROVIDERS[:30]:
        capex = float(numpy.exp(generator.normal()))
        for metric, value in (
            (ProviderMetric.CAPEX, capex),
            (ProviderMetric.REGIONS, float(generator.integers(1, 40))),
            (ProviderMetric.REVENUE, capex**2 * float(numpy.exp(0.2 * generator.normal()))),
        ):
            values.append(
                ProviderMetricValue(provider=provider, period="2026Q2", metric=metric, value=value, source=source)
            )
    return values


def query() -> DriverQuery:
    return DriverQuery(
        target=ProviderMetric.REVENUE, criteria=[ProviderMetric.REGIONS, ProviderMetric.CAPEX], bootstrap=100
    )


class TestDriverControls:
    def test_the_defaults_and_the_query(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        controls = DriverControls(catalog)
        qtbot.addWidget(controls)

        built = controls.query()

        assert built is not None
        assert built.target is catalog.targets()[0].metric
        assert set(built.criteria) <= set(DriverControls.DEFAULT_CRITERIA)
        assert built.target not in built.criteria
        assert built.scope is DriverScope.CROSS_SECTION
        assert built.lag == 0
        assert not controls.lag_box.isEnabled()
        assert controls.criteria_button.text() == f"Criteria ({len(built.criteria)}) ▾"

    def test_the_target_is_never_a_criterion(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        controls = DriverControls(catalog)
        qtbot.addWidget(controls)

        controls.target_box.setCurrentIndex(controls.target_box.findData(ProviderMetric.PRODUCTS.value))

        built = controls.query()
        assert built is not None
        assert ProviderMetric.PRODUCTS not in built.criteria
        disabled = [
            str(action.data()) for action in controls._actions(controls.criteria_button) if not action.isEnabled()
        ]
        assert disabled == [ProviderMetric.PRODUCTS.value]

    def test_a_panel_takes_the_lag_and_the_controls(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        controls = DriverControls(catalog)
        qtbot.addWidget(controls)
        controls.scope_box.setCurrentIndex(1)
        controls.lag_box.setValue(3)
        controls.set_checked([ProviderMetric.CAPEX], [ProviderMetric.PRODUCTS])

        built = controls.query()

        assert built is not None
        assert built.scope is DriverScope.PANEL
        assert built.lag == 3
        assert built.criteria == [ProviderMetric.CAPEX]
        assert built.controls == [ProviderMetric.PRODUCTS]

    def test_no_criterion_disables_the_run(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        controls = DriverControls(catalog)
        qtbot.addWidget(controls)

        controls.set_checked([])

        assert controls.query() is None
        assert not controls.run_button.isEnabled()

    def test_the_criteria_are_capped(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        controls = DriverControls(catalog)
        qtbot.addWidget(controls)
        actions = controls._actions(controls.controls_button)

        for action in actions[:6]:
            action.setChecked(True)
            controls._on_control(action)

        assert len(controls._checked(controls.controls_button)) == DriverControls.MAX_CONTROLS


class TestDriversPanel:
    def test_a_run_is_submitted_then_shown(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        loop = MagicMock()
        panel = DriversPanel(Theme(), loop, catalog)
        qtbot.addWidget(panel)
        panel.controls.set_checked([ProviderMetric.REGIONS, ProviderMetric.CAPEX])
        panel.controls.target_box.setCurrentIndex(panel.controls.target_box.findData(ProviderMetric.REVENUE.value))

        panel.controls.run_button.click()

        assert loop.submit.call_count == 1
        assert not panel.controls.run_button.isEnabled()
        job, on_done, _ = loop.submit.call_args.args
        storage = MagicMock()
        storage.refresh_metrics = AsyncMock(return_value=90)
        storage.metrics.read = AsyncMock(return_value=planted())
        outcome = asyncio.run(job(storage))
        storage.refresh_metrics.assert_awaited_once()
        on_done(outcome)

        result, _ = outcome
        assert not panel.stale
        assert result.coefficients[0].criterion is ProviderMetric.CAPEX
        assert next(bar[0] for bar in panel.importance_chart.bars) == "Capital expenditure"
        assert len(panel.correlation_chart.bars) == 2
        assert panel.correlation_chart.bars[0][0].endswith("**")
        assert len(panel.scatters.charts[0].points) == 30
        assert panel.table.rowCount() == 2
        assert f"Predominant: {catalog.label(ProviderMetric.CAPEX)}" in panel.summary.text()
        assert panel.controls.export_button.isEnabled()
        assert panel.controls.run_button.isEnabled()

    def test_the_scatter_switches_between_log_and_natural_scale(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)
        analysis = DriverAnalysis(catalog)
        values = planted()
        panel._on_outcome(0, (analysis.run(query(), values), analysis.panel.build(query(), values)))
        capex = {value.provider: value.value for value in values if value.metric is ProviderMetric.CAPEX}
        assert panel.scale_button.isChecked()
        logged = {provider: x for provider, _, x, _ in panel.scatters.charts[0].points}
        assert panel.scatters.charts[0].x_label == f"log {catalog.label(ProviderMetric.CAPEX)}"

        panel.scale_button.setChecked(False)

        natural = {provider: x for provider, _, x, _ in panel.scatters.charts[0].points}
        assert natural == pytest.approx(capex)
        assert logged != pytest.approx(capex)
        assert panel.scatters.charts[0].x_label == catalog.label(ProviderMetric.CAPEX)
        assert panel.scatters.charts[0].y_label == catalog.label(ProviderMetric.REVENUE)
        panel.scale_button.setChecked(True)
        assert {provider: x for provider, _, x, _ in panel.scatters.charts[0].points} == pytest.approx(logged)

    def test_the_scale_without_a_result_does_nothing(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)

        panel.scale_button.setChecked(False)

        assert panel.scatters.charts == []
        assert not panel.scatters.message.isHidden()

    def test_a_late_answer_of_an_older_run_is_dropped(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)
        outcome = (
            DriverAnalysis(catalog).run(query(), planted()),
            DriverAnalysis(catalog).panel.build(query(), planted()),
        )
        panel.generation = 2

        panel._on_outcome(1, outcome)

        assert panel.outcome is None
        assert panel.table.rowCount() == 0

    def test_the_warnings_are_shown(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)
        few = [value for value in planted() if value.provider in PROVIDERS[:3]]
        analysis = DriverAnalysis(catalog)

        panel._on_outcome(0, (analysis.run(query(), few), analysis.panel.build(query(), few)))

        assert not panel.caveats.isHidden()
        kinds = [warning.kind for warning in panel.caveats.warnings]
        assert kinds[0] is DriverWarningKind.REGRESSION_SKIPPED, "the blocking warnings first"
        assert DriverWarningKind.FEW_PROVIDERS in kinds
        assert any("Only 3 providers" in chip.toolTip() for chip in panel.caveats.chips)
        assert panel.caveats.caption.text() == f"Caveats ({len(kinds)})"
        assert panel.importance_chart.bars == []
        assert "No regression" in panel.summary.text()

    def test_the_observations_are_exported(self, qtbot: QtBot, catalog: MetricCatalog, tmp_path: Path) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)
        assert panel.export(tmp_path / "none.csv") is None
        analysis = DriverAnalysis(catalog)
        panel._on_outcome(0, (analysis.run(query(), planted()), analysis.panel.build(query(), planted())))

        written = panel.export(tmp_path / "drivers.csv")

        assert written == tmp_path / "drivers.csv"
        with written.open(encoding="utf-8") as file:
            rows = list(csv.reader(file))
        assert rows[0] == [
            "provider",
            "period",
            *(
                catalog.label(metric)
                for metric in (ProviderMetric.REVENUE, ProviderMetric.REGIONS, ProviderMetric.CAPEX)
            ),
        ]
        assert len(rows) == 31
        assert rows[1][1] == "2026Q2"

    def test_refresh_marks_the_metrics_stale(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)
        panel.stale = False

        panel.refresh()

        assert panel.stale


class TestAnalysisViewDrivers:
    def test_the_driver_charts_can_be_widened(self, qtbot: QtBot, offline_loop: StorageLoop) -> None:
        view = AnalysisView(Theme(), offline_loop)
        qtbot.addWidget(view)

        keys = [section.key for section in view.driver_sections]

        assert keys == [
            "analysis/drivers/table",
            "analysis/drivers-correlations",
            "analysis/drivers-importance",
            "analysis/drivers-scatter",
        ]
        assert view.driver_sections[0].widen_button is None
        window = view.driver_sections[1].open_window()
        assert window is not None
        assert view.drivers.correlation_chart.window() is window
        window.close_button.click()
        assert view.drivers.correlation_chart.window() is not window
        view.refresh()
        assert view.drivers.stale
        assert view.driver_sections[3].tools is view.drivers.scale_button


@pytest.mark.db
class TestDriversOnTheDatabase:
    async def test_a_run_reads_the_stored_metrics(
        self, qtbot: QtBot, storage: Storage, gui_loop: StorageLoop, catalog: MetricCatalog
    ) -> None:
        await storage.metrics.upsert(planted(MetricSource.EDGAR))
        panel = DriversPanel(Theme(), gui_loop, catalog)
        qtbot.addWidget(panel)
        panel.controls.target_box.setCurrentIndex(panel.controls.target_box.findData(ProviderMetric.REVENUE.value))
        panel.controls.set_checked([ProviderMetric.REGIONS, ProviderMetric.CAPEX])

        panel.run()

        qtbot.waitUntil(lambda: panel.outcome is not None, timeout=20_000)
        assert panel.outcome is not None
        result, _ = panel.outcome
        assert result.observations == 30
        assert result.coefficients[0].criterion is ProviderMetric.CAPEX
        assert not panel.stale


class TestRoleLegend:
    def test_the_legend_follows_the_pickers(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)
        panel.controls.target_box.setCurrentIndex(panel.controls.target_box.findData(ProviderMetric.REVENUE.value))

        panel.controls.set_checked(
            [ProviderMetric.REGIONS, ProviderMetric.CAPEX, ProviderMetric.AGE], [ProviderMetric.PRODUCTS]
        )

        chips = panel.legend.chips
        assert list(chips) == [
            DriverRole.TARGET,
            DriverRole.CRITERION,
            DriverRole.CONTROL,
            DriverRole.SCOPE,
            DriverRole.LAG,
        ]
        assert chips[DriverRole.TARGET].value == catalog.label(ProviderMetric.REVENUE)
        assert chips[DriverRole.CRITERION].value.startswith("3 · ")
        assert chips[DriverRole.CRITERION].value.endswith(" +1")
        assert chips[DriverRole.CONTROL].value == f"1 · {catalog.label(ProviderMetric.PRODUCTS)}"
        assert chips[DriverRole.LAG].dimmed
        assert "Not used by the analysis picked" in chips[DriverRole.LAG].toolTip()
        assert catalog.label(ProviderMetric.AGE) in chips[DriverRole.CRITERION].toolTip()
        assert "Spearman" in chips[DriverRole.CRITERION].toolTip()

    def test_a_panel_uses_the_lag(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)

        panel.controls.scope_box.setCurrentIndex(1)
        panel.controls.lag_box.setValue(3)

        lag = panel.legend.chips[DriverRole.LAG]
        assert (lag.value, lag.dimmed) == ("3 quarters", False)
        assert panel.legend.chips[DriverRole.SCOPE].value == "every quarter (panel)"

    def test_clicking_a_chip_opens_its_picker(
        self, qtbot: QtBot, catalog: MetricCatalog, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)
        opened: List[DriverRole] = []
        monkeypatch.setattr(panel.controls, "open_picker", opened.append)

        for role in (DriverRole.CRITERION, DriverRole.LAG):
            chip = panel.legend.chips[role]
            qtbot.mouseClick(chip, Qt.MouseButton.LeftButton)

        assert opened == [DriverRole.CRITERION, DriverRole.LAG]

    def test_opening_the_lag_switches_to_a_panel(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)

        panel.controls.open_picker(DriverRole.LAG)

        assert panel.controls.selection()[3] is DriverScope.PANEL
        assert panel.controls.lag_box.isEnabled()


class TestWarningBoard:
    def test_clicking_a_warning_highlights_its_criteria(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)
        values = planted() + [
            ProviderMetricValue(provider=provider, period="2026Q2", metric=ProviderMetric.AGE, value=1.0 + index)
            for index, provider in enumerate(PROVIDERS[:5])
        ]
        three = DriverQuery(
            target=ProviderMetric.REVENUE,
            criteria=[ProviderMetric.REGIONS, ProviderMetric.CAPEX, ProviderMetric.AGE],
            bootstrap=0,
        )
        analysis = DriverAnalysis(catalog)
        panel._on_outcome(0, (analysis.run(three, values), analysis.panel.build(three, values)))
        index = next(
            position
            for position, warning in enumerate(panel.caveats.warnings)
            if warning.kind is DriverWarningKind.MISSING_VALUES
        )
        chip = panel.caveats.chips[index]

        qtbot.mouseClick(chip, Qt.MouseButton.LeftButton)

        picked = {panel.table.item(index.row(), 0).text() for index in panel.table.selectionModel().selectedRows()}  # type: ignore[union-attr]
        assert catalog.label(ProviderMetric.AGE) in picked
        assert chip.selected
        assert "What to do:" in chip.toolTip()
        qtbot.mouseClick(chip, Qt.MouseButton.LeftButton)
        assert not chip.selected
        assert panel.table.selectionModel().selectedRows() == []

    def test_no_caveat_is_said(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)
        assert panel.caveats.isHidden(), "nothing before a run"

        panel.caveats.show_warnings([])

        (chip,) = panel.caveats.chips
        assert chip.title == "No caveat"
        assert not panel.caveats.isHidden()

    def test_an_error_is_shown_as_blocking(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)

        panel._on_error(StorageReadError("provider metrics", "connection refused"))

        (chip,) = panel.caveats.chips
        assert chip.title == "Error"
        assert "connection refused" in chip.toolTip()
        assert chip.accent == Theme().warning_color(WarningSeverity.BLOCKING)


class TestHelpChip:
    def test_hover_click_and_size(self, qtbot: QtBot) -> None:
        chip = HelpChip(Theme(), Theme().driver_role_color(DriverRole.TARGET), "◎", "Target")
        qtbot.addWidget(chip)
        chip.set_content("Revenue", "<qt>Explained</qt>")
        chip.show()
        clicks: List[bool] = []
        chip.clicked.connect(lambda: clicks.append(True))

        qtbot.mouseClick(chip, Qt.MouseButton.LeftButton)
        chip.enterEvent(None)
        hovered = chip.hovered
        chip.leaveEvent(None)

        assert clicks == [True]
        assert hovered
        assert not chip.hovered
        assert chip.sizeHint().width() > chip.fontMetrics().horizontalAdvance("Target Revenue")
        assert chip.toolTip() == "<qt>Explained</qt>"
        assert not chip.grab().isNull()


class TestColumnGuide:
    def test_every_column_is_explained_right_of_the_table(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)

        guide = panel.guide

        assert len(guide.entries) == panel.table.columnCount() == len(DriversPanel.COLUMNS)
        header = panel.table.horizontalHeaderItem(1)
        assert header is not None
        assert header.text() == "Share of R²"
        assert "How to read it:" in header.toolTip()
        assert "Shapley" in guide.entries[1].text()
        assert "How to read it:" in guide.entries[1].toolTip()

    def test_clicking_an_entry_selects_its_column(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)
        analysis = DriverAnalysis(catalog)
        panel._on_outcome(0, (analysis.run(query(), planted()), analysis.panel.build(query(), planted())))
        panel.show()
        entry = panel.guide.entries[5]

        qtbot.mouseClick(entry, Qt.MouseButton.LeftButton)

        selection = panel.table.selectionModel()
        assert selection is not None
        assert {index.column() for index in selection.selectedIndexes()} == {5}
        assert len(selection.selectedIndexes()) == panel.table.rowCount()
        assert entry.property("active") is True
        qtbot.mouseClick(entry, Qt.MouseButton.LeftButton)
        assert selection.selectedIndexes() == []
        assert panel.guide.active is None

    def test_the_table_fits_its_columns(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)

        columns = sum(panel.table.columnWidth(column) for column in range(panel.table.columnCount()))

        assert columns <= panel.table.width() <= columns + 12


class TestScatterGrid:
    def test_one_chart_per_criterion_the_most_predominant_first(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        panel = DriversPanel(Theme(), MagicMock(), catalog)
        qtbot.addWidget(panel)
        analysis = DriverAnalysis(catalog)
        three = DriverQuery(
            target=ProviderMetric.REVENUE,
            criteria=[ProviderMetric.REGIONS, ProviderMetric.CAPEX, ProviderMetric.AGE],
            bootstrap=0,
        )

        panel._on_outcome(0, (analysis.run(three, planted()), analysis.panel.build(three, planted())))

        charts = panel.scatters.charts
        assert [chart.x_label for chart in charts] == [
            f"log {catalog.label(ProviderMetric.CAPEX)}",
            f"log {catalog.label(ProviderMetric.REGIONS)}",
            f"log {catalog.label(ProviderMetric.AGE)}",
        ]
        assert charts[0].title.startswith(catalog.label(ProviderMetric.CAPEX))
        assert charts[0].title.endswith("of R²")
        assert charts[2].points == []
        assert charts[2].title.endswith("not correlated")
        assert charts[0].y_range is not None
        assert {chart.y_range for chart in charts} == {charts[0].y_range}, "a shared target axis"

    def test_the_grid_flows_with_its_width(self, qtbot: QtBot) -> None:
        theme = Theme()
        grid = DriverScatterGrid(theme)
        qtbot.addWidget(grid)
        points = [(PROVIDERS[index], "2026Q2", float(index), float(index)) for index in range(5)]
        grid.set_panels(
            [(f"c{index}", f"c{index}", points) for index in range(5)], "target", QColor("blue"), QColor("red")
        )

        grid.show()
        grid.resize(800, 600)
        narrow = grid.columns
        grid.resize(1900, 600)

        assert narrow == 2
        assert grid.columns == 4
        layout = grid.grid
        assert layout.getItemPosition(layout.indexOf(grid.charts[4])) == (1, 0, 1, 1)
        grid.set_panels([], "target", QColor("blue"), QColor("red"), "Nothing to plot.")
        assert grid.charts == []
        assert grid.message.text() == "Nothing to plot."

    def test_the_charts_widen_together(self, qtbot: QtBot, offline_loop: StorageLoop, catalog: MetricCatalog) -> None:
        view = AnalysisView(Theme(), offline_loop)
        qtbot.addWidget(view)
        analysis = DriverAnalysis(catalog)
        view.drivers._on_outcome(0, (analysis.run(query(), planted()), analysis.panel.build(query(), planted())))
        section = view.driver_sections[3]

        window = section.open_window()

        assert window is not None
        assert section.body is view.drivers.scatters
        assert view.drivers.scatters.window() is window
        assert all(chart.window() is window for chart in view.drivers.scatters.charts)
        window.close_button.click()
        assert view.drivers.scatters.window() is not window
