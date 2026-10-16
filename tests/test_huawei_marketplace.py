from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Union
from unittest.mock import patch

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.huawei.marketplace import HuaweiMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parent / "fixtures" / "marketplace"
API_URL = "https://searchrec.marketplace-intl.huaweicloud.com/rest/mkp/v1/mkpsearchengineservice/search"
LOGGER = "scrapling.spiders.huawei-marketplace"


@pytest.fixture(scope="module")
def crawler() -> HuaweiMarketplaceCrawler:
    return HuaweiMarketplaceCrawler(classifier=SoftwareClassifier())


@pytest.fixture
def fresh(crawler: HuaweiMarketplaceCrawler) -> HuaweiMarketplaceCrawler:
    crawler.software_categories.clear()
    return crawler


def response(content: Union[str, bytes], meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=API_URL,
        content=content,
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
        meta=meta or {},
    )


def fixture_page(fixture: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return response((FIXTURES / fixture).read_bytes(), meta)


def search_page(
    listings: List[JsonValue], total: JsonValue = 3, meta: Optional[Dict[str, JsonValue]] = None
) -> Response:
    return response(json.dumps({"total": total, "pagination": {"items": listings}}), meta)


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [item["name"] for item in items(results)]


def body(offset: int) -> Dict[str, JsonValue]:
    return {"aggs": {}, "filter": {}, "flow_id": "101002", "keyword": "", "limit": 100, "offset": offset}


def test_configuration(crawler: HuaweiMarketplaceCrawler) -> None:
    assert crawler.name == "huawei-marketplace"
    assert HuaweiMarketplaceCrawler.catalogue_url == API_URL
    assert HuaweiMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"searchrec.marketplace-intl.huaweicloud.com"}


async def test_start_requests_post_the_first_page(crawler: HuaweiMarketplaceCrawler) -> None:
    starts = [request async for request in crawler.start_requests()]

    assert len(starts) == 1
    assert (starts[0].url, starts[0].sid, starts[0].priority) == (API_URL, "huawei-marketplace-http", 10)
    assert starts[0].meta == {"page": 1}
    assert starts[0]._session_kwargs == {"method": "POST", "json": body(0), "headers": {"x-language": "en-us"}}


async def test_extracts_the_software(fresh: HuaweiMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, fixture_page("huawei_search_page1.json"))

    assert names(results) == [
        "Crawl4AI",
        "dataarc speech synthesis SaaS platform",
        "TrueWatch Observability-License",
        "EspoCRM Customer Relationship Management System",
        "Redmine Project Management System",
    ]
    assert items(results)[0] == {
        "name": "Crawl4AI",
        "description": (
            "An asynchronous web crawler and content extraction library designed for LLM scenarios, specifically "
            "cleaning and transforming web pages into structured content directly readable by large language models, "
            "serving RAG, AI Agents, and data pipelines."
        ),
        "publisher": "深圳华为云计算技术有限公司",
        "url": "https://marketplace.huaweicloud.com/intl/contents/372f04eb-8227-49a0-8b72-5413555a4eb0",
        "delivery": "virtual-machine",
        "marketplace_categories": ["AI Applications & Services", "Intelligent automation"],
        "categories": ["developer-tool", "end-user-software"],
        "types": ["ai-ml", "low-code"],
        "added_at": "2026-10-16T03:12:12Z",
        "updated_at": "2026-10-16T03:15:18Z",
    }
    assert not {"added_at", "updated_at"} & items(results)[1].keys()


@pytest.mark.parametrize(
    ("excluded", "reason"),
    [
        ("Mercurius Compliance Accelerator", "category Professional Services"),
        ("Fortface", "category Professional Services"),
        ("Websoft9 Cloud Database Service for Neo4j", "category Data"),
        ("Intelligent Inspection Robot", "delivery Hardware"),
        ("Cloud Disaster Recovery Suite", "delivery Professional Services"),
    ],
)
async def test_services_hardware_and_data_are_excluded(
    fresh: HuaweiMarketplaceCrawler,
    crawl_page: CrawlPage,
    caplog: pytest.LogCaptureFixture,
    excluded: str,
    reason: str,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    assert excluded not in names(await crawl_page(fresh, fixture_page("huawei_search_page1.json")))
    assert f"Skipping the huawei-marketplace listing {excluded!r}, not a software ({reason})." in caplog.messages


@pytest.mark.parametrize(
    ("name", "delivery", "publisher", "types"),
    [
        ("dataarc speech synthesis SaaS platform", "saas", "数创弧光\uff08深圳\uff09科技有限公司", ["media", "ai-ml"]),
        ("TrueWatch Observability-License", "download", "TRUEWATCH TECHNOLOGY INC PTE. LTD.", ["monitoring"]),
        ("EspoCRM Customer Relationship Management System", "virtual-machine", "深圳华为云计算技术有限公司", ["crm"]),
        ("Redmine Project Management System", "virtual-machine", "深圳华为云计算技术有限公司", ["project-management"]),
    ],
)
async def test_delivery_publisher_and_types(
    fresh: HuaweiMarketplaceCrawler,
    crawl_page: CrawlPage,
    name: str,
    delivery: str,
    publisher: str,
    types: List[str],
) -> None:
    results = await crawl_page(fresh, fixture_page("huawei_search_page1.json"))
    software = next(item for item in items(results) if item["name"] == name)

    actual = software["types"]
    assert (software["delivery"], software["publisher"]) == (delivery, publisher)
    assert isinstance(actual, list)
    assert [kind for kind in types if kind not in actual] == [], actual


async def test_requests_the_next_page(fresh: HuaweiMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, fixture_page("huawei_search_page1.json", {"page": 1}))

    (request,) = requests(results)
    assert results[-1] is request
    assert (request.url, request.priority, request.dont_filter) == (API_URL, 10, True)
    assert request.meta == {"page": 2, "may_be_empty": True}
    assert request._session_kwargs == {"method": "POST", "json": body(100), "headers": {"x-language": "en-us"}}


async def test_last_page_requests_nothing(fresh: HuaweiMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, fixture_page("huawei_search_last.json", {"page": 11, "may_be_empty": True}))

    assert names(results) == [
        "Yonyou YonSuite",
        "Cloudwise APM",
        "HK CN2 Anti-DDoS Server (800G China+10T Global)",
    ]
    assert requests(results) == []


async def test_page_past_the_end_is_empty(fresh: HuaweiMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, fixture_page("huawei_search_empty.json", {"page": 12, "may_be_empty": True}))

    assert results == []


async def test_page_limit_stops_the_pagination(fresh: HuaweiMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    with patch.object(HuaweiMarketplaceCrawler, "page_limit", 1):
        results = await crawl_page(fresh, fixture_page("huawei_search_page1.json", {"page": 1}))

    assert requests(results) == []
    assert len(items(results)) == 5


async def test_malformed_listings(fresh: HuaweiMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        fresh,
        search_page(
            [
                {
                    "title": "Bare",
                    "content_abstract": "Bare software",
                    "delivery_code_en": "Teleport",
                    "onshelf_time": "someday",
                    "update_time": 1792120518,
                },
                {"title": "Server", "content_abstract": "On a server", "delivery_code_en": "Cloud Server", "url": 3},
                {"title": "No description", "delivery_code": "saas"},
                "not a listing",
            ]
        ),
    )

    assert [(item["name"], item["delivery"], item["url"], item["publisher"]) for item in items(results)] == [
        ("Bare", "other", None, None),
        ("Server", "virtual-machine", None, None),
    ]
    assert "added_at" not in items(results)[0]
    assert items(results)[0]["updated_at"] == "2026-10-16T03:15:18Z"
    assert requests(results) == []


async def test_missing_pagination_is_an_empty_page(fresh: HuaweiMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, response(json.dumps({"total": 0, "pagination": None}), {"may_be_empty": True}))

    assert results == []


async def test_empty_first_page_is_an_error(
    fresh: HuaweiMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError, match="no product found"):
        await crawl_page(fresh, search_page([], total=0))

    assert any(record.levelname == "ERROR" and "holds no software" in record.message for record in caplog.records)


@pytest.mark.parametrize("content", ["[]", '{"total": "1065"}', "<html></html>"])
async def test_unexpected_page_is_an_error(
    fresh: HuaweiMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, content: str
) -> None:
    with pytest.raises(CatalogueFormatError, match="unexpected catalogue format"):
        await crawl_page(fresh, response(content))

    assert any(record.levelname == "ERROR" for record in caplog.records)
