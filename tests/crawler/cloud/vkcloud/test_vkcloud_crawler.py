from __future__ import annotations

import json
from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.vkcloud.crawler import VKCloudCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
URL = "https://cloud.vk.ru/cloud-platform/"
SITEMAP = "https://cloud.vk.ru/sitemap.xml"


def page(*rows: JsonValue) -> Response:
    """Build a catalogue page pushing some flight data rows, as the Next.js App Router pages do."""
    flight = "".join(f"{index:x}:{json.dumps(row, ensure_ascii=False)}\n" for index, row in enumerate(rows))
    script = f"<script>self.__next_f.push({json.dumps([1, flight], ensure_ascii=False)})</script>"
    return Response(
        url=URL,
        content=f"<html><body>{script}</body></html>",
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
    )


def catalogue(*groups: JsonValue) -> JsonValue:
    return ["$", "$L1a", None, {"catalog": {"items": list(groups)}}]


def menu(*groups: JsonValue) -> JsonValue:
    return ["$", "header", None, {"apiData": {"items": [{"__component": "header.header-menu", "items": list(groups)}]}}]


def card(title: str, text: str, href: str) -> Dict[str, JsonValue]:
    return {"title": title, "service": {"title": title, "text": text, "url": {"url": href}}}


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


async def fixture_items(make_response: MakeResponse, crawl_page: CrawlPage) -> List[Dict[str, JsonValue]]:
    return items(await crawl_page(VKCloudCrawler(), make_response(URL, "vkcloud_cloud_platform.html")))


def test_configuration() -> None:
    crawler = VKCloudCrawler()

    assert crawler.name == "vkcloud"
    assert VKCloudCrawler.catalogue_url == URL
    assert VKCloudCrawler.complement_urls == ()
    assert VKCloudCrawler.dates_sitemaps == (SITEMAP,)
    assert VKCloudCrawler.name_prefixes == ("VK Cloud ", "VK ")
    assert crawler.allowed_domains == {"cloud.vk.ru"}


async def test_start_requests_read_the_sitemap_dates_first() -> None:
    requests = [request async for request in VKCloudCrawler().start_requests()]

    assert [request.url for request in requests] == [SITEMAP, URL]
    assert requests[0].meta == {VKCloudCrawler.PAGE_DATES: SITEMAP}


async def test_extracts_the_catalogue_then_the_menu_products(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await fixture_items(make_response, crawl_page)

    assert [item["name"] for item in results] == [
        "Cloud Servers",
        "Облако 152-ФЗ",
        "Autoscaling",
        "Managed Containers",
        "Cloud Databases",
        "Clickhouse",
        "Registry",
        "VK Data Platform",
        "Cloud Flink",
    ]
    assert results[1] == {
        "name": "Облако 152-ФЗ",
        "description": (
            "Хранение и обработка персональных данных в облаке, аттестованном в соответствии с 152-ФЗ"  # noqa: RUF001
        ),
        "pricing_policy": [],
        "url": "https://cloud.vk.ru/solutions/152-fz/",
        "catalogue_categories": ["Вычисления"],
    }
    assert results[8] == {
        "name": "Cloud Flink",
        "description": "Стриминг больших данных",
        "pricing_policy": [],
        "url": "https://cloud.vk.ru/flink/",
        "catalogue_categories": ["Data-платформа"],
    }


async def test_products_are_filed_under_every_group_listing_them(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await fixture_items(make_response, crawl_page)

    assert {item["name"]: item["catalogue_categories"] for item in results} == {
        "Cloud Servers": ["Вычисления", "Базовые сервисы"],
        "Облако 152-ФЗ": ["Вычисления"],
        "Autoscaling": ["Вычисления", "Kubernetes"],
        "Managed Containers": ["Kubernetes"],
        "Cloud Databases": ["Базы данных", "Базовые сервисы"],
        "Clickhouse": ["Базы данных", "Data-платформа"],
        "Registry": ["Базовые сервисы"],
        "VK Data Platform": ["Data-платформа"],
        "Cloud Flink": ["Data-платформа"],
    }


async def test_the_first_listing_gives_the_name_and_description(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    clickhouse = next(
        item for item in await fixture_items(make_response, crawl_page) if str(item["url"]).endswith("/clickhouse/")
    )

    assert (clickhouse["name"], clickhouse["description"]) == (
        "Clickhouse",
        "Аналитическая база данных для хранения и обработки исторических данных",
    )


async def test_legacy_host_links_are_moved_to_the_current_host(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    registry = next(item for item in await fixture_items(make_response, crawl_page) if item["name"] == "Registry")

    assert registry["url"] == "https://cloud.vk.ru/registry/"


async def test_product_pages_are_dated_by_the_sitemap(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = VKCloudCrawler()
    sitemap = make_response(SITEMAP, "vkcloud_sitemap.xml")
    sitemap.meta[VKCloudCrawler.PAGE_DATES] = SITEMAP

    assert await crawl_page(crawler, sitemap) == []
    results = items(await crawl_page(crawler, make_response(URL, "vkcloud_cloud_platform.html")))

    dates = {item["name"]: (item.get("updated_at"), item.get("updated_caveat")) for item in results}
    assert dates["Cloud Servers"] == ("2026-10-13T14:21:51.360000Z", "page-modified")
    assert dates["Registry"] == ("2026-10-12T14:53:59.831000Z", "page-modified")
    assert dates["Cloud Flink"] == (None, None)


async def test_listings_matched_by_page_or_name_are_merged(crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        VKCloudCrawler(),
        page(
            catalogue(
                {"title": "Сети", "services": [card("Load Balancer", "Балансировка", "/load-balancer/")]},
                {"title": "Хранилище", "services": [card("Object Storage", "S3", "/storage/")]},
            ),
            menu(
                {
                    "title": "Сети и доставка",
                    "dropdown": [
                        {"title": "Load Balancing", "text": "Распределение", "url": {"url": "/load-balancer/"}}
                    ],
                },
                {
                    "title": "Data-платформа",
                    "dropdown": [{"title": "VK Object Storage", "text": "Хранилище", "url": {"url": "/s3/"}}],
                },
            ),
        ),
    )

    assert [(item["name"], item["url"], item["catalogue_categories"]) for item in items(results)] == [
        ("Load Balancer", "https://cloud.vk.ru/load-balancer/", ["Сети", "Сети и доставка"]),
        ("Object Storage", "https://cloud.vk.ru/storage/", ["Хранилище", "Data-платформа"]),
    ]


async def test_invalid_entries_are_skipped(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    results = await crawl_page(
        VKCloudCrawler(),
        page(
            "$Sreact.fragment",
            catalogue(
                {
                    "title": "Вычисления",
                    "services": [
                        {"title": "No service"},
                        {"service": {"text": "Без названия", "url": {"url": "/nameless/"}}},
                        card("Cloud GPU", "Графические ускорители", "/cloud-gpu/"),
                        {"title": "No link", "service": {"text": "Без ссылки", "url": None}},
                        "$undefined",
                    ],
                },
                {"title": "Пусто", "services": None},
            ),
            menu({"title": "Меню", "dropdown": [{"title": "", "text": "Пустое имя"}], "dropdown_items": "$5"}),
        ),
    )

    assert [(item["name"], item.get("url"), item["catalogue_categories"]) for item in items(results)] == [
        ("Cloud GPU", "https://cloud.vk.ru/cloud-gpu/", ["Вычисления"]),
        ("No link", None, ["Вычисления"]),
    ]
    warnings = [record.getMessage() for record in caplog.records if record.levelname == "WARNING"]
    assert sum("Skipping the invalid catalogue entry" in message for message in warnings) == 4


async def test_page_without_catalogue_is_empty(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    empty = Response(
        url=URL,
        content="<html><body><script>self.__next_f.push([0])</script></body></html>",
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
    )

    with pytest.raises(EmptyCatalogueError):
        await crawl_page(VKCloudCrawler(), empty)

    warnings = [record.getMessage() for record in caplog.records if record.levelname == "WARNING"]
    errors = [record.getMessage() for record in caplog.records if record.levelname == "ERROR"]
    assert any("holds no services catalogue" in message for message in warnings)
    assert any("has no products menu" in message for message in warnings)
    assert len(errors) == 1
    assert "holds no product" in errors[0]


async def test_unreadable_flight_data_is_an_empty_page(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    broken = Response(
        url=URL,
        content='<html><body><script>self.__next_f.push([1, "0:{\\"catalog\\": "])</script>'
        "<script>self.__next_f.push([1, broken])</script></body></html>",
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
    )

    with pytest.raises(EmptyCatalogueError):
        await crawl_page(VKCloudCrawler(), broken)

    assert [record.levelname for record in caplog.records].count("ERROR") == 1
