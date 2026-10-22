from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.selectel.marketplace import SelectelMarketplaceCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parents[3] / "fixtures" / "marketplace"
URL = "https://docs.selectel.ru/ai-marketplace/about/about-ai-marketplace/"
ROW = '<tr><th><p><a href="{href}">{name}</a></p></th><td><p>{description}</p></td></tr>'


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


@pytest.fixture
def crawler(classifier: SoftwareClassifier) -> SelectelMarketplaceCrawler:
    return SelectelMarketplaceCrawler(classifier=classifier)


def response(content: Union[str, bytes]) -> Response:
    return Response(url=URL, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def fixture_page() -> Response:
    return response((FIXTURES / "selectel_ai_marketplace.html").read_bytes())


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def test_configuration(crawler: SelectelMarketplaceCrawler) -> None:
    assert crawler.name == "selectel-marketplace"
    assert SelectelMarketplaceCrawler.catalogue_url == URL
    assert SelectelMarketplaceCrawler.complement_urls == ()
    assert SelectelMarketplaceCrawler.dates_sitemaps == ()
    assert crawler.allowed_domains == {"docs.selectel.ru"}


async def test_extracts_the_images_of_the_table(crawler: SelectelMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = items(await crawl_page(crawler, fixture_page()))

    assert [(item["name"], item["url"]) for item in results] == [
        ("Data Analytics Virtual Machine (DAVM)", "https://docs.selectel.ru/ai-marketplace/davm/"),
        ("Open WebUI Virtual Machine", "https://docs.selectel.ru/ai-marketplace/open-webui/"),
        ("n8n Virtual Machine", "https://docs.selectel.ru/ai-marketplace/n8n/"),
        ("CVAT Virtual Machine", "https://docs.selectel.ru/ai-marketplace/cvat/"),
        ("Dify Virtual Machine", "https://docs.selectel.ru/ai-marketplace/dify/"),
        ("Unsloth Virtual Machine", "https://docs.selectel.ru/ai-marketplace/unsloth/"),
    ]


async def test_image_fields(crawler: SelectelMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = items(await crawl_page(crawler, fixture_page()))

    webui = results[1]
    assert webui["description"] == (
        "Преднастроенный облачный сервер с инструментом для развертывания больших языковых моделей (LLM) и работы с "  # noqa: RUF001
        "ними через веб‑интерфейс. Инструмент предоставляет полный контроль над обрабатываемыми данными и поддержку "  # noqa: RUF001
        "расширенного RAG"
    )
    assert webui["delivery"] == "virtual-machine"
    assert webui.get("publisher") is None
    assert webui["marketplace_categories"] == []
    assert webui.get("marketplace_category_paths") is None
    assert webui["categories"] == ["developer-tool", "end-user-software"]


async def test_image_listed_twice_is_streamed_once(crawler: SelectelMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    row = ROW.format(href="/ai-marketplace/n8n/", name="n8n Virtual Machine", description="Автоматизация процессов")

    results = items(await crawl_page(crawler, response(f"<table>{row}{row}</table>")))

    assert [item["name"] for item in results] == ["n8n Virtual Machine"]


async def test_invalid_rows_are_skipped(
    crawler: SelectelMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    rows = "".join(
        [
            "<tr><th>Образ</th><td>Описание</td></tr>",
            ROW.format(href="/ai-marketplace/aim/", name="Aim Virtual Machine", description=""),
            '<tr><th><p><a href="/ai-marketplace/cvat/">CVAT Virtual Machine</a></p></th></tr>',
            ROW.format(href="/ai-marketplace/litellm/", name="LiteLLM Virtual Machine", description="AI-шлюз для LLM"),
        ]
    )

    results = items(await crawl_page(crawler, response(f"<table>{rows}</table>")))

    assert [(item["name"], item["url"]) for item in results] == [
        ("LiteLLM Virtual Machine", "https://docs.selectel.ru/ai-marketplace/litellm/")
    ]
    assert any(record.levelname == "WARNING" and "Aim Virtual Machine" in record.message for record in caplog.records)
    assert any(record.levelname == "WARNING" and "CVAT Virtual Machine" in record.message for record in caplog.records)


async def test_page_without_images_is_an_error(
    crawler: SelectelMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(crawler, response("<html><body><article><p>Нет образов</p></article></body></html>"))

    assert any(record.levelname == "ERROR" and "holds no software" in record.message for record in caplog.records)
