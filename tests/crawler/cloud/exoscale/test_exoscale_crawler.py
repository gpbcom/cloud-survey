from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.exoscale.crawler import ExoscaleCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
SITE = "https://www.exoscale.com"
SCION_URL = f"{SITE}/scion-network/"


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def menu_page(*entries: str) -> Response:
    return page(ExoscaleCrawler.catalogue_url, f'<nav><div id="dropdown-products">{"".join(entries)}</div></nav>')


def product_page(head: str, body: str = "") -> Response:
    content = f"<html><head>{head}</head><body>{body}</body></html>"
    return page(SCION_URL, content, {ExoscaleCrawler.PRODUCT_PAGE: SCION_URL})


def requested(results: List[Union[Dict[str, JsonValue], Request]]) -> List[str]:
    return [request.url for request in results if isinstance(request, Request)]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = ExoscaleCrawler()

    assert crawler.name == "exoscale"
    assert ExoscaleCrawler.catalogue_url == "https://www.exoscale.com/products/"
    assert ExoscaleCrawler.complement_urls == ("https://www.exoscale.com/sitemap.xml",)
    assert ExoscaleCrawler.name_prefixes == ("Exoscale ",)
    assert crawler.allowed_domains == {"www.exoscale.com"}
    assert crawler.not_product_urls == set()


async def test_extracts_the_menu_products(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        ExoscaleCrawler(), make_response(ExoscaleCrawler.catalogue_url, "exoscale_products.html")
    )

    assert names(results) == [
        "Compute Instances",
        "GPU Servers",
        "Dedicated Inference",
        "Object Storage",
        "Archival Storage",
        "Key Management Service",
    ]
    assert results[0] == {
        "name": "Compute Instances",
        "description": "SSD-backed VMs billed by the second",
        "pricing_policy": [],
        "url": f"{SITE}/compute/",
        "catalogue_categories": ["Compute"],
    }
    assert results[5] == {
        "name": "Key Management Service",
        "description": "Create and control your own encryption keys",
        "pricing_policy": [],
        "url": "https://community.exoscale.com/product/security/kms/",
        "catalogue_categories": ["Security"],
    }


async def test_menu_products_are_filed_under_their_tabs_and_groups(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(
        ExoscaleCrawler(), make_response(ExoscaleCrawler.catalogue_url, "exoscale_products.html")
    )

    categories = {result["name"]: result.get("catalogue_categories") for result in results if isinstance(result, dict)}
    assert categories == {
        "Compute Instances": ["Compute"],
        "GPU Servers": ["Compute", "Concrete AI", "GPUs and Databases"],
        "Dedicated Inference": ["Concrete AI", "Inference"],
        "Object Storage": ["Storage"],
        "Archival Storage": ["Storage", "Object Storage"],
        "Key Management Service": ["Security"],
    }


async def test_overviews_and_compliance_entries_are_remembered(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = ExoscaleCrawler()

    results = await crawl_page(crawler, make_response(ExoscaleCrawler.catalogue_url, "exoscale_products.html"))

    assert {"Concrete AI Overview", "Encryption"}.isdisjoint(names(results))
    assert crawler.not_product_urls == {"exoscale.com/ai-cloud-infrastructure", "exoscale.com/compliance/encryption"}


async def test_menu_entries_without_link_or_description(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    crawler = ExoscaleCrawler()

    results = await crawl_page(
        crawler,
        menu_page(
            '<a class="mega__item"><b>Storage Overview</b><span>All storages</span></a>',
            '<a class="mega__item" href="/dns/"><b>DNS</b></a>',
            '<a class="mega__item"><b>SCION</b><span>Secure networking</span></a>',
        ),
    )

    assert results == [{"name": "SCION", "description": "Secure networking", "pricing_policy": [], "url": None}]
    assert crawler.not_product_urls == set()
    assert any(record.levelname == "WARNING" and "DNS" in record.message for record in caplog.records)


async def test_page_without_menu_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(ExoscaleCrawler(), page(ExoscaleCrawler.catalogue_url, "<html><body></body></html>"))

    assert any(record.levelname == "ERROR" and "holds no product" in record.message for record in caplog.records)


async def test_sitemap_requests_the_product_pages_missing_from_the_menu(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = ExoscaleCrawler()
    await crawl_page(crawler, make_response(ExoscaleCrawler.catalogue_url, "exoscale_products.html"))

    results = await crawl_page(crawler, make_response(ExoscaleCrawler.SITEMAP_URL, "exoscale_sitemap.xml"))

    assert [(request.url, request.priority, request.meta) for request in results if isinstance(request, Request)] == [
        (SCION_URL, 0, {ExoscaleCrawler.PRODUCT_PAGE: SCION_URL})
    ]


async def test_sitemap_keeps_the_top_level_product_pages(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(ExoscaleCrawler(), make_response(ExoscaleCrawler.SITEMAP_URL, "exoscale_sitemap.xml"))

    assert requested(results) == [f"{SITE}/ai-cloud-infrastructure/", f"{SITE}/compute/", SCION_URL]


async def test_empty_sitemap_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(CatalogueFormatError, match="lists no page"):
        await crawl_page(ExoscaleCrawler(), page(ExoscaleCrawler.SITEMAP_URL, "<urlset></urlset>"))

    assert any(record.levelname == "ERROR" and "lists no page" in record.message for record in caplog.records)


async def test_product_page_repeating_its_title_is_described_by_its_header(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    response = make_response(SCION_URL, "exoscale_product_page.html")
    response.meta[ExoscaleCrawler.PRODUCT_PAGE] = SCION_URL

    results = await crawl_page(ExoscaleCrawler(), response)

    assert results == [
        {
            "name": "Scion Network",
            "description": "The Secure & Reliable Future of Networking. Take security to the next level with the SCION "
            "network. At Exoscale, you can access the SCION Internet using our compute instances. Connect your "
            "existing services securely using templates and integrations from our partners like Anapaya and Sunrise.",
            "pricing_policy": [],
            "url": SCION_URL,
        }
    ]


@pytest.mark.parametrize(
    ("head", "description"),
    [
        (
            '<meta property="og:title" content="SCION"><meta name="description" content="Secure paths.">',
            "Secure paths.",
        ),
        ('<meta name="description" content="Secure paths."><title>SCION</title>', "Secure paths."),
        ('<meta property="og:title" content="SCION"><meta name="description" content="Scion">', "Scion"),
    ],
    ids=["meta description", "no Open Graph title", "no header"],
)
async def test_product_page_descriptions(crawl_page: CrawlPage, head: str, description: str) -> None:
    results = await crawl_page(ExoscaleCrawler(), product_page(head, "<h1>SCION</h1>"))

    assert [result["description"] for result in results if isinstance(result, dict)] == [description]


async def test_product_page_without_description_is_skipped(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    results = await crawl_page(ExoscaleCrawler(), product_page('<meta property="og:title" content="SCION">'))

    assert results == []
    assert any(record.levelname == "WARNING" and "SCION" in record.message for record in caplog.records)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Exoscale Scion Network", "Scion Network"),
        ("Sovereign, Liquid-Cooled GPUs | Exoscale", "Sovereign, Liquid-Cooled GPUs"),
        ("Grafana", "Grafana"),
    ],
)
def test_page_titles_lose_their_brand(title: str, expected: str) -> None:
    assert ExoscaleCrawler()._page_title(title) == expected
