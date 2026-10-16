from __future__ import annotations

import json
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.ovh.crawler import OVHcloudCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
NC2_URL = "https://www.ovhcloud.com/en/hosted-private-cloud/nutanix/nc2/"


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def next_data_page(data: JsonValue) -> Response:
    script = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
    return page(OVHcloudCrawler.catalogue_url, f"<html><body>{script}</body></html>")


def product_page(title: str, description: str = "A product.", url: str = NC2_URL, requested: str = NC2_URL) -> Response:
    head = f'<meta property="og:title" content="{title}"><meta name="description" content="{description}">'
    return page(url, f"<html><head>{head}</head><body></body></html>", {OVHcloudCrawler.PRODUCT_PAGE: requested})


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = OVHcloudCrawler()

    assert crawler.name == "ovhcloud"
    assert OVHcloudCrawler.catalogue_url == "https://www.ovhcloud.com/en-gb/public-cloud/"
    assert OVHcloudCrawler.complement_urls == ("https://www.ovhcloud.com/en/www.ovhcloud.com_en_sitemap.xml",)
    assert crawler.allowed_domains == {"www.ovhcloud.com"}
    assert crawler.category_urls == set()


async def test_extracts_the_menu_products(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(OVHcloudCrawler(), make_response(OVHcloudCrawler.catalogue_url, "ovh_public_cloud.html"))

    assert names(results) == [
        "Compute",
        "Managed Kubernetes Service",
        "Storage",
        "VMware on OVHcloud",
        "Nutanix on OVHcloud",
    ]
    assert results[1] == {
        "name": "Managed Kubernetes Service",
        "description": "Container orchestration for demanding environments",
        "pricing_policy": [],
        "url": "https://www.ovhcloud.com/en/public-cloud/kubernetes/",
    }


@pytest.mark.parametrize(
    "excluded",
    ["Serverless", "Traffic spike management", "All Public Cloud products", "Public Cloud", "Who are we?", "Resources"],
)
async def test_menu_non_products_are_filtered_out(
    make_response: MakeResponse, crawl_page: CrawlPage, excluded: str
) -> None:
    results = await crawl_page(OVHcloudCrawler(), make_response(OVHcloudCrawler.catalogue_url, "ovh_public_cloud.html"))

    assert excluded not in names(results)


async def test_menu_categories_are_remembered(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = OVHcloudCrawler()

    await crawl_page(crawler, make_response(OVHcloudCrawler.catalogue_url, "ovh_public_cloud.html"))

    assert crawler.category_urls == {
        "ovhcloud.com/public-cloud",
        "ovhcloud.com/hosted-private-cloud",
        "ovhcloud.com/about-us",
    }


@pytest.mark.parametrize(
    "data",
    [{"props": {}}, {"props": {"pageProps": {"itemsDesktop": []}}}, {"props": {"pageProps": {"itemsDesktop": {}}}}],
)
async def test_page_without_menu_is_an_error(
    crawl_page: CrawlPage, data: JsonValue, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(CatalogueFormatError, match="products menu"):
        await crawl_page(OVHcloudCrawler(), next_data_page(data))

    assert any(record.levelname == "ERROR" and "no products menu" in record.getMessage() for record in caplog.records)


async def test_menu_without_product_is_an_error(crawl_page: CrawlPage) -> None:
    menu: JsonValue = {"home": [{"level": 1, "label": "Public Cloud", "children": [{"level": 2, "children": []}]}]}

    with pytest.raises(EmptyCatalogueError):
        await crawl_page(OVHcloudCrawler(), next_data_page({"props": {"pageProps": {"itemsDesktop": menu}}}))


async def test_sitemap_requests_the_product_pages_missing_from_the_menu(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = OVHcloudCrawler()
    await crawl_page(crawler, make_response(OVHcloudCrawler.catalogue_url, "ovh_public_cloud.html"))

    results = await crawl_page(crawler, make_response(OVHcloudCrawler.SITEMAP_URL, "ovh_sitemap.xml"))

    assert [(request.url, request.priority, request.meta) for request in results if isinstance(request, Request)] == [
        (
            NC2_URL,
            0,
            {OVHcloudCrawler.PRODUCT_PAGE: NC2_URL, OVHcloudCrawler.PRODUCT_UPDATED: "2026-09-22T09:41:05+00:00"},
        )
    ]


async def test_sitemap_pages_without_last_modification_are_undated(crawl_page: CrawlPage) -> None:
    sitemap = f"<urlset><url><loc>{NC2_URL}</loc></url></urlset>"

    results = await crawl_page(OVHcloudCrawler(), page(OVHcloudCrawler.SITEMAP_URL, sitemap))

    assert [(request.url, request.meta) for request in results if isinstance(request, Request)] == [
        (NC2_URL, {OVHcloudCrawler.PRODUCT_PAGE: NC2_URL})
    ]


async def test_empty_sitemap_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(CatalogueFormatError, match="lists no page"):
        await crawl_page(OVHcloudCrawler(), page(OVHcloudCrawler.SITEMAP_URL, "<urlset></urlset>"))

    assert any(record.levelname == "ERROR" and "lists no page" in record.getMessage() for record in caplog.records)


async def test_product_page(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(NC2_URL, "ovh_product_page.html")
    response.meta[OVHcloudCrawler.PRODUCT_PAGE] = NC2_URL

    results = await crawl_page(OVHcloudCrawler(), response)

    assert results == [
        {
            "name": "Nutanix Cloud Clusters (NC2) on OVHcloud",
            "description": "NC2 on OVHcloud: Enjoy the sovereignty of OVH datacentres for your multi-cloud migrations, "
            "while keeping your costs under control.",
            "pricing_policy": [],
            "url": NC2_URL,
        }
    ]


async def test_product_page_is_dated_by_its_sitemap_last_modification(crawl_page: CrawlPage) -> None:
    response = product_page("Nutanix NC2")
    response.meta[OVHcloudCrawler.PRODUCT_UPDATED] = "2026-09-22T09:41:05+00:00"

    results = await crawl_page(OVHcloudCrawler(), response)

    assert results == [
        {
            "name": "Nutanix NC2",
            "description": "A product.",
            "pricing_policy": [],
            "url": NC2_URL,
            "updated_at": "2026-09-22T09:41:05Z",
        }
    ]


@pytest.mark.parametrize(
    "response",
    [
        product_page("DDoS: definition, specifics and how to protect"),
        product_page("What is a DDoS attack?"),
        product_page(""),
        product_page("Hosted Private Cloud", url="https://www.ovhcloud.com/en/hosted-private-cloud/vmware/"),
    ],
    ids=["article", "question", "untitled", "redirected"],
)
async def test_non_product_pages_are_skipped(crawl_page: CrawlPage, response: Response) -> None:
    assert await crawl_page(OVHcloudCrawler(), response) == []


async def test_product_page_already_streamed_is_skipped(crawl_page: CrawlPage) -> None:
    crawler = OVHcloudCrawler()

    first = await crawl_page(crawler, product_page("Nutanix NC2"))
    second = await crawl_page(crawler, product_page("NC2 on Nutanix"))

    assert (names(first), second) == (["Nutanix NC2"], [])


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            "https://www.ovhcloud.com/en-gb/public-cloud/kubernetes/",
            "https://www.ovhcloud.com/en/public-cloud/kubernetes",
        ),
        ("https://www.ovhcloud.com/fr/public-cloud/", "https://ovhcloud.com/en-ie/public-cloud/?utm=menu"),
    ],
)
def test_url_keys_ignore_the_locale(first: str, second: str) -> None:
    crawler = OVHcloudCrawler()

    assert crawler._url_key(first) == crawler._url_key(second)


async def test_menu_tree_shapes(crawl_page: CrawlPage) -> None:
    def leaf(label: str, description: str) -> JsonValue:
        return {"level": 3, "label": label, "description": description, "link": None, "children": []}

    menu: JsonValue = {
        "public-cloud": {
            "id": 1,
            "columns": [
                "not a node",
                5,
                {
                    "level": 1,
                    "label": "Public Cloud",
                    "children": [leaf("x" * 201, "Too long"), leaf("Gateway", "NAT")],
                },
            ],
        },
    }

    results = await crawl_page(OVHcloudCrawler(), next_data_page({"props": {"pageProps": {"itemsDesktop": menu}}}))

    assert names(results) == ["Gateway"]
