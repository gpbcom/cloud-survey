from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel
from PyQt6.QtCore import QModelIndex, Qt
from pytestqt.qtbot import QtBot

from gui.paging.records.record_layout import RecordLayout
from gui.paging.records.record_table_model import RecordTableModel
from models.companies.stored.papers.stored_researcher import StoredResearcher
from models.storage.records.enums import RecordSort
from models.storage.records.record_query import RecordQuery
from storage.storage import Storage

type Job = Callable[[Storage], Awaitable[Tuple[List[BaseModel], Optional[int]]]]
type Done = Callable[[Tuple[List[BaseModel], Optional[int]]], None]

PEOPLE = [StoredResearcher(author_id=f"A{5000 + index}", company="ibm", name=f"Person {index}") for index in range(5)]


class Captured:
    def __init__(self) -> None:
        self.queries: List[RecordQuery] = []
        self.calls: List[Tuple[Job, Done]] = []

    async def read(self, _storage: Storage, query: RecordQuery) -> Tuple[List[BaseModel], Optional[int]]:
        self.queries.append(query)
        records: List[BaseModel] = [*PEOPLE[query.offset : query.offset + query.limit]]
        return records, len(PEOPLE) if query.with_total else None

    def submit(self, job: Job, on_done: Done, _on_error: Callable[[Exception], None]) -> None:
        self.calls.append((job, on_done))

    def answer(self, index: int) -> None:
        job, on_done = self.calls[index]
        on_done(asyncio.run(job(MagicMock())))


def build(captured: Captured, monkeypatch: pytest.MonkeyPatch) -> RecordTableModel:
    layout = RecordLayout(
        headers=[("Name", "The name"), ("Works", "The works")],
        sorts={0: RecordSort.NAME},
        default=0,
        numeric={1},
        wide={0},
        reader=captured.read,
        cells=lambda record: [str(record.model_dump()["name"]), "3"],
        link=lambda record: f"https://openalex.org/{record.model_dump()['author_id']}",
    )
    loop = MagicMock()
    loop.submit.side_effect = captured.submit
    monkeypatch.setattr(RecordTableModel, "PAGE_SIZE", 2)
    return RecordTableModel(loop, layout)


class TestRecordTableModel:
    def test_the_rows_are_read_page_by_page_and_counted_once(
        self, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured = Captured()
        model = build(captured, monkeypatch)

        model.set_query(RecordQuery(companies=["ibm"]))
        with qtbot.waitSignal(model.loaded) as loaded:
            captured.answer(0)

        assert loaded.args == [5]
        assert model.data(model.index(0, 0)) == "Person 0"
        assert model.data(model.index(0, 1), Qt.ItemDataRole.TextAlignmentRole) is not None
        assert model.data(model.index(4, 0)) == "…"
        captured.answer(1)
        assert captured.queries[1].offset == 4
        assert not captured.queries[1].with_total
        assert model.data(model.index(4, 0)) == "Person 4"
        assert model.link_at(model.index(4, 0)) == "https://openalex.org/A5004"
        assert model.record_at(QModelIndex()) is None
        assert model.headerData(1, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole) == "The works"

    def test_a_page_of_an_older_query_is_dropped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = Captured()
        model = build(captured, monkeypatch)
        model.set_query(RecordQuery(text="old"))
        model.set_query(RecordQuery(text="new"))

        captured.answer(0)

        assert model.rowCount() == 0
        captured.answer(1)
        assert model.rowCount() == 5

    def test_only_the_sortable_columns_sort_in_the_database(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = Captured()
        model = build(captured, monkeypatch)

        model.sort(1, Qt.SortOrder.AscendingOrder)
        assert captured.calls == []
        model.sort(0, Qt.SortOrder.AscendingOrder)

        captured.answer(0)
        assert (captured.queries[0].sort, captured.queries[0].descending) == (RecordSort.NAME, False)
