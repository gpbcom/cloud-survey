from __future__ import annotations

from typing import Dict, List
from unittest.mock import MagicMock

import pytest
from pydantic import JsonValue
from PyQt6.QtCore import Qt
from pytestqt.qtbot import QtBot

from gui.research.progress.feed_table import FeedTable
from gui.research.research_view import ResearchView
from gui.theme import Theme
from models.companies.enums import CompanyFactKind, CompanyFeed
from models.companies.progress.research_coverage import ResearchCoverage


def paper(company: str, index: int) -> Dict[str, JsonValue]:
    return {
        "kind": "paper",
        "openalex_id": f"W{2000000000 + index}",
        "company": company,
        "title": f"Paper {index}",
        "source_url": "https://api.openalex.org/works",
    }


@pytest.fixture
def view(qtbot: QtBot) -> ResearchView:
    built = ResearchView(Theme(), MagicMock())
    qtbot.addWidget(built)
    return built


def click(view: ResearchView, key: str, modifier: Qt.KeyboardModifier, qtbot: QtBot) -> None:
    widget = view.picker.list
    for row in range(widget.count()):
        item = widget.item(row)
        if item is not None and item.data(Qt.ItemDataRole.UserRole) == key:
            widget.scrollToItem(item)
            rect = widget.visualItemRect(item)
            viewport = widget.viewport()
            assert viewport is not None
            qtbot.mouseClick(viewport, Qt.MouseButton.LeftButton, modifier, rect.center())
            return
    raise AssertionError(f"{key} is not offered")


class TestCompanyPicking:
    def test_every_catalogue_company_is_offered_by_name(self, view: ResearchView) -> None:
        assert len(view.names) == 103
        assert view.picker.list.count() == 103
        assert view.names["ibm"] == "IBM"

    def test_a_click_picks_one_company_alone_and_ctrl_adds_others(self, view: ResearchView, qtbot: QtBot) -> None:
        view.show()
        click(view, "ibm", Qt.KeyboardModifier.NoModifier, qtbot)
        click(view, "opera", Qt.KeyboardModifier.NoModifier, qtbot)

        assert view.picker.selected() == ["opera"]
        assert view.patents_button.text() == "Search patents"

        click(view, "ibm", Qt.KeyboardModifier.ControlModifier, qtbot)

        assert sorted(view.picker.selected()) == ["ibm", "opera"]
        assert view.patents_button.text() == "Search patents (2 companies)"
        assert view.papers_button.text() == "Search papers (2 companies)"

    def test_the_filter_narrows_select_all(self, view: ResearchView) -> None:
        view.picker.search.setText("nvid")
        view.picker.select_all()

        assert view.picker.selected() == ["nvidia"]
        view.picker.search.clear()
        view.picker.none_button.click()
        assert view.picker.selected() == []

    def test_each_search_needs_a_company_and_no_crawl_patents_a_source(self, view: ResearchView) -> None:
        assert not view.patents_button.isEnabled()
        assert not view.papers_button.isEnabled()
        view.pick(["ibm"])
        assert view.patents_button.isEnabled()
        assert view.papers_button.isEnabled()
        view.set_feeds([])
        assert not view.patents_button.isEnabled()
        assert view.papers_button.isEnabled(), "the papers search has no Google Patents source to pick"
        view.set_feeds([CompanyFeed.GOOGLE_PATENT_PAGES])
        view.set_crawling(True)
        assert not view.patents_button.isEnabled()
        assert not view.papers_button.isEnabled()
        view.set_crawling(False)
        assert view.patents_button.isEnabled()

    def test_the_patents_and_the_papers_are_searched_apart(self, view: ResearchView, qtbot: QtBot) -> None:
        view.pick(["ibm", "opera"])
        view.set_feeds([CompanyFeed.GOOGLE_PATENTS, CompanyFeed.GOOGLE_PATENT_PAGES])

        with qtbot.waitSignal(view.search_requested) as patents:
            view.patents_button.click()
        with qtbot.waitSignal(view.search_requested) as papers:
            view.papers_button.click()

        assert patents.args == [["ibm", "opera"], ["google-patents", "google-patents-pages"]]
        assert papers.args == [["ibm", "opera"], ["openalex"]]
        assert CompanyFeed.OPENALEX not in view.sources


class TestRefusedPatents:
    def test_a_refused_patents_search_resumes_by_itself(self, view: ResearchView, qtbot: QtBot) -> None:
        view.pick(["amazon"])
        with qtbot.waitSignal(view.search_requested):
            view.patents_button.click()
        view.start(["amazon"], [CompanyFeed.GOOGLE_PATENTS])

        view.finish("Search over: Google Patents refused the search (refused).", "refused")

        assert view.resume_timer.isActive()
        assert view.resume_timer.interval() == view.resume_minutes * 60_000
        assert "Resuming the patents search by itself" in view.status.text()
        assert view.stop_button.isEnabled()
        with qtbot.waitSignal(view.search_requested) as resumed:
            view.resume_timer.timeout.emit()
        assert resumed.args == [["amazon"], ["google-patents"]]

    def test_stop_cancels_the_resume_and_a_busy_window_delays_it(self, view: ResearchView, qtbot: QtBot) -> None:
        view.pick(["amazon"])
        with qtbot.waitSignal(view.search_requested):
            view.patents_button.click()
        view.finish("Refused (refused).", "refused")

        view.set_crawling(True)
        with qtbot.assertNotEmitted(view.search_requested):
            view.resume_timer.timeout.emit()
        assert view.resume_timer.interval() == view.BUSY_RETRY_MINUTES * 60_000
        view.set_crawling(False)

        view.stop()
        assert not view.resume_timer.isActive()
        assert "cancelled" in view.status.text()

    def test_no_resume_when_unchecked(self, view: ResearchView, qtbot: QtBot) -> None:
        view.pick(["amazon"])
        view.resume_box.setChecked(False)
        with qtbot.waitSignal(view.search_requested):
            view.patents_button.click()

        view.finish("Refused (refused).", "refused")

        assert not view.resume_timer.isActive()


class TestStreaming:
    def test_the_batches_fill_the_progress_and_the_feed(self, view: ResearchView) -> None:
        view.start(["opera", "ibm"], [CompanyFeed.OPENALEX])

        view.add_batch("openalex", [paper("opera", 1), paper("opera", 2), paper("ibm", 3)], 3)
        view.add_batch(
            "google-patents-pages",
            [{"kind": "patent-detail", "publication_number": "US-11000000-B2", "source_url": "https://x.y"}],
            1,
        )

        assert view.progress.count("opera", CompanyFactKind.PAPER) == 2
        assert view.progress.count("ibm", CompanyFactKind.PAPER) == 1
        assert view.progress.count(view.progress.ALL, CompanyFactKind.PATENT_DETAIL) == 1
        assert view.feed.rowCount() == 4
        top = view.feed.item(0, 2)
        assert top is not None
        assert top.text() == "patent page"
        assert view.stop_button.isEnabled()
        assert "4 facts received" in view.status.text()

    def test_the_feed_keeps_the_newest_rows_only(self, view: ResearchView, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(FeedTable, "MAX_ROWS", 5)
        view.start(["opera"], [CompanyFeed.OPENALEX])

        view.add_batch("openalex", [paper("opera", index) for index in range(8)], 8)

        assert view.feed.rowCount() == 5
        newest = view.feed.item(0, 4)
        assert newest is not None
        assert newest.text() == "Paper 7"
        assert view.feed.received == 8

    def test_finish_marks_the_end_and_reads_what_is_stored(self, view: ResearchView) -> None:
        view.start(["opera"], [CompanyFeed.OPENALEX])

        view.finish("Search over.", "stopped")

        status = view.progress.item(0, 1)
        assert status is not None
        assert status.text() == "stopped"
        assert not view.stop_button.isEnabled()
        view.loop.submit.assert_called()  # type: ignore[attr-defined]

    def test_stop_asks_the_window(self, view: ResearchView, qtbot: QtBot) -> None:
        view.start(["opera"], [CompanyFeed.OPENALEX])

        with qtbot.waitSignal(view.stop_requested):
            view.stop_button.click()

        assert "Stopping" in view.status.text()

    def test_the_stored_counts_are_shown(self, view: ResearchView) -> None:
        coverage = {"opera": ResearchCoverage(company="opera", papers=870, researchers=179)}
        view.start(["opera"], [CompanyFeed.OPENALEX])

        view._on_coverage(coverage)

        stored = view.progress.item(0, 7)
        assert stored is not None
        assert stored.text() == "0 / 870"
        items: List[str] = [
            item.text() for row in range(view.picker.list.count()) if (item := view.picker.list.item(row)) is not None
        ]
        assert "Opera  ·  0 patents, 870 papers" in items


class TestStoredPanel:
    def test_the_stored_panel_shows_the_companies_picked(self, view: ResearchView) -> None:
        view.pick(["ibm"])
        assert view.stored.companies == [], "the hidden panel is not read"

        view.show_panel(1)

        assert view.panels.currentWidget() is view.stored
        assert view.stored.companies == ["ibm"]
        view.pick(["ibm", "opera"])
        assert sorted(view.stored.companies) == ["ibm", "opera"]

    def test_a_refresh_while_hidden_marks_the_stored_data_stale(self, view: ResearchView) -> None:
        view.show_panel(1)
        view.show_panel(0)
        view.stored.stale.clear()

        view.refresh()

        assert view.stored.stale == {kind for kind, _, _ in view.stored.KINDS}
