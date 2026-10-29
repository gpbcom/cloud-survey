from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytestqt.qtbot import QtBot

from analytics.compounding.compounding_analysis import CompoundingAnalysis
from gui.analysis.analysis_view import AnalysisView
from gui.analysis.compounding.compounding_panel import CompoundingPanel
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.compounding.compounding_query import CompoundingQuery
from models.compounding.compounding_report import CompoundingReport
from models.compounding.config.compounding_config import CompoundingConfig
from models.compounding.data.compounding_data import CompoundingData
from models.compounding.data.dated_product import DatedProduct
from models.compounding.data.year_value import YearValue
from models.compounding.enums import CompoundingCard, FoundationSource, Specification, ValueOrigin

AWS, AZURE, GCP = CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.GCP


def planted_data() -> CompoundingData:
    products: List[DatedProduct] = []
    for offset, provider in enumerate((AWS, AZURE, GCP)):
        for index, category in enumerate(
            ["virtual-machines", "object-storage", "kubernetes", "data-lake", "serverless"]
        ):
            products.append(DatedProduct(provider=provider, year=2012 + offset + 2 * index, categories=[category]))
    return CompoundingData(
        products=products,
        market=[
            YearValue(year=year, value=10.0 * 1.3 ** (year - 2010), origin=ValueOrigin.CRAWLED)
            for year in range(2010, 2026)
        ],
        shares=[
            YearValue(provider=AWS, year=year, value=30.0, origin=ValueOrigin.CRAWLED) for year in range(2014, 2026)
        ],
        snapshot={AWS: ["virtual-machines", "kubernetes"], AZURE: ["virtual-machines", "object-storage"]},
        categories=["virtual-machines", "object-storage", "kubernetes", "data-lake", "serverless"],
    )


def planted_report(panel: CompoundingPanel) -> CompoundingReport:
    assert panel.config is not None
    config: CompoundingConfig = panel.config.model_copy(
        update={"settings": panel.config.settings.model_copy(update={"min_events": 1, "bootstrap": 0, "placebo": 5})}
    )
    return CompoundingAnalysis(config).run(CompoundingQuery(providers=[AWS, AZURE, GCP]), planted_data())


@pytest.fixture
def panel(qtbot: QtBot) -> CompoundingPanel:
    built = CompoundingPanel(Theme(), MagicMock())
    qtbot.addWidget(built)
    return built


class TestCompoundingPanel:
    def test_the_controls_read_the_shipped_configuration(self, panel: CompoundingPanel) -> None:
        query = panel.controls.query()

        assert panel.config is not None
        assert AWS in panel.config.kept()
        assert query.specification is Specification.BASE
        assert query.source is FoundationSource.CURATED
        assert query.lag == 1
        assert panel.controls.run_button.toolTip()

    def test_run_submits_a_job_which_reads_and_fits(
        self, panel: CompoundingPanel, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        panel.controls.run_button.click()

        job, on_done, _ = panel.loop.submit.call_args.args  # type: ignore[attr-defined]
        assert not panel.controls.run_button.isEnabled()
        data = planted_data()
        monkeypatch.setattr(
            "analytics.compounding.data.compounding_loader.CompoundingLoader.load", AsyncMock(return_value=data)
        )
        report = asyncio.run(job(MagicMock()))
        on_done(report)

        assert panel.report is report
        assert report is not None
        assert panel.controls.run_button.isEnabled()
        assert panel.coverage_table.rowCount() == len(report.coverage)

    def test_an_outcome_fills_every_card(self, panel: CompoundingPanel) -> None:
        report = planted_report(panel)

        panel._on_outcome(0, report)

        results, inputs = panel.results, panel.inputs
        assert inputs.launches_chart.lines
        assert inputs.market_chart.lines
        assert inputs.shares_chart.lines
        assert results.heaps_chart.series
        assert results.growth_chart.lines
        assert results.growth_box.count() == 3
        assert results.entry_table.rowCount() == len(report.entry)
        assert results.hazard_table.rowCount() == len(report.hazard)
        assert results.placebo_box.count() == len(report.placebo)
        assert results.lags_chart.rows or not any(fit.converged for fit in report.lags)
        assert results.transfer_table.rowCount() == len(report.transfer)
        assert results.summary_table.rowCount() == len(report.summary)
        assert inputs.foundations_table.rowCount() == sum(len(found) for found in report.foundations.values())
        assert panel.caveats.text() or not report.warnings

    def test_a_late_answer_is_dropped(self, panel: CompoundingPanel) -> None:
        panel.generation = 2

        panel._on_outcome(1, planted_report(panel))

        assert panel.report is None

    def test_the_summary_is_exported(self, panel: CompoundingPanel, tmp_path: Path) -> None:
        assert panel.export(tmp_path / "none.csv") is None
        report = planted_report(panel)
        panel._on_outcome(0, report)

        written = panel.export(tmp_path / "summary.csv")

        assert written is not None
        rows = list(csv.reader(written.open(encoding="utf-8")))
        assert rows[0][0] == "Provider"
        assert len(rows) == len(report.summary) + 1

    def test_the_crawl_buttons_ask_for_a_crawl(self, panel: CompoundingPanel) -> None:
        asked: List[str] = []
        panel.crawl_requested.connect(asked.append)

        panel.controls.history_button.click()
        panel.controls.crawl_button.click()

        assert asked == ["history", "all"]

    def test_refresh_marks_the_analysis_stale(self, panel: CompoundingPanel) -> None:
        panel._on_outcome(0, planted_report(panel))

        panel.refresh()

        assert panel.stale
        assert "run the analysis again" in panel.summary.text()


class TestAnalysisViewCompounding:
    def test_every_card_has_a_section(self, qtbot: QtBot, offline_loop: StorageLoop) -> None:
        view = AnalysisView(Theme(), offline_loop)
        qtbot.addWidget(view)

        keys = [section.key for section in view.compounding_sections]

        assert keys == [f"analysis/compounding-{card.value}" for card in CompoundingCard]
        assert view.compounding_sections[0].widen_button is None
        window = view.compounding_sections[4].open_window()
        assert window is not None
        window.close_button.click()
