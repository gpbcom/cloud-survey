from __future__ import annotations

import logging
from typing import Awaitable, Callable, Dict, List, Optional, Tuple, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.krystal.crawler import KrystalCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
VOIP_URL = "https://krystal.io/voip"


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Tuple[str, JsonValue]]:
    return [(result.url, result.meta[KrystalCrawler.PRODUCT_NAME]) for result in results if isinstance(result, Request)]


def test_configuration() -> None:
    crawler = KrystalCrawler()

    assert crawler.name == "krystal"
    assert KrystalCrawler.catalogue_url == "https://krystal.io/cloud/products"
    assert KrystalCrawler.complement_urls == ("https://krystal.io/sitemap", "https://krystal.io/sitemap.xml")
    assert crawler.allowed_domains == {"krystal.io"}


async def test_extracts_the_cloud_products(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        KrystalCrawler(), make_response(KrystalCrawler.catalogue_url, "krystal_cloud_products.html")
    )

    assert names(results) == [
        "Virtual Machines",
        "CPU Optimised",
        "Memory Optimised",
        "GPUs",
        "Block Storage",
        "File Storage",
        "Object Storage",
        "Backups",
        "Container Registry",
        "DNS Management",
        "SDN Private Networks",
        "Load Balancers",
        "Firewall",
    ]
    assert results[6] == {
        "name": "Object Storage",
        "description": "High-speed, secure, and scalable S3-compatible object storage solution.",
        "pricing_policy": [],
        "url": "https://krystal.io/cloud/storage/object-storage",
        "catalogue_categories": ["Storage"],
    }
    assert requests(results) == []


async def test_cloud_products_are_filed_under_their_sections(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(
        KrystalCrawler(), make_response(KrystalCrawler.catalogue_url, "krystal_cloud_products.html")
    )

    categories = {result["name"]: result["catalogue_categories"] for result in results if isinstance(result, dict)}
    assert categories["GPUs"] == ["Compute"]
    assert categories["Backups"] == ["Storage"]
    assert categories["Firewall"] == ["Networking"]


async def test_cloud_card_of_several_sections_is_streamed_once(crawl_page: CrawlPage) -> None:
    card = '<ul><li><a href="/cloud/gpus"><h3>GPUs</h3><p>Nvidia GPUs.</p></a></li></ul>'
    content = f"<main><section><h2>Compute</h2>{card}</section><section><h2>AI</h2>{card}</section></main>"

    results = await crawl_page(KrystalCrawler(), page(KrystalCrawler.catalogue_url, content))

    assert [(result["name"], result["catalogue_categories"]) for result in results if isinstance(result, dict)] == [
        ("GPUs", ["Compute", "AI"])
    ]


async def test_extracts_the_product_sections_of_the_html_sitemap(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(KrystalCrawler(), make_response(KrystalCrawler.SITEMAP_PAGE_URL, "krystal_sitemap.html"))

    assert names(results) == [
        "Web Hosting",
        "Business Hosting",
        "Managed WordPress",
        "Reseller Hosting",
        "VPS Hosting",
        "CDN",
        "Domain names",
    ]
    assert [result for result in results if isinstance(result, dict)][-1] == {
        "name": "Domain names",
        "description": "Register a domain with Krystal",
        "pricing_policy": [],
        "url": "https://krystal.io/domains",
        "catalogue_categories": ["Domain Names"],
    }
    items = [result for result in results if isinstance(result, dict)]
    assert items[0]["catalogue_categories"] == ["Website Hosting"]
    assert names(results).index("CDN") == 5
    assert items[5]["catalogue_categories"] == ["Servers"]


@pytest.mark.parametrize("excluded", ["Krystal Cloud", "Transfer", "Pricing", "Register", "Our Creed", "Careers"])
async def test_html_sitemap_non_products_are_skipped(
    make_response: MakeResponse, crawl_page: CrawlPage, excluded: str
) -> None:
    results = await crawl_page(KrystalCrawler(), make_response(KrystalCrawler.SITEMAP_PAGE_URL, "krystal_sitemap.html"))

    assert excluded not in names(results)


async def test_footer_requests_the_missing_product_pages(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = KrystalCrawler()
    await crawl_page(crawler, make_response(KrystalCrawler.catalogue_url, "krystal_cloud_products.html"))

    results = await crawl_page(crawler, make_response(KrystalCrawler.SITEMAP_PAGE_URL, "krystal_sitemap.html"))

    assert requests(results) == [
        ("https://krystal.io/website-builder", "Website builder"),
        ("https://krystal.io/managed", "Managed solutions"),
    ]
    assert [result.meta[BaseCloudCrawler.PRODUCT_CATEGORIES] for result in results if isinstance(result, Request)] == [
        ["Services"],
        ["Services"],
    ]


async def test_footer_link_of_several_columns_is_requested_once(crawl_page: CrawlPage) -> None:
    column = '<div class="space-y-4"><p>{title}</p><ul><li><a href="/cdn">CDN</a></li></ul></div>'
    vps = '<div class="col-span-2"><h3>VPS Hosting</h3><p>Servers.</p><a href="/cloud-vps">VPS</a></div>'
    content = f"<main><section><h2>Servers</h2>{vps}</section></main><footer>"
    content += column.format(title="Services") + column.format(title="Cloud") + "</footer>"

    results = await crawl_page(KrystalCrawler(), page(KrystalCrawler.SITEMAP_PAGE_URL, content))

    assert [result.meta[BaseCloudCrawler.PRODUCT_CATEGORIES] for result in results if isinstance(result, Request)] == [
        ["Services", "Cloud"]
    ]


async def test_footer_is_only_read_on_the_html_sitemap(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    cards = make_response(KrystalCrawler.catalogue_url, "krystal_cloud_products.html").body.decode()
    footer = make_response(KrystalCrawler.SITEMAP_PAGE_URL, "krystal_sitemap.html").body.decode()

    results = await crawl_page(KrystalCrawler(), page(KrystalCrawler.catalogue_url, cards + footer))

    assert len(names(results)) == 13
    assert requests(results) == []


async def test_xml_sitemap_requests_the_pages_linked_from_nowhere_else(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = KrystalCrawler()
    crawler.seen_urls.add(crawler._url_key("https://krystal.io/intelligent-wordpress-protection"))

    results = await crawl_page(crawler, make_response(KrystalCrawler.SITEMAP_URL, "krystal_sitemap.xml"))

    assert requests(results) == [
        ("https://krystal.io/ai-website-builder", "AI Website Builder"),
        (VOIP_URL, "VoIP"),
    ]
    assert all(result.priority == 0 for result in results if isinstance(result, Request))


async def test_empty_xml_sitemap_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(CatalogueFormatError, match="lists no page"):
        await crawl_page(KrystalCrawler(), page(KrystalCrawler.SITEMAP_URL, "<urlset></urlset>"))

    assert any(record.levelno == logging.ERROR and "lists no page" in record.getMessage() for record in caplog.records)


async def test_product_page_is_named_after_the_listing_label(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    response = make_response(VOIP_URL, "krystal_product_voip.html")
    response.meta.update({KrystalCrawler.PRODUCT_PAGE: VOIP_URL, KrystalCrawler.PRODUCT_NAME: "VoIP"})

    results = await crawl_page(KrystalCrawler(), response)

    assert results == [
        {
            "name": "VoIP",
            "description": "Use one of the best business VoIP services out there with Dial 9, using this exclusive "
            "package for Krystal clients.",
            "pricing_policy": [],
            "url": VOIP_URL,
        }
    ]


async def test_product_page_is_filed_under_its_footer_columns(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    response = make_response(VOIP_URL, "krystal_product_voip.html")
    response.meta.update(
        {
            KrystalCrawler.PRODUCT_PAGE: VOIP_URL,
            KrystalCrawler.PRODUCT_NAME: "VoIP",
            BaseCloudCrawler.PRODUCT_CATEGORIES: ["Services"],
        }
    )

    results = await crawl_page(KrystalCrawler(), response)

    assert [(result["name"], result["catalogue_categories"]) for result in results if isinstance(result, dict)] == [
        ("VoIP", ["Services"])
    ]


async def test_skips_incomplete_sitemap_cards(crawl_page: CrawlPage) -> None:
    cards = (
        '<div class="col-span-2"><h3>No link</h3><p>Lost</p></div>'
        '<div class="col-span-2"><h3>No description</h3><a href="/email">Email</a></div>'
        '<div class="col-span-2"><h3>Email</h3><p>Business email</p><a href="/email/">Email</a></div>'
    )
    content = f"<main><section><h2>Servers</h2>{cards}</section><section><p>Untitled</p></section></main>"

    results = await crawl_page(KrystalCrawler(), page(KrystalCrawler.SITEMAP_PAGE_URL, content))

    assert names(results) == ["Email"]


async def test_skips_incomplete_cloud_cards(crawl_page: CrawlPage) -> None:
    cards = (
        '<li><a href="/cloud/x"><p>No title</p></a></li><li><a href="/cloud/kubernetes"><h3>K8s</h3><p>K</p></a></li>'
    )

    results = await crawl_page(
        KrystalCrawler(), page(KrystalCrawler.catalogue_url, f"<main><section><ul>{cards}</ul></section></main>")
    )

    assert results == [
        {"name": "K8s", "description": "K", "pricing_policy": [], "url": "https://krystal.io/cloud/kubernetes"}
    ]


@pytest.mark.parametrize(
    "response",
    [
        page(KrystalCrawler.catalogue_url, "<main><section><h2>Compute</h2></section></main>"),
        page(KrystalCrawler.SITEMAP_PAGE_URL, "<main><section><h2>About Krystal</h2></section></main>"),
    ],
    ids=["cloud products", "html sitemap"],
)
async def test_page_without_products_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, response: Response
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(EmptyCatalogueError):
        await crawl_page(KrystalCrawler(), response)

    assert any(
        record.levelno == logging.ERROR and "holds no product" in record.getMessage() for record in caplog.records
    )
