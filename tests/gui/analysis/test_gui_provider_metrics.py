from __future__ import annotations

import asyncio
import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest
from PyQt6.QtCore import Qt, QUrl
from pytestqt.qtbot import QtBot

from analytics.drivers.catalog.driver_help_loader import DriverHelpLoader
from analytics.drivers.catalog.metric_catalog_loader import MetricCatalogLoader
from gui.analysis.drivers.drivers_panel import DriversPanel
from gui.analysis.drivers.metrics.metrics_model import MetricsModel
from gui.analysis.drivers.metrics.metrics_table import MetricsTable
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource, MetricValueColumn, ProviderMetric
from models.drivers.help.driver_help import DriverHelp
from models.drivers.metrics.metric_catalog import MetricCatalog
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from storage.exception import StorageReadError

AWS, AZURE, OVH = CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.OVH
FETCHED = datetime(2026, 10, 1, 8, 30, tzinfo=UTC)


@pytest.fixture(scope="module")
def catalog() -> MetricCatalog:
    return MetricCatalogLoader().load()


@pytest.fixture(scope="module")
def driver_help() -> DriverHelp:
    return DriverHelpLoader().load()


def measures() -> List[ProviderMetricValue]:
    return [
        ProviderMetricValue(
            provider=AWS,
            period="2026Q2",
            metric=ProviderMetric.CAPEX,
            value=31.25,
            source=MetricSource.EDGAR,
            source_url="https://www.sec.gov/amzn-10q",
            fetched_at=FETCHED,
        ),
        ProviderMetricValue(
            provider=AZURE, period="2026Q2", metric=ProviderMetric.REGIONS, value=64.0, source=MetricSource.WIKIDATA
        ),
        ProviderMetricValue(
            provider=OVH, period="2025Q4", metric=ProviderMetric.PRODUCTS, value=1234.0, fetched_at=FETCHED
        ),
        ProviderMetricValue(provider=AWS, period="2025Q4", metric=ProviderMetric.PRODUCTS, value=250.0),
    ]


def column(name: MetricValueColumn) -> int:
    return MetricsModel.COLUMNS.index(name)


def shown(table: MetricsTable, name: MetricValueColumn) -> List[str]:
    return [table.model.text(row, name) for row in range(table.model.rowCount())]


def build(qtbot: QtBot, catalog: MetricCatalog, driver_help: DriverHelp) -> MetricsTable:
    table = MetricsTable(Theme(), catalog, driver_help)
    qtbot.addWidget(table)
    table.load(measures())
    return table


class TestMetricsTable:
    def test_the_values_are_shown_with_their_units_and_sources(
        self, qtbot: QtBot, catalog: MetricCatalog, driver_help: DriverHelp
    ) -> None:
        table = build(qtbot, catalog, driver_help)

        assert table.count_label.text() == "4 values"
        assert table.model.rowCount() == 4
        assert table.model.columnCount() == len(MetricValueColumn)
        assert table.export_button.isEnabled()
        row = next(row for row in range(4) if table.model.values[row].metric is ProviderMetric.CAPEX)
        assert table.model.text(row, MetricValueColumn.PROVIDER) == Theme().provider_label(AWS)
        assert table.model.text(row, MetricValueColumn.METRIC) == catalog.label(ProviderMetric.CAPEX)
        assert table.model.text(row, MetricValueColumn.VALUE) == "31.25 USD bn"
        assert table.model.text(row, MetricValueColumn.SOURCE) == "edgar"
        assert table.model.text(row, MetricValueColumn.FETCHED) == "2026-10-01"
        assert table.model.text(row, MetricValueColumn.URL) == "https://www.sec.gov/amzn-10q"
        ovh = next(row for row in range(4) if table.model.values[row].provider is OVH)
        assert table.model.text(ovh, MetricValueColumn.VALUE) == "1,234 products"
        assert table.model.text(ovh, MetricValueColumn.URL) == ""

    def test_every_header_is_explained(self, qtbot: QtBot, catalog: MetricCatalog, driver_help: DriverHelp) -> None:
        table = build(qtbot, catalog, driver_help)

        titles = [
            table.model.headerData(position, Qt.Orientation.Horizontal) for position in range(len(MetricValueColumn))
        ]
        tooltips = [
            table.model.headerData(position, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
            for position in range(len(MetricValueColumn))
        ]

        assert titles[column(MetricValueColumn.URL)] == "Read from"
        assert all(tooltips), "every column explained from the drivers block of help.yaml"
        assert "Double-click" in str(tooltips[column(MetricValueColumn.URL)])
        assert table.model.headerData(0, Qt.Orientation.Vertical) is None
        for widget in (table.provider_picker, table.metric_box, table.source_box, table.search, table.export_button):
            assert widget.toolTip()

    def test_the_filters_combine(self, qtbot: QtBot, catalog: MetricCatalog, driver_help: DriverHelp) -> None:
        table = build(qtbot, catalog, driver_help)
        assert table.metric_box.itemData(0) == ""
        assert table.metric_box.itemText(0) == "All metrics"
        assert table.source_box.findData(MetricSource.EDGAR.value) > 0
        assert table.source_box.findData(MetricSource.MANUAL.value) == -1, "only the sources stored are offered"

        table.metric_box.setCurrentIndex(table.metric_box.findData(ProviderMetric.PRODUCTS.value))

        assert sorted(shown(table, MetricValueColumn.PERIOD)) == ["2025Q4", "2025Q4"]
        assert table.count_label.text() == "2 of 4 values"
        table.provider_picker.tree.set_checked([OVH])
        assert shown(table, MetricValueColumn.PROVIDER) == [Theme().provider_label(OVH)]
        table.metric_box.setCurrentIndex(0)
        table.provider_picker.reset()
        table.source_box.setCurrentIndex(table.source_box.findData(MetricSource.WIKIDATA.value))
        assert shown(table, MetricValueColumn.METRIC) == [catalog.label(ProviderMetric.REGIONS)]
        table.source_box.setCurrentIndex(0)
        table.search.setText("SEC.GOV")
        assert shown(table, MetricValueColumn.SOURCE) == ["edgar"]
        table.search.setText("nothing like it")
        assert table.count_label.text() == "0 of 4 values"
        assert not table.export_button.isEnabled()

    def test_a_reload_keeps_the_filter_picked(
        self, qtbot: QtBot, catalog: MetricCatalog, driver_help: DriverHelp
    ) -> None:
        table = build(qtbot, catalog, driver_help)
        table.source_box.setCurrentIndex(table.source_box.findData(MetricSource.EDGAR.value))

        table.load(measures()[:2])

        assert table.source_box.currentData() == MetricSource.EDGAR.value
        assert table.count_label.text() == "1 of 2 values"
        table.load(measures()[1:])
        assert table.source_box.currentIndex() == 0, "a source no longer stored is dropped"
        assert table.count_label.text() == "3 values"

    def test_the_columns_sort(self, qtbot: QtBot, catalog: MetricCatalog, driver_help: DriverHelp) -> None:
        table = build(qtbot, catalog, driver_help)

        table.view.sortByColumn(column(MetricValueColumn.VALUE), Qt.SortOrder.DescendingOrder)

        assert [value.value for value in table.model.values] == [1234.0, 250.0, 64.0, 31.25]
        table.view.sortByColumn(column(MetricValueColumn.FETCHED), Qt.SortOrder.AscendingOrder)
        assert [value.fetched_at for value in table.model.values][-2:] == [FETCHED, FETCHED]
        table.view.sortByColumn(column(MetricValueColumn.PERIOD), Qt.SortOrder.AscendingOrder)
        assert shown(table, MetricValueColumn.PERIOD) == ["2025Q4", "2025Q4", "2026Q2", "2026Q2"]
        table.load(list(reversed(measures())))
        assert shown(table, MetricValueColumn.PERIOD) == ["2025Q4", "2025Q4", "2026Q2", "2026Q2"], "sort kept"

    def test_a_double_click_opens_the_source(
        self, qtbot: QtBot, catalog: MetricCatalog, driver_help: DriverHelp, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        table = build(qtbot, catalog, driver_help)
        opened = MagicMock(return_value=True)
        monkeypatch.setattr("gui.analysis.drivers.metrics.metrics_table.QDesktopServices.openUrl", opened)
        table.view.sortByColumn(column(MetricValueColumn.URL), Qt.SortOrder.DescendingOrder)

        table.view.doubleClicked.emit(table.model.index(0, 0))
        table.view.doubleClicked.emit(table.model.index(1, 0))

        opened.assert_called_once_with(QUrl("https://www.sec.gov/amzn-10q"))

    def test_the_values_shown_are_exported(
        self, qtbot: QtBot, catalog: MetricCatalog, driver_help: DriverHelp, tmp_path: Path
    ) -> None:
        table = build(qtbot, catalog, driver_help)
        table.source_box.setCurrentIndex(table.source_box.findData(MetricSource.DERIVED.value))
        table.view.sortByColumn(column(MetricValueColumn.VALUE), Qt.SortOrder.AscendingOrder)

        written = table.export(tmp_path / "metrics.csv")

        assert written == tmp_path / "metrics.csv"
        with written.open(encoding="utf-8") as file:
            rows = list(csv.reader(file))
        assert rows[0] == list(MetricsTable.CSV_HEADER)
        assert [(row[0], row[2], row[3], row[5], row[6], row[7]) for row in rows[1:]] == [
            (AWS.value, "2025Q4", "products", "250.0", "products", "derived"),
            (OVH.value, "2025Q4", "products", "1234.0", "products", "derived"),
        ]
        assert rows[2][8] == FETCHED.isoformat()

    def test_an_export_that_fails_is_shown(
        self, qtbot: QtBot, catalog: MetricCatalog, driver_help: DriverHelp, tmp_path: Path
    ) -> None:
        table = build(qtbot, catalog, driver_help)

        assert table.export(tmp_path / "missing" / "metrics.csv") is None

        assert not table.message.isHidden()
        assert "cannot be exported" in table.message.text()
        empty = MetricsTable(Theme(), catalog, driver_help)
        qtbot.addWidget(empty)
        assert empty.export(tmp_path / "none.csv") is None
        assert not (tmp_path / "none.csv").exists()

    def test_the_export_button_asks_for_a_file(
        self,
        qtbot: QtBot,
        catalog: MetricCatalog,
        driver_help: DriverHelp,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        table = build(qtbot, catalog, driver_help)
        target = tmp_path / "picked.csv"
        monkeypatch.setattr(
            "gui.analysis.drivers.metrics.metrics_table.QFileDialog.getSaveFileName",
            MagicMock(return_value=(str(target), "CSV (*.csv)")),
        )

        table.export_button.click()

        assert target.exists()


class TestDriversPanelMetrics:
    def test_a_run_fills_the_table(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        loop = MagicMock()
        panel = DriversPanel(Theme(), loop, catalog)
        qtbot.addWidget(panel)
        panel.controls.target_box.setCurrentIndex(panel.controls.target_box.findData(ProviderMetric.REVENUE.value))
        panel.controls.set_checked([ProviderMetric.REGIONS, ProviderMetric.CAPEX])

        panel.run()

        job, on_done, _ = loop.submit.call_args.args
        storage = MagicMock()
        storage.refresh_metrics = AsyncMock(return_value=4)
        storage.metrics.list = AsyncMock(return_value=measures())
        on_done(asyncio.run(job(storage)))
        assert panel.metrics_table.model.rowCount() == 4

    def test_refresh_reads_the_metrics_again(self, qtbot: QtBot, catalog: MetricCatalog) -> None:
        loop = MagicMock()
        panel = DriversPanel(Theme(), loop, catalog)
        qtbot.addWidget(panel)

        panel.refresh()

        submitted = [call.args for call in loop.submit.call_args_list]
        job, on_done, on_error = next(args for args in submitted if args[0] == panel._read_metrics)
        storage = MagicMock()
        storage.metrics.list = AsyncMock(return_value=measures()[:3])
        on_done(asyncio.run(job(storage)))
        assert panel.metrics_table.count_label.text() == "3 values"
        on_error(StorageReadError("provider metrics", "connection refused"))
        assert "connection refused" in panel.metrics_table.message.text()
        assert not panel.metrics_table.message.isHidden()
