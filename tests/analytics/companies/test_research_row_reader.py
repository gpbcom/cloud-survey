from __future__ import annotations

from datetime import date
from typing import Dict, List

from pydantic import JsonValue

from analytics.companies.progress.research_row_reader import ResearchRowReader
from models.companies.enums import CompanyFactKind, CompanyFeed

PATENT: Dict[str, JsonValue] = {
    "kind": "patent",
    "company": "ibm",
    "query": "International Business Machines Corp",
    "publication_number": "US-11000000-B2",
    "title": "Quantum widget",
    "assignee": "International Business Machines Corp",
    "priority_date": "2019-03-01",
    "source_url": "https://patents.google.com/patent/US11000000B2/en",
}


def test_every_patents_and_papers_kind_becomes_a_row() -> None:
    items: List[Dict[str, JsonValue]] = [
        PATENT,
        {
            "kind": "patent-window",
            "company": "ibm",
            "query": "International Business Machines Corp",
            "after": "2019-01-01",
            "before": "2019-02-01",
            "expected": 800,
            "fetched": 400,
            "status": "incomplete",
        },
        {"kind": "patent-detail", "publication_number": "US-11000000-B2", "source_url": "https://patents.google.com/x"},
        {
            "kind": "paper",
            "openalex_id": "W2741809807",
            "company": "opera",
            "title": "A browser",
            "cited_by_count": 3,
            "source_url": "https://api.openalex.org/works",
        },
        {
            "kind": "researcher",
            "author_id": "A5023888391",
            "company": "opera",
            "name": "Ada",
            "h_index": 4,
            "source_url": "https://api.openalex.org/authors",
        },
        {
            "kind": "paper-count",
            "company": "opera",
            "year": 2020,
            "papers": 12,
            "source_url": "https://api.openalex.org/works",
        },
    ]

    rows = ResearchRowReader().read(CompanyFeed.GOOGLE_PATENTS, items)

    assert [row.kind for row in rows] == [
        CompanyFactKind.PATENT,
        CompanyFactKind.PATENT_WINDOW,
        CompanyFactKind.PATENT_DETAIL,
        CompanyFactKind.PAPER,
        CompanyFactKind.RESEARCHER,
        CompanyFactKind.PAPER_COUNT,
    ]
    assert rows[0].identifier == "US11000000B2"
    assert rows[0].day == date(2019, 3, 1)
    assert rows[1].detail == "incomplete: 400 of 800 read"
    assert rows[2].company is None
    assert rows[4].detail == "0 works, h-index 4"
    assert rows[5].title == "12 papers"


def test_statements_unknown_kinds_and_invalid_facts_are_not_shown() -> None:
    items: List[Dict[str, JsonValue]] = [
        {"kind": "financial", "company": "ibm"},
        {"kind": "not-a-kind"},
        {"company": "ibm"},
        {"kind": "patent", "company": "ibm"},
        PATENT,
    ]

    rows = ResearchRowReader().read(CompanyFeed.GOOGLE_PATENTS, items)

    assert len(rows) == 1
