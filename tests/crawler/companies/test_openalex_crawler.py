from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Union
from unittest.mock import MagicMock

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.companies.openalex.crawler import OpenAlexCrawler
from models.companies.catalog.openalex_affiliation import OpenAlexAffiliation
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.papers.paper_record import PaperRecord
from models.companies.papers.paper_year_count import PaperYearCount
from models.markets.crawl_scope import CrawlScope
from models.markets.markets_catalog import MarketsCatalog

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
CompanyPage = Callable[..., Response]
WORKS = "https://api.openalex.org/works?filter=x&api_key=secret-1"


def build(companies: CompaniesCatalog, concepts: FinancialConcepts, markets: MarketsCatalog) -> OpenAlexCrawler:
    return OpenAlexCrawler(companies, concepts, markets, CrawlScope(companies="nvidia"))


@pytest.fixture
def keyless(
    companies_catalog: CompaniesCatalog,
    financial_concepts: FinancialConcepts,
    markets_catalog: MarketsCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> OpenAlexCrawler:
    for variable in companies_catalog.openalex.key_envs:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv(companies_catalog.openalex.mailto_env, "me@example.com")
    return build(companies_catalog, financial_concepts, markets_catalog)


@pytest.fixture
def keyed(
    companies_catalog: CompaniesCatalog,
    financial_concepts: FinancialConcepts,
    markets_catalog: MarketsCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> OpenAlexCrawler:
    first, second = companies_catalog.openalex.key_envs
    monkeypatch.setenv(first, "secret-1")
    monkeypatch.setenv(second, "secret-2")
    return build(companies_catalog, financial_concepts, markets_catalog)


async def test_each_company_is_first_counted_per_year(keyless: OpenAlexCrawler) -> None:
    (count,) = [request async for request in keyless.start_requests()]

    assert count.meta["step"] == "count"
    assert "group_by=publication_year" in count.url
    assert "authorships.institutions.lineage:I4210127875" in count.url
    assert "mailto=me%40example.com" in count.url


async def test_a_count_gives_the_yearly_papers_then_the_first_page_of_each_year(
    keyless: OpenAlexCrawler, company_page: CompanyPage, crawl_page: CrawlPage
) -> None:
    response = company_page(WORKS, "openalex-count.json", {"company": "nvidia", "step": "count"})

    results = await crawl_page(keyless, response)

    counts = [result for result in results if isinstance(result, dict)]
    pages = [result for result in results if isinstance(result, Request)]
    assert [(count["year"], count["papers"]) for count in counts] == [(2019, 2), (2020, 12000)]
    assert [(page.meta["year"], page.meta["page"], page.meta["cursor"]) for page in pages] == [
        (2019, 1, None),
        (2020, 1, None),
    ]
    assert "publication_year:2019" in pages[0].url
    assert "page=1" in pages[0].url
    first = PaperYearCount.model_validate({key: item for key, item in counts[0].items() if key != "kind"})
    assert "secret-1" not in first.source_url


async def test_with_a_key_a_crowded_year_is_read_with_a_cursor(
    keyed: OpenAlexCrawler, company_page: CompanyPage, crawl_page: CrawlPage
) -> None:
    response = company_page(WORKS, "openalex-count.json", {"company": "nvidia", "step": "count"})

    pages = [result for result in await crawl_page(keyed, response) if isinstance(result, Request)]

    assert pages[1].meta["cursor"] == "*"
    assert "api_key=secret-1" in pages[1].url


async def test_a_page_gives_its_papers_and_asks_the_new_company_researchers(
    keyed: OpenAlexCrawler, company_page: CompanyPage, crawl_page: CrawlPage
) -> None:
    meta: Dict[str, JsonValue] = {
        "company": "nvidia",
        "step": "works",
        "year": 2019,
        "expected": 2,
        "page": 1,
        "cursor": None,
    }

    results = await crawl_page(keyed, company_page(WORKS, "openalex-works.json", meta))

    papers = [
        PaperRecord.model_validate({key: item for key, item in result.items() if key != "kind"})
        for result in results
        if isinstance(result, dict)
    ]
    follow = [result for result in results if isinstance(result, Request)]
    assert [paper.openalex_id for paper in papers] == ["W1001", "W1002"]
    assert papers[0].authorships[0].company_affiliated is True
    assert papers[0].authorships[1].company_affiliated is False
    assert "secret-1" not in papers[0].source_url
    (authors,) = follow
    assert authors.meta["step"] == "authors"
    assert "id:A5001|A5002" in authors.url


async def test_a_researcher_profile_is_read(
    keyed: OpenAlexCrawler, company_page: CompanyPage, crawl_page: CrawlPage
) -> None:
    (researcher,) = await crawl_page(
        keyed, company_page(WORKS, "openalex-authors.json", {"company": "nvidia", "step": "authors"})
    )

    assert isinstance(researcher, dict)
    assert (researcher["author_id"], researcher["h_index"], researcher["institution"]) == ("A5001", 12, "NVIDIA")


async def test_a_spent_key_moves_to_the_next_one_then_stops(keyed: OpenAlexCrawler, company_page: CompanyPage) -> None:
    keyed.pause = MagicMock()  # type: ignore[method-assign]
    refusal = company_page(WORKS, "", {"company": "nvidia"}, status=429)

    assert await keyed.is_blocked(refusal)
    retried = await keyed.retry_blocked_request(Request(WORKS), refusal)
    assert "api_key=secret-2" in retried.url
    keyed.pause.assert_not_called()

    assert await keyed.is_blocked(refusal)
    keyed.pause.assert_called_once()


AMAZON = "https://openalex.org/I1311688040"
HOMONYMS = OpenAlexAffiliation(
    institutions=["I1311688040"], exclude_affiliations=["Amazon Environmental Research", r"\bAmazon(ia|as)\b"]
)


def authorship(name: str, institutions: List[JsonValue], texts: List[JsonValue]) -> JsonValue:
    return {
        "author": {"id": f"https://openalex.org/A50{len(name):08d}", "display_name": name},
        "institutions": institutions,
        "affiliations": texts,
    }


def test_only_the_authors_signing_as_members_are_affiliated(keyless: OpenAlexCrawler) -> None:
    amazon: Dict[str, JsonValue] = {"id": AMAZON, "lineage": [AMAZON]}
    germany: Dict[str, JsonValue] = {"id": "https://openalex.org/I4210200001", "lineage": [AMAZON]}
    work: Dict[str, JsonValue] = {
        "authorships": [
            authorship(
                "Seattle", [amazon], [{"raw_affiliation_string": "Amazon, Seattle", "institution_ids": [AMAZON]}]
            ),
            authorship(
                "Brasilia",
                [amazon],
                [{"raw_affiliation_string": "Amazon Environmental Research Institute", "institution_ids": [AMAZON]}],
            ),
            authorship("Berlin", [germany], []),
            authorship("Elsewhere", [{"id": "https://openalex.org/I145311948"}], []),
        ]
    }

    authorships = keyless._authorships(work, HOMONYMS)

    assert [(item["name"], item["company_affiliated"]) for item in authorships] == [
        ("Seattle", True),
        ("Brasilia", False),
        ("Berlin", True),
        ("Elsewhere", False),
    ]
    strict = OpenAlexAffiliation(institutions=["I1311688040"], include_affiliations=["Amazon Web Services"])
    assert [item["company_affiliated"] for item in keyless._authorships(work, strict)] == [False, False, False, False]


def test_a_profile_gives_the_evidence_of_membership(keyless: OpenAlexCrawler) -> None:
    profile: Dict[str, JsonValue] = {
        "last_known_institutions": [{"id": "https://openalex.org/I145311948", "lineage": []}],
        "affiliations": [
            {"institution": {"id": AMAZON, "lineage": [AMAZON]}, "years": [2020]},
            {"institution": {"id": "https://openalex.org/I145311948"}, "years": [2010, 2020]},
        ],
    }

    assert keyless._evidence(profile, HOMONYMS) == (False, 1)
    profile["last_known_institutions"] = [{"id": AMAZON}]
    assert keyless._evidence(profile, HOMONYMS) == (True, 1)
