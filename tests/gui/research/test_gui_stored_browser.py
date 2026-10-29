from __future__ import annotations

from datetime import date
from typing import List

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from pytestqt.qtbot import QtBot

from gui.research.stored.stored_browser import StoredBrowser
from gui.storage_bridge.storage_loop import StorageLoop
from models.companies.papers.paper_record import PaperRecord
from models.companies.patents.patent_detail import PatentDetail
from models.companies.patents.patent_record import PatentRecord
from models.storage.records.enums import RecordKind
from storage.storage import Storage

pytestmark = pytest.mark.db


async def seed(storage: Storage) -> None:
    await storage.patents.upsert_records(
        [
            PatentRecord(
                company=company,
                query=company,
                publication_number=number,
                title=title,
                assignee=company.upper(),
                inventors=["Ada Lovelace"],
                priority_date=day,
                source_url=f"https://patents.google.com/patent/{number}/en",
            )
            for company, number, title, day in (
                ("nvidia", "US11000000B2", "Neural rendering", date(2018, 1, 31)),
                ("nvidia", "US11000001B2", "Ray tracing", date(2019, 1, 31)),
                ("amd", "US11000002B2", "Chiplets", date(2020, 1, 31)),
            )
        ]
    )
    await storage.patents.upsert_details(
        [
            PatentDetail(
                publication_number="US11000000B2",
                abstract="A neural renderer.",
                citations=[{"publication_number": "US5093563A", "kind": "cites", "examiner": True}],
                source_url="https://patents.google.com/patent/US11000000B2/en",
            )
        ]
    )
    await storage.papers.upsert_papers(
        [
            PaperRecord(
                openalex_id="W2000000001",
                company="nvidia",
                title="Instant neural graphics",
                doi="10.1145/3528223.3530127",
                authorships=[{"position": 0, "author_id": "A5001", "name": "Thomas Muller"}],
                source_url="https://api.openalex.org/works",
            )
        ]
    )


def cells(browser: StoredBrowser, kind: RecordKind, qtbot: QtBot) -> List[str]:
    model = browser.model(kind)
    qtbot.waitUntil(lambda: all(model.record(number) is not None for number in range(model.total)))
    return [str(model.data(model.index(row, 0))) for row in range(model.total)]


async def test_the_stored_records_are_browsed_and_detailed(
    qtbot: QtBot, storage: Storage, gui_loop: StorageLoop, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed(storage)
    browser = StoredBrowser(gui_loop)
    qtbot.addWidget(browser)

    with qtbot.waitSignal(browser.model(RecordKind.PATENTS).loaded):
        browser.set_companies(["nvidia"])
    assert cells(browser, RecordKind.PATENTS, qtbot) == ["US11000001B2", "US11000000B2"]
    assert browser.count.text() == "2 patents (1 company)"

    view = browser.views[RecordKind.PATENTS]
    view.selectRow(1)
    qtbot.waitUntil(lambda: "US5093563A" in browser.details.toPlainText())
    assert "A neural renderer." in browser.details.toPlainText()

    opened: List[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(QUrl(url).toString()))
    view.doubleClicked.emit(browser.model(RecordKind.PATENTS).index(0, 0))
    assert opened == ["https://patents.google.com/patent/US11000001B2/en"]

    with qtbot.waitSignal(browser.model(RecordKind.PAPERS).loaded):
        browser.show_kind(RecordKind.PAPERS)
    assert cells(browser, RecordKind.PAPERS, qtbot) == ["Instant neural graphics"]
    browser.views[RecordKind.PAPERS].selectRow(0)
    qtbot.waitUntil(lambda: "Thomas Muller" in browser.details.toPlainText())

    with qtbot.waitSignal(browser.model(RecordKind.PAPERS).loaded):
        browser.set_companies([])
    with qtbot.waitSignal(browser.model(RecordKind.PAPERS).loaded):
        browser.filter_box.setText("chiplet")
    assert browser.model(RecordKind.PAPERS).total == 0
    with qtbot.waitSignal(browser.model(RecordKind.PATENTS).loaded):
        browser.show_kind(RecordKind.PATENTS)
    assert cells(browser, RecordKind.PATENTS, qtbot) == ["US11000002B2"]

    with qtbot.waitSignal(browser.model(RecordKind.INVENTORS).loaded):
        browser.show_kind(RecordKind.INVENTORS)
    assert browser.model(RecordKind.INVENTORS).total == 0, "the profiles are derived after a patents crawl"
