from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.civo.marketplace import CivoMarketplaceCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parent / "fixtures" / "marketplace"
URL = "https://www.civo.com/marketplace"


@pytest.fixture(scope="module")
def crawler() -> CivoMarketplaceCrawler:
    return CivoMarketplaceCrawler(classifier=SoftwareClassifier())


@pytest.fixture
def fresh(crawler: CivoMarketplaceCrawler) -> CivoMarketplaceCrawler:
    crawler.software_categories.clear()
    return crawler


def response(content: Union[str, bytes]) -> Response:
    return Response(url=URL, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def fixture_page() -> Response:
    return response((FIXTURES / "civo_marketplace.html").read_bytes())


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [item["name"] for item in items(results)]


def test_configuration(crawler: CivoMarketplaceCrawler) -> None:
    assert crawler.name == "civo-marketplace"
    assert CivoMarketplaceCrawler.catalogue_url == URL
    assert CivoMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"www.civo.com"}


async def test_extracts_the_applications_once(fresh: CivoMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, fixture_page())

    assert names(results) == [
        "Civo cluster autoscaler",
        "GitLab",
        "Kubefirst",
        "Acorn",
        "Ambassador Edge Stack",
        "Argo Rollouts",
        "Argo Workflows",
        "Argo CD",
        "ASP.NET core",
        "Atmo",
        "Bitwarden Passwordless.dev",
        "Bitwarden Self Host Unified (BETA)",
        "Cerbos",
        "MariaDB",
        "MinIO",
        "Netdata",
    ]
    assert items(results)[0] == {
        "name": "Civo cluster autoscaler",
        "description": "Cluster Autoscaler is a tool that automatically adjusts the size of the Kubernetes cluster.",
        "publisher": None,
        "url": "https://www.civo.com/marketplace/civo-cluster-autoscaler",
        "delivery": "kubernetes",
        "marketplace_categories": ["Management"],
        "categories": ["developer-tool"],
        "types": ["container"],
    }
    assert results == items(results)


@pytest.mark.parametrize(
    ("name", "category", "types"),
    [
        ("GitLab", "Management", ["devops"]),
        ("Argo CD", "CI/CD", ["devops"]),
        ("Cerbos", "Security", ["security"]),
        ("MariaDB", "Database", ["database"]),
        ("MinIO", "Storage", ["storage"]),
        ("Netdata", "Monitoring", ["monitoring"]),
    ],
)
async def test_category_and_types(
    fresh: CivoMarketplaceCrawler, crawl_page: CrawlPage, name: str, category: str, types: List[str]
) -> None:
    software = next(item for item in items(await crawl_page(fresh, fixture_page())) if item["name"] == name)

    assert (software["marketplace_categories"], software["types"], software["delivery"]) == (
        [category],
        types,
        "kubernetes",
    )


async def test_malformed_cards(fresh: CivoMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    content = (
        '<a class="marketplace-application"><div class="content"><h5>No link</h5></div>'
        '<div class="description">Bare description</div></a>'
        '<a class="marketplace-application" href="/marketplace/no-name">'
        '<div class="description"><p>No name</p></div></a>'
    )

    software = items(await crawl_page(fresh, response(content)))

    assert [(item["name"], item["description"], item["url"], item["marketplace_categories"]) for item in software] == [
        ("No link", "Bare description", None, [])
    ]


async def test_page_without_cards_is_an_error(
    fresh: CivoMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(fresh, response("<html><body><h1>Marketplace</h1></body></html>"))

    assert any(record.levelname == "ERROR" and "holds no software" in record.getMessage() for record in caplog.records)
