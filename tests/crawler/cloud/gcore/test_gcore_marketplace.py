from __future__ import annotations

import logging
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.gcore.marketplace import GcoreMarketplaceCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parents[3] / "fixtures" / "marketplace"
URL = "https://gcore.com/cloud/marketplace"
LISTING = '<li><h3 class="gc-column-title">{name}</h3><p>{description}</p></li>'


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


@pytest.fixture
def crawler(classifier: SoftwareClassifier) -> GcoreMarketplaceCrawler:
    return GcoreMarketplaceCrawler(classifier=classifier)


def response(content: Union[str, bytes]) -> Response:
    return Response(url=URL, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def fixture_page() -> Response:
    return response((FIXTURES / "gcore_marketplace.html").read_bytes())


def services_page(listings: str) -> Response:
    return response(f'<section><ul class="gc-available-services-list">{listings}</ul></section>')


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [item["name"] for item in items(results)]


def test_configuration(crawler: GcoreMarketplaceCrawler) -> None:
    assert crawler.name == "gcore-marketplace"
    assert GcoreMarketplaceCrawler.catalogue_url == URL
    assert GcoreMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"gcore.com"}


async def test_extracts_the_application_templates(crawler: GcoreMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, fixture_page())

    assert names(results) == [
        "Prometheus",
        "Artifactory",
        "AlertManager",
        "Grafana",
        "OpenVPN",
        "Shadowsocks",
        "UnumDB",
        "RabbitMQ",
    ]
    assert items(results)[0] == {
        "name": "Prometheus",
        "description": (
            "A monitoring system with a dimensional data model, a flexible query language, and an efficient database."
        ),
        "publisher": None,
        "url": "https://gcore.com/cloud/marketplace#prometheus",
        "delivery": "virtual-machine",
        "marketplace_categories": [],
        "categories": ["developer-tool"],
    }


async def test_the_page_gives_no_category_path(crawler: GcoreMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, fixture_page())

    assert items(results)
    assert not any("marketplace_category_paths" in item for item in items(results))


async def test_other_lists_are_not_read(crawler: GcoreMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, fixture_page())

    assert "Virtual Machines" not in names(results)


@pytest.mark.parametrize(
    ("name", "audiences"),
    [
        ("Grafana", ["developer-tool"]),
        ("OpenVPN", ["developer-tool"]),
        ("Shadowsocks", ["developer-tool"]),
        ("UnumDB", ["developer-tool"]),
        ("RabbitMQ", ["developer-tool"]),
    ],
)
async def test_classification(
    crawler: GcoreMarketplaceCrawler, crawl_page: CrawlPage, name: str, audiences: List[str]
) -> None:
    results = await crawl_page(crawler, fixture_page())

    assert next(item["categories"] for item in items(results) if item["name"] == name) == audiences


async def test_listings_without_name_or_description_are_skipped(
    crawler: GcoreMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    listings = '<li><h3 class="gc-column-title">No description</h3></li><li><p>No name.</p></li>' + LISTING.format(
        name="Grafana", description="Dashboards."
    )

    results = await crawl_page(crawler, services_page(listings))

    assert names(results) == ["Grafana"]


async def test_name_without_letters_has_no_url(crawler: GcoreMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, services_page(LISTING.format(name="+++", description="A template.")))

    assert [(item["name"], item["url"]) for item in items(results)] == [("+++", None)]


async def test_invalid_listing_is_skipped(
    crawler: GcoreMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    listings = LISTING.format(name="Empty", description=" ") + LISTING.format(name="Grafana", description="Dashboards.")

    with caplog.at_level(logging.WARNING):
        results = await crawl_page(crawler, services_page(listings))

    assert names(results) == ["Grafana"]
    assert any("invalid marketplace entry 'Empty'" in record.getMessage() for record in caplog.records)


async def test_page_without_applications_is_an_error(
    crawler: GcoreMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(EmptyCatalogueError):
        await crawl_page(crawler, response("<html><body><h1>Marketplace</h1></body></html>"))

    assert any(
        record.levelno == logging.ERROR and "holds no software" in record.getMessage() for record in caplog.records
    )
