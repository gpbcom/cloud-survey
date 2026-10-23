from __future__ import annotations

import itertools
from pathlib import Path
from typing import Dict, List, Tuple

import pytest
from PyQt6.QtCore import QPoint, Qt
from pytestqt.qtbot import QtBot

from analytics.history.chronology_loader import ChronologyLoader
from analytics.history.exception import ChronologyFileError
from gui.analysis.analysis_view import AnalysisView
from gui.analysis.history.history_panel import HistoryPanel
from gui.analysis.history.leadership_chart import LeadershipChart
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.history.chronology import Chronology
from models.history.enums import EventKind


@pytest.fixture(scope="module")
def shipped() -> Chronology:
    return ChronologyLoader().load()


def painted(qtbot: QtBot, panel: HistoryPanel, width: int = 1400) -> LeadershipChart:
    chart = panel.chart
    qtbot.addWidget(chart)
    qtbot.addWidget(panel.table)
    chart.resize(width, chart.minimumHeight())
    chart.show()
    chart.grab()
    return chart


class TestLeadershipChart:
    def test_a_band_per_reign_and_a_marker_per_default_event(self, qtbot: QtBot, shipped: Chronology) -> None:
        chart = painted(qtbot, HistoryPanel(Theme(), shipped))

        assert len(chart.bands) == len(shipped.reigns)
        assert {event.key for _, _, event in chart.markers} == {event.key for event in shipped.events if event.default}
        assert chart.minimumHeight() >= len(shipped.segments) * chart.LANE_HEIGHT

    def test_markers_sit_on_their_date_and_their_labels_never_overlap(self, qtbot: QtBot, shipped: Chronology) -> None:
        chart = painted(qtbot, HistoryPanel(Theme(), shipped))
        frame = chart._frame()
        assert frame is not None

        for x, _, event in chart.markers:
            assert x == pytest.approx(frame.map_x(event.when()))
        rows: Dict[float, List[Tuple[float, float]]] = {}
        for _, label, _ in chart.markers:
            if label is not None:
                rows.setdefault(label.top(), []).append((label.left(), label.right()))
        assert len(rows) <= chart.STRIP_ROWS
        for spans in rows.values():
            spans.sort()
            assert all(previous[1] <= current[0] for previous, current in itertools.pairwise(spans))

    def test_markers_outside_the_zoom_are_skipped(self, qtbot: QtBot, shipped: Chronology) -> None:
        chart = painted(qtbot, HistoryPanel(Theme(), shipped))
        every = len(chart.markers)

        chart.zoom.set_x_window((1960.0, 1990.0))
        chart.grab()

        frame = chart._frame()
        assert frame is not None
        assert frame.x_high < 1995.0, "the window is clamped inside the chronology, then shown"
        assert 0 < len(chart.markers) < every
        assert all(frame.x_low <= event.when() <= frame.x_high for _, _, event in chart.markers)
        assert all(reign.begins() <= frame.x_high for _, reign in chart.bands)

    def test_the_tooltips_explain_bands_and_markers(self, qtbot: QtBot, shipped: Chronology) -> None:
        chart = painted(qtbot, HistoryPanel(Theme(), shipped))
        _, lenovo = next(hit for hit in chart.bands if hit[1].company == "lenovo")
        event = next(event for event in shipped.events if event.key == "cma-cloud")

        band = chart._reign_tooltip(lenovo)
        marker = chart._event_tooltip(event)

        assert "Lenovo</b> leads PCs, 2013" in band
        assert "Evidence:" in band
        assert "Profitability" in band
        assert "2025-07-31 \u2014 UK CMA cloud decision" in marker
        assert "Outcome:</b> Pending" in marker
        assert Theme.POLICY_SHOCK in marker

    def test_a_click_picks_a_band_and_selects_its_line(self, qtbot: QtBot, shipped: Chronology) -> None:
        panel = HistoryPanel(Theme(), shipped)
        chart = painted(qtbot, panel)
        band, reign = next(hit for hit in chart.bands if hit[1].company == "tsmc")
        target = band.center().toPoint() + QPoint(40, 0)
        assert chart._marker_at(band.center() + (target - band.center().toPoint()).toPointF()) is None

        with qtbot.waitSignal(chart.picked) as picked:
            qtbot.mouseClick(chart, Qt.MouseButton.LeftButton, pos=target)

        assert picked.args == [reign.key()]
        assert chart.highlighted == reign.key()
        selected = panel.table.selectedItems()
        assert selected
        assert panel.table.keys[selected[0].row()] == reign.key()

    def test_a_clicked_line_highlights_the_chart(self, qtbot: QtBot, shipped: Chronology) -> None:
        panel = HistoryPanel(Theme(), shipped)
        painted(qtbot, panel)
        row = panel.table.keys.index("event:ibm-unbundling")

        panel.table.cellClicked.emit(row, 4)

        assert panel.chart.highlighted == "event:ibm-unbundling"


class TestEventSelector:
    def test_defaults_entries_and_kinds(self, qtbot: QtBot, shipped: Chronology) -> None:
        panel = HistoryPanel(Theme(), shipped)
        selector = panel.selector
        qtbot.addWidget(selector)
        menu = selector.menu()
        assert menu is not None
        texts = [action.text() for action in menu.actions()]

        assert selector.text().startswith(f"Notable events ({sum(event.default for event in shipped.events)})")
        assert "1969 \u2014 US v. IBM filed" in texts
        assert "1982 \u2014 AT&&T consent decree" in texts, "the ampersand is not a shortcut"
        regulation = {event.key for event in shipped.events if event.kind is EventKind.REGULATION}
        every = next(action for action in menu.actions() if action.text() == "Show all regulation")
        selector.set_selected([])
        assert panel.chart.events == []

        every.trigger()

        assert {event.key for event in panel.chart.events} == regulation
        hide = next(action for action in menu.actions() if action.text() == "Hide all")
        hide.trigger()
        assert selector.selected() == []
        assert selector.text().startswith("Notable events (0)")


class TestChronologyTable:
    def test_every_line_is_printed(self, qtbot: QtBot, shipped: Chronology) -> None:
        panel = HistoryPanel(Theme(), shipped)
        qtbot.addWidget(panel.table)

        assert panel.table.rowCount() == len(panel.timeline.entries(shipped))
        first = panel.table.item(0, 4)
        assert first is not None
        assert first.text().startswith("IBM takes the lead in mainframes")
        assert first.toolTip() == first.text()
        assert panel.table.height() < 60 * (panel.table.VISIBLE_ROWS + 2)


class TestHistoryPanel:
    def test_a_broken_chronology_is_said(self, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
        def broken(*_: Path) -> Chronology:
            raise ChronologyFileError(Path("chronology.yaml"), "the file is not valid YAML.")

        monkeypatch.setattr(ChronologyLoader, "load", broken)

        panel = HistoryPanel(Theme())
        qtbot.addWidget(panel.chart)

        assert panel.chronology is None
        assert "not valid YAML" in panel.chart.message
        assert panel.table.rowCount() == 0
        assert not panel.chart.grab().isNull()


class TestAnalysisViewLeaders:
    def test_the_leaders_card_widens(self, qtbot: QtBot, offline_loop: StorageLoop) -> None:
        view = AnalysisView(Theme(), offline_loop)
        qtbot.addWidget(view)
        chart, table = view.history_sections

        assert [chart.key, table.key] == ["analysis/leaders", "analysis/leaders/table"]
        assert table.widen_button is None
        assert chart.tools is view.history.selector
        window = chart.open_window()
        assert window is not None
        assert view.history.chart.window() is window
        window.close_button.click()
        assert view.history.chart.window() is not window
