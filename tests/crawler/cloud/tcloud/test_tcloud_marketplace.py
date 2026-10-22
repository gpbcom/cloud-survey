from __future__ import annotations

import json
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.tcloud.marketplace import TCloudPublicMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parents[3] / "fixtures" / "marketplace"
API = "https://marketplace.t-cloud-public.com/api/v1/client"


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


@pytest.fixture
def crawler(classifier: SoftwareClassifier) -> TCloudPublicMarketplaceCrawler:
    return TCloudPublicMarketplaceCrawler(classifier=classifier)


def response(url: str, content: Union[str, bytes], meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url,
        content=content,
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
        meta=meta or {},
    )


def categories_page(content: Optional[Union[str, bytes]] = None) -> Response:
    content = content if content is not None else (FIXTURES / "tcloud_categories.json").read_bytes()
    return response(f"{API}/categories", content, {"categories": True})


def products_page(content: Optional[Union[str, bytes]] = None) -> Response:
    return response(f"{API}/products", content or (FIXTURES / "tcloud_products.json").read_bytes())


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [item["name"] for item in items(results)]


async def crawl(crawler: TCloudPublicMarketplaceCrawler, crawl_page: CrawlPage) -> List[Dict[str, JsonValue]]:
    await crawl_page(crawler, categories_page())
    return items(await crawl_page(crawler, products_page()))


def test_configuration(crawler: TCloudPublicMarketplaceCrawler) -> None:
    assert crawler.name == "tcloud-marketplace"
    assert TCloudPublicMarketplaceCrawler.catalogue_url == f"{API}/products"
    assert crawler.CATEGORIES_URL.endswith("/api/v1/client/categories")
    assert TCloudPublicMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"marketplace.t-cloud-public.com"}
    assert crawler.category_names == {}


async def test_starts_with_the_categories(crawler: TCloudPublicMarketplaceCrawler) -> None:
    requests = [request async for request in crawler.start_requests()]

    assert [(request.url, request.priority, request.meta) for request in requests] == [
        (f"{API}/categories", TCloudPublicMarketplaceCrawler.PRIMARY_PRIORITY, {"categories": True})
    ]


async def test_categories_then_request_the_products(
    crawler: TCloudPublicMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(crawler, categories_page())

    assert [(result.url, result.priority) for result in results if isinstance(result, Request)] == [
        (f"{API}/products", TCloudPublicMarketplaceCrawler.PRIMARY_PRIORITY)
    ]
    assert len(results) == 1
    assert len(crawler.category_names) == 19
    assert crawler.category_names["Ld3HP4UUqDMPzA8qaafOf"] == "Artificial Intelligence"


async def test_extracts_the_software(crawler: TCloudPublicMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    software = await crawl(crawler, crawl_page)

    assert [item["name"] for item in software] == [
        "Managed Container Stack (MCS) OpenShift",
        "LLM Serving Service (TCP Models)",
        "OTC prometheus-exporterv1",
        "Airlock Microgateway",
        "d.velop invoices",
        "Keycloak as a Service",
        "Codesphere",
    ]
    assert software[1] == {
        "name": "LLM Serving Service (TCP Models)",
        "description": software[1]["description"],
        "publisher": "AI Foundation Services",
        "url": "https://marketplace.t-cloud-public.com/product-offering/g2chzNTJzN5HTINwEkE5z",
        "delivery": "ai-model",
        "marketplace_categories": ["Artificial Intelligence", "LLM HUB"],
        "marketplace_category_paths": [
            {"path": ["Artificial Intelligence"], "id": "Ld3HP4UUqDMPzA8qaafOf"},
            {"path": ["LLM HUB"], "id": "O1Ptu2y5fcEwhUc4PZRKR"},
        ],
        "categories": ["developer-tool", "end-user-software"],
        "added_at": "2025-05-16T15:31:00Z",
    }
    assert str(software[1]["description"]).startswith("LLM Serving Service provides access to large language")


@pytest.mark.parametrize(
    "excluded",
    [
        "Migration Service",
        "Cloud Assessment",
        "Detecon Sovereign Cloud Assessment",
        "Atos Cloud Transformation Services",
        "Enterprise Backup & Disaster Recovery",
    ],
)
async def test_professional_services_are_excluded(
    crawler: TCloudPublicMarketplaceCrawler, crawl_page: CrawlPage, excluded: str
) -> None:
    assert excluded not in [item["name"] for item in await crawl(crawler, crawl_page)]


@pytest.mark.parametrize(
    ("name", "delivery", "audiences"),
    [
        ("Managed Container Stack (MCS) OpenShift", "saas", ["developer-tool"]),
        ("OTC prometheus-exporterv1", "container", ["developer-tool"]),
        ("Airlock Microgateway", "container", ["developer-tool"]),
        ("d.velop invoices", "saas", ["developer-tool", "end-user-software"]),
    ],
)
async def test_delivery_and_audiences(
    crawler: TCloudPublicMarketplaceCrawler, crawl_page: CrawlPage, name: str, delivery: str, audiences: List[str]
) -> None:
    software = next(item for item in await crawl(crawler, crawl_page) if item["name"] == name)

    assert (software["delivery"], software["categories"]) == (delivery, audiences)


async def test_malformed_entries(crawler: TCloudPublicMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    await crawl_page(crawler, categories_page(json.dumps([{"id": "c1", "name": "Monitoring"}, {"id": "c2"}, "c3"])))
    products = [
        {
            "name": "Long only",
            "description": "<p>Long &amp; rich</p>",
            "categories": ["c1", "c2", 3],
            "type": "x",
            "created_at": "not a date",
        },
        {"name": "No description", "id": "p2", "description_short": " ", "categories": None, "seller": "Acme"},
        "not a product",
    ]

    software = items(await crawl_page(crawler, products_page(json.dumps(products))))

    assert [
        (
            item["name"],
            item["description"],
            item["url"],
            item["publisher"],
            item["delivery"],
            item["marketplace_categories"],
        )
        for item in software
    ] == [("Long only", "Long & rich", None, None, "other", ["Monitoring"])]
    assert software[0]["marketplace_category_paths"] == [{"path": ["Monitoring"], "id": "c1"}]
    assert "added_at" not in software[0]


async def test_only_services_is_an_empty_page(
    crawler: TCloudPublicMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    await crawl_page(crawler, categories_page())
    products = [{"name": "Landing Zone", "description_short": "Build", "categories": ["tINtYYC6YKzSc_OHa7F5-"]}]

    with pytest.raises(EmptyCatalogueError):
        await crawl_page(crawler, products_page(json.dumps(products)))

    assert any(record.levelname == "ERROR" and "holds no software" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("page", [categories_page(json.dumps({"items": []})), products_page(json.dumps({"a": 1}))])
async def test_non_array_responses_are_errors(
    crawler: TCloudPublicMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, page: Response
) -> None:
    with pytest.raises(CatalogueFormatError, match="the response is not a JSON array"):
        await crawl_page(crawler, page)

    assert [record.levelname for record in caplog.records].count("ERROR") == 1
