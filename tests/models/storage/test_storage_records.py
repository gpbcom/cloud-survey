from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.companies.stored.papers.stored_researcher import StoredResearcher
from models.storage.records.enums import RecordSort
from models.storage.records.record_page import RecordPage
from models.storage.records.record_query import RecordQuery


class TestRecordQuery:
    def test_the_companies_are_keys_each_once(self) -> None:
        query = RecordQuery(companies=["IBM ", "ibm", "opera", "not a key"])

        assert query.companies == ["ibm", "opera"]

    def test_a_blank_text_is_no_text(self) -> None:
        assert RecordQuery(text="   ").text is None
        assert RecordQuery(text="  neural   rendering ").text == "neural rendering"

    def test_the_bounds_are_checked(self) -> None:
        with pytest.raises(ValidationError):
            RecordQuery(limit=0)
        with pytest.raises(ValidationError):
            RecordQuery(limit=5001)
        with pytest.raises(ValidationError):
            RecordQuery(offset=-1)

    def test_another_page_keeps_the_query_without_the_count(self) -> None:
        query = RecordQuery(companies=["ibm"], sort=RecordSort.CITATIONS, limit=50)

        page = query.page(100)

        assert (page.companies, page.sort, page.offset, page.limit, page.with_total) == (
            ["ibm"],
            RecordSort.CITATIONS,
            100,
            50,
            False,
        )


class TestRecordPage:
    def test_a_counted_page_knows_whether_records_follow(self) -> None:
        person = StoredResearcher(author_id="A5001", company="ibm", name="Ada")

        assert RecordPage[StoredResearcher](items=[person], offset=0, limit=1, total=2).has_more
        assert not RecordPage[StoredResearcher](items=[person], offset=1, limit=1, total=2).has_more
        assert RecordPage[StoredResearcher](items=[person], offset=0, limit=1).has_more
        assert not RecordPage[StoredResearcher](items=[], offset=0, limit=1).has_more
