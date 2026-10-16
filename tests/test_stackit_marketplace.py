from __future__ import annotations

import json
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Union
from unittest.mock import patch

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.stackit.marketplace import STACKITMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parent / "fixtures" / "marketplace"
API = "https://stackit-marketplace.api.stackit.cloud/v1/catalog/products"
LISTING = f"{API}?limit=100&locale=en"
CURSOR = (
    "eyJjdXJzb3JPcHRpb25zIjpbeyJmaWVsZCI6Im5hbWUiLCJkZXNjZW5kaW5nIjpmYWxzZSwidmFsdWUiOiJyb2NvbiBNSVNUUkFMIn1dLCJyZXNv"
    "dXJjZUlkIjoicm9jb24tbWlzdHJhbC1jN2I1YzdkZiJ9"
)


@pytest.fixture(scope="module")
def crawler() -> STACKITMarketplaceCrawler:
    return STACKITMarketplaceCrawler(classifier=SoftwareClassifier())


@pytest.fixture
def fresh(crawler: STACKITMarketplaceCrawler) -> STACKITMarketplaceCrawler:
    crawler.software_categories.clear()
    return crawler


def response(
    url: str, content: Union[str, bytes], meta: Optional[Dict[str, JsonValue]] = None, status: int = 200
) -> Response:
    return Response(
        url=url,
        content=content,
        status=status,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
        meta=meta or {},
    )


def listing(fixture: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return response(LISTING, (FIXTURES / fixture).read_bytes(), meta)


def detail(product: str, content: Union[str, bytes], status: int = 200) -> Response:
    url = f"{API}/{product}?locale=en"
    return response(url, content, {STACKITMarketplaceCrawler.PRODUCT: product, "may_be_empty": True}, status)


def detail_fixture(product: str, fixture: str) -> Response:
    return detail(product, (FIXTURES / fixture).read_bytes())


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def test_configuration(crawler: STACKITMarketplaceCrawler) -> None:
    assert crawler.name == "stackit-marketplace"
    assert STACKITMarketplaceCrawler.catalogue_url == LISTING
    assert STACKITMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"stackit-marketplace.api.stackit.cloud"}


async def test_first_page_requests_the_software_details_then_the_next_page(
    fresh: STACKITMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(fresh, listing("stackit_products_page1.json"))

    assert items(results) == []
    assert [(request.url, request.meta) for request in requests(results)] == [
        (f"{API}/ab-initio-d15a43bf?locale=en", {"product": "ab-initio-d15a43bf", "may_be_empty": True}),
        (
            f"{API}/akarion-grc-cloud-c5649585?locale=en",
            {"product": "akarion-grc-cloud-c5649585", "may_be_empty": True},
        ),
        (
            f"{API}/gft-enterprisegpt-3025dfb8?locale=en",
            {"product": "gft-enterprisegpt-3025dfb8", "may_be_empty": True},
        ),
        (f"{LISTING}&cursor={CURSOR}", {"page": 2, "may_be_empty": True}),
    ]
    assert requests(results)[-1].priority == STACKITMarketplaceCrawler.PRIMARY_PRIORITY


async def test_last_page_has_no_next_page(fresh: STACKITMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, listing("stackit_products_page2.json", {"page": 2, "may_be_empty": True}))

    assert [request.url for request in requests(results)] == [f"{API}/scoby-analytics-9107400b?locale=en"]


async def test_page_limit_stops_the_pagination(fresh: STACKITMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    with patch.object(STACKITMarketplaceCrawler, "page_limit", 1):
        results = await crawl_page(fresh, listing("stackit_products_page1.json"))

    assert all("cursor=" not in request.url for request in requests(results))


@pytest.mark.parametrize(
    ("product", "fixture", "expected"),
    [
        (
            "akarion-grc-cloud-c5649585",
            "stackit_product_akarion.json",
            {
                "name": "AKARION GRC Cloud",
                "publisher": "Akarion AG",
                "url": "https://marketplace.stackit.cloud/en/products/akarion-grc-cloud-c5649585",
                "delivery": "saas",
                "marketplace_categories": ["Business Applications", "Infrastructure Software", "Professional Services"],
                "types": ["legal-compliance", "ai-ml", "development"],
            },
        ),
        (
            "gft-enterprisegpt-3025dfb8",
            "stackit_product_enterprisegpt.json",
            {
                "name": "EnterpriseGPT",
                "publisher": "GFT Deutschland GmbH",
                "url": "https://marketplace.stackit.cloud/en/products/gft-enterprisegpt-3025dfb8",
                "delivery": "virtual-machine",
                "marketplace_categories": ["Business Applications", "Machine Learning"],
                "types": ["ai-ml"],
            },
        ),
        (
            "ab-initio-d15a43bf",
            "stackit_product_ab_initio.json",
            {
                "name": "Ab Initio® Data Platform",
                "publisher": "Ab Initio Software Germany GmbH",
                "url": "https://marketplace.stackit.cloud/en/products/ab-initio-d15a43bf",
                "delivery": "container",
                "marketplace_categories": [
                    "Business Applications",
                    "Data & AI",
                    "Infrastructure Software",
                    "Internet of Things",
                    "Machine Learning",
                    "Professional Services",
                ],
                "types": ["ai-ml", "iot"],
            },
        ),
    ],
)
async def test_detail_gives_the_software(
    fresh: STACKITMarketplaceCrawler,
    crawl_page: CrawlPage,
    product: str,
    fixture: str,
    expected: Dict[str, JsonValue],
) -> None:
    software = items(await crawl_page(fresh, detail_fixture(product, fixture)))

    assert len(software) == 1
    assert {key: software[0][key] for key in expected} == expected
    assert software[0]["description"]


async def test_streamed_software_details_are_not_requested_again(
    fresh: STACKITMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    await crawl_page(fresh, detail_fixture("akarion-grc-cloud-c5649585", "stackit_product_akarion.json"))

    results = await crawl_page(fresh, listing("stackit_products_page1.json"))

    assert f"{API}/akarion-grc-cloud-c5649585?locale=en" not in [request.url for request in requests(results)]


async def test_listing_entries_without_identifier_are_skipped(
    fresh: STACKITMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    page = {"items": [{"name": "No id", "deliveryMethod": "SAAS"}, "entry", {"productId": "a b/c"}], "cursor": ""}

    results = await crawl_page(fresh, response(LISTING, json.dumps(page)))

    assert [request.url for request in requests(results)] == [f"{API}/a%20b%2Fc?locale=en"]


@pytest.mark.parametrize(
    ("content", "status"),
    [
        (
            json.dumps(
                {"productId": "p1", "name": "Consulting", "summary": "Advice", "deliveryMethod": "PROFESSIONAL_SERVICE"}
            ),
            200,
        ),
        (json.dumps({"productId": "p1", "summary": "No name"}), 200),
        ("Not found", 404),
    ],
)
async def test_invalid_details_give_no_software(
    fresh: STACKITMarketplaceCrawler, crawl_page: CrawlPage, content: str, status: int
) -> None:
    assert await crawl_page(fresh, detail("p1", content, status)) == []


async def test_detail_without_identifier_or_categories(fresh: STACKITMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    content = json.dumps({"name": "Bare", "summary": "Bare product", "categories": None, "vendor": "Acme"})
    page = response(f"{API}/p1?locale=en", content, {STACKITMarketplaceCrawler.PRODUCT: ""})

    software = items(await crawl_page(fresh, page))

    assert [
        (item["url"], item["publisher"], item["delivery"], item["marketplace_categories"]) for item in software
    ] == [(None, None, "other", [])]


async def test_empty_first_page_is_an_error(
    fresh: STACKITMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(fresh, response(LISTING, json.dumps({"items": [], "cursor": "", "totalCount": 0})))

    assert any(record.levelname == "ERROR" and "lists no product" in record.getMessage() for record in caplog.records)


async def test_empty_next_page_is_allowed(fresh: STACKITMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    page = response(LISTING, json.dumps({"items": [], "cursor": ""}), {"page": 2, "may_be_empty": True})

    assert await crawl_page(fresh, page) == []


@pytest.mark.parametrize(
    ("page", "reason"),
    [
        (response(LISTING, json.dumps({"items": None})), "the page has no products list"),
        (response(LISTING, json.dumps([])), "the response is not a JSON object"),
        (response(LISTING, "<html></html>"), "the page is not JSON"),
        (detail("p1", json.dumps(["not", "an", "object"])), "the response is not a JSON object"),
    ],
)
async def test_malformed_responses_are_errors(
    fresh: STACKITMarketplaceCrawler,
    crawl_page: CrawlPage,
    caplog: pytest.LogCaptureFixture,
    page: Response,
    reason: str,
) -> None:
    with pytest.raises(CatalogueFormatError, match=reason):
        await crawl_page(fresh, page)

    assert [record.levelname for record in caplog.records].count("ERROR") == 1
