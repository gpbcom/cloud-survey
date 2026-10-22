from __future__ import annotations

import json
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.gcp.crawler import GoogleCloudPlatformCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
CATEGORY_URL = "https://cloud.google.com/products?pds=CAE"
MENU_LINK = (
    '<a track-type="nav" track-metadata-position="nav - products" href="{href}"><div>{name}</div>'
    "<div>{description}</div></a>"
)


def page(url: str, content: str) -> Response:
    return Response(url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def category_page(data: str) -> Response:
    script = f"AF_initDataCallback({{key: 'ds:1', hash: '2', data:{data}, sideChannel: {{}}}});"
    return page(CATEGORY_URL, f'<script class="ds:1">{script}</script>')


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = GoogleCloudPlatformCrawler()

    assert crawler.name == "gcp"
    assert GoogleCloudPlatformCrawler.catalogue_url == "https://cloud.google.com/products"
    assert GoogleCloudPlatformCrawler.complement_urls == ("https://cloud.google.com/products?hl=en",)
    assert crawler.allowed_domains == {"cloud.google.com"}


async def test_home_page_requests_the_category_pages(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        GoogleCloudPlatformCrawler(), make_response(GoogleCloudPlatformCrawler.catalogue_url, "gcp_products.html")
    )

    assert [(request.url, request.priority) for request in results if isinstance(request, Request)] == [
        ("https://cloud.google.com/products?pds=CAE", GoogleCloudPlatformCrawler.PRIMARY_PRIORITY),
        ("https://cloud.google.com/products?pds=CAU", GoogleCloudPlatformCrawler.PRIMARY_PRIORITY),
    ]
    assert [request.meta for request in results if isinstance(request, Request)] == [
        {GoogleCloudPlatformCrawler.CATEGORY_META: "AI and ML"},
        {GoogleCloudPlatformCrawler.CATEGORY_META: "Infrastructure"},
    ]
    assert names(results) == []


async def test_category_labels_prefer_the_tracking_label(crawl_page: CrawlPage) -> None:
    content = (
        '<button track-type="category-filter" data-category-id="4"'
        ' track-metadata-eventdetail="Databases and analytics">Databases</button>'
    )

    results = await crawl_page(GoogleCloudPlatformCrawler(), page(GoogleCloudPlatformCrawler.catalogue_url, content))

    assert [request.meta for request in results if isinstance(request, Request)] == [
        {GoogleCloudPlatformCrawler.CATEGORY_META: "Databases and analytics"}
    ]


async def test_home_page_without_category_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(CatalogueFormatError, match="no catalogue category"):
        await crawl_page(GoogleCloudPlatformCrawler(), page(GoogleCloudPlatformCrawler.catalogue_url, "<html></html>"))

    assert any(record.levelname == "ERROR" and "lists no category" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(("category_id", "code"), [(1, "CAE"), (5, "CAU"), (11, "CAs"), (127, "CH8"), (300, "CKwC")])
def test_category_codes(category_id: int, code: str) -> None:
    assert GoogleCloudPlatformCrawler()._category_code(category_id) == code


async def test_extracts_the_category_products(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(GoogleCloudPlatformCrawler(), make_response(CATEGORY_URL, "gcp_category.html"))

    assert results[0] == {
        "name": "Gemini platform",
        "description": "Unified platform for ML models, generative AI, and agent building.",
        "pricing_policy": [],
        "url": "https://cloud.google.com/products/gemini-enterprise-agent-platform",
    }
    assert names(results) == ["Gemini platform", "Gemini Code Assist", "Gemini for your business"]


async def test_category_products_are_filed_under_the_page_category_and_their_group(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    fixture = make_response(CATEGORY_URL, "gcp_category.html")
    response = Response(
        url=CATEGORY_URL,
        content=fixture.body,
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
        meta={GoogleCloudPlatformCrawler.CATEGORY_META: "AI/ML"},
    )

    results = await crawl_page(GoogleCloudPlatformCrawler(), response)

    assert [(result["name"], result["catalogue_categories"]) for result in results if isinstance(result, dict)] == [
        ("Gemini platform", ["AI/ML"]),
        ("Gemini Code Assist", ["AI/ML"]),
        ("Gemini for your business", ["AI/ML", "Other"]),
    ]


async def test_category_products_merge_the_groups_listing_them(crawl_page: CrawlPage) -> None:
    uuid = "6c1d3b4e-1f2a-4b5c-8d9e-0a1b2c3d4e5f"
    run: JsonValue = [
        uuid,
        [None, None, "https://cloud.google.com/run"],
        None,
        None,
        None,
        None,
        "Cloud Run",
        "Apps",
        0,
    ]
    tasks: JsonValue = [uuid, None, None, None, None, None, "Cloud Tasks", "Task queues", 0]
    groups: JsonValue = [
        [[run], None, "Featured", "Featured products", None, 1, 1],
        [[run, tasks], None, "Serverless", "Run code without servers.", None, 2, 1],
        [[run], None, "Containers", "", None, 3, 1],
    ]

    results = await crawl_page(GoogleCloudPlatformCrawler(), category_page(json.dumps([[groups]])))

    assert [(result["name"], result["catalogue_categories"]) for result in results if isinstance(result, dict)] == [
        ("Cloud Run", ["Serverless", "Containers"]),
        ("Cloud Tasks", ["Serverless"]),
    ]


async def test_former_names_are_remembered(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = GoogleCloudPlatformCrawler()
    await crawl_page(crawler, make_response(CATEGORY_URL, "gcp_category.html"))
    menu = MENU_LINK.format(href="https://cloud.google.com/vertex-ai", name="Vertex AI", description="ML platform")

    results = await crawl_page(crawler, page(GoogleCloudPlatformCrawler.MENU_URL, menu))

    assert results == []  # Already streamed under its new name, Gemini platform.
    assert {"vertexai", "geminiplatform"} <= crawler.seen_products


async def test_menu_completes_the_catalogue(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = GoogleCloudPlatformCrawler()
    await crawl_page(crawler, make_response(CATEGORY_URL, "gcp_category.html"))
    menu = "".join(
        MENU_LINK.format(href=href, name=name, description="Description")
        for href, name in [
            ("https://cloud.google.com/gemini-enterprise", "Gemini for business"),
            ("https://docs.cloud.google.com/products/gemini/code-assist", "Code Assist"),
            ("https://cloud.google.com/products/block-storage", "Block Storage"),
            ("https://cloud.google.com/solutions/active-assist", "Active Assist"),
            ("https://console.cloud.google.com/vertex-ai/model-garden", "Model Garden"),
            ("https://cloud.google.com/use-cases/data-analytics-agents", "Data Analytics Agents"),
        ]
    )

    results = await crawl_page(crawler, page(GoogleCloudPlatformCrawler.MENU_URL, menu))

    assert results == [
        {
            "name": "Block Storage",
            "description": "Description",
            "pricing_policy": [],
            "url": "https://cloud.google.com/products/block-storage",
        }
    ]


async def test_menu_alone(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        GoogleCloudPlatformCrawler(), make_response(GoogleCloudPlatformCrawler.MENU_URL, "gcp_products.html")
    )

    assert [(result["name"], result["catalogue_categories"]) for result in results if isinstance(result, dict)] == [
        ("Gemini for business", ["AI and Machine Learning"]),
        ("Gemini platform", ["AI and Machine Learning"]),
    ]


async def test_menu_categories_are_the_headlines_else_the_category_links(crawl_page: CrawlPage) -> None:
    header = '<a track-type="nav" track-metadata-position="nav - products" href="{href}"><div>{name}</div></a>'
    headline = (
        '<a track-type="nav" track-metadata-position="nav - products" track-metadata-module_headline="{headline}"'
        ' href="{href}"><div>{name}</div><div>Description</div></a>'
    )
    content = headline.format(headline="Featured Products", href="https://cloud.google.com/run", name="Cloud Run")
    content += header.format(href="https://cloud.google.com/serverless", name="Serverless")
    content += MENU_LINK.format(href="https://cloud.google.com/run", name="Cloud Run", description="Description")
    content += header.format(href="https://cloud.google.com/products?pds=CAc", name="See all serverless products")
    content += MENU_LINK.format(href="https://cloud.google.com/sql", name="Cloud SQL", description="Description")
    content += headline.format(headline="Media Services", href="https://cloud.google.com/cdn", name="Cloud CDN")

    results = await crawl_page(GoogleCloudPlatformCrawler(), page(GoogleCloudPlatformCrawler.MENU_URL, content))

    assert [(result["name"], result.get("catalogue_categories")) for result in results if isinstance(result, dict)] == [
        ("Cloud Run", ["Serverless"]),
        ("Cloud SQL", None),
        ("Cloud CDN", ["Media Services"]),
    ]


@pytest.mark.parametrize(
    ("data", "reason"),
    [(None, "is missing"), ("[not json", "is not JSON")],
)
async def test_category_page_without_catalogue_data(
    crawl_page: CrawlPage, data: Optional[str], reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    response = page(CATEGORY_URL, "<script>other()</script>") if data is None else category_page(data)

    with pytest.raises(CatalogueFormatError, match=reason):
        await crawl_page(GoogleCloudPlatformCrawler(), response)

    assert [record.levelname for record in caplog.records].count("ERROR") == 1


async def test_category_entries_are_validated(crawl_page: CrawlPage) -> None:
    uuid = "6c1d3b4e-1f2a-4b5c-8d9e-0a1b2c3d4e5f"
    entries: JsonValue = [
        [[uuid, [None, None, "https://cloud.google.com/run"], None, None, None, None, "Cloud Run", "Serverless", 0]],
        [["not-a-uuid", None, None, None, None, None, "Fake", "Fake", 0]],
        [[uuid, None, None, None, None, None, 7, "Numeric name", 0]],
        [[uuid, "no url", None, None, None, None, "Cloud Tasks", "Task queues", 0]],
        [[uuid, [None, None, ""], None, None, None, None, "Cloud Scheduler", "", 0]],
        "text",
    ]

    results = await crawl_page(GoogleCloudPlatformCrawler(), category_page(json.dumps(entries)))

    assert results == [
        {"name": "Cloud Run", "description": "Serverless", "pricing_policy": [], "url": "https://cloud.google.com/run"},
        {"name": "Cloud Tasks", "description": "Task queues", "pricing_policy": [], "url": None},
    ]


def test_former_names_formats() -> None:
    crawler = GoogleCloudPlatformCrawler()
    aliases: JsonValue = [["Vertex AI"], "Duet AI", [7, "Retail Search"]]
    entry: List[JsonValue] = [None] * 24
    entry.append(aliases)

    assert crawler._former_names(entry) == ["Vertex AI", "Duet AI", "Retail Search"]
    assert crawler._former_names([None] * 10) == []


async def test_ignores_other_menus(crawl_page: CrawlPage) -> None:
    content = (
        '<a track-type="nav" track-metadata-position="nav - solutions"><div>Retail</div><div>Solutions</div></a>'
        '<a track-type="other" track-metadata-position="nav - products"><div>Footer</div><div>Link</div></a>'
    )

    with pytest.raises(EmptyCatalogueError):
        await crawl_page(GoogleCloudPlatformCrawler(), page(GoogleCloudPlatformCrawler.MENU_URL, content))


async def test_skips_invalid_products(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    content = MENU_LINK.format(href="/run", name="x" * 201, description="Description")
    content += MENU_LINK.format(href="/run", name="Cloud Run", description="Description")

    results = await crawl_page(GoogleCloudPlatformCrawler(), page(GoogleCloudPlatformCrawler.MENU_URL, content))

    assert results == [
        {"name": "Cloud Run", "description": "Description", "pricing_policy": [], "url": "https://cloud.google.com/run"}
    ]
    assert any(record.levelname == "WARNING" for record in caplog.records)


@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("https://docs.cloud.google.com/run/docs", "cloud.google.com/run/docs"),
        ("https://cloud.google.com/run/docs/", "cloud.google.com/run/docs"),
    ],
)
def test_documentation_links_are_product_links(url: str, key: str) -> None:
    assert GoogleCloudPlatformCrawler()._url_key(url) == key
