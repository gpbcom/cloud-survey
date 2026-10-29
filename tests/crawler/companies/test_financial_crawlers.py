from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.companies.edgar.crawler import EdgarFinancialsCrawler
from crawler.companies.google_finance.crawler import GoogleFinanceStatementsCrawler
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.markets.crawl_scope import CrawlScope
from models.markets.markets_catalog import MarketsCatalog

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
CompanyPage = Callable[..., Response]
NVDA_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json"
NVDA_QUOTE = "https://www.google.com/finance/quote/NVDA:NASDAQ?hl=en"


def facts_of(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


class TestEdgarFinancialsCrawler:
    @pytest.fixture
    def crawler(
        self,
        companies_catalog: CompaniesCatalog,
        financial_concepts: FinancialConcepts,
        markets_catalog: MarketsCatalog,
    ) -> EdgarFinancialsCrawler:
        return EdgarFinancialsCrawler(
            companies_catalog, financial_concepts, markets_catalog, CrawlScope(companies="hp,nvidia")
        )

    async def test_one_request_per_filer_with_the_contact_agent(
        self, crawler: EdgarFinancialsCrawler, companies_catalog: CompaniesCatalog, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(companies_catalog.sec_user_agent_env, "research admin@example.com")

        requests = [request async for request in crawler.start_requests()]

        assert [request.meta["filer"] for request in requests] == ["0000047217", "0001645590", "0001045810"]
        assert requests[2].url == NVDA_FACTS
        assert requests[2].meta["company"] == "nvidia"
        assert requests[2]._session_kwargs["headers"]["User-Agent"] == "research admin@example.com"

    async def test_the_mapped_facts_are_streamed_as_filed(
        self, crawler: EdgarFinancialsCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        response = company_page(NVDA_FACTS, "edgar-nvidia.json", {"company": "nvidia", "filer": "0001045810"})

        facts = facts_of(await crawl_page(crawler, response))
        revenues = [fact for fact in facts if fact["metric"] == "revenue"]
        shares = next(fact for fact in facts if fact["metric"] == "shares-outstanding")
        eps = next(fact for fact in facts if fact["metric"] == "eps-diluted")

        assert all(fact["kind"] == "financial" and fact["filer"] == "0001045810" for fact in facts)
        assert len(revenues) == 4
        assert {fact["form"] for fact in revenues} == {"10-K", "10-Q"}
        assert (shares["currency"], shares["start"], shares["value"]) == (None, None, 24640000000)
        assert eps["currency"] == "USD"
        assert not any(fact["metric"] == "accounts-payable" for fact in facts)

    async def test_only_the_reporting_currency_is_read(
        self, crawler: EdgarFinancialsCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        response = company_page(NVDA_FACTS, "edgar-tsmc.json", {"company": "tsmc", "filer": "0001046179"})

        facts = facts_of(await crawl_page(crawler, response))

        assert {fact["currency"] for fact in facts} == {"TWD"}
        assert {fact["metric"] for fact in facts} == {"revenue", "rd-expense", "noncurrent-bonds"}

    async def test_a_filer_without_xbrl_gives_nothing(
        self, crawler: EdgarFinancialsCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        response = company_page(NVDA_FACTS, "", {"company": "sun", "filer": "0000709519"}, status=404)

        assert not await crawler.is_blocked(response)
        assert await crawl_page(crawler, response) == []


class TestGoogleFinanceStatementsCrawler:
    @pytest.fixture
    def crawler(
        self,
        companies_catalog: CompaniesCatalog,
        financial_concepts: FinancialConcepts,
        markets_catalog: MarketsCatalog,
    ) -> GoogleFinanceStatementsCrawler:
        scope = CrawlScope(companies="nvidia,openai,alibaba")
        return GoogleFinanceStatementsCrawler(companies_catalog, financial_concepts, markets_catalog, scope)

    async def test_the_valued_listing_of_each_listed_company_is_requested(
        self, crawler: GoogleFinanceStatementsCrawler
    ) -> None:
        requests = [request async for request in crawler.start_requests()]

        assert [request.meta["listing"] for request in requests] == ["NASDAQ:NVDA", "NYSE:BABA"]
        assert requests[0].url == NVDA_QUOTE
        assert "CONSENT=" in requests[0]._session_kwargs["headers"]["Cookie"]

    async def test_the_statements_are_read_at_their_pinned_positions(
        self, crawler: GoogleFinanceStatementsCrawler, company_page: CompanyPage, crawl_page: CrawlPage
    ) -> None:
        response = company_page(NVDA_QUOTE, "gfinance-nvda.html", {"company": "nvidia", "listing": "NASDAQ:NVDA"})

        facts = facts_of(await crawl_page(crawler, response))
        year = {fact["metric"]: fact for fact in facts if fact["end"] == "2025-01-26" and fact["granularity"] == "year"}

        assert year["revenue"]["value"] == 130497000000
        assert year["net-income"]["value"] == 72880000000
        assert year["operating-cash-flow"]["value"] == 64089000000
        assert year["capex"]["value"] == 3236000000
        assert year["shares-outstanding"]["currency"] is None
        assert year["revenue"]["fiscal_period"] == "FY"
        assert {fact["granularity"] for fact in facts} >= {"year", "quarter"}

    async def test_a_page_without_statements_tries_the_next_exchange_code(
        self, crawler: GoogleFinanceStatementsCrawler, company_page: CompanyPage
    ) -> None:
        response = company_page(
            "https://www.google.com/finance/quote/7203:TYO?hl=en",
            "patents-count-small.json",
            {"company": "sony", "listing": "TYO:6758", "candidate": 5},
        )

        assert list(crawler.extract_facts(response)) == []
        assert list(crawler.follow_ups(response, 0)) == []
