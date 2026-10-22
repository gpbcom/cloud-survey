from __future__ import annotations

import logging
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.arsys.crawler import ArsysCrawler
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
K8S_URL = "https://www.arsys.net/cloud/kubernetes"


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None, status: int = 200) -> Response:
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


def menu_page(links: str) -> Response:
    return page(ArsysCrawler.catalogue_url, f'<div class="section"><ul class="main">{links}</ul></div>')


def product_page(response: Response, name: Optional[str] = None) -> Response:
    response.meta[ArsysCrawler.PRODUCT_PAGE] = response.url
    if name is not None:
        response.meta[ArsysCrawler.PRODUCT_NAME] = name
    return response


def requests_of(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def test_configuration() -> None:
    crawler = ArsysCrawler()

    assert crawler.name == "arsys"
    assert ArsysCrawler.catalogue_url == "https://www.arsys.net/"
    assert ArsysCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"www.arsys.net"}


async def test_menu_requests_the_product_pages(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(ArsysCrawler(), make_response(ArsysCrawler.catalogue_url, "arsys_home.html"))

    requests = requests_of(results)
    assert len(requests) == len(results) == 16
    assert [request.meta[ArsysCrawler.PRODUCT_NAME] for request in requests] == [
        "Buy Domain",
        "Domain Transfer",
        "Domain Reseller",
        "Domain Protection",
        "SSL Certificate",
        "Corporate Domains",
        "Special Domains",
        "Geographic Domains",
        "Business Email",
        "Microsoft Office 365",
        "Email Migration",
        "Backup email",
        "Professional Antivirus",
        "IT Solutions",
        "Professional Services",
        "Passive Security",
    ]
    assert (requests[0].url, requests[0].priority, requests[0].meta) == (
        "https://www.arsys.net/domains",
        0,
        {
            ArsysCrawler.PRODUCT_PAGE: "https://www.arsys.net/domains",
            ArsysCrawler.PRODUCT_NAME: "Buy Domain",
            BaseCloudCrawler.PRODUCT_CATEGORIES: ["Domains"],
        },
    )


async def test_menu_requests_carry_their_menu_sections(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(ArsysCrawler(), make_response(ArsysCrawler.catalogue_url, "arsys_home.html"))

    categories = {
        request.meta[ArsysCrawler.PRODUCT_NAME]: request.meta[BaseCloudCrawler.PRODUCT_CATEGORIES]
        for request in requests_of(results)
    }
    assert categories["SSL Certificate"] == ["Domains"]
    assert categories["Professional Antivirus"] == ["Email"]
    assert categories["Passive Security"] == ["Managed"]


async def test_menu_link_of_several_sections_gathers_them(crawl_page: CrawlPage) -> None:
    ssl = '<ul class="main"><li><a href="/security/ssl">SSL Certificate</a></li></ul>'
    content = f'<div><ul><li><a href="/domains">Domains</a><div class="section">{ssl}</div></li>'
    content += f'<li><a href="/security"><i></i> Security</a><div class="section">{ssl}</div></li></ul></div>'

    results = await crawl_page(ArsysCrawler(), page(ArsysCrawler.catalogue_url, content))

    assert [request.meta.get(BaseCloudCrawler.PRODUCT_CATEGORIES) for request in requests_of(results)] == [
        ["Domains", "Security"]
    ]


@pytest.mark.parametrize(
    "excluded",
    [
        "/domains/names-generator",
        "/domains/prices",
        "/domains/whois",
        "/partners",
        "/managed-services/partners",
        "/managed-services/digital-transformation",
        "/managed-services/support",
        "/about",
        "/about/press",
        "/contact",
    ],
)
async def test_menu_non_products_are_skipped(make_response: MakeResponse, crawl_page: CrawlPage, excluded: str) -> None:
    results = await crawl_page(ArsysCrawler(), make_response(ArsysCrawler.catalogue_url, "arsys_home.html"))

    assert f"https://www.arsys.net{excluded}" not in [request.url for request in requests_of(results)]


async def test_menu_links_with_a_query_or_already_listed_are_skipped(crawl_page: CrawlPage) -> None:
    links = '<a href="/cloud">Cloud Server</a><a href="/cloud?go=demo">Cloud Demo</a><a href="/cloud/">Cloud</a>'
    links += '<a href="/tools/seo">SEO Analysis</a>'

    results = await crawl_page(ArsysCrawler(), menu_page(links))

    assert [(request.url, request.meta[ArsysCrawler.PRODUCT_NAME]) for request in requests_of(results)] == [
        ("https://www.arsys.net/cloud", "Cloud Server")
    ]


async def test_product_already_streamed_is_not_requested(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = ArsysCrawler()
    office = make_response("https://www.arsys.net/office", "arsys_product_page.html")
    await crawl_page(crawler, product_page(office, "Microsoft 365"))

    results = await crawl_page(crawler, make_response(ArsysCrawler.catalogue_url, "arsys_home.html"))

    assert "https://www.arsys.net/office" not in [request.url for request in requests_of(results)]
    assert len(results) == 15


async def test_page_without_menu_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(CatalogueFormatError, match="main menu is missing"):
        await crawl_page(ArsysCrawler(), page(ArsysCrawler.catalogue_url, "<html><body><nav></nav></body></html>"))

    assert "has no main menu" in caplog.text


async def test_product_page(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = product_page(make_response(K8S_URL, "arsys_product_page.html"), "Kubernetes")

    results = await crawl_page(ArsysCrawler(), response)

    assert results == [
        {
            "name": "Kubernetes",
            "description": "Deploy your project in Kubernetes containers in Data Centre Designer at no cost to you and "
            "with total security. K8s and K3s. Sign up now!",
            "pricing_policy": [],
            "url": K8S_URL,
        }
    ]


async def test_product_page_is_filed_under_its_menu_sections(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    response = product_page(make_response(K8S_URL, "arsys_product_page.html"), "Kubernetes")
    response.meta[BaseCloudCrawler.PRODUCT_CATEGORIES] = ["Cloud"]

    results = await crawl_page(ArsysCrawler(), response)

    assert [(result["name"], result["catalogue_categories"]) for result in results if isinstance(result, dict)] == [
        ("Kubernetes", ["Cloud"])
    ]


async def test_missing_product_page_is_skipped(crawl_page: CrawlPage) -> None:
    head = '<meta property="og:title" content="Page not found"><meta name="description" content="We didn\'t find it">'
    response = page("https://www.arsys.net/ecommerce", f"<html><head>{head}</head></html>", status=404)

    assert await crawl_page(ArsysCrawler(), product_page(response, "Online Store")) == []
