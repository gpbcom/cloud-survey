from __future__ import annotations

import logging
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.gcore.crawler import GcoreCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
VDS_URL = "https://gcore.com/hosting/vds"
LINK = (
    '<a class="gc-menu-link-item" href="{href}"><div><h3 class="gc-menu-link-item__label">{name}</h3>'
    '<p class="gc-menu-link-item__description">{description}</p></div></a>'
)


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def menu_page(tabs: List[str], grids: List[str]) -> Response:
    rail = "".join(f'<span class="gc-tabbed-menu__rail-label">{tab}</span>' for tab in tabs)
    content = "".join(f'<div class="gc-tabbed-menu__grid">{grid}</div>' for grid in grids)
    return page(GcoreCrawler.catalogue_url, f'<div class="gc-tabbed-menu"><nav>{rail}</nav>{content}</div>')


def product_page(head: str, body: str) -> Response:
    return page(VDS_URL, f"<html><head>{head}</head><body>{body}</body></html>", {GcoreCrawler.PRODUCT_PAGE: VDS_URL})


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = GcoreCrawler()

    assert crawler.name == "gcore"
    assert GcoreCrawler.catalogue_url == "https://gcore.com/"
    assert GcoreCrawler.complement_urls == ("https://gcore.com/sitemap-main.xml",)
    assert GcoreCrawler.name_prefixes == ("Gcore ",)
    assert crawler.allowed_domains == {"gcore.com"}


async def test_extracts_the_menu_products(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(GcoreCrawler(), make_response(GcoreCrawler.catalogue_url, "gcore_home.html"))

    assert names(results) == ["CDN", "DNS", "GPU Cloud", "Compute", "Hosting", "WAF"]
    assert results[3] == {
        "name": "Compute",
        "description": "Run apps on virtual machines or bare metal",
        "pricing_policy": [],
        "url": "https://gcore.com/cloud/bare-metal",
    }


@pytest.mark.parametrize("excluded", ["Gaming", "Media & Streaming", "Global Content Delivery", "Cloud Migration"])
async def test_use_case_tabs_are_skipped(make_response: MakeResponse, crawl_page: CrawlPage, excluded: str) -> None:
    results = await crawl_page(GcoreCrawler(), make_response(GcoreCrawler.catalogue_url, "gcore_home.html"))

    assert excluded not in names(results)


async def test_sitemap_requests_the_allowlisted_product_pages(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = GcoreCrawler()
    await crawl_page(crawler, make_response(GcoreCrawler.catalogue_url, "gcore_home.html"))

    results = await crawl_page(crawler, make_response(GcoreCrawler.SITEMAP_URL, "gcore_sitemap.xml"))

    assert [(request.url, request.priority, request.meta) for request in results if isinstance(request, Request)] == [
        (url, 0, {GcoreCrawler.PRODUCT_PAGE: url})
        for url in ("https://gcore.com/cloud/virtual-machines", VDS_URL, "https://gcore.com/public-dns")
    ]


async def test_empty_sitemap_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(CatalogueFormatError, match="lists no page"):
        await crawl_page(GcoreCrawler(), page(GcoreCrawler.SITEMAP_URL, "<urlset></urlset>"))

    assert any(record.levelno == logging.ERROR and "lists no page" in record.getMessage() for record in caplog.records)


async def test_product_page_is_named_after_its_heading(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(VDS_URL, "gcore_product_page.html")
    response.meta[GcoreCrawler.PRODUCT_PAGE] = VDS_URL

    results = await crawl_page(GcoreCrawler(), response)

    assert results == [
        {
            "name": "VDS Hosting",
            "description": "Buy VDS virtual servers from €3.25/month. KVM-based hosting in USA, Europe, Asia with SSD "
            "drives, DDoS protection, and 200 Mbit/s speed. 24/7 support. Instant setup.",
            "pricing_policy": [],
            "url": VDS_URL,
        }
    ]


@pytest.mark.parametrize(
    ("head", "body", "expected"),
    [
        ('<meta property="og:title" content="Container Registry | Gcore">', "", ["Container Registry"]),
        ("", "<h1>Gcore Peering</h1>", ["Gcore Peering"]),
        ("", "<h1>Load balancers \u2013 Gcore Cloud</h1>", ["Load balancers"]),
        ("", "<h1>DataBox: the 5G offer</h1>", ["DataBox"]),
        ('<meta property="og:title" content="Under attack">', "<h1> </h1>", ["Under attack"]),
        ("", "<p>No title</p>", []),
    ],
    ids=["og title", "heading", "dash suffix", "colon suffix", "empty heading", "untitled"],
)
async def test_product_page_names(crawl_page: CrawlPage, head: str, body: str, expected: List[str]) -> None:
    head += '<meta name="description" content="A product.">'

    assert names(await crawl_page(GcoreCrawler(), product_page(head, body))) == expected


async def test_menu_links_without_name_or_description_are_skipped(crawl_page: CrawlPage) -> None:
    grid = '<a class="gc-menu-link-item" href="/cdn"><h3 class="gc-menu-link-item__label">CDN</h3></a>'
    grid += LINK.format(href="/dns", name="DNS", description="Fast DNS")

    results = await crawl_page(GcoreCrawler(), menu_page(["Edge Network"], [grid]))

    assert names(results) == ["DNS"]


async def test_grids_without_tab_are_kept(crawl_page: CrawlPage) -> None:
    grids = [
        LINK.format(href="/cdn/gaming", name="Gaming", description="Keep lag out of play"),
        LINK.format(href="/storage", name="Gcore Storage", description="S3-compatible storage"),
    ]

    results = await crawl_page(GcoreCrawler(), menu_page(["By Industry"], grids))

    assert names(results) == ["Gcore Storage"]


async def test_page_without_menu_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(EmptyCatalogueError):
        await crawl_page(GcoreCrawler(), page(GcoreCrawler.catalogue_url, "<html><body></body></html>"))

    assert any(
        record.levelno == logging.ERROR and "holds no product" in record.getMessage() for record in caplog.records
    )


@pytest.mark.parametrize(
    ("first", "second"), [("Gcore Storage", "Storage"), ("Managed Kubernetes", "Gcore Managed Kubernetes")]
)
async def test_brand_prefix_is_ignored(crawl_page: CrawlPage, first: str, second: str) -> None:
    grid = LINK.format(href="/a", name=first, description="One") + LINK.format(
        href="/b", name=second, description="Two"
    )

    assert names(await crawl_page(GcoreCrawler(), menu_page(["Cloud"], [grid]))) == [first]


async def test_invalid_menu_products_are_skipped(crawl_page: CrawlPage) -> None:
    grid = LINK.format(href="/a", name="x" * 201, description="Too long")
    grid += LINK.format(href="/fastedge", name="Fast Edge", description="Serverless apps at the edge")

    assert names(await crawl_page(GcoreCrawler(), menu_page(["Edge Network"], [grid]))) == ["Fast Edge"]


async def test_sitemap_skips_the_product_pages_already_streamed(crawl_page: CrawlPage) -> None:
    crawler = GcoreCrawler()
    crawler.seen_urls.add("gcore.com/hosting/vds")
    sitemap = f"<urlset><url><loc>{VDS_URL}/</loc></url><url><loc>https://gcore.com/pentest</loc></url></urlset>"

    results = await crawl_page(crawler, page(GcoreCrawler.SITEMAP_URL, sitemap))

    assert [request.url for request in results if isinstance(request, Request)] == ["https://gcore.com/pentest"]
