from __future__ import annotations

import logging
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.seeweb.crawler import SeewebCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
CLOUD_DB_URL = "https://www.seeweb.it/en/products/cloud-db"


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def menu_page(links: str) -> Response:
    return page(SeewebCrawler.catalogue_url, f'<div class="product-column"><p>Compute</p><ul>{links}</ul></div>')


def requests_of(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def test_configuration() -> None:
    crawler = SeewebCrawler()

    assert crawler.name == "seeweb"
    assert SeewebCrawler.catalogue_url == "https://www.seeweb.it/en"
    assert SeewebCrawler.complement_urls == ()
    assert SeewebCrawler.name_prefixes == ("Seeweb ",)
    assert crawler.allowed_domains == {"www.seeweb.it"}


async def test_menu_requests_the_product_pages(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(SeewebCrawler(), make_response(SeewebCrawler.catalogue_url, "seeweb_home.html"))

    requests = requests_of(results)
    assert len(results) == len(requests) == 10
    assert [request.meta[SeewebCrawler.PRODUCT_NAME] for request in requests] == [
        "Cloud Mail",
        "Cloud DB",
        "Cloud Streaming",
        "Proxmox Infrastructure",
        "Plesk & cPanel",
        "Technical Support",
        "SSL certificates",
        "Server Antivirus",
        "Cloud Backup",
        "Cloud Data Protection",
    ]
    assert (requests[1].url, requests[1].meta) == (
        CLOUD_DB_URL,
        {SeewebCrawler.PRODUCT_PAGE: CLOUD_DB_URL, SeewebCrawler.PRODUCT_NAME: "Cloud DB"},
    )


async def test_product_page_is_named_after_the_menu(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(CLOUD_DB_URL, "seeweb_product_page.html")
    response.meta.update({SeewebCrawler.PRODUCT_PAGE: CLOUD_DB_URL, SeewebCrawler.PRODUCT_NAME: "Cloud DB"})

    results = await crawl_page(SeewebCrawler(), response)

    assert results == [
        {
            "name": "Cloud DB",
            "description": "Manage your databases in a scalable, secure, and automated way thanks to Seeweb\u2019s new "
            "DBaaS platform. Create, monitor, and optimize your clusters with multi-engine support and "
            "high-availability architectures from a single intuitive dashboard, without worrying about the "
            "infrastructure.",
            "pricing_policy": [],
            "url": CLOUD_DB_URL,
        }
    ]


@pytest.mark.parametrize(
    "link",
    [
        '<li><a href="/en/solutions/ai">AI solutions</a></li>',
        '<li><a href="/en/products/cloud-server/pricing">Cloud Server pricing</a></li>',
        '<li><a href="/en/about">About us</a></li>',
        '<li><a href="/en/products/serverless-gpu"> </a></li>',
        '<li><a href="/en/products/cloud-server/">Cloud Server again</a></li>',
    ],
    ids=["solution", "sub-page", "not a product", "unnamed", "duplicate"],
)
async def test_non_product_links_are_skipped(crawl_page: CrawlPage, link: str) -> None:
    links = '<li><a href="/en/products/cloud-server">Cloud Server</a></li>' + link

    requests = requests_of(await crawl_page(SeewebCrawler(), menu_page(links)))

    assert [request.url for request in requests] == ["https://www.seeweb.it/en/products/cloud-server"]


async def test_product_pages_already_streamed_are_not_requested(crawl_page: CrawlPage) -> None:
    crawler = SeewebCrawler()
    crawler.seen_urls.add("seeweb.it/en/products/cloud-server")
    links = '<li><a href="/en/products/cloud-server">Cloud Server</a></li>'
    links += '<li><a href="/en/products/cloud-db">Cloud DB</a></li>'

    requests = requests_of(await crawl_page(crawler, menu_page(links)))

    assert [request.url for request in requests] == [CLOUD_DB_URL]


async def test_menu_without_product_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(EmptyCatalogueError):
        await crawl_page(SeewebCrawler(), menu_page('<li><a href="/en/solutions/ai">AI solutions</a></li>'))

    assert any(
        record.levelno == logging.ERROR and "links to no product page" in record.getMessage()
        for record in caplog.records
    )


SENTENCES = " ".join(f"Sentence number {index} of the introduction." for index in range(30))
WORDS = " ".join(["word"] * 250)


@pytest.mark.parametrize(
    ("head", "body", "expected"),
    [
        (
            '<meta name="description" content="Descrizione in italiano.">',
            '<div class="cont-title"><p> </p><p>English intro.</p><p>Second paragraph.</p></div>',
            "English intro.",
        ),
        (
            "",
            '<div class="cont-title"><h1>K8s</h1><p>Persistent <strong>storage</strong>, <b>dynamic</b>.</p></div>',
            "Persistent storage, dynamic.",
        ),
        ('<meta name="description" content="Meta text.">', '<div class="cont-title"><p></p></div>', "Meta text."),
        (
            '<meta name="description" content="Più piani di supporto.">',
            '<div class="title"><h1>System Assurance</h1><p>A team of <strong>technicians</strong>.</p></div>',
            "A team of technicians.",
        ),
        ("", f'<div class="cont-title"><p>{"a" * 999}.</p></div>', f"{'a' * 999}."),
        ("", f'<div class="cont-title"><p>{SENTENCES}</p></div>', SENTENCES[: SENTENCES.rindex(".", 0, 1000) + 1]),
        ("", f'<div class="cont-title"><p>{WORDS}</p></div>', f"{' '.join(['word'] * 199)}\u2026"),
    ],
    ids=[
        "introduction first",
        "inline elements",
        "meta description",
        "title layout",
        "whole",
        "cut at a sentence",
        "cut at a word",
    ],
)
async def test_product_page_descriptions(crawl_page: CrawlPage, head: str, body: str, expected: str) -> None:
    url = "https://www.seeweb.it/en/products/kubernetes-storage"
    meta: Dict[str, JsonValue] = {SeewebCrawler.PRODUCT_PAGE: url, SeewebCrawler.PRODUCT_NAME: "Kubernetes Storage"}

    results = await crawl_page(SeewebCrawler(), page(url, f"<html><head>{head}</head><body>{body}</body></html>", meta))

    assert results == [{"name": "Kubernetes Storage", "description": expected, "pricing_policy": [], "url": url}]


async def test_product_page_without_description_is_skipped(crawl_page: CrawlPage) -> None:
    meta: Dict[str, JsonValue] = {SeewebCrawler.PRODUCT_PAGE: CLOUD_DB_URL, SeewebCrawler.PRODUCT_NAME: "Cloud DB"}

    assert await crawl_page(SeewebCrawler(), page(CLOUD_DB_URL, "<h1>Cloud DB</h1>", meta)) == []
