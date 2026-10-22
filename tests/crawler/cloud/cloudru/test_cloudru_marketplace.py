from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.cloudru.marketplace import CloudRuMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parents[3] / "fixtures" / "marketplace"
URL = "https://cloud.ru/marketplace"
PAGE_URL = "https://cloud.ru/marketplace/products/{slug}"
CATEGORIES: List[JsonValue] = [
    {"type": "mcp-servers", "displayName": "MCP-серверы", "slug": "mcp-servers", "cards": ["$18:props:cards:0"]},
    {"type": "analytics", "displayName": "Анализ событий и логов", "slug": "analytics", "cards": []},
]
# The Russian preposition meaning "with", escaped: ruff takes it for a confusable Latin letter.
WITH = "\N{CYRILLIC SMALL LETTER ES}"


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


@pytest.fixture
def crawler(classifier: SoftwareClassifier) -> CloudRuMarketplaceCrawler:
    return CloudRuMarketplaceCrawler(classifier=classifier)


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


def fixture_listing() -> Response:
    return response(URL, (FIXTURES / "cloudru_marketplace.html").read_bytes())


def listing(cards: List[JsonValue]) -> Response:
    data: JsonValue = ["$", "$L20", None, {"cards": cards, "categories": CATEGORIES}]
    stream = '1:"$Sreact.fragment"\n18:' + json.dumps(data) + "\n"
    return response(URL, f"<html><body><script>self.__next_f.push({json.dumps([1, stream])})</script></body></html>")


def card(name: str, slug: str, categories: List[JsonValue], **fields: JsonValue) -> Dict[str, JsonValue]:
    return {"displayName": name, "previewText": f"{name} описание", "slug": slug, "categories": categories, **fields}


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def product_page(request: Request, fixture: Optional[str], status: int = 200) -> Response:
    content = (FIXTURES / fixture).read_bytes() if fixture else b"<html><body>Not found</body></html>"
    return response(request.url, content, request.meta, status)


def test_configuration(crawler: CloudRuMarketplaceCrawler) -> None:
    assert crawler.name == "cloudru-marketplace"
    assert CloudRuMarketplaceCrawler.catalogue_url == URL
    assert CloudRuMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"cloud.ru"}


async def test_streams_the_console_software_of_the_listing(
    crawler: CloudRuMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(crawler, fixture_listing())

    assert [(item["name"], item["delivery"], item["marketplace_categories"]) for item in items(results)] == [
        ("Evolution Repo MCP", "api", ["MCP-серверы", "Разработка"]),
        ("VK MCP", "api", ["MCP-серверы", "Связи"]),
        ("Агент для составления документации по коду", "saas", ["AI-агенты", "Разработка"]),
    ]
    first = items(results)[0]
    assert first["description"] == "MCP-интерфейс к Repo Cloud.ru DevTools"
    assert first["url"] == (
        "https://console.cloud.ru/spa/ml-ai-agents/marketplace/mcp-server/7859d2db-7254-4eb5-a5b0-d316b7b97c83"
    )
    assert first["publisher"] is None
    assert first["marketplace_category_paths"] == [{"path": ["MCP-серверы", "Разработка"], "id": "Разработка"}]


async def test_requests_the_marketplace_pages_of_the_other_software(
    crawler: CloudRuMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(crawler, fixture_listing())

    pages = requests(results)
    assert [request.url for request in pages] == [
        PAGE_URL.format(slug="cilium"),
        PAGE_URL.format(slug="ubuntu-22-04"),
        PAGE_URL.format(slug="secure-dns"),
        PAGE_URL.format(slug="gitlab"),
    ]
    assert pages[3].meta[CloudRuMarketplaceCrawler.TAXONOMY] == {
        "dev-management": "Управление разработкой",
        "workspace": "Решения для бизнеса",
    }
    assert all(request.meta[CloudRuMarketplaceCrawler.MAY_BE_EMPTY] for request in pages)


async def test_a_marketplace_page_gives_the_publisher_and_the_dates(
    crawler: CloudRuMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    gitlab = requests(await crawl_page(crawler, fixture_listing()))[3]

    results = await crawl_page(crawler, product_page(gitlab, "cloudru_product_gitlab.html"))

    assert results == [
        {
            "name": "GitLab 18",
            "description": f"GitLab - мощный веб-инструмент жизненного цикла DevOps {WITH} открытым исходным кодом",
            "publisher": "GitLab Inc",
            "url": "https://cloud.ru/marketplace/products/gitlab",
            "delivery": "virtual-machine",
            "marketplace_categories": ["Управление разработкой", "Решения для бизнеса"],
            "marketplace_category_paths": [
                {"path": ["Управление разработкой"], "id": "dev-management"},
                {"path": ["Решения для бизнеса"], "id": "workspace"},
            ],
            "categories": ["developer-tool", "end-user-software"],
            "added_at": "2025-02-18T07:48:59.464491Z",
            "updated_at": "2026-05-28T12:16:03.555554Z",
            "updated_caveat": "catalogue-entry",
        }
    ]


async def test_a_blank_licence_owner_gives_no_publisher(
    crawler: CloudRuMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    cilium = requests(await crawl_page(crawler, fixture_listing()))[0]

    results = await crawl_page(crawler, product_page(cilium, "cloudru_product_cilium.html"))

    assert [(item["name"], item["publisher"], item["delivery"], item["added_at"]) for item in items(results)] == [
        ("Cilium", None, "kubernetes", "2024-09-16T13:23:14.727201Z")
    ]
    assert requests(results) == []


async def test_a_missing_marketplace_page_keeps_the_card(
    crawler: CloudRuMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    dns = requests(await crawl_page(crawler, fixture_listing()))[2]

    results = await crawl_page(crawler, product_page(dns, None, status=404))

    assert [(item["name"], item["delivery"], item.get("added_at")) for item in items(results)] == [
        ("BI.ZONE Secure DNS", "other", None)
    ]
    assert items(results)[0]["marketplace_categories"] == ["Анализ событий и логов", "Решения для бизнеса"]


async def test_a_page_without_record_keeps_the_card(
    crawler: CloudRuMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    ubuntu = requests(await crawl_page(crawler, fixture_listing()))[1]

    with caplog.at_level(logging.WARNING):
        results = await crawl_page(crawler, product_page(ubuntu, "cloudru_product_gitlab.html"))

    assert [(item["name"], item["publisher"], item["delivery"]) for item in items(results)] == [
        ("Ubuntu 22.04 LTS", None, "virtual-machine")
    ]
    assert "No software record" in caplog.text


async def test_streamed_software_is_not_requested_again(
    crawler: CloudRuMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    gitlab = requests(await crawl_page(crawler, fixture_listing()))[3]
    await crawl_page(crawler, product_page(gitlab, "cloudru_product_gitlab.html"))

    results = await crawl_page(crawler, fixture_listing())

    assert items(results) == []
    assert [request.url for request in requests(results)] == [
        PAGE_URL.format(slug="cilium"),
        PAGE_URL.format(slug="ubuntu-22-04"),
        PAGE_URL.format(slug="secure-dns"),
    ]


async def test_deliveries_and_unknown_categories(crawler: CloudRuMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    cards: List[JsonValue] = [
        card("Grafana", "", ["analytics", "unknown"], productTypes=[{"id": "docker-image"}], redirectUrl="/grafana"),
        card("Plugin", "", ["analytics"], productTypes=[{"id": "extension"}, {"id": "addons"}], redirectUrl="/p"),
        card("Search MCP", "", ["mcp-servers"], productTypes=[], selection="$18:props:cards:0:selection"),
    ]

    results = await crawl_page(crawler, listing(cards))

    assert [
        (item["name"], item["delivery"], item["url"], item["marketplace_categories"]) for item in items(results)
    ] == [
        ("Grafana", "container", "https://cloud.ru/grafana", ["Анализ событий и логов"]),
        ("Plugin", "kubernetes", "https://cloud.ru/p", ["Анализ событий и логов"]),
        ("Search MCP", "api", None, ["MCP-серверы"]),
    ]


async def test_invalid_cards_are_skipped(
    crawler: CloudRuMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    cards: List[JsonValue] = [
        card(" ", "", ["mcp-servers"], redirectUrl="https://console.cloud.ru/blank"),
        "$18:props:cards:4",
        card("Search MCP", "", ["mcp-servers"], redirectUrl="https://console.cloud.ru/search"),
    ]

    with caplog.at_level(logging.WARNING):
        results = await crawl_page(crawler, listing(cards))

    assert [item["name"] for item in items(results)] == ["Search MCP"]
    assert "invalid marketplace entry ' '" in caplog.text


async def test_empty_listing_is_an_error(
    crawler: CloudRuMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(EmptyCatalogueError):
        await crawl_page(crawler, listing([]))

    assert any(
        record.levelno == logging.ERROR and "lists no software" in record.getMessage() for record in caplog.records
    )


async def test_page_without_listing_is_a_format_error(
    crawler: CloudRuMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(CatalogueFormatError):
        await crawl_page(crawler, response(URL, "<html><body><h1>Маркетплейс</h1></body></html>"))

    assert any(
        record.levelno == logging.ERROR and "holds no flight data" in record.getMessage() for record in caplog.records
    )
