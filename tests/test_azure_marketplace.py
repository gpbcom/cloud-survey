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
from crawler.cloud.azure.marketplace import AzureMarketplaceCrawler
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
Results = List[Union[Dict[str, JsonValue], Request]]
FIXTURES = Path(__file__).parent / "fixtures" / "marketplace"
TILES = "https://marketplace.microsoft.com/view/tiledata"
QUERY = "ReviewsMyCommentsFilter=true&country=US&entityType=App&region=ALL"
SEARCH = "https://marketplace.microsoft.com/en-us/search/products"
PRODUCT = "https://marketplace.microsoft.com/en-us/product/"


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


@pytest.fixture
def crawler(classifier: SoftwareClassifier) -> AzureMarketplaceCrawler:
    return AzureMarketplaceCrawler(classifier=classifier)


def response(url: str, content: Union[bytes, str], meta: Optional[Dict[str, JsonValue]] = None) -> Response:
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


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def tiles_page(
    content: Union[bytes, str],
    page: int = 1,
    filters: Optional[Dict[str, str]] = None,
    labels: Optional[List[str]] = None,
) -> Response:
    query_filters: Dict[str, JsonValue] = dict(filters or {})
    query_labels: List[JsonValue] = list(labels or [])
    meta: Dict[str, JsonValue] = {"page": page, "filters": query_filters, "labels": query_labels}
    if filters and page == 1:
        meta["may_be_empty"] = True
    return response(f"{TILES}?{QUERY}&page={page}", content, meta)


def tiles_of(tiles: List[Dict[str, JsonValue]], count: Optional[int] = 1000) -> str:
    return json.dumps({"apps": {"galleryTiles": list(tiles), "count": count}})


def tile(
    title: Optional[str] = "Acme Recruit", offer_type: JsonValue = "SaaS", **extra: JsonValue
) -> Dict[str, JsonValue]:
    entry: Dict[str, JsonValue] = {
        "entityId": "acme.recruit",
        "title": title,
        "shortDescription": "Hire the best candidates.",
        "publisher": "Acme",
        "categoriesDetails": [],
        "catalogOfferType": offer_type,
    }
    entry.update(extra)
    return entry


def software(results: Results) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def requests(results: Results) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def types(item: Dict[str, JsonValue]) -> List[str]:
    values = item["types"]
    assert isinstance(values, list)
    return [str(value) for value in values]


def test_configuration(crawler: AzureMarketplaceCrawler) -> None:
    assert crawler.name == "azure-marketplace"
    assert AzureMarketplaceCrawler.catalogue_url == f"{TILES}?{QUERY}&page=1"
    assert AzureMarketplaceCrawler.complement_urls == (SEARCH,)
    assert crawler.allowed_domains == {"marketplace.microsoft.com"}


async def test_starts_with_every_app_then_the_taxonomy(crawler: AzureMarketplaceCrawler) -> None:
    started = [request async for request in crawler.start_requests()]

    assert [(request.url, request.priority, request.sid, request.meta) for request in started] == [
        (
            f"{TILES}?{QUERY}&page=1",
            AzureMarketplaceCrawler.PRIMARY_PRIORITY,
            "azure-marketplace-http",
            {"page": 1, "filters": {}, "labels": []},
        ),
        (SEARCH, 0, "", {}),
    ]
    assert started[0]._session_kwargs == {"method": "GET", "json": None, "headers": None}


async def test_extracts_the_apps(crawler: AzureMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, tiles_page(fixture("azure_tiles.json")))

    found = software(results)
    assert [(item["name"], item["delivery"]) for item in found] == [
        ("Jira Cloud for Outlook (Official)", "saas"),
        ("HubSpot Sales", "saas"),
        ("Deneb: Declarative Visualization in Power BI", "saas"),
        ("Ubuntu 24.04 LTS - all plans including Ubuntu Pro", "virtual-machine"),
        ("M365 Connector for Claude by Anthropic", "saas"),
        ("Advanced Landed Cost", "saas"),
        ("Altana", "saas"),
        ("Fortinet FortiGate Next-Generation Firewall", "other"),
    ]
    jira = found[0]
    assert jira["url"] == f"{PRODUCT}wa200000056"
    assert jira["publisher"] == "Atlassian.com"
    assert jira["description"] == "Organize your team\u2019s work without leaving your inbox"
    assert jira["marketplace_categories"] == []
    assert found[3]["marketplace_categories"] == ["Infrastructure Services", "IT & Management Tools"]
    assert "operating-system" in types(found[3])
    assert found[5]["url"] == (
        f"{PRODUCT}pubid.thetasystemslimited%7caid.advanced_landed_cost%7cpappid.8ebdc541-0ea9-415e-9532-b25b8ebdc541"
    )
    assert "security" in types(found[7])


async def test_skips_the_managed_services(
    crawler: AzureMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    results = await crawl_page(crawler, tiles_page(fixture("azure_tiles.json")))

    assert "ACP Azure Lighthouse Onboarding - PAL" not in [item["name"] for item in software(results)]
    assert (
        "Skipping the azure-marketplace app 'ACP Azure Lighthouse Onboarding - PAL', a service (ManagedServices)."
        in caplog.messages
    )


@pytest.mark.parametrize(
    ("offer_type", "delivery"),
    [
        ("Containers", "container"),
        ("ContainerApps", "container"),
        ("IotEdgeModules", "container"),
        ("SolutionTemplate", "other"),
        ("ManagedApplication", "other"),
        ("Dynamics365ForFinance", "saas"),
        ("NewOfferType", "other"),
        (None, "other"),
    ],
)
async def test_delivery_mapping(
    crawler: AzureMarketplaceCrawler, crawl_page: CrawlPage, offer_type: JsonValue, delivery: str
) -> None:
    results = await crawl_page(crawler, tiles_page(tiles_of([tile(offer_type=offer_type)])))

    assert [item["delivery"] for item in software(results)] == [delivery]


async def test_category_query_labels_the_apps(crawler: AzureMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    filters = {"category": "human-resources", "subcategories": "talent-acquisition"}
    labels = ["Human Resources", "Talent Acquisition"]

    results = await crawl_page(crawler, tiles_page(fixture("azure_tiles_category.json"), 1, filters, labels))

    found = software(results)
    assert [(item["name"], item["marketplace_categories"]) for item in found] == [
        ("Dynamics ATS Recruiting", ["Human Resources", "Sales", "Talent Acquisition"]),
        ("Volunteer Engagement", ["Human Resources", "Talent Acquisition"]),
        ("X0PA ROOM", ["Human Resources", "Talent Acquisition"]),
        ("Employee onboarding Autopilot", ["Human Resources", "Talent Acquisition"]),
    ]
    assert "ats" in types(found[0])
    [next_page] = requests(results)
    assert next_page.url == f"{TILES}?{QUERY}&category=human-resources&subcategories=talent-acquisition&page=2"
    assert (next_page.priority, next_page.meta) == (0, {"page": 2, "filters": filters, "labels": labels})


async def test_category_query_streams_known_apps_again(crawler: AzureMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    first = await crawl_page(crawler, tiles_page(fixture("azure_tiles_category.json")))
    tagged = await crawl_page(
        crawler, tiles_page(fixture("azure_tiles_category.json"), 1, {"category": "Sales"}, ["Sales"])
    )
    again = await crawl_page(
        crawler, tiles_page(fixture("azure_tiles_category.json"), 1, {"category": "Sales"}, ["Sales"])
    )

    assert len(software(first)) == 4
    assert [(item["name"], item["marketplace_categories"]) for item in software(tagged)] == [
        ("Volunteer Engagement", ["Human Resources", "Sales"]),
        ("X0PA ROOM", ["Human Resources", "Sales"]),
        ("Employee onboarding Autopilot", ["Human Resources", "Sales"]),
    ]
    assert software(again) == []


async def test_taxonomy_requests_the_category_queries(crawler: AzureMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, response(SEARCH, fixture("azure_search.html")))

    sent = requests(results)
    assert len(results) == len(sent)
    assert [(request.url.removeprefix(f"{TILES}?{QUERY}&"), request.meta["labels"]) for request in sent] == [
        ("category=human-resources&subcategories=talent-acquisition&page=1", ["Human Resources", "Talent Acquisition"]),
        ("category=human-resources&subcategories=talent-management&page=1", ["Human Resources", "Talent Management"]),
        ("category=devops&page=1", ["DevOps"]),
        ("category=microsoft-entra-id&subcategories=crm&page=1", ["Microsoft Entra ID", "CRM"]),
        ("category=microsoft-entra-id&subcategories=media&page=1", ["Microsoft Entra ID", "Media"]),
    ]
    assert {(request.priority, request.meta["may_be_empty"], request.sid) for request in sent} == {
        (0, True, "azure-marketplace-http")
    }


async def test_taxonomy_fallbacks(crawler: AzureMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    state = {"apps": {"dataMap": {"categories": {"web": {"SubCategoryDataMapping": {"blogs": {}}}, "iot": "bad"}}}}
    page = f"<script>window.__INITIAL_STATE__ = {json.dumps(state)};</script>"

    sent = requests(await crawl_page(crawler, response(SEARCH, page)))

    assert [(request.url.removeprefix(f"{TILES}?{QUERY}&"), request.meta["labels"]) for request in sent] == [
        ("category=web&subcategories=blogs&page=1", ["web", "blogs"]),
        ("category=iot&page=1", ["iot"]),
    ]


@pytest.mark.parametrize(
    ("page", "reason"),
    [
        ("<html><body>No state</body></html>", "no `__INITIAL_STATE__` script"),
        ("<script>window.__INITIAL_STATE__ = {broken</script>", "the `__INITIAL_STATE__` script is not JSON"),
        ('<script>window.__INITIAL_STATE__ = {"apps": {"dataMap": {}}};</script>', "no `apps.dataMap.categories`"),
        ("<script>window.__INITIAL_STATE__ = [];</script>", "no `apps.dataMap.categories`"),
    ],
)
async def test_bad_taxonomy_page(
    crawler: AzureMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, page: str, reason: str
) -> None:
    with pytest.raises(CatalogueFormatError, match=reason):
        await crawl_page(crawler, response(SEARCH, page))

    assert any(record.levelno == logging.ERROR and SEARCH in record.getMessage() for record in caplog.records)


async def test_requests_the_next_page_of_every_app(crawler: AzureMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, tiles_page(fixture("azure_tiles.json")))

    [next_page] = requests(results)
    assert results[-1] is next_page
    assert (next_page.url, next_page.priority, next_page.meta) == (
        f"{TILES}?{QUERY}&page=2",
        AzureMarketplaceCrawler.PRIMARY_PRIORITY,
        {"page": 2, "filters": {}, "labels": []},
    )


@pytest.mark.parametrize(
    ("content", "page"),
    [
        (fixture("azure_tiles_last.json"), 1346),
        (tiles_of([tile()], None), 1),
        (tiles_of([], 1000), 1),
    ],
)
async def test_last_page(
    crawler: AzureMarketplaceCrawler, crawl_page: CrawlPage, content: Union[bytes, str], page: int
) -> None:
    results = await crawl_page(crawler, tiles_page(content, page, {"category": "devops"}, ["DevOps"]))

    assert requests(results) == []


async def test_page_limit_applies_per_query(crawler: AzureMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    with patch.object(AzureMarketplaceCrawler, "page_limit", 2):
        beyond = await crawl_page(crawler, tiles_page(tiles_of([tile()]), 2))
        other_query = await crawl_page(crawler, tiles_page(tiles_of([tile()]), 1, {"category": "devops"}, ["DevOps"]))

    assert requests(beyond) == []
    assert [request.meta["page"] for request in requests(other_query)] == [2]


async def test_malformed_tiles(
    crawler: AzureMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    tiles: List[JsonValue] = [
        "not a tile",
        tile(None, entityId="acme.untitled"),
        tile("Acme No Id", entityId=None, categoriesDetails="bad"),
        tile("Acme Upper", entityId="Acme.Upper", categoriesDetails=["bad", {"longTitle": "Security"}]),
    ]

    results = await crawl_page(crawler, tiles_page(json.dumps({"apps": {"galleryTiles": tiles, "count": 4}})))

    assert [(item["name"], item["url"], item["marketplace_categories"]) for item in software(results)] == [
        ("Acme No Id", None, []),
        ("Acme Upper", f"{PRODUCT}acme.upper", ["Security"]),
    ]
    assert any(record.levelno == logging.WARNING for record in caplog.records)


@pytest.mark.parametrize("content", ['{"apps": {"count": 3}}', "[]"])
async def test_page_without_tiles(
    crawler: AzureMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, content: str
) -> None:
    with pytest.raises(CatalogueFormatError, match=r"`apps.galleryTiles` is not a list"):
        await crawl_page(crawler, tiles_page(content))

    assert any(record.levelno == logging.ERROR and "galleryTiles" in record.getMessage() for record in caplog.records)


async def test_empty_page_of_every_app_is_an_error(
    crawler: AzureMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(crawler, tiles_page(tiles_of([])))

    assert any(record.levelno == logging.ERROR for record in caplog.records)
