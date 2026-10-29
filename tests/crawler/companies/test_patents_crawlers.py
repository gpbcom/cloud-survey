from __future__ import annotations

from datetime import date
from typing import Awaitable, Callable, Dict, List, Optional, Union
from unittest.mock import MagicMock
from urllib.parse import unquote

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.companies.google_patents.crawler import GooglePatentsCrawler
from crawler.exception import UnknownCrawlerTargetError
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import CompanyFeed, PatentCitationKind, PatentWindowStatus
from models.companies.patents.patent_detail import PatentDetail
from models.companies.patents.patent_window import PatentWindow
from models.markets.crawl_scope import CrawlScope
from models.markets.markets_catalog import MarketsCatalog

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
CompanyPage = Callable[..., Response]
SEARCH = "https://patents.google.com/xhr/query?url=x&exp="
PAGE = "https://patents.google.com/patent/US10000000B2/en"


def window(after: str, before: str, country: Optional[str] = None, status: str = "pending") -> PatentWindow:
    return PatentWindow(
        company="nvidia", query="Nvidia Corp", after=after, before=before, country=country, expected=0, status=status
    )


def meta_of(item: PatentWindow, step: str, expected: int = 0) -> Dict[str, JsonValue]:
    return {
        "company": item.company,
        "query": item.query,
        "after": item.after.isoformat(),
        "before": item.before.isoformat(),
        "country": item.country or "",
        "step": step,
        "expected": expected,
    }


def splitter(
    companies: CompaniesCatalog,
    concepts: FinancialConcepts,
    markets: MarketsCatalog,
    countries: List[str],
    known: Optional[List[PatentWindow]] = None,
) -> GooglePatentsCrawler:
    crawler = GooglePatentsCrawler(companies, concepts, markets, CrawlScope(companies="nvidia"), known=known)
    crawler.split_countries = countries
    crawler.refresh_after = date(2023, 1, 1)
    return crawler


class TestWindowPlanning:
    def test_a_window_is_halved_at_its_middle_day(
        self,
        companies_catalog: CompaniesCatalog,
        financial_concepts: FinancialConcepts,
        markets_catalog: MarketsCatalog,
    ) -> None:
        crawler = splitter(companies_catalog, financial_concepts, markets_catalog, ["US", "CN"])

        first, second = crawler._children(window("2020-01-01", "2020-01-11"))

        assert (first.after, first.before, second.after, second.before) == (
            date(2020, 1, 1),
            date(2020, 1, 6),
            date(2020, 1, 6),
            date(2020, 1, 11),
        )

    def test_a_single_day_is_split_by_office_then_no_more(
        self,
        companies_catalog: CompaniesCatalog,
        financial_concepts: FinancialConcepts,
        markets_catalog: MarketsCatalog,
    ) -> None:
        crawler = splitter(companies_catalog, financial_concepts, markets_catalog, ["US", "CN"])
        day = window("2020-01-01", "2020-01-02")

        offices = crawler._children(day)

        assert [child.country for child in offices] == ["US", "CN"]
        assert crawler._can_split(day)
        assert crawler._children(offices[0]) == []
        assert not crawler._can_split(offices[0])

    def test_the_stored_windows_are_skipped_or_replaced_by_their_halves(
        self,
        companies_catalog: CompaniesCatalog,
        financial_concepts: FinancialConcepts,
        markets_catalog: MarketsCatalog,
    ) -> None:
        root = window("2000-01-01", "2000-01-11")
        known = [
            window("2000-01-01", "2000-01-11", status="split"),
            window("2000-01-01", "2000-01-06", status="complete"),
            window("2023-06-01", "2023-06-11", status="complete"),
        ]
        crawler = splitter(companies_catalog, financial_concepts, markets_catalog, [], known)

        planned = crawler._plan([root, window("2023-06-01", "2023-06-11")])

        assert [(item.after, item.before) for item in planned] == [
            (date(2000, 1, 6), date(2000, 1, 11)),
            (date(2023, 6, 1), date(2023, 6, 11)),
        ]


class TestGooglePatentsCrawler:
    @pytest.fixture
    def crawler(
        self,
        companies_catalog: CompaniesCatalog,
        financial_concepts: FinancialConcepts,
        markets_catalog: MarketsCatalog,
    ) -> GooglePatentsCrawler:
        built = GooglePatentsCrawler(
            companies_catalog, financial_concepts, markets_catalog, CrawlScope(companies="nvidia")
        )
        built.browser = False
        return built

    def test_the_search_ignores_robots_and_never_retries_a_refusal(self, crawler: GooglePatentsCrawler) -> None:
        assert crawler.robots_txt_obey is False
        assert crawler.max_blocked_retries == 0
        assert crawler.download_delay == crawler.companies.patents.delay_seconds

    async def test_each_assignee_search_is_counted_over_its_whole_history(
        self, crawler: GooglePatentsCrawler, companies_catalog: CompaniesCatalog
    ) -> None:
        requests = [request async for request in crawler.start_requests()]
        entry = companies_catalog.entry("nvidia")

        assert entry is not None
        assert entry.patents is not None
        assert [request.meta["query"] for request in requests] == entry.patents.assignees
        terms = unquote(requests[0].url.split("url=", 1)[1].split("&exp=")[0])
        assert terms.startswith("assignee=Nvidia+Corp&after=priority:19921231&before=priority:")
        assert terms.endswith("&dups=language&num=10")

    async def test_a_small_window_is_exported(
        self, crawler: GooglePatentsCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        item = window("2019-01-01", "2019-02-01")

        results = await crawl_page(crawler, company_page(SEARCH, "patents-count-small.json", meta_of(item, "count")))

        (export,) = results
        assert isinstance(export, Request)
        assert export.meta["step"] == "export"
        assert export.meta["expected"] == 2
        assert export.url.endswith("&exp=&download=true")

    async def test_a_large_window_is_settled_split_and_its_halves_counted(
        self, crawler: GooglePatentsCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        item = window("2010-01-01", "2020-01-01")

        results = await crawl_page(crawler, company_page(SEARCH, "patents-count-large.json", meta_of(item, "count")))

        settled = [result for result in results if isinstance(result, dict)]
        halves = [result for result in results if isinstance(result, Request)]
        assert [(fact["status"], fact["expected"]) for fact in settled] == [("split", 2500)]
        assert [request.meta["step"] for request in halves] == ["count", "count"]
        assert halves[0].meta["before"] == halves[1].meta["after"]

    async def test_an_export_streams_each_publication_once_then_the_complete_window(
        self, crawler: GooglePatentsCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        item = window("2019-01-01", "2019-02-01")

        results = await crawl_page(crawler, company_page(SEARCH, "patents-export.csv", meta_of(item, "export", 2)))

        records = [result for result in results if isinstance(result, dict) and result["kind"] == "patent"]
        (settled,) = [result for result in results if isinstance(result, dict) and result["kind"] == "patent-window"]
        assert [record["publication_number"] for record in records] == ["US20230214654A1", "US11000000B2"]
        assert records[0]["inventors"] == ["Minwoo Park", "Yilin YANG"]
        assert records[0]["grant_date"] is None
        assert records[1]["grant_date"] == "2021-05-11"
        assert (settled["status"], settled["expected"], settled["fetched"]) == ("complete", 2, 2)
        assert crawler.assignees[("nvidia", "Nvidia Corporation")] == 1

    async def test_an_export_short_of_its_count_is_halved(
        self, crawler: GooglePatentsCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        item = window("2019-01-01", "2019-02-01")

        results = await crawl_page(crawler, company_page(SEARCH, "patents-export.csv", meta_of(item, "export", 5)))

        settled = [result for result in results if isinstance(result, dict) and result["kind"] == "patent-window"]
        halves = [result for result in results if isinstance(result, Request)]
        assert settled[0]["status"] == PatentWindowStatus.SPLIT.value
        assert len(halves) == 2

    async def test_a_refusal_stops_the_crawl(self, crawler: GooglePatentsCrawler, company_page: CompanyPage) -> None:
        crawler.pause = MagicMock()  # type: ignore[method-assign]

        refused = await crawler.is_blocked(company_page(SEARCH, "", {}, status=503))

        assert refused
        crawler.pause.assert_called_once()
        assert crawler.refusal is not None
        assert "Google Patents refused the search (HTTP 503)" in crawler.refusal


class TestGooglePatentsInTheBrowser:
    @pytest.fixture
    def crawler(
        self,
        companies_catalog: CompaniesCatalog,
        financial_concepts: FinancialConcepts,
        markets_catalog: MarketsCatalog,
    ) -> GooglePatentsCrawler:
        built = GooglePatentsCrawler(
            companies_catalog, financial_concepts, markets_catalog, CrawlScope(companies="nvidia")
        )
        built.browser = True
        return built

    async def test_a_count_opens_the_search_page_in_the_visible_browser(self, crawler: GooglePatentsCrawler) -> None:
        requests = [request async for request in crawler.start_requests()]

        assert requests[0].sid == "google-patents-chromium"
        assert requests[0].url.startswith("https://patents.google.com/?assignee=Nvidia+Corp&after=priority:19921231")
        assert requests[0].url.endswith("&dups=language&num=10")

    async def test_the_search_the_page_ran_is_read_and_its_export_follows(
        self, crawler: GooglePatentsCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        item = window("2019-01-01", "2019-02-01")
        opened = company_page("https://patents.google.com/?assignee=x", "patent-page.html", meta_of(item, "count"))
        opened.captured_xhr = [company_page(SEARCH, "patents-count-small.json", {})]

        (export,) = await crawl_page(crawler, opened)

        assert isinstance(export, Request)
        assert export.meta["step"] == "export"
        assert export.sid == "google-patents-chromium"
        assert export._session_kwargs["page_setup"] == crawler._block_search
        assert callable(export._session_kwargs["page_action"])

    async def test_the_export_the_page_ran_is_read(
        self, crawler: GooglePatentsCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        item = window("2019-01-01", "2019-02-01")
        opened = company_page("https://patents.google.com/?assignee=x", "patent-page.html", meta_of(item, "export", 2))
        opened.captured_xhr = [company_page(f"{SEARCH}&download=true", "patents-export.csv", {})]

        results = await crawl_page(crawler, opened)

        records = [result for result in results if isinstance(result, dict) and result["kind"] == "patent"]
        assert [record["publication_number"] for record in records] == ["US20230214654A1", "US11000000B2"]

    async def test_a_refused_search_of_the_page_stops_the_crawl(
        self, crawler: GooglePatentsCrawler, company_page: CompanyPage
    ) -> None:
        crawler.pause = MagicMock()  # type: ignore[method-assign]
        opened = company_page("https://patents.google.com/?assignee=x", "patent-page.html", {})
        opened.captured_xhr = [company_page(SEARCH, "", {}, status=429)]

        assert await crawler.is_blocked(opened)
        crawler.pause.assert_called_once()


class TestGooglePatentPages:
    @pytest.fixture
    def crawler(
        self,
        companies_catalog: CompaniesCatalog,
        financial_concepts: FinancialConcepts,
        markets_catalog: MarketsCatalog,
    ) -> GooglePatentsCrawler:
        queue = ["US10000000B2", "US11000000B2", "US20230214654A1"]
        built = GooglePatentsCrawler(
            companies_catalog, financial_concepts, markets_catalog, queue=queue, source=CompanyFeed.GOOGLE_PATENT_PAGES
        )
        built.browser = False
        return built

    async def test_the_queue_is_read_up_to_the_page_budget(
        self, crawler: GooglePatentsCrawler, companies_catalog: CompaniesCatalog, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(companies_catalog.patents.page_budget_env, "2")

        requests = [request async for request in crawler.start_requests()]

        assert [request.url for request in requests] == [PAGE, "https://patents.google.com/patent/US11000000B2/en"]
        assert crawler.robots_txt_obey is True

    async def test_a_page_gives_its_family_classes_and_citations(
        self, crawler: GooglePatentsCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        (item,) = await crawl_page(crawler, company_page(PAGE, "patent-page.html", {"publication": "US10000000B2"}))

        assert isinstance(item, dict)
        assert item["kind"] == "patent-detail"
        detail = PatentDetail.model_validate({key: value for key, value in item.items() if key != "kind"})
        assert detail.family_id == "54766427"
        assert detail.title == "Coherent LADAR using intra-pixel quadrature detection"
        assert detail.abstract == "A frequency modulated (coherent) laser detection and ranging system."
        assert detail.assignees_original == ["Raytheon Co"]
        assert detail.inventors == ["Joseph Marron"]
        assert detail.cpc == ["G01S7/4914", "G01S17/32"]
        assert detail.claims == 20
        assert (detail.priority_date, detail.grant_date) == (date(2015, 3, 10), date(2018, 6, 19))
        citations = {(citation.publication_number, citation.kind): citation for citation in detail.citations}
        assert set(citations) == {
            ("US5093563A", PatentCitationKind.CITES),
            ("US20030076485A1", PatentCitationKind.CITES),
            ("US11353558B2", PatentCitationKind.CITED_BY),
        }
        assert citations[("US5093563A", PatentCitationKind.CITES)].examiner is True
        assert citations[("US20030076485A1", PatentCitationKind.CITES)].examiner is False
        assert citations[("US11353558B2", PatentCitationKind.CITED_BY)].assignee == "Gm Cruise Holdings Llc"

    async def test_a_missing_page_gives_nothing(
        self, crawler: GooglePatentsCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        response = company_page(PAGE, "", {"publication": "US10000000B2"}, status=404)

        assert not await crawler.is_blocked(response)
        assert await crawl_page(crawler, response) == []


def test_the_pages_open_in_the_visible_browser_and_a_wrong_source_is_refused(
    companies_catalog: CompaniesCatalog, financial_concepts: FinancialConcepts, markets_catalog: MarketsCatalog
) -> None:
    crawler = GooglePatentsCrawler(
        companies_catalog,
        financial_concepts,
        markets_catalog,
        queue=["US10000000B2"],
        source=CompanyFeed.GOOGLE_PATENT_PAGES,
    )
    crawler.browser = True

    (request,) = crawler._page_requests()

    assert (request.url, request.sid, request.meta["publication"]) == (PAGE, "google-patents-chromium", "US10000000B2")
    with pytest.raises(UnknownCrawlerTargetError):
        GooglePatentsCrawler(companies_catalog, financial_concepts, markets_catalog, source=CompanyFeed.OPENALEX)
