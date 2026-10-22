from __future__ import annotations

import json
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.vkcloud.marketplace import VKCloudMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parents[3] / "fixtures" / "marketplace"
URL = "https://cloud.vk.ru/api/v-s/getCatalog/"


@pytest.fixture(scope="module")
def crawler() -> VKCloudMarketplaceCrawler:
    return VKCloudMarketplaceCrawler(classifier=SoftwareClassifier())


@pytest.fixture
def fresh(crawler: VKCloudMarketplaceCrawler) -> VKCloudMarketplaceCrawler:
    crawler.software_categories.clear()
    crawler.software_category_paths.clear()
    return crawler


def response(content: Union[str, bytes]) -> Response:
    return Response(url=URL, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def fixture_page() -> Response:
    return response((FIXTURES / "vkcloud_catalog.json").read_bytes())


def catalog_page(listings: JsonValue) -> Response:
    return response(json.dumps({"data": listings, "filterValues": {}}, ensure_ascii=False))


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def by_name(results: List[Union[Dict[str, JsonValue], Request]], name: str) -> Dict[str, JsonValue]:
    return next(item for item in items(results) if item["name"] == name)


def test_configuration(crawler: VKCloudMarketplaceCrawler) -> None:
    assert crawler.name == "vkcloud-marketplace"
    assert VKCloudMarketplaceCrawler.catalogue_url == URL
    assert VKCloudMarketplaceCrawler.complement_urls == ()
    assert VKCloudMarketplaceCrawler.dates_sitemaps == ()
    assert crawler.allowed_domains == {"cloud.vk.ru"}


async def test_the_whole_catalogue_is_one_request(fresh: VKCloudMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    requests = [request async for request in fresh.start_requests()]
    results = await crawl_page(fresh, fixture_page())

    assert [request.url for request in requests] == [URL]
    assert not [result for result in results if isinstance(result, Request)]
    assert len(items(results)) == 7


async def test_extracts_the_software(fresh: VKCloudMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, fixture_page())

    assert [item["name"] for item in items(results)] == [
        "AW BI",
        "Tracer",
        "Valkey",
        "Test IT",
        "«Альт СП Сервер»",
        "Кибер Бэкап Облачный",
        "Check Point CloudGuard Network R82 - Security Gateway BYOL",
    ]
    software = {key: value for key, value in items(results)[0].items() if key != "categories"}
    assert software == {
        "name": "AW BI",
        "description": (
            "Универсальная BI-экосистема «из коробки»: встроенное аналитическое хранилище, ETL, ML-прогнозирование, "
            "большое количество визуализаций, кастомные визуализации, рассылки отчетов."
        ),
        "publisher": "АО ОСТ",  # noqa: RUF001
        "url": "https://cloud.vk.ru/marketplace/922f6fab-1a46-4ffb-948e-47618c8172ea/",
        "delivery": "virtual-machine",
        "marketplace_categories": ["AI/ML", "Аналитика"],
        "marketplace_category_paths": [
            {"path": ["AI/ML"], "id": "ai_ml"},
            {"path": ["Аналитика"], "id": "analytics"},
        ],
        "updated_at": "2026-03-18T11:24:59Z",
        "updated_caveat": "catalogue-entry",
    }
    assert all(item["categories"] for item in items(results))


@pytest.mark.parametrize(
    ("name", "publisher", "delivery", "categories", "url"),
    [
        (
            "Tracer",
            None,
            "saas",
            ["Аналитика", "Инструменты для разработки", "Мониторинг"],
            "https://cloud.vk.ru/marketplace/1f258019-7984-4274-84ad-03b4d3657cd6/",
        ),
        (
            "Test IT",
            "Test IT",
            "other",
            ["Прикладное ПО"],
            "https://cloud.vk.ru/marketplace/0b076dde-1dcb-418c-99c5-f6f406cc1d1d/",
        ),
        (
            "«Альт СП Сервер»",
            "Базальт СПО",
            "virtual-machine",
            ["Операционные системы"],
            "https://cloud.vk.ru/marketplace/os/basealt-serversp8/",
        ),
        (
            "Кибер Бэкап Облачный",
            "Киберпротект",
            "saas",
            ["Бэкап"],
            "https://cloud.vk.ru/marketplace/630008e7-a649-4111-a21f-6d8461cd5f7a/",
        ),
        (
            "Check Point CloudGuard Network R82 - Security Gateway BYOL",
            None,
            "virtual-machine",
            ["Сетевая инфраструктура", "Безопасность"],
            "https://cloud.vk.ru/marketplace/324b25f8-eab4-4161-bf2f-642067cfb1c9/",
        ),
    ],
)
async def test_publisher_delivery_categories_and_page(
    fresh: VKCloudMarketplaceCrawler,
    crawl_page: CrawlPage,
    name: str,
    publisher: str,
    delivery: str,
    categories: List[str],
    url: str,
) -> None:
    software = by_name(await crawl_page(fresh, fixture_page()), name)

    assert (software["publisher"], software["delivery"], software["marketplace_categories"], software["url"]) == (
        publisher,
        delivery,
        categories,
        url,
    )


async def test_category_paths_are_identified_by_their_tag(
    fresh: VKCloudMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    software = by_name(await crawl_page(fresh, fixture_page()), "«Альт СП Сервер»")

    assert software["marketplace_category_paths"] == [{"path": ["Операционные системы"], "id": "os"}]
    assert software["updated_at"] == "2025-07-21T21:00:00Z"


async def test_a_software_listed_again_with_new_categories_gathers_them(
    fresh: VKCloudMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    listing: Dict[str, JsonValue] = {
        "title": "OpenVPN",
        "text": "VPN-сервер",
        "company": "VK Cloud",
        "href": "/marketplace/11bd457f",
        "tags": [{"title": "Безопасность", "tag": "security", "type": "category"}],
    }
    again: Dict[str, JsonValue] = {
        **listing,
        "tags": [{"title": "Сетевая инфраструктура", "tag": "network_infrastructure", "type": "category"}],
    }

    first = items(await crawl_page(fresh, catalog_page([listing])))
    second = items(await crawl_page(fresh, catalog_page([again])))

    assert first[0]["marketplace_categories"] == ["Безопасность"]
    assert [item["marketplace_categories"] for item in second] == [["Безопасность", "Сетевая инфраструктура"]]
    assert second[0]["marketplace_category_paths"] == [
        {"path": ["Безопасность"], "id": "security"},
        {"path": ["Сетевая инфраструктура"], "id": "network_infrastructure"},
    ]


async def test_invalid_entries_are_skipped(
    fresh: VKCloudMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    results = await crawl_page(
        fresh,
        catalog_page(
            [
                {"title": "Bare", "text": "Без тегов", "provider": "Provider", "releaseDate": "not a date"},
                {"title": "", "text": "Без названия", "href": "/marketplace/nameless"},
                {"title": "No description", "href": "/marketplace/no-description"},
                "not a listing",
                {
                    "title": "Labels only",
                    "text": "Теги в labels",
                    "developer": " ",
                    "href": "/marketplace/labels?tab=1",
                    "tags": None,
                    "labels": [
                        {"title": "", "tag": "empty", "type": "category"},
                        {"tag": "saas", "type": "product_type"},
                    ],
                },
            ]
        ),
    )

    assert [(item["name"], item["url"], item["publisher"], item["delivery"]) for item in items(results)] == [
        ("Bare", None, "Provider", "other"),
        ("Labels only", "https://cloud.vk.ru/marketplace/labels?tab=1", None, "saas"),
    ]
    assert all("updated_at" not in item and "marketplace_category_paths" not in item for item in items(results))
    warnings = [record.getMessage() for record in caplog.records if record.levelname == "WARNING"]
    assert sum("Skipping the invalid marketplace entry" in message for message in warnings) == 2
    assert any("not an object" in message for message in warnings)


async def test_empty_catalogue_is_an_error(
    fresh: VKCloudMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(fresh, catalog_page([]))

    assert any(record.levelname == "ERROR" and "holds no software" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(("content", "reason"), [('{"data": null}', "no software list"), ("<html></html>", "not JSON")])
async def test_unexpected_responses_are_errors(
    fresh: VKCloudMarketplaceCrawler,
    crawl_page: CrawlPage,
    caplog: pytest.LogCaptureFixture,
    content: str,
    reason: str,
) -> None:
    with pytest.raises(CatalogueFormatError, match=reason):
        await crawl_page(fresh, response(content))

    assert [record.levelname for record in caplog.records].count("ERROR") == 1
