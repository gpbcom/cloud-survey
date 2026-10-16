from __future__ import annotations

import json
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.scaleway.marketplace import ScalewayMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parent / "fixtures" / "marketplace"
URL = "https://www.scaleway.com/en/marketplace/catalog/"


@pytest.fixture(scope="module")
def crawler() -> ScalewayMarketplaceCrawler:
    return ScalewayMarketplaceCrawler(classifier=SoftwareClassifier())


@pytest.fixture
def fresh(crawler: ScalewayMarketplaceCrawler) -> ScalewayMarketplaceCrawler:
    crawler.software_categories.clear()
    return crawler


def response(content: Union[str, bytes]) -> Response:
    return Response(url=URL, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def fixture_page() -> Response:
    return response((FIXTURES / "scaleway_catalog.html").read_bytes())


def next_data_page(page_props: JsonValue) -> Response:
    script = json.dumps({"props": {"pageProps": page_props}})
    return response(f'<script id="__NEXT_DATA__" type="application/json">{script}</script>')


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [item["name"] for item in items(results)]


def test_configuration(crawler: ScalewayMarketplaceCrawler) -> None:
    assert crawler.name == "scaleway-marketplace"
    assert ScalewayMarketplaceCrawler.catalogue_url == URL
    assert ScalewayMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"www.scaleway.com"}


async def test_extracts_the_software(fresh: ScalewayMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, fixture_page())

    assert names(results) == [
        "Cubbit",
        "Galene.AI Platform",
        "ContentGrid",
        "Devana AI",
        "Reemo desktop",
        "GitLab Server",
        "Sellsy",
        "Wordpress",
        "Grafana",
        "OpenVPN",
    ]
    assert items(results)[1] == {
        "name": "Galene.AI Platform",
        "description": (
            "Galene.AI provides companies of all sizes with sovereign AI copilots and custom agents that connect to "
            "company data via MCP and run on Scaleway\u2019s GPU instances with end-to-end encryption."
        ),
        "publisher": "Galene.AI",
        "url": "https://www.scaleway.com/en/marketplace/catalog/galene-ai/",
        "delivery": "virtual-machine",
        "marketplace_categories": ["Artificial Intelligence", "Security"],
        "categories": ["developer-tool", "end-user-software"],
        "types": ["ai-ml", "security"],
    }


@pytest.mark.parametrize("excluded", ["Rocky Linux", "Ubuntu ML"])
async def test_operating_systems_are_excluded(
    fresh: ScalewayMarketplaceCrawler, crawl_page: CrawlPage, excluded: str
) -> None:
    assert excluded not in names(await crawl_page(fresh, fixture_page()))


@pytest.mark.parametrize(
    ("name", "delivery", "publisher", "types"),
    [
        ("Cubbit", "container", "Cubbit", ["storage"]),
        ("ContentGrid", "saas", "xenit-solutions", ["document-management", "ai-ml"]),
        ("Devana AI", "kubernetes", "Devana", ["ai-ml"]),
        ("Reemo desktop", "other", "Reemo", ["security"]),
        ("Wordpress", "virtual-machine", "Scaleway Instant app", ["cms"]),
        ("Grafana", "container", "Scaleway Easy Deploy", ["monitoring"]),
    ],
)
async def test_delivery_publisher_and_types(
    fresh: ScalewayMarketplaceCrawler,
    crawl_page: CrawlPage,
    name: str,
    delivery: str,
    publisher: str,
    types: List[str],
) -> None:
    software = next(item for item in items(await crawl_page(fresh, fixture_page())) if item["name"] == name)

    assert (software["delivery"], software["publisher"], software["types"]) == (delivery, publisher, types)


async def test_malformed_entries(fresh: ScalewayMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        fresh,
        next_data_page(
            {
                "allApps": [
                    {
                        "title": "Bare",
                        "description": "Bare application",
                        "deliveryMethod": "Teleport",
                        "filters": {"categories": ["unknown", 3]},
                    },
                    {"title": "No filters", "slug": "no-filters", "description": "No filters", "filters": None},
                    {"title": "No description", "slug": "no-description", "filters": {"vendor": "ghost"}},
                    "not an application",
                ],
                "allFilters": {"vendors": [{"slug": "ghost"}, "vendor"]},
                "navigation": None,
            }
        ),
    )

    assert [(item["name"], item["url"], item["publisher"], item["delivery"]) for item in items(results)] == [
        ("Bare", None, None, "other"),
        ("No filters", "https://www.scaleway.com/en/marketplace/catalog/no-filters/", None, "other"),
    ]
    assert items(results)[0]["marketplace_categories"] == ["unknown"]


async def test_only_operating_systems_is_an_empty_page(
    fresh: ScalewayMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    page = next_data_page({"allApps": [{"title": "Debian", "description": "OS", "filters": {"categories": ["os"]}}]})

    with pytest.raises(EmptyCatalogueError):
        await crawl_page(fresh, page)

    assert any(record.levelname == "ERROR" and "holds no software" in record.getMessage() for record in caplog.records)


async def test_page_without_applications_is_an_error(
    fresh: ScalewayMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(CatalogueFormatError, match="the page data has no applications list"):
        await crawl_page(fresh, next_data_page({"allApps": None}))

    assert [record.levelname for record in caplog.records].count("ERROR") == 1
