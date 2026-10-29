from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.companies.figure_documents.crawler import FigureDocumentsCrawler
from curated.bundle.bundle_catalogs import BundleCatalogs
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.markets.crawl_scope import CrawlScope
from models.markets.markets_catalog import MarketsCatalog

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
CompanyPage = Callable[..., Response]
FORTUNE = "https://web.archive.org/web/20120315140024id_/http://money.cnn.com/magazines/fortune/fortune500_archive/snapshots/1981/676.html"


@pytest.fixture
def crawler(
    companies_catalog: CompaniesCatalog, financial_concepts: FinancialConcepts, markets_catalog: MarketsCatalog
) -> FigureDocumentsCrawler:
    return FigureDocumentsCrawler(companies_catalog, financial_concepts, markets_catalog, CrawlScope(companies="ibm"))


async def test_each_readable_document_is_requested_once(crawler: FigureDocumentsCrawler) -> None:
    requests = [request async for request in crawler.start_requests()]

    entry = BundleCatalogs().figures().of("ibm")
    assert entry is not None
    readable = {year.source for year in entry.years if crawler._readable(year.source)}
    assert {request.url for request in requests} == readable
    assert all(not request.url.endswith(".pdf") for request in requests)
    fortune = next(request for request in requests if request.url == FORTUNE)
    assert fortune.meta["fiscal-years"] == [1980]
    assert fortune.meta["company"] == "ibm"


@pytest.mark.parametrize(
    ("url", "readable"),
    [
        ("https://www.sec.gov/Archives/edgar/data/28887/0000028887-94-000022.txt", True),
        (FORTUNE, True),
        ("https://web.archive.org/web/2001/http://www.ibm.com/annualreport/1999.pdf", False),
        ("https://archive.org/details/bitsavers_datamation_40372807", False),
        ("https://www.ibm.com/investor/1999.html", False),
    ],
)
def test_only_text_documents_of_the_archives_are_read(
    crawler: FigureDocumentsCrawler, url: str, readable: bool
) -> None:
    assert crawler._readable(url) is readable


async def test_the_numbers_of_a_page_are_streamed_without_its_markup(
    crawler: FigureDocumentsCrawler, crawl_page: CrawlPage, company_page: CompanyPage
) -> None:
    meta: Dict[str, JsonValue] = {"company": "ibm", "fiscal-years": [1980], "source": FORTUNE}

    (item,) = await crawl_page(crawler, company_page(FORTUNE, "figures-fortune-snapshot.html", meta))

    assert isinstance(item, dict)
    assert item["kind"] == "document-numbers"
    numbers = item["numbers"]
    assert isinstance(numbers, list)
    assert {26213.0, 3562.0, 26703.0, 16453.0, 341279.0, 8.0} <= set(numbers)
    assert 600.0 not in numbers
    assert 98765.0 not in numbers
    assert item["fiscal_years"] == [1980]


async def test_a_text_filing_gives_its_numbers_without_sign(
    crawler: FigureDocumentsCrawler, crawl_page: CrawlPage, company_page: CompanyPage
) -> None:
    url = "https://www.sec.gov/Archives/edgar/data/28887/0000028887-94-000022.txt"
    meta: Dict[str, JsonValue] = {"company": "ibm", "fiscal-years": [1993, 1994], "source": url}

    (item,) = await crawl_page(crawler, company_page(url, "figures-sec-10k.txt", meta))

    assert isinstance(item, dict)
    assert {5583912.0, 329121.0, 172500.0, 79800.0, 1994.0} <= set(item["numbers"])  # type: ignore[arg-type]


async def test_a_document_gone_gives_no_number(
    crawler: FigureDocumentsCrawler, crawl_page: CrawlPage, company_page: CompanyPage
) -> None:
    meta: Dict[str, JsonValue] = {"company": "ibm", "fiscal-years": [1980], "source": FORTUNE}

    (item,) = await crawl_page(crawler, company_page(FORTUNE, "", meta, status=404))

    assert isinstance(item, dict)
    assert item["numbers"] == []
