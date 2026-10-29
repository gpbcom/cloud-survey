from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.companies.openalex_identity.crawler import OpenAlexIdentityCrawler
from crawler.companies.sec_identity.crawler import SecIdentityCrawler
from crawler.factory import CrawlerFactory
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import CompanyFeed
from models.markets.crawl_scope import CrawlScope
from models.markets.markets_catalog import MarketsCatalog

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
CompanyPage = Callable[..., Response]


def without_filers(companies: CompaniesCatalog, key: str) -> CompaniesCatalog:
    entries = [
        entry.model_copy(update={"sec_ciks": []}) if entry.key == key else entry for entry in companies.companies
    ]
    return companies.model_copy(update={"companies": entries})


class TestSecIdentityCrawler:
    @pytest.fixture
    def crawler(
        self,
        companies_catalog: CompaniesCatalog,
        financial_concepts: FinancialConcepts,
        markets_catalog: MarketsCatalog,
    ) -> SecIdentityCrawler:
        companies = without_filers(companies_catalog, "nvidia")
        return SecIdentityCrawler(companies, financial_concepts, markets_catalog, CrawlScope(companies="nvidia,ibm"))

    async def test_the_tickers_file_is_requested_once(self, crawler: SecIdentityCrawler) -> None:
        (request,) = [request async for request in crawler.start_requests()]

        assert request.url == SecIdentityCrawler.TICKERS_URL
        assert request.meta["step"] == "tickers"

    async def test_the_filers_of_a_listed_ticker_or_the_name_are_checked(
        self, crawler: SecIdentityCrawler, crawl_page: CrawlPage, company_page: CompanyPage
    ) -> None:
        response = company_page(SecIdentityCrawler.TICKERS_URL, "sec-tickers-exchange.json", {"step": "tickers"})

        results = await crawl_page(crawler, response)

        requests = [result for result in results if isinstance(result, Request)]
        assert {(request.meta["company"], request.meta["filer"]) for request in requests} == {
            ("nvidia", "0001045810"),
            ("nvidia", "0002222222"),
        }
        ticker = next(request for request in requests if request.meta["filer"] == "0001045810")
        assert ticker.meta["ticker"] == "NVDA"
        assert ticker.url == "https://data.sec.gov/submissions/CIK0001045810.json"
        assert not [result for result in results if isinstance(result, dict)]

    async def test_a_filer_stating_the_listed_ticker_is_verified(
        self, crawler: SecIdentityCrawler, crawl_page: CrawlPage, company_page: CompanyPage
    ) -> None:
        meta: Dict[str, JsonValue] = {
            "step": "submissions",
            "company": "nvidia",
            "filer": "0001045810",
            "ticker": "NVDA",
            "reason": "its ticker NVDA is a listing of the company",
        }
        response = company_page(
            SecIdentityCrawler.SUBMISSIONS_URL.format(cik="0001045810"), "sec-submissions-nvidia.json", meta
        )

        (item,) = await crawl_page(crawler, response)

        assert isinstance(item, dict)
        assert item["kind"] == "identity"
        assert item["identifier_kind"] == "sec-cik"
        assert item["value"] == "0001045810"
        assert item["verified"] is True
        assert item["label"] == "NVIDIA CORP"
        assert item["evidence_url"] == "https://www.sec.gov/edgar/browse/?CIK=1045810"

    async def test_a_filer_matched_on_its_name_waits_for_a_person(
        self, crawler: SecIdentityCrawler, crawl_page: CrawlPage, company_page: CompanyPage
    ) -> None:
        meta: Dict[str, JsonValue] = {
            "step": "submissions",
            "company": "nvidia",
            "filer": "0002222222",
            "ticker": "",
            "reason": "its name is the company's",
        }
        response = company_page(
            SecIdentityCrawler.SUBMISSIONS_URL.format(cik="0002222222"), "sec-submissions-other.json", meta
        )

        (item,) = await crawl_page(crawler, response)

        assert isinstance(item, dict)
        assert item["verified"] is False


class TestOpenAlexIdentityCrawler:
    @pytest.fixture
    def crawler(
        self,
        companies_catalog: CompaniesCatalog,
        financial_concepts: FinancialConcepts,
        markets_catalog: MarketsCatalog,
        monkeypatch: pytest.MonkeyPatch,
    ) -> OpenAlexIdentityCrawler:
        for variable in companies_catalog.openalex.key_envs:
            monkeypatch.delenv(variable, raising=False)
        monkeypatch.setenv(companies_catalog.openalex.mailto_env, "me@example.com")
        return OpenAlexIdentityCrawler(
            companies_catalog, financial_concepts, markets_catalog, CrawlScope(companies="ibm")
        )

    async def test_each_company_is_searched_by_its_name(self, crawler: OpenAlexIdentityCrawler) -> None:
        (request,) = [request async for request in crawler.start_requests()]

        assert request.url.startswith("https://api.openalex.org/institutions?search=IBM&filter=type:company")
        assert "mailto=me%40example.com" in request.url
        assert request.meta["company"] == "ibm"

    async def test_only_new_top_level_institutions_of_the_name_are_proposed(
        self, crawler: OpenAlexIdentityCrawler, crawl_page: CrawlPage, company_page: CompanyPage
    ) -> None:
        response = company_page(OpenAlexIdentityCrawler.URL, "openalex-institutions-ibm.json", {"company": "ibm"})

        items = await crawl_page(crawler, response)

        assert [item["value"] for item in items if isinstance(item, dict)] == ["I888000001"]
        (item,) = items
        assert isinstance(item, dict)
        assert item["verified"] is False
        assert item["kind"] == "identity"
        assert item["evidence_url"] == "https://openalex.org/I888000001"


def test_the_resolvers_are_built_by_the_factory() -> None:
    factory = CrawlerFactory()

    assert isinstance(factory.get_companies(CompanyFeed.SEC_IDENTITY), SecIdentityCrawler)
    assert isinstance(factory.get_companies(CompanyFeed.OPENALEX_IDENTITY), OpenAlexIdentityCrawler)
