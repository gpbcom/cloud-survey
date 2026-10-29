from __future__ import annotations

from datetime import UTC, datetime

import pytest

from models.companies.papers.paper_record import PaperRecord
from models.companies.papers.researcher_record import ResearcherRecord
from models.storage.records.record_query import RecordQuery
from storage.storage import Storage

pytestmark = pytest.mark.db


def paper(openalex_id: str, *members: str, company: str = "amazon") -> PaperRecord:
    return PaperRecord(
        openalex_id=openalex_id,
        company=company,
        publication_year=2020,
        authorships=[
            {"position": index, "author_id": author, "name": f"Author {author}", "company_affiliated": True}
            for index, author in enumerate(members)
        ],
        source_url="https://api.openalex.org/works",
    )


def person(author_id: str, current: bool = False, years: int = 0) -> ResearcherRecord:
    return ResearcherRecord(
        author_id=author_id,
        company="amazon",
        name=f"Author {author_id}",
        current_affiliation=current,
        affiliation_years=years,
        source_url="https://api.openalex.org/authors",
    )


class TestConfirmResearchers:
    async def test_members_are_confirmed_by_profile_or_papers_the_others_hidden(self, storage: Storage) -> None:
        await storage.papers.upsert_papers(
            [paper("W2000000001", "A5000000001", "A5000000004"), paper("W2000000002", "A5000000001")]
        )
        await storage.papers.upsert_researchers(
            [
                person("A5000000001"),
                person("A5000000002", current=True),
                person("A5000000003", years=2),
                person("A5000000004", years=1),
            ]
        )

        confirmed = await storage.papers.confirm_researchers(["amazon"], years=2, papers=2)

        assert confirmed == 3
        page = await storage.papers.researcher_page(RecordQuery(companies=["amazon"]))
        assert sorted(item.author_id for item in page.items) == ["A5000000001", "A5000000002", "A5000000003"]
        assert (await storage.papers.coverage(["amazon"]))["amazon"] == (2, 3)


class TestSweep:
    async def test_a_complete_search_removes_what_it_no_longer_found(self, storage: Storage) -> None:
        await storage.papers.upsert_papers(
            [paper("W2000000001", "A5000000001"), paper("W2000000002", "A5000000002"), paper("W2000000003")]
        )
        await storage.papers.upsert_papers([paper("W2000000003", "A5000000003", company="ibm")])
        await storage.papers.upsert_researchers([person("A5000000001"), person("A5000000002")])
        started = datetime.now(UTC)
        await storage.papers.upsert_papers([paper("W2000000001", "A5000000001"), paper("W2000000003")])
        await storage.papers.upsert_researchers([person("A5000000001")])

        removed = await storage.papers.sweep(["amazon"], started)

        assert removed == (1, 1)
        assert await storage.papers.read("W2000000002") is None, "a paper left without a company goes"
        assert await storage.papers.read("W2000000003") is not None
        assert (await storage.papers.coverage())["amazon"] == (2, 1)

    async def test_an_incomplete_search_removes_nothing(self, storage: Storage) -> None:
        await storage.papers.upsert_papers([paper(f"W200000000{index}", "A5000000001") for index in range(1, 5)])
        started = datetime.now(UTC)
        await storage.papers.upsert_papers([paper("W2000000001", "A5000000001")])

        assert await storage.papers.sweep(["amazon"], started) == (0, 0)
        assert (await storage.papers.coverage())["amazon"][0] == 4


class TestUnlink:
    async def test_the_rejected_papers_lose_their_company_and_orphans_go(self, storage: Storage) -> None:
        await storage.papers.upsert_papers([paper("W2000000001", "A5000000001"), paper("W2000000002")])
        await storage.papers.upsert_papers([paper("W2000000002", company="ibm")])

        removed = await storage.papers.unlink({"amazon": {"W2000000001", "W2000000002"}, "opera": set()})

        assert removed == 2
        assert await storage.papers.read("W2000000001") is None
        assert (await storage.papers.coverage()) == {"ibm": (1, 0)}
