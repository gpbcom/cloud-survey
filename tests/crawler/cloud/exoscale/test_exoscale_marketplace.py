from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.exoscale.marketplace import ExoscaleMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parents[3] / "fixtures" / "marketplace"
URL = "https://www.exoscale.com/marketplace/"
SITEMAP = "https://www.exoscale.com/sitemap.xml"
LISTING = f"{URL}listing/"


@pytest.fixture(scope="module")
def crawler() -> ExoscaleMarketplaceCrawler:
    return ExoscaleMarketplaceCrawler(classifier=SoftwareClassifier())


@pytest.fixture
def fresh(crawler: ExoscaleMarketplaceCrawler) -> ExoscaleMarketplaceCrawler:
    crawler.software_categories.clear()
    crawler.software_category_paths.clear()
    return crawler


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


def read(fixture: str) -> bytes:
    return (FIXTURES / fixture).read_bytes()


def listing_page(slug: str, content: Union[str, bytes], status: int = 200) -> Response:
    url = f"{LISTING}{slug}/"
    return response(url, content, {"listing": url, "may_be_empty": True}, status)


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [item["name"] for item in items(results)]


def test_configuration(crawler: ExoscaleMarketplaceCrawler) -> None:
    assert crawler.name == "exoscale-marketplace"
    assert ExoscaleMarketplaceCrawler.catalogue_url == URL
    assert ExoscaleMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"www.exoscale.com"}


async def test_extracts_the_cards_then_requests_the_sitemap(
    fresh: ExoscaleMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(fresh, response(URL, read("exoscale_marketplace.html")))

    assert names(results) == [
        "Anapaya EDGE",
        "BunkerWeb",
        "Cisco Adaptive Security Virtual Appliance (ASAv)",
        "Acronis Cyber Protect",
        "ANANTIS TrapEye - Preemptive Cyber Deception",
        "8gears Container Registry",
        "APPUiO Managed OpenShift - by VSHN",
        "APPUiO Cloud - Kubernetes Namespace as a Service - by VSHN",
        "360vue",
    ]
    assert items(results)[1] == {
        "name": "BunkerWeb",
        "description": "Open-source, cloud-native WAF and reverse proxy",
        "publisher": "Bunkerity SAS",
        "url": f"{LISTING}bunkerweb-community/",
        "delivery": "virtual-machine",
        "marketplace_categories": ["Templates"],
        "marketplace_category_paths": [{"path": ["Templates"], "id": "templates"}],
        "categories": ["developer-tool"],
    }
    assert [(request.url, request.meta) for request in requests(results)] == [(SITEMAP, {"sitemap": True})]


@pytest.mark.parametrize(
    ("name", "delivery", "category", "audiences", "section"),
    [
        ("Acronis Cyber Protect", "saas", "Managed Services", ["developer-tool"], "managed-services"),
        ("8gears Container Registry", "saas", "Managed Services", ["developer-tool"], "managed-services"),
        ("360vue", "saas", "Powered by Exoscale", ["developer-tool", "end-user-software"], "powered-by-exoscale"),
    ],
)
async def test_section_gives_the_delivery_and_category(
    fresh: ExoscaleMarketplaceCrawler,
    crawl_page: CrawlPage,
    name: str,
    delivery: str,
    category: str,
    audiences: List[str],
    section: str,
) -> None:
    results = await crawl_page(fresh, response(URL, read("exoscale_marketplace.html")))
    software = next(item for item in items(results) if item["name"] == name)

    assert (software["delivery"], software["marketplace_categories"], software["categories"]) == (
        delivery,
        [category],
        audiences,
    )
    assert software["marketplace_category_paths"] == [{"path": [category], "id": section}]


async def test_sitemap_requests_the_listing_pages_not_shown_as_cards(
    fresh: ExoscaleMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    await crawl_page(fresh, response(URL, read("exoscale_marketplace.html")))

    results = await crawl_page(fresh, response(SITEMAP, read("exoscale_sitemap.xml"), {"sitemap": True}))

    assert items(results) == []
    assert [(request.url, request.meta) for request in requests(results)] == [
        (
            f"{LISTING}{slug}/",
            {"listing": f"{LISTING}{slug}/", "may_be_empty": True},
        )
        for slug in (
            "FortiAnalyzer-virtual-appliances-byol",
            "check-point-cloudguard-iaas-byol",
            "compliant-kubernetes-by-elastisys",
        )
    ]


async def test_listing_page_repeating_its_title_is_described_by_its_overview(
    fresh: ExoscaleMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(
        fresh, listing_page("check-point-cloudguard-iaas-byol", read("exoscale_listing_check_point.html"))
    )

    assert items(results) == [
        {
            "name": "Check Point CloudGuard IaaS",
            "description": (
                "Process efficiencies and increased network agility are driving SaaS, PaaS and IaaS technology "
                "adoption at a rapid pace. This new infrastructure is also presenting businesses with a unique set of "
                "security challenges."
            ),
            "publisher": "Check Point",
            "url": f"{LISTING}check-point-cloudguard-iaas-byol/",
            "delivery": "virtual-machine",
            "marketplace_categories": [],
            "categories": ["developer-tool"],
        }
    ]
    assert requests(results) == []


async def test_listing_page_with_its_own_description(fresh: ExoscaleMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    software = items(await crawl_page(fresh, listing_page("anapaya-edge", read("exoscale_listing_anapaya.html"))))

    assert [(item["name"], item["description"], item["publisher"]) for item in software] == [
        ("Anapaya EDGE", "Anapaya EDGE - the gateway to the SCION Internet", "Anapaya")
    ]
    assert "marketplace_category_paths" not in software[0]


@pytest.mark.parametrize(
    ("content", "status", "expected"),
    [
        ("Not found", 404, []),
        ("<html><body><p>No title</p></body></html>", 200, []),
        (
            '<html><head><meta name="description" content="Tool - PAYG"></head><body><h1>Tool - PAYG</h1>'
            '<div class="mkplace-listing__blob-item--product-overview"><div class="mkplace-listing__blob-item__blob">'
            "Overview text</div></div></body></html>",
            200,
            [("Tool", "Overview text", None, "other")],
        ),
        (
            '<html><head><meta name="description" content="Tool"></head><body><h1>Tool</h1></body></html>',
            200,
            [("Tool", "Tool", None, "other")],
        ),
    ],
)
async def test_listing_page_fallbacks(
    fresh: ExoscaleMarketplaceCrawler,
    crawl_page: CrawlPage,
    content: str,
    status: int,
    expected: List[JsonValue],
) -> None:
    software = items(await crawl_page(fresh, listing_page("tool", content, status)))

    assert [(item["name"], item["description"], item["publisher"], item["delivery"]) for item in software] == expected


async def test_cards_of_unknown_sections_and_malformed_cards(
    fresh: ExoscaleMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    content = (
        '<section id="empty"><h2>Empty</h2></section>'
        '<section id="new-section"><h1>New</h1>'
        '<article class="mkplace-item"><h3 class="mkplace-item__title">No link</h3>'
        '<p class="mkplace-item__bodycopy">Some tool</p></article>'
        '<article class="mkplace-item"><p class="mkplace-item__bodycopy">No name</p></article></section>'
    )

    results = await crawl_page(fresh, response(URL, content))

    assert [
        (item["name"], item["url"], item["delivery"], item["marketplace_categories"]) for item in items(results)
    ] == [("No link", None, "other", ["New"])]
    assert items(results)[0]["marketplace_category_paths"] == [{"path": ["New"], "id": "new-section"}]


async def test_page_without_cards_is_an_error(
    fresh: ExoscaleMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(fresh, response(URL, "<html><body><section id='x'></section></body></html>"))

    assert any(record.levelname == "ERROR" and "holds no software" in record.getMessage() for record in caplog.records)


async def test_sitemap_without_page_is_an_error(
    fresh: ExoscaleMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(CatalogueFormatError, match="the sitemap lists no page"):
        await crawl_page(fresh, response(SITEMAP, "<urlset></urlset>", {"sitemap": True}))

    assert [record.levelname for record in caplog.records].count("ERROR") == 1
