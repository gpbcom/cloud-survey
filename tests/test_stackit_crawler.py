from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.stackit.crawler import STACKITCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
DISTRIBUTED_URL = "https://stackit.com/en/products/stackit-distributed-cloud"
INTAKE_URL = "https://stackit.com/en/products/data-ai/stackit-intake"


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def tile(name: Optional[str], details: Optional[str], link: Optional[str]) -> str:
    title = f'<span class="digits-tile__title-line">{name}</span>' if name is not None else ""
    paragraph = f'<p class="digits-tile__details">{details}</p>' if details is not None else ""
    anchor = f'<a class="digits-base-tile__link" href="{link}"></a>' if link is not None else ""
    return f'<article class="digits-base-tile">{anchor}<h3>{title}</h3>{paragraph}</article>'


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = STACKITCrawler()

    assert crawler.name == "stackit"
    assert STACKITCrawler.catalogue_url == "https://stackit.com/en/products"
    assert STACKITCrawler.complement_urls == ("https://stackit.com/en/sitemap/default.xml",)
    assert STACKITCrawler.name_prefixes == ("STACKIT ",)
    assert crawler.allowed_domains == {"stackit.com"}


async def test_extracts_the_product_tiles(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(STACKITCrawler(), make_response(STACKITCrawler.catalogue_url, "stackit_products.html"))

    assert names(results) == [
        "STACKIT Server Update Management",
        "STACKIT Compute Engine",
        "STACKIT DNS",
        "STACKIT Workflows",
    ]
    assert results[2] == {
        "name": "STACKIT DNS",
        "description": "Fast and public DNS resolution",
        "pricing_policy": [],
        "url": "https://stackit.com/en/products/network/stackit-dns",
    }


async def test_invalid_tiles_are_skipped(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    tiles = [
        tile(None, "No name", "/en/products/runtime/nameless"),
        tile("STACKIT Nothing", None, "/en/products/runtime/stackit-nothing"),
        tile("STACKIT Linkless", "Without page", None),
    ]

    results = await crawl_page(STACKITCrawler(), page(STACKITCrawler.catalogue_url, "".join(tiles)))

    assert results == [{"name": "STACKIT Linkless", "description": "Without page", "pricing_policy": [], "url": None}]
    assert any(record.levelname == "WARNING" and "STACKIT Nothing" in record.message for record in caplog.records)


async def test_page_without_tiles_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(STACKITCrawler(), page(STACKITCrawler.catalogue_url, "<html><body></body></html>"))

    assert any(record.levelname == "ERROR" and "holds no product" in record.message for record in caplog.records)


async def test_sitemap_requests_the_product_pages_missing_from_the_tiles(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = STACKITCrawler()
    await crawl_page(crawler, make_response(STACKITCrawler.catalogue_url, "stackit_products.html"))

    results = await crawl_page(crawler, make_response(STACKITCrawler.SITEMAP_URL, "stackit_sitemap.xml"))

    assert [(request.url, request.priority, request.meta) for request in results if isinstance(request, Request)] == [
        (
            INTAKE_URL,
            0,
            {STACKITCrawler.PRODUCT_PAGE: INTAKE_URL, STACKITCrawler.PRODUCT_UPDATED: "2026-06-16T08:54:42+02:00"},
        ),
        (
            DISTRIBUTED_URL,
            0,
            {
                STACKITCrawler.PRODUCT_PAGE: DISTRIBUTED_URL,
                STACKITCrawler.PRODUCT_UPDATED: "2026-10-15T10:14:56+02:00",
            },
        ),
    ]


async def test_sitemap_pages_without_last_modification_are_undated(crawl_page: CrawlPage) -> None:
    sitemap = f"<urlset><url><loc>{DISTRIBUTED_URL}</loc></url></urlset>"

    results = await crawl_page(STACKITCrawler(), page(STACKITCrawler.SITEMAP_URL, sitemap))

    assert [(request.url, request.meta) for request in results if isinstance(request, Request)] == [
        (DISTRIBUTED_URL, {STACKITCrawler.PRODUCT_PAGE: DISTRIBUTED_URL})
    ]


async def test_empty_sitemap_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(CatalogueFormatError, match="lists no page"):
        await crawl_page(STACKITCrawler(), page(STACKITCrawler.SITEMAP_URL, "<urlset></urlset>"))

    assert any(record.levelname == "ERROR" and "lists no page" in record.message for record in caplog.records)


async def test_product_page(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(DISTRIBUTED_URL, "stackit_product_page.html")
    response.meta[STACKITCrawler.PRODUCT_PAGE] = DISTRIBUTED_URL

    results = await crawl_page(STACKITCrawler(), response)

    assert results == [
        {
            "name": "STACKIT Distributed Cloud",
            "description": "Cloud power right in your data center: BSI-compliant, air-gapped, and digitally sovereign. "
            "Perfect for KRITIS. Learn more now!",
            "pricing_policy": [],
            "url": DISTRIBUTED_URL,
        }
    ]


async def test_product_page_is_dated_by_its_sitemap_last_modification(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    response = make_response(DISTRIBUTED_URL, "stackit_product_page.html")
    response.meta[STACKITCrawler.PRODUCT_PAGE] = DISTRIBUTED_URL
    response.meta[STACKITCrawler.PRODUCT_UPDATED] = "2026-10-15T10:14:56+02:00"

    results = await crawl_page(STACKITCrawler(), response)

    assert [
        (result["name"], result.get("added_at"), result["updated_at"]) for result in results if isinstance(result, dict)
    ] == [("STACKIT Distributed Cloud", None, "2026-10-15T08:14:56Z")]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("STACKIT DNS: Highly available and fast domain resolution", "STACKIT DNS"),
        ("STACKIT Distributed Cloud | Sovereign On-Premises Cloud", "STACKIT Distributed Cloud"),
        ("STACKIT Git \u2013 Store and manage code", "STACKIT Git"),
        ("STACKIT  Network & Security", "STACKIT Network & Security"),
    ],
)
def test_page_titles_lose_their_tagline(title: str, expected: str) -> None:
    assert STACKITCrawler()._page_title(title) == expected
