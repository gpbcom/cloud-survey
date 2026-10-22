from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.fetchers import FetcherSession
from scrapling.spiders import Request, Response
from scrapling.spiders.session import SessionManager

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.yandex.crawler import YandexCloudCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
FIXTURES = Path(__file__).parents[3] / "fixtures" / "crawler"
SERVICES_URL = "https://yandex.cloud/en/services"
RUSSIAN_URL = "https://yandex.cloud/ru/services"
SITEMAP_URL = "https://yandex.cloud/sitemap_pages.xml"
SPARK_URL = "https://yandex.cloud/en/services/managed-spark"
LOGGER = "scrapling.spiders.yandex"
STATE = re.compile(r"\n__DATA__ = (\{.*\});</script>", re.S)


def page(
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


def fixture_state(fixture: str) -> Dict[str, JsonValue]:
    match = STATE.search((FIXTURES / fixture).read_text(encoding="utf-8"))
    assert match is not None
    state = json.loads(match.group(1))
    assert isinstance(state, dict)
    return state


def services_data(state: Dict[str, JsonValue]) -> Dict[str, JsonValue]:
    context = state["context"]
    assert isinstance(context, dict)
    data = context["servicesData"]
    assert isinstance(data, dict)
    return data


def state_page(state: JsonValue, url: str = SERVICES_URL) -> Response:
    return page(
        url, f"<html><body><script>window.__DATA__ = {{}};</script><script>__DATA__ = {json.dumps(state)};</script>"
    )


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [item["name"] for item in items(results)]


def test_configuration() -> None:
    crawler = YandexCloudCrawler()

    assert crawler.name == "yandex"
    assert YandexCloudCrawler.catalogue_url == SERVICES_URL
    assert YandexCloudCrawler.complement_urls == (RUSSIAN_URL,)
    assert YandexCloudCrawler.dates_sitemaps == (SITEMAP_URL,)
    assert YandexCloudCrawler.name_prefixes == ("Yandex Cloud ", "Yandex ")
    assert YandexCloudCrawler.lazy_browser is True
    assert crawler.allowed_domains == {"yandex.cloud"}


def test_pages_are_read_by_an_http_session_naming_the_crawler() -> None:
    manager = SessionManager()

    YandexCloudCrawler().configure_sessions(manager)

    assert manager.session_ids == ["yandex-session", "yandex-http"]
    assert manager.default_session_id == "yandex-http"
    session = manager.get("yandex-http")
    assert isinstance(session, FetcherSession)
    assert session._default_headers == {"User-Agent": "Mozilla/5.0 (compatible; poc-crawler/0.1.0)"}
    assert (session._default_impersonate, session._stealth) == ("chrome", False)


async def test_start_requests_read_the_sitemap_then_both_services_pages() -> None:
    starts = [request async for request in YandexCloudCrawler().start_requests()]

    assert [(request.url, request.priority, request.sid) for request in starts] == [
        (SITEMAP_URL, 20, ""),
        (SERVICES_URL, 10, ""),
        (RUSSIAN_URL, 0, ""),
    ]


async def test_extracts_the_services(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(YandexCloudCrawler(), make_response(SERVICES_URL, "yandex_services_en.html"))

    assert names(results) == [
        "Compute Cloud",
        "Object Storage",
        "Cloud CDN",
        "Managed Service for PostgreSQL",
        "DataLens",
        "Yandex AI Studio",
        "SpeechKit",
        "Translate",
        "Managed Service for Kubernetes®",
        "Container Registry",
        "Identity and Access Management",
        "Yandex Cloud Billing",
    ]
    assert items(results)[0] == {
        "name": "Compute Cloud",
        "description": "Virtual machines and block storage",
        "pricing_policy": [],
        "url": "https://yandex.cloud/en/services/compute",
        "catalogue_categories": ["Infrastructure & Network"],
    }


async def test_descriptions_lose_their_html(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(YandexCloudCrawler(), make_response(SERVICES_URL, "yandex_services_en.html"))

    descriptions = {item["name"]: item["description"] for item in items(results)}
    assert descriptions["Managed Service for Kubernetes®"] == "Managed Kubernetes® clusters"
    assert descriptions["Translate"] == "Machine translation supporting more than 100 languages"


async def test_services_are_filed_under_their_groups_without_featured(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(YandexCloudCrawler(), make_response(SERVICES_URL, "yandex_services_en.html"))

    categories = {item["name"]: item["catalogue_categories"] for item in items(results)}
    assert categories["Compute Cloud"] == ["Infrastructure & Network"]
    assert categories["DataLens"] == ["Data Platform"]
    assert categories["Yandex AI Studio"] == ["AI for business"]
    assert categories["Managed Service for Kubernetes®"] == ["DevOps tools"]
    assert categories["Yandex Cloud Billing"] == ["Monitoring & Resources"]
    assert all("Featured" not in labels for labels in categories.values() if isinstance(labels, list))


async def test_external_services_link_to_their_website(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(YandexCloudCrawler(), make_response(SERVICES_URL, "yandex_services_en.html"))

    urls = {item["name"]: item["url"] for item in items(results)}
    assert urls["Yandex AI Studio"] == "https://aistudio.yandex.ru/"
    assert urls["SpeechKit"] == "https://aistudio.yandex.ru/ru/ai-speech"


async def test_services_listed_in_several_groups_gather_them(crawl_page: CrawlPage) -> None:
    state = fixture_state("yandex_services_en.html")
    by_category = services_data(state)["dataByCategory"]
    assert isinstance(by_category, dict)
    platform, operations = by_category["data-platform"], by_category["resources-operations"]
    assert isinstance(platform, list)
    assert isinstance(operations, list)
    operations.append(platform[2])

    results = await crawl_page(YandexCloudCrawler(), state_page(state))

    assert names(results).count("DataLens") == 1
    datalens = next(item for item in items(results) if item["name"] == "DataLens")
    assert datalens["catalogue_categories"] == ["Data Platform", "Monitoring & Resources"]


async def test_services_without_group_are_not_categorized(crawl_page: CrawlPage) -> None:
    state = fixture_state("yandex_services_en.html")
    data = services_data(state)
    data["categories"] = []

    results = await crawl_page(YandexCloudCrawler(), state_page(state))

    assert len(items(results)) == 12
    assert all("catalogue_categories" not in item for item in items(results))


async def test_services_without_description_are_read_from_their_page(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = YandexCloudCrawler()
    results = await crawl_page(crawler, make_response(SERVICES_URL, "yandex_services_en.html"))

    assert "Managed Service for Apache Spark™" not in names(results)
    assert results[-2:] == requests(results)
    first, second = requests(results)
    assert (first.url, first.priority) == (SPARK_URL, 10)
    assert first.meta == {
        "product_page": SPARK_URL,
        "product_name": "Managed Service for Apache Spark™",
        "product_categories": ["Data Platform"],
    }
    assert second.meta["product_categories"] == ["Monitoring & Resources"]

    product = await crawl_page(
        crawler, page(SPARK_URL, (FIXTURES / "yandex_service_managed_spark.html").read_bytes(), first.meta)
    )

    assert product == [
        {
            "name": "Managed Service for Apache Spark™",
            "description": (
                "Process large volumes of data quickly with Yandex Cloud's managed Apache Spark™ service, featuring "
                "distributed computing and integration with the Hadoop ecosystem."
            ),
            "pricing_policy": [],
            "url": SPARK_URL,
            "catalogue_categories": ["Data Platform"],
        }
    ]


async def test_service_pages_are_dated_by_the_sitemap(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = YandexCloudCrawler()
    sitemap = page(SITEMAP_URL, (FIXTURES / "yandex_sitemap_pages.xml").read_bytes(), {"page_dates": SITEMAP_URL})

    assert await crawl_page(crawler, sitemap) == []
    results = await crawl_page(crawler, make_response(SERVICES_URL, "yandex_services_en.html"))

    dates = {item["name"]: (item.get("updated_at"), item.get("updated_caveat")) for item in items(results)}
    assert dates["Compute Cloud"] == ("2026-07-28T14:15:22.069000Z", "page-modified")
    assert dates["Object Storage"][1] == "page-modified"
    assert dates["Cloud CDN"] == (None, None)


async def test_russian_page_adds_the_services_it_only_lists(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = YandexCloudCrawler()
    await crawl_page(crawler, make_response(SERVICES_URL, "yandex_services_en.html"))

    results = await crawl_page(crawler, make_response(RUSSIAN_URL, "yandex_services_ru.html"))

    assert names(results) == [
        "Yandex Cloud Detection and Response",
        "Key Management Service",
        "GOST Gateway",
        "SourceCraft",
    ]
    assert items(results)[0] == {
        "name": "Yandex Cloud Detection and Response",
        "description": "Сервис для мониторинга и реагирования на инциденты в облаке",
        "pricing_policy": [],
        "url": "https://yandex.cloud/ru/services/ycdr",
        "catalogue_categories": ["Безопасность"],
    }
    assert items(results)[3]["catalogue_categories"] == ["Инструменты DevOps"]
    assert requests(results) == []


async def test_invalid_services_are_skipped(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    state = fixture_state("yandex_services_en.html")
    by_category = services_data(state)["dataByCategory"]
    assert isinstance(by_category, dict)
    by_category["available-in-region"] = [
        {"slug": "blank", "name": "  ", "description": "No name"},
        {"name": "No page", "description": 7, "externalUrl": "https://example.com/no-page"},
        {"description": "Neither slug nor name"},
        "not a service",
        {"slug": "valid", "name": "Valid", "description": "A&nbsp;valid service", "externalUrl": "ftp://example.com"},
    ]
    state["context"] = {"servicesData": {"categories": [], "dataByCategory": by_category}}
    caplog.set_level(logging.WARNING, logger=LOGGER)

    results = await crawl_page(YandexCloudCrawler(), state_page(state))

    assert items(results) == [{"name": "Valid", "description": "A valid service", "pricing_policy": [], "url": None}]
    warnings = [record.message for record in caplog.records if record.levelname == "WARNING"]
    assert len([message for message in warnings if "Skipping the invalid catalogue entry" in message]) == 4
    assert any("Skipping the invalid catalogue entry 'No page'" in message for message in warnings)


async def test_empty_page_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    state = fixture_state("yandex_services_en.html")
    state["context"] = {"servicesData": {"categories": [], "dataByCategory": {}}}

    with pytest.raises(EmptyCatalogueError, match="no product found"):
        await crawl_page(YandexCloudCrawler(), state_page(state))

    assert any(record.levelname == "ERROR" and "holds no product" in record.message for record in caplog.records)


async def test_page_without_state_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(CatalogueFormatError, match="page state is missing"):
        await crawl_page(
            YandexCloudCrawler(), page(SERVICES_URL, "<html><script>window.__DATA__ = {};</script></html>")
        )

    assert any(record.levelname == "ERROR" and "embeds no page state" in record.message for record in caplog.records)


async def test_captcha_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    captcha = page("https://yandex.cloud/showcaptchafast?d=1E4B&retpath=aHR0", "<html><title>Captcha</title></html>")

    with pytest.raises(CatalogueFormatError, match="the page is a captcha"):
        await crawl_page(YandexCloudCrawler(), captcha)

    assert any(
        record.levelname == "ERROR" and "redirected to the captcha" in record.message for record in caplog.records
    )
