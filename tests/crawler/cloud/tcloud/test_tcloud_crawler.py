from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.tcloud.crawler import TCloudPublicCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
CORE_SERVICES = "https://www.t-cloud-public.com/en/products-services/core-services"
BMS_URL = f"{CORE_SERVICES}/bare-metal-server"


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def product_page(head: str, body: str) -> Response:
    content = f"<html><head>{head}</head><body>{body}</body></html>"
    return page(BMS_URL, content, {TCloudPublicCrawler.PRODUCT_PAGE: BMS_URL})


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = TCloudPublicCrawler()

    assert crawler.name == "tcloud"
    assert TCloudPublicCrawler.catalogue_url == CORE_SERVICES
    assert TCloudPublicCrawler.complement_urls == ("https://www.t-cloud-public.com/en/sitemap.xml",)
    assert TCloudPublicCrawler.name_prefixes == ("T Cloud Public ", "Open Telekom Cloud ")
    assert crawler.allowed_domains == {"www.t-cloud-public.com"}


async def test_extracts_the_services_tables(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(TCloudPublicCrawler(), make_response(CORE_SERVICES, "tcloud_core_services.html"))

    assert names(results) == [
        "Auto Scaling",
        "Dedicated Host",
        "Elastic Cloud Server",
        "Cloud Backup and Recovery",
        "Cloud Server Backup Service",
        "Elastic Volume Service",
    ]
    assert results[0] == {
        "name": "Auto Scaling",
        "description": "Scale your servers automatically based on defined metrics",
        "pricing_policy": [],
        "url": f"{CORE_SERVICES}/auto-scaling",
        "catalogue_categories": ["Computing"],
    }
    assert [result.get("catalogue_categories") for result in results if isinstance(result, dict)][3:] == [
        ["Storage"],
        ["Storage"],
        ["Storage"],
    ]


async def test_services_listed_in_several_tables_get_all_their_categories(crawl_page: CrawlPage) -> None:
    row = (
        '<tr><td><a href="/en/products-services/core-services/cloud-eye">Cloud Eye</a></td>'
        '<td><scale-tooltip><div slot="content">Monitoring</div></scale-tooltip></td></tr>'
    )
    tables = "".join(
        f"<table><tr><td><strong>{category}</strong></td><td>Region DE</td></tr>{row}</table>"
        for category in ("Management", "Security")
    )

    results = await crawl_page(TCloudPublicCrawler(), page(CORE_SERVICES, tables))

    assert [result.get("catalogue_categories") for result in results if isinstance(result, dict)] == [
        ["Management", "Security"]
    ]


async def test_invalid_rows_are_skipped(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    tooltip = '<td><scale-tooltip><div slot="content">{}</div></scale-tooltip></td>'
    rows = [
        "<tr><td><strong>Computing</strong></td><td>Region DE</td></tr>",
        '<tr><td><a href="/en/products-services/core-services/no-tooltip">No Tooltip</a></td></tr>',
        '<tr><td><a href="/en/products-services/managed-services">Managed</a></td>'
        + tooltip.format("Managed")
        + "</tr>",
        '<tr><td><a href="/en/products-services/core-services/cloud-eye">Cloud Eye</a></td>'
        + tooltip.format("Monitoring")
        + "</tr>",
    ]

    results = await crawl_page(TCloudPublicCrawler(), page(CORE_SERVICES, f"<table>{''.join(rows)}</table>"))

    assert names(results) == ["Cloud Eye"]
    assert any(record.levelname == "WARNING" and "No Tooltip" in record.message for record in caplog.records)


async def test_page_without_services_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(TCloudPublicCrawler(), page(CORE_SERVICES, "<html><body><table></table></body></html>"))

    assert any(record.levelname == "ERROR" and "holds no product" in record.message for record in caplog.records)


async def test_sitemap_requests_the_product_pages_missing_from_the_tables(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = TCloudPublicCrawler()
    await crawl_page(crawler, make_response(CORE_SERVICES, "tcloud_core_services.html"))

    results = await crawl_page(crawler, make_response(TCloudPublicCrawler.SITEMAP_URL, "tcloud_sitemap.xml"))

    assert [(request.url, request.priority, request.meta) for request in results if isinstance(request, Request)] == [
        (
            BMS_URL,
            0,
            {
                TCloudPublicCrawler.PRODUCT_PAGE: BMS_URL,
                TCloudPublicCrawler.PRODUCT_UPDATED: "2024-05-02T11:12:53+02:00",
            },
        )
    ]


async def test_empty_sitemap_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(CatalogueFormatError, match="lists no page"):
        await crawl_page(TCloudPublicCrawler(), page(TCloudPublicCrawler.SITEMAP_URL, "<urlset></urlset>"))

    assert any(record.levelname == "ERROR" and "lists no page" in record.message for record in caplog.records)


async def test_product_page_is_named_after_its_heading(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(BMS_URL, "tcloud_product_page.html")
    response.meta[TCloudPublicCrawler.PRODUCT_PAGE] = BMS_URL

    results = await crawl_page(TCloudPublicCrawler(), response)

    assert results == [
        {
            "name": "Bare Metal Server (BMS)",
            "description": "Bring your ideas to life with customised hardware resources designed for Machine Learning "
            "and AI scenarios. No need for hypervisors & virtualization.",
            "pricing_policy": [],
            "url": BMS_URL,
        }
    ]


async def test_product_page_is_dated_by_its_sitemap_last_modification(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    response = make_response(BMS_URL, "tcloud_product_page.html")
    response.meta[TCloudPublicCrawler.PRODUCT_PAGE] = BMS_URL
    response.meta[TCloudPublicCrawler.PRODUCT_UPDATED] = "2024-05-02T11:12:53+02:00"

    results = await crawl_page(TCloudPublicCrawler(), response)

    assert [
        (result["name"], result.get("added_at"), result["updated_at"]) for result in results if isinstance(result, dict)
    ] == [("Bare Metal Server (BMS)", None, "2024-05-02T09:12:53Z")]


@pytest.mark.parametrize("body", ["", "<h1> </h1>"], ids=["no heading", "empty heading"])
async def test_product_page_without_heading_is_named_after_its_title(crawl_page: CrawlPage, body: str) -> None:
    head = (
        '<meta property="og:title" content="Bare Metal Server | T Cloud Public"><meta name="description" content="BMS">'
    )

    results = await crawl_page(TCloudPublicCrawler(), product_page(head, body))

    assert names(results) == ["Bare Metal Server"]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Bare Metal Server | T Cloud Public", "Bare Metal Server"),
        ("Elastic Cloud Server  |  Open Telekom Cloud", "Elastic Cloud Server"),
        ("Cloud Eye", "Cloud Eye"),
    ],
)
def test_page_titles_lose_their_brand_suffix(title: str, expected: str) -> None:
    assert TCloudPublicCrawler()._page_title(title) == expected
