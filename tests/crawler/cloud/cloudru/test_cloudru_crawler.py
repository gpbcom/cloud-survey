from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.cloudru.crawler import CloudRuCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
URL = "https://cloud.ru/products"
INFRASTRUCTURE: Dict[str, JsonValue] = {"title": "Инфраструктура", "slug": "infrastructure"}
NETWORKS: Dict[str, JsonValue] = {"title": "Сети", "slug": "networks"}
POPULAR: Dict[str, JsonValue] = {"title": "Популярное", "slug": "popular"}
# The Russian preposition meaning "with", escaped: ruff takes it for a confusable Latin letter.
WITH = "\N{CYRILLIC SMALL LETTER ES}"
GPU_DATACENTER = f"VMware: виртуальный ЦОД {WITH} GPU"


def page(content: str) -> Response:
    return Response(url=URL, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def flight_page(rows: List[str], chunks: int = 1) -> Response:
    """A page pushing the flight data rows, split in some chunks (a row may be cut between two chunks)."""
    stream = "\n".join(rows) + "\n"
    size = -(-len(stream) // chunks)
    scripts = "".join(
        f"<script>self.__next_f.push({json.dumps([1, stream[start : start + size]])})</script>"
        for start in range(0, len(stream), size)
    )
    return page(f"<html><body><script>(self.__next_f=self.__next_f||[]).push([0])</script>{scripts}</body></html>")


def catalogue_page(products: List[JsonValue], chunks: int = 1) -> Response:
    data: JsonValue = ["$", "$L2c", None, {"categories": [POPULAR, INFRASTRUCTURE, NETWORKS], "products": products}]
    return flight_page(['1:"$Sreact.fragment"', "24:" + json.dumps(data)], chunks)


def product(title: str, slug: str, categories: List[JsonValue], **fields: JsonValue) -> Dict[str, JsonValue]:
    return {
        "title": title,
        "description": f"{title} описание",
        "customLink": "",
        "slug": slug,
        "available": True,
        "categories": categories,
        **fields,
    }


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = CloudRuCrawler()

    assert crawler.name == "cloudru"
    assert CloudRuCrawler.catalogue_url == URL
    assert CloudRuCrawler.complement_urls == ()
    assert CloudRuCrawler.dates_sitemaps == ()
    assert crawler.allowed_domains == {"cloud.ru"}


async def test_extracts_the_products_of_the_flight_data(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(CloudRuCrawler(), make_response(URL, "cloudru_products.html"))

    assert [item["name"] for item in items(results)] == [
        "Evolution Compute",
        "Evolution Data Platform",
        "Direct Connect",
        "Advanced Document Database Service with MongoDB",
        GPU_DATACENTER,
        "Advanced Relational Database Service for SQL Server",
    ]
    assert results[0] == {
        "name": "Evolution Compute",
        "description": "Виртуальные машины для развертывания сервисов и приложений",
        "pricing_policy": [],
        "url": "https://cloud.ru/products/evolution-compute",
        "catalogue_categories": ["Инфраструктура"],
    }
    assert len(results) == 6


async def test_products_are_filed_under_their_tabs_without_the_selection(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(CloudRuCrawler(), make_response(URL, "cloudru_products.html"))

    categories = {item["name"]: item.get("catalogue_categories") for item in items(results)}
    assert categories == {
        "Evolution Compute": ["Инфраструктура"],
        "Evolution Data Platform": None,
        "Direct Connect": ["Сети"],
        "Advanced Document Database Service with MongoDB": ["Базы данных", "Платформа данных", "Аналитика данных"],
        GPU_DATACENTER: ["Инфраструктура"],
        "Advanced Relational Database Service for SQL Server": ["Базы данных", "Платформа данных"],
    }


async def test_products_link_to_their_custom_link_else_their_page(crawl_page: CrawlPage) -> None:
    products: List[JsonValue] = [
        product("Evolution Compute", "evolution-compute", [INFRASTRUCTURE]),
        product("Cloud Advisor", "cloud-advisor", [NETWORKS], customLink="/advisor"),
        product("Partner", "partner", [NETWORKS], customLink="https://partner.example.com/cloud"),
    ]

    results = await crawl_page(CloudRuCrawler(), catalogue_page(products))

    assert [item["url"] for item in items(results)] == [
        "https://cloud.ru/products/evolution-compute",
        "https://cloud.ru/advisor",
        "https://partner.example.com/cloud",
    ]


async def test_rows_cut_between_chunks_are_joined(crawl_page: CrawlPage) -> None:
    products: List[JsonValue] = [
        product(f"Evolution Service {number}", f"service-{number}", [INFRASTRUCTURE]) for number in range(5)
    ]

    results = await crawl_page(CloudRuCrawler(), catalogue_page(products, chunks=4))

    assert len(items(results)) == 5


async def test_products_listed_several_times_gather_their_categories(crawl_page: CrawlPage) -> None:
    products: List[JsonValue] = [
        product("Evolution Compute", "evolution-compute", [POPULAR, INFRASTRUCTURE]),
        product("Direct Connect", "direct-connect", [NETWORKS]),
        product("Evolution  Compute", "evolution-compute", [NETWORKS, INFRASTRUCTURE]),
    ]

    results = await crawl_page(CloudRuCrawler(), catalogue_page(products))

    assert [(item["name"], item.get("catalogue_categories")) for item in items(results)] == [
        ("Evolution Compute", ["Инфраструктура", "Сети"]),
        ("Direct Connect", ["Сети"]),
    ]


async def test_invalid_and_unavailable_entries_are_skipped(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    products: List[JsonValue] = [
        product(" ", "blank", [INFRASTRUCTURE]),
        product("Retired", "retired", [INFRASTRUCTURE], available=False),
        "not a product",
        product("Direct Connect", "direct-connect", [NETWORKS, "$24:1:3:categories:2"]),
    ]

    with caplog.at_level(logging.WARNING):
        results = await crawl_page(CloudRuCrawler(), catalogue_page(products))

    assert [(item["name"], item.get("catalogue_categories")) for item in items(results)] == [
        ("Direct Connect", ["Сети"])
    ]
    assert any(
        record.levelno == logging.WARNING and "invalid catalogue entry ' '" in record.getMessage()
        for record in caplog.records
    )


async def test_empty_catalogue_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(EmptyCatalogueError):
        await crawl_page(CloudRuCrawler(), catalogue_page([]))

    assert any(
        record.levelno == logging.ERROR and "holds no product" in record.getMessage() for record in caplog.records
    )


async def test_page_without_catalogue_is_a_format_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(CatalogueFormatError):
        await crawl_page(CloudRuCrawler(), flight_page(['1:"$Sreact.fragment"', '2:{"children":[]}']))

    assert any(
        record.levelno == logging.ERROR and "holds no products catalogue" in record.getMessage()
        for record in caplog.records
    )


async def test_page_without_flight_data_is_a_format_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(CatalogueFormatError):
        await crawl_page(CloudRuCrawler(), page("<html><body><h1>Сервисы</h1></body></html>"))

    assert any(
        record.levelno == logging.ERROR and "holds no flight data" in record.getMessage() for record in caplog.records
    )
