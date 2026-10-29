from __future__ import annotations

from datetime import date
from typing import List

import pytest

from models.companies.enums import PatentCitationKind, PatentWindowStatus
from models.companies.papers.paper_record import PaperRecord
from models.companies.papers.researcher_record import ResearcherRecord
from models.companies.patents.patent_detail import PatentDetail
from models.companies.patents.patent_record import PatentRecord
from models.companies.patents.patent_window import PatentWindow
from models.storage.records.enums import RecordSort
from models.storage.records.record_query import RecordQuery
from storage.storage import Storage

pytestmark = pytest.mark.db


def record(number: str, priority: date, company: str = "nvidia", title: str = "") -> PatentRecord:
    return PatentRecord(
        company=company,
        query="Nvidia Corp" if company == "nvidia" else "Advanced Micro Devices",
        publication_number=number,
        title=title or f"Invention {number}",
        assignee="Nvidia Corporation" if company == "nvidia" else "AMD Inc",
        inventors=["Minwoo Park", "Jan Kautz"],
        priority_date=priority,
        source_url=f"https://patents.google.com/patent/{number}/en",
    )


async def seed_patents(storage: Storage) -> None:
    await storage.patents.upsert_records(
        [
            record("US11000000B2", date(2018, 1, 31), title="Neural rendering"),
            record("US11000001B2", date(2019, 1, 31)),
            record("US11000002B2", date(2020, 1, 31)),
            record("US11000003B2", date(2017, 1, 31), company="amd"),
            record("US11000002B2", date(2020, 1, 31), company="amd"),
        ]
    )


class TestPatentPages:
    async def test_the_pages_never_overlap_and_only_the_first_is_counted(self, storage: Storage) -> None:
        await seed_patents(storage)
        query = RecordQuery(limit=2)

        first = await storage.patents.list(query)
        second = await storage.patents.list(query.page(2))

        assert first.total == 4
        assert second.total is None
        numbers = [patent.publication_number for patent in [*first.items, *second.items]]
        assert numbers == ["US11000002B2", "US11000001B2", "US11000000B2", "US11000003B2"]
        assert first.has_more
        assert (await storage.patents.list(query.page(4))).items == []

    async def test_the_companies_text_and_order_filter_the_page(self, storage: Storage) -> None:
        await seed_patents(storage)

        amd = await storage.patents.list(RecordQuery(companies=["amd"], sort=RecordSort.PRIORITY))
        found = await storage.patents.list(RecordQuery(text="neural"))
        ascending = await storage.patents.list(RecordQuery(sort=RecordSort.PUBLICATION, descending=False))

        assert [(patent.publication_number, patent.companies) for patent in amd.items] == [
            ("US11000002B2", ["amd", "nvidia"]),
            ("US11000003B2", ["amd"]),
        ]
        assert [patent.publication_number for patent in found.items] == ["US11000000B2"]
        assert ascending.items[0].publication_number == "US11000000B2"

    async def test_the_file_of_a_patent_gathers_its_page(self, storage: Storage) -> None:
        await seed_patents(storage)
        await storage.patents.upsert_details(
            [
                PatentDetail(
                    publication_number="US11000000B2",
                    abstract="A renderer.",
                    inventors=["Jonathan White"],
                    assignees_original=["Nvidia Corp"],
                    assignees_current=["Nvidia Corporation"],
                    cpc=["G06T15/00", "G06N3/08"],
                    citations=[
                        {"publication_number": "US5093563A", "kind": "cites", "examiner": True},
                        {"publication_number": "US11353558B2", "kind": "cited-by"},
                    ],
                    source_url="https://patents.google.com/patent/US11000000B2/en",
                )
            ]
        )

        file = await storage.patents.read("us11000000b2")

        assert file is not None
        assert (file.patent.page_read, file.abstract) == (True, "A renderer.")
        assert (file.inventors, file.assignees_original, file.assignees_current) == (
            ["Jonathan White"],
            ["Nvidia Corp"],
            ["Nvidia Corporation"],
        )
        assert file.cpc == ["G06T15/00", "G06N3/08"]
        assert {(citation.publication_number, citation.kind) for citation in file.citations} == {
            ("US5093563A", PatentCitationKind.CITES),
            ("US11353558B2", PatentCitationKind.CITED_BY),
        }
        assert await storage.patents.read("US99999999B2") is None


class TestWindowPages:
    async def test_the_windows_are_listed_with_their_search_date(self, storage: Storage) -> None:
        window = PatentWindow(
            company="nvidia", query="Nvidia Corp", after=date(2019, 1, 1), before=date(2019, 2, 1), expected=3
        )
        await storage.patents.upsert_windows(
            [
                window.model_copy(update={"status": PatentWindowStatus.COMPLETE, "fetched": 3}),
                window.model_copy(update={"after": date(2019, 2, 1), "before": date(2019, 3, 1)}),
                window.model_copy(update={"company": "amd", "query": "AMD"}),
            ]
        )

        page = await storage.patents.window_page(RecordQuery(companies=["nvidia"]))
        found = await storage.patents.window_page(RecordQuery(text="amd"))

        assert [(window.after, window.status) for window in page.items] == [
            (date(2019, 2, 1), PatentWindowStatus.PENDING),
            (date(2019, 1, 1), PatentWindowStatus.COMPLETE),
        ]
        assert page.items[0].searched_at is not None
        assert page.items[0].country is None
        assert [window.company for window in found.items] == ["amd"]


class TestProfilePages:
    async def test_the_inventors_are_matched_to_their_listed_companies(self, storage: Storage) -> None:
        await seed_patents(storage)
        await storage.patent_profiles.rebuild()

        nvidia = await storage.patent_profiles.list(RecordQuery(companies=["nvidia"]))
        nobody = await storage.patent_profiles.list(RecordQuery(companies=["nvidi"]))
        named = await storage.patent_profiles.list(RecordQuery(text="kautz"))

        assert {profile.name for profile in nvidia.items} == {"Minwoo Park", "Jan Kautz"}
        assert nvidia.items[0].companies == ["amd", "nvidia"]
        assert nobody.items == []
        assert nobody.total == 0
        assert [profile.name for profile in named.items] == ["Jan Kautz"]

    async def test_the_assignees_are_listed_by_company(self, storage: Storage) -> None:
        await seed_patents(storage)
        await storage.patent_profiles.rebuild()

        page = await storage.patent_profiles.assignee_page(RecordQuery(companies=["nvidia"]))

        assert [(profile.company, profile.name, profile.publications) for profile in page.items] == [
            ("nvidia", "Nvidia Corporation", 3)
        ]


def paper(openalex_id: str, company: str, day: date, citations: int) -> PaperRecord:
    return PaperRecord(
        openalex_id=openalex_id,
        company=company,
        doi=f"10.1000/{openalex_id.lower()}",
        title=f"Paper {openalex_id}",
        publication_year=day.year,
        publication_date=day,
        venue="NeurIPS",
        cited_by_count=citations,
        authorships=[
            {
                "position": 0,
                "author_id": "A5001",
                "name": "Author 1",
                "institutions": ["I1304085615"],
                "company_affiliated": True,
            },
            {"position": 1, "name": "Author 2", "institutions": ["I63966007", "I97018004"]},
        ],
        source_url="https://api.openalex.org/works",
    )


class TestPaperPages:
    async def test_the_papers_are_paged_sorted_and_read_with_their_authors(self, storage: Storage) -> None:
        await storage.papers.upsert_papers(
            [
                paper("W1001", "nvidia", date(2019, 5, 1), 40),
                paper("W1002", "nvidia", date(2021, 5, 1), 10),
                paper("W1003", "amd", date(2020, 5, 1), 90),
            ]
        )

        latest = await storage.papers.list(RecordQuery(companies=["nvidia"]))
        cited = await storage.papers.list(RecordQuery(sort=RecordSort.CITATIONS))
        one = await storage.papers.read("W1001")

        assert [item.openalex_id for item in latest.items] == ["W1002", "W1001"]
        assert latest.total == 2
        assert latest.items[0].authors == []
        ids: List[str] = [item.openalex_id for item in cited.items]
        assert ids == ["W1003", "W1001", "W1002"]
        assert one is not None
        assert [(author.name, author.institutions) for author in one.authors] == [
            ("Author 1", ["I1304085615"]),
            ("Author 2", ["I63966007", "I97018004"]),
        ]
        assert one.link() == "https://doi.org/10.1000/w1001"
        assert await storage.papers.read("W9999") is None

    async def test_the_researchers_are_paged_by_citations(self, storage: Storage) -> None:
        await storage.papers.upsert_researchers(
            [
                ResearcherRecord(author_id="A5001", company="nvidia", name="Ada", cited_by_count=5, source_url="u"),
                ResearcherRecord(author_id="A5002", company="nvidia", name="Bob", cited_by_count=50, source_url="u"),
                ResearcherRecord(author_id="A5003", company="amd", name="Cy", cited_by_count=500, source_url="u"),
            ]
        )

        page = await storage.papers.researcher_page(RecordQuery(companies=["nvidia"]))
        by_name = await storage.papers.researcher_page(RecordQuery(sort=RecordSort.NAME, descending=False))

        assert [person.name for person in page.items] == ["Bob", "Ada"]
        assert [person.name for person in by_name.items] == ["Ada", "Bob", "Cy"]
