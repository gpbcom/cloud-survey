from __future__ import annotations

import logging
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.aruba.marketplace import ArubaCloudMarketplaceCrawler
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parent / "fixtures" / "marketplace"
URL = "https://www.arubacloud.com/cloud-apps/"
CARD = (
    '<article class="card"><div class="card-body"><h3 data-mh="title">{name}</h3>'
    '<div class="text-neutral-700">{paragraphs}</div>{link}</div></article>'
)


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


@pytest.fixture
def crawler(classifier: SoftwareClassifier) -> ArubaCloudMarketplaceCrawler:
    return ArubaCloudMarketplaceCrawler(classifier=classifier)


def response(content: Union[str, bytes]) -> Response:
    return Response(url=URL, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def fixture_page() -> Response:
    return response((FIXTURES / "aruba_cloud_apps.html").read_bytes())


def catalogue_page(cards: str) -> Response:
    return response(f'<section id="catalogo"><h2>Application catalog</h2>{cards}</section>')


def card(name: str, paragraphs: str, link: str = "") -> str:
    return CARD.format(name=name, paragraphs=paragraphs, link=link)


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [item["name"] for item in items(results)]


def by_name(results: List[Union[Dict[str, JsonValue], Request]], name: str) -> Dict[str, JsonValue]:
    return next(item for item in items(results) if item["name"] == name)


def test_configuration(crawler: ArubaCloudMarketplaceCrawler) -> None:
    assert crawler.name == "aruba-marketplace"
    assert ArubaCloudMarketplaceCrawler.catalogue_url == URL
    assert ArubaCloudMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"www.arubacloud.com"}


async def test_extracts_the_catalogue(crawler: ArubaCloudMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, fixture_page())

    assert names(results) == [
        "OpenClaw",
        "Hermes Agent",
        "N8N",
        "Docker",
        "WordPress",
        "WireGuard VPN",
        "LAMP",
        "LEMP",
        "MinIO",
        "Windows Server with MSSQL",
        "SQL Server",
        "Nextcloud",
        "Virtual Desktop",
        "PLESK",
        "CyberPanel",
    ]
    assert by_name(results, "WordPress") == {
        "name": "WordPress",
        "description": (
            "WordPress is the open-source CMS for websites, blogs, landing pages, portals, and e-commerce. Useful for "
            "managing content, themes, plugins, and web configurations independently."
        ),
        "publisher": None,
        "url": "https://www.arubacloud.com/vps/wordpress/",
        "delivery": "virtual-machine",
        "marketplace_categories": ["CMS AND WEB"],
        "categories": ["end-user-software"],
        "types": ["cms"],
    }


async def test_featured_cards_are_not_read_twice(
    crawler: ArubaCloudMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        await crawl_page(crawler, fixture_page())

    assert "15 application cards" in caplog.text
    assert "duplicated software" not in caplog.text


async def test_cards_without_page_get_an_anchor(crawler: ArubaCloudMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, fixture_page())

    assert by_name(results, "Windows Server with MSSQL")["url"] == (
        "https://www.arubacloud.com/cloud-apps/#windows-server-with-mssql"
    )
    assert by_name(results, "N8N")["url"] == "https://www.arubacloud.com/vps/n8n/"


async def test_card_without_category(crawler: ArubaCloudMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    nextcloud = by_name(await crawl_page(crawler, fixture_page()), "Nextcloud")

    assert nextcloud["marketplace_categories"] == []
    assert str(nextcloud["description"]).startswith("Nextcloud allows you to manage files, sharing, and collaboration")


async def test_availability_is_not_a_description(crawler: ArubaCloudMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, fixture_page())

    assert not any("Availability" in str(item["description"]) for item in items(results))


@pytest.mark.parametrize(
    ("name", "types"),
    [
        ("OpenClaw", ["ai-ml"]),
        ("Docker", ["container"]),
        ("WireGuard VPN", ["networking"]),
        ("MinIO", ["storage"]),
        ("SQL Server", ["database"]),
        ("Nextcloud", ["collaboration"]),
    ],
)
async def test_classification(
    crawler: ArubaCloudMarketplaceCrawler, crawl_page: CrawlPage, name: str, types: List[str]
) -> None:
    assert by_name(await crawl_page(crawler, fixture_page()), name)["types"] == types


async def test_malformed_cards(
    crawler: ArubaCloudMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    cards = (
        '<article class="card"><div class="text-neutral-700"><p>No name.</p></div></article>'
        + card("No description", "<p><span>WEB STACK</span></p><p><strong>Availability:</strong> Linux</p>")
        + card("+++", "<p><span>STORAGE</span></p><p>A storage template.</p>")
    )

    with caplog.at_level(logging.WARNING):
        results = await crawl_page(crawler, catalogue_page(cards))

    assert [(item["name"], item["url"], item["marketplace_categories"]) for item in items(results)] == [
        ("+++", None, ["STORAGE"])
    ]
    assert "invalid marketplace entry 'No description'" in caplog.text


async def test_page_without_catalogue_is_an_error(
    crawler: ArubaCloudMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    featured = f'<section id="app-evidenza">{card("OpenClaw", "<p>An agent.</p>")}</section>'

    with caplog.at_level(logging.ERROR), pytest.raises(EmptyCatalogueError):
        await crawl_page(crawler, response(featured))

    assert any(
        record.levelno == logging.ERROR and "holds no software" in record.getMessage() for record in caplog.records
    )
