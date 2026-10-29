from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.companies.edgar_schedules.crawler import EdgarSchedulesCrawler
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.markets.crawl_scope import CrawlScope
from models.markets.markets_catalog import MarketsCatalog

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
CompanyPage = Callable[..., Response]
DEC = "https://data.sec.gov/submissions/CIK0000028887.json"
NETSCAPE = "https://www.sec.gov/Archives/edgar/data/944458/0001047469-98-012170.txt"
FILING = {"company": "netscape", "filer": "0000944458", "step": "filing"}


def facts_of(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def requests_of(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


class TestEdgarSchedulesCrawler:
    @pytest.fixture
    def crawler(
        self,
        companies_catalog: CompaniesCatalog,
        financial_concepts: FinancialConcepts,
        markets_catalog: MarketsCatalog,
    ) -> EdgarSchedulesCrawler:
        return EdgarSchedulesCrawler(
            companies_catalog, financial_concepts, markets_catalog, CrawlScope(companies="dec,netscape")
        )

    def test_amounts_are_read_as_written(self, crawler: EdgarSchedulesCrawler) -> None:
        assert crawler._amount("3,060,512") == 3060512
        assert crawler._amount("(127,284)") == -127284
        assert crawler._amount("-12") == -12
        assert crawler._amount("(.95)") == -0.95
        assert crawler._amount("N/A") is None

    def test_days_are_read_as_written(self, crawler: EdgarSchedulesCrawler) -> None:
        assert str(crawler._day("JUN-28-1997")) == "1997-06-28"
        assert crawler._day("1997-06-28") is None
        assert str(crawler._header_day("19980327")) == "1998-03-27"

    async def test_one_submissions_request_per_filer_with_the_contact_agent(
        self, crawler: EdgarSchedulesCrawler, companies_catalog: CompaniesCatalog, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(companies_catalog.sec_user_agent_env, "research admin@example.com")

        requests = [request async for request in crawler.start_requests()]

        assert [request.meta["filer"] for request in requests] == ["0000028887", "0000944458"]
        assert requests[0].url == DEC
        assert requests[0].meta["step"] == "submissions"
        assert requests[0]._session_kwargs["headers"]["User-Agent"] == "research admin@example.com"

    async def test_the_reports_of_1993_to_2001_and_the_older_pages_are_requested(
        self, crawler: EdgarSchedulesCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        meta: Dict[str, JsonValue] = {"company": "dec", "filer": "0000028887", "step": "submissions"}
        response = company_page(DEC, "edgar-submissions-dec.json", meta)

        results = await crawl_page(crawler, response)
        urls = [request.url for request in requests_of(results)]

        assert facts_of(results) == []
        assert urls == [
            "https://data.sec.gov/submissions/CIK0000028887-submissions-001.json",
            "https://www.sec.gov/Archives/edgar/data/28887/0000950135-97-003873.txt",
            "https://www.sec.gov/Archives/edgar/data/28887/0000950135-98-002979.txt",
            "https://www.sec.gov/Archives/edgar/data/28887/0000950109-95-003899.txt",
            "https://www.sec.gov/Archives/edgar/data/28887/0000950135-96-004046.txt",
        ]
        assert [request.meta["step"] for request in requests_of(results)][:2] == ["submissions-page", "filing"]

    async def test_a_page_of_older_filings_leads_to_its_reports_from_1993(
        self, crawler: EdgarSchedulesCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        meta: Dict[str, JsonValue] = {"company": "dec", "filer": "0000028887", "step": "submissions-page"}
        response = company_page(DEC, "edgar-submissions-dec-page.json", meta)

        urls = [request.url for request in requests_of(await crawl_page(crawler, response))]

        assert urls == ["https://www.sec.gov/Archives/edgar/data/28887/0000028887-93-000010.txt"]

    async def test_the_mapped_tags_are_streamed_as_filed(
        self, crawler: EdgarSchedulesCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        facts = facts_of(await crawl_page(crawler, company_page(NETSCAPE, "edgar-fds-netscape-10k.txt", FILING)))
        by_concept: Dict[str, Dict[str, JsonValue]] = {}
        for fact in facts:  # Netscape's schedule comes first in the full text.
            by_concept.setdefault(str(fact["concept"]), fact)
        revenue = by_concept["fds:TOTAL-REVENUES"]

        assert all(fact["kind"] == "financial" and fact["source"] == "edgar-fds" for fact in facts)
        assert (revenue["value"], revenue["start"], revenue["fiscal_period"]) == (533851000, "1997-01-01", "FY")
        assert (revenue["form"], revenue["filed"], revenue["currency"]) == ("10-K", "1998-03-27", "USD")
        assert by_concept["fds:NET-INCOME"]["value"] == -115496000
        assert by_concept["fds:EPS-DILUTED"]["value"] == -1.34
        assert by_concept["fds:CASH"]["start"] is None
        assert {"fds:DEPRECIATION", "fds:PP&E", "fds:TOTAL-COSTS"}.isdisjoint(by_concept)

    async def test_every_column_of_a_restated_schedule_is_read(
        self, crawler: EdgarSchedulesCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        facts = facts_of(await crawl_page(crawler, company_page(NETSCAPE, "edgar-fds-netscape-10k.txt", FILING)))
        borland = [fact for fact in facts if fact["concept"] == "fds:TOTAL-REVENUES" and fact["value"] == 189122000]

        assert sorted(str(fact["end"]) for fact in borland) == ["1997-12-31", "1998-12-31", "1998-12-31"]

    async def test_a_schedule_of_another_article_is_left_out(
        self, crawler: EdgarSchedulesCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        facts = facts_of(await crawl_page(crawler, company_page(NETSCAPE, "edgar-fds-netscape-10k.txt", FILING)))

        assert not any(fact["value"] == 9000000 for fact in facts)

    async def test_a_missing_document_is_not_a_refusal(
        self, crawler: EdgarSchedulesCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        response = company_page(NETSCAPE, "", FILING, status=404)

        assert not await crawler.is_blocked(response)
        assert await crawl_page(crawler, response) == []
