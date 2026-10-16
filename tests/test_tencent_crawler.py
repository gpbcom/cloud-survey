from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.tencent.crawler import TencentCloudCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
PRODUCTS_URL = "https://www.tencentcloud.com/product"
DOCS_URL = "https://www.tencentcloud.com/document/product"
TPNS_URL = "https://www.tencentcloud.com/products/tpns"
ALB_URL = "https://www.tencentcloud.com/products/alb"
ALB_DOC_URL = "https://www.tencentcloud.com/document/product/1311"
ALB_OVERVIEW_URL = "https://www.tencentcloud.com/document/product/1311/83642"


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


def docs_page(groups: JsonValue) -> Response:
    script = json.dumps({"props": {"pageProps": {"catalogueList": groups}}})
    return page(DOCS_URL, f'<html><body><script id="__NEXT_DATA__" type="application/json">{script}</script>')


def card(href: str, title: Optional[str], description: Optional[str], css: str = "") -> str:
    heading = f'<h3 class="v3-product-menu-card-cell-tit">{title}</h3>' if title is not None else ""
    text = f'<div class="v3-product-menu-card-cell-desc">{description}</div>' if description is not None else ""
    return f'<a class="v3-product-menu-card-cell-link {css}" href="{href}">{heading}{text}</a>'


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def test_configuration() -> None:
    crawler = TencentCloudCrawler()

    assert crawler.name == "tencent"
    assert TencentCloudCrawler.catalogue_url == PRODUCTS_URL
    assert TencentCloudCrawler.complement_urls == (DOCS_URL,)
    assert crawler.allowed_domains == {"www.tencentcloud.com"}
    assert TencentCloudCrawler.name_prefixes == ("Tencent Cloud ", "TencentCloud ", "Tencent ", "T-Sec ")


async def test_starts_with_the_products_page_then_the_documentation() -> None:
    started = [request async for request in TencentCloudCrawler().start_requests()]

    assert [(request.url, request.priority) for request in started] == [
        (PRODUCTS_URL, TencentCloudCrawler.PRIMARY_PRIORITY),
        (DOCS_URL, 0),
    ]
    assert started[0]._session_kwargs["wait_selector"] == "a.v3-product-menu-card-cell-link"
    assert started[1]._session_kwargs["wait_selector"] == "script#__NEXT_DATA__"


async def test_extracts_the_product_cards(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(TencentCloudCrawler(), make_response(PRODUCTS_URL, "tencent_product_en.html"))

    assert names(results) == [
        "Tencent WorkBuddy Enterprise",
        "Tencent CodeBuddy",
        "Tencent WorkBuddy",
        "Tencent WorkBuddy Managed Agents",
        "Face Recognition",
        "Tencent Machine Translation",
        "Cloud Virtual Machine",
        "Tencent Cloud Lighthouse",
        "Cloud Dedicated Zone",
        "Cloud Native Database TDSQL-C",
        "Cloud Application Rendering",
    ]
    assert results[1] == {
        "name": "Tencent CodeBuddy",
        "description": "Tencent CodeBuddy depicts the entire equipment development process",
        "pricing_policy": [],
        "url": "https://www.tencentcloud.com/products/acc",
    }


async def test_double_slashes_of_the_card_links_are_normalized(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(TencentCloudCrawler(), make_response(PRODUCTS_URL, "tencent_product_en.html"))

    assert [
        result["url"] for result in results if isinstance(result, dict) and result["name"] == "Cloud Dedicated Zone"
    ] == ["https://www.tencentcloud.com/products/cdz"]


@pytest.mark.parametrize("excluded", ["Tencent Cloud DataBuddy", "Tencent Healthcare Data Services"])
async def test_release_links_are_left_out(make_response: MakeResponse, crawl_page: CrawlPage, excluded: str) -> None:
    results = await crawl_page(TencentCloudCrawler(), make_response(PRODUCTS_URL, "tencent_product_en.html"))

    assert excluded not in names(results)


async def test_card_shapes(crawl_page: CrawlPage) -> None:
    cards = [
        card("/products/news", "Release", "A release note", css="v3-link-item"),
        card("/products/untitled", None, "No title"),
        card("/products/nodesc", "No description", None),
        card("", "Gateway", "NAT gateway"),
        card("#top", "Anchor", "An anchor link"),
    ]

    results = await crawl_page(TencentCloudCrawler(), page(PRODUCTS_URL, f"<html><body>{''.join(cards)}</body></html>"))

    assert results == [
        {"name": "Gateway", "description": "NAT gateway", "pricing_policy": [], "url": None},
        {"name": "Anchor", "description": "An anchor link", "pricing_policy": [], "url": None},
    ]


async def test_products_page_without_card_is_an_error(
    make_response: MakeResponse, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(TencentCloudCrawler(), make_response(PRODUCTS_URL, "tencent_edgeone_challenge.html"))

    assert caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].getMessage() == f"The tencent catalogue page {PRODUCTS_URL} holds no product."


async def test_documentation_requests_the_product_pages_not_streamed_yet(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = TencentCloudCrawler()
    await crawl_page(crawler, make_response(PRODUCTS_URL, "tencent_product_en.html"))

    results = await crawl_page(crawler, make_response(DOCS_URL, "tencent_document_product_en.html"))

    assert names(results) == []
    assert [(request.url, request.meta[TencentCloudCrawler.PRODUCT_NAME]) for request in requests(results)] == [
        ("https://www.tencentcloud.com/products/gpu", "Cloud GPU Service"),
        ("https://www.tencentcloud.com/products/batch", "Batch Compute"),
        ("https://www.tencentcloud.com/products/cdb", "TencentDB for MySQL"),
        ("https://www.tencentcloud.com/products/tdsql", "TencentDB for MariaDB"),
        ("https://www.tencentcloud.com/products/vod", "Video on Demand"),
        ("https://www.tencentcloud.com/products/quota", "Quota Center"),
        ("https://www.tencentcloud.com/products/api", "TencentCloud API"),
    ]
    assert all(request._session_kwargs["wait_selector"] == "head > title" for request in requests(results))
    assert [request.meta[TencentCloudCrawler.DOC_ID] for request in requests(results)][:2] == ["560", "599"]


@pytest.mark.parametrize(
    "excluded",
    ["LVB Recording", "SDK", "Marketplace", "API", "Message Center", "Software Product Lifecycle Announcements"],
)
async def test_documentation_non_products_are_left_out(
    make_response: MakeResponse, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, excluded: str
) -> None:
    caplog.set_level(logging.DEBUG, logger="scrapling.spiders.tencent")

    results = await crawl_page(TencentCloudCrawler(), make_response(DOCS_URL, "tencent_document_product_en.html"))

    assert excluded not in [request.meta[TencentCloudCrawler.PRODUCT_NAME] for request in requests(results)]


async def test_documentation_entry_of_a_streamed_page_is_not_requested(crawl_page: CrawlPage) -> None:
    crawler = TencentCloudCrawler()
    await crawl_page(crawler, page(PRODUCTS_URL, card("/products/cvm", "CVM", "Virtual machines")))
    leaves: JsonValue = [{"title": "Compute", "children": [{"title": "Cloud Virtual Machine", "slug": "cvm"}]}]

    assert await crawl_page(crawler, docs_page(leaves)) == []


async def test_documentation_tree_shapes(crawl_page: CrawlPage) -> None:
    groups: JsonValue = [
        "not a group",
        {"title": "Storage", "children": None},
        {
            "title": "Compute",
            "children": [
                "not an entry",
                {"title": "Batch", "children": [{"title": "Batch Compute", "slug": "Batch", "children": None}]},
                {"title": "Support plan", "slug": "support plan"},
            ],
        },
    ]

    results = await crawl_page(TencentCloudCrawler(), docs_page(groups))

    assert [request.url for request in requests(results)] == ["https://www.tencentcloud.com/products/batch"]


@pytest.mark.parametrize("groups", [{}, None], ids=["object", "missing"])
async def test_documentation_without_catalogue_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, groups: JsonValue
) -> None:
    with pytest.raises(CatalogueFormatError, match="`catalogueList` is not a list"):
        await crawl_page(TencentCloudCrawler(), docs_page(groups))

    assert caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].getMessage() == f"The tencent documentation page {DOCS_URL} has no `catalogueList` list."


async def test_documentation_challenge_page_is_an_error(
    make_response: MakeResponse, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(CatalogueFormatError, match="`__NEXT_DATA__` script is missing"):
        await crawl_page(TencentCloudCrawler(), make_response(DOCS_URL, "tencent_edgeone_challenge.html"))

    assert caplog.records[-1].levelno == logging.ERROR


async def test_documentation_without_product_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    groups: JsonValue = [{"title": "More", "children": [{"title": "Billing Center", "slug": "finance"}]}]

    with pytest.raises(CatalogueFormatError, match="the documentation lists no product"):
        await crawl_page(TencentCloudCrawler(), docs_page(groups))

    assert caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].getMessage() == f"The tencent documentation page {DOCS_URL} lists no product."


async def test_product_page_named_by_the_documentation(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(TPNS_URL, "tencent_product_tpns.html")
    response.meta.update({TencentCloudCrawler.PRODUCT_PAGE: TPNS_URL, TencentCloudCrawler.PRODUCT_NAME: "TPNS"})

    results = await crawl_page(TencentCloudCrawler(), response)

    assert names(results) == ["TPNS"]
    assert isinstance(results[0], dict)
    assert str(results[0]["description"]).startswith(
        "Tencent Push Notification Service (TPNS) provides quick and reliable app push notifications."
    )
    assert results[0]["url"] == TPNS_URL


async def test_product_page_named_by_its_title(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    url = "https://www.tencentcloud.com/products/cvm"
    response = make_response(url, "tencent_product_cvm.html")
    response.meta[TencentCloudCrawler.PRODUCT_PAGE] = url

    results = await crawl_page(TencentCloudCrawler(), response)

    assert names(results) == ["Cloud Virtual Machine"]
    assert isinstance(results[0], dict)
    assert results[0]["url"] == url


@pytest.mark.parametrize(
    "response",
    [
        page(
            TPNS_URL, "<html><head><title>404</title></head></html>", {TencentCloudCrawler.PRODUCT_PAGE: TPNS_URL}, 404
        ),
        page(
            TPNS_URL,
            '<html><head><meta name="description" content="A product."></head></html>',
            {TencentCloudCrawler.PRODUCT_PAGE: TPNS_URL},
        ),
        page(
            "https://www.tencentcloud.com/",
            "<html><head><title>Tencent Cloud</title></head></html>",
            {TencentCloudCrawler.PRODUCT_PAGE: TPNS_URL},
        ),
    ],
    ids=["missing", "untitled", "redirected"],
)
async def test_unknown_product_pages_are_skipped(crawl_page: CrawlPage, response: Response) -> None:
    assert await crawl_page(TencentCloudCrawler(), response) == []


async def test_missing_product_page_reads_the_documentation(crawl_page: CrawlPage) -> None:
    meta: Dict[str, JsonValue] = {
        TencentCloudCrawler.PRODUCT_PAGE: ALB_URL,
        TencentCloudCrawler.PRODUCT_NAME: "Application Load Balancer",
        TencentCloudCrawler.DOC_ID: "1311",
    }

    results = await crawl_page(
        TencentCloudCrawler(), page(ALB_URL, "<html><head><title>404</title></head></html>", meta, 404)
    )

    assert [(request.url, request.meta) for request in requests(results)] == [
        (
            ALB_DOC_URL,
            {
                TencentCloudCrawler.DOC_CATALOGUE: ALB_DOC_URL,
                TencentCloudCrawler.PRODUCT_NAME: "Application Load Balancer",
            },
        )
    ]
    assert requests(results)[0]._session_kwargs["wait_selector"] == "script#__NEXT_DATA__"


async def test_documentation_requests_the_overview_article(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(ALB_DOC_URL, "tencent_document_alb.html")
    response.meta.update({TencentCloudCrawler.DOC_CATALOGUE: ALB_DOC_URL, TencentCloudCrawler.PRODUCT_NAME: "ALB"})

    results = await crawl_page(TencentCloudCrawler(), response)

    assert [(request.url, request.meta) for request in requests(results)] == [
        (ALB_OVERVIEW_URL, {TencentCloudCrawler.DOC_ARTICLE: ALB_DOC_URL, TencentCloudCrawler.PRODUCT_NAME: "ALB"})
    ]


def doc_page(url: str, props: JsonValue, meta: Dict[str, JsonValue]) -> Response:
    script = json.dumps({"props": {"pageProps": props}})
    return page(url, f'<html><body><script id="__NEXT_DATA__" type="application/json">{script}</script>', meta)


@pytest.mark.parametrize(
    ("sections", "link"),
    [
        (
            [
                {
                    "title": "Product Introduction",
                    "link": "/document/product/1311/1",
                    "children": [{"title": "Strengths"}],
                }
            ],
            "/document/product/1311/1",
        ),
        ([{"title": "What Is ALB?", "link": "/document/product/1311/2", "children": None}], "/document/product/1311/2"),
        ([{"title": "Overview", "children": [{"title": "Overview"}]}], None),
        (["not a section", {"title": "Purchase Guide", "link": "/document/product/1311/3"}], None),
        ({}, None),
    ],
    ids=["section", "what-is", "no-link", "no-overview", "no-list"],
)
async def test_overview_article_links(crawl_page: CrawlPage, sections: JsonValue, link: Optional[str]) -> None:
    meta: Dict[str, JsonValue] = {
        TencentCloudCrawler.DOC_CATALOGUE: ALB_DOC_URL,
        TencentCloudCrawler.PRODUCT_NAME: "ALB",
    }

    results = await crawl_page(TencentCloudCrawler(), doc_page(ALB_DOC_URL, {"data": {"list": sections}}, meta))

    assert [request.url for request in requests(results)] == ([f"https://www.tencentcloud.com{link}"] if link else [])


async def test_overview_article(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(ALB_OVERVIEW_URL, "tencent_document_alb_overview.html")
    response.meta.update(
        {TencentCloudCrawler.DOC_ARTICLE: ALB_DOC_URL, TencentCloudCrawler.PRODUCT_NAME: "Application Load Balancer"}
    )

    results = await crawl_page(TencentCloudCrawler(), response)

    assert names(results) == ["Application Load Balancer"]
    assert isinstance(results[0], dict)
    assert str(results[0]["description"]).startswith("Application Load Balancer (ALB) is a layer-7 (application layer)")
    assert results[0]["url"] == ALB_DOC_URL


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ({"description": "ALB balances layer-7 traffic.", "slate": "not JSON"}, ["ALB"]),
        (
            {
                "slate": json.dumps(
                    [
                        {"type": "h2", "children": [{"text": "What Is ALB?"}]},
                        {"type": "p", "children": [{"text": " "}]},
                        {"type": "p", "children": ["x", {"text": "ALB balances traffic."}]},
                    ]
                )
            },
            ["ALB"],
        ),
        ({"slate": "not JSON"}, []),
        ({"slate": json.dumps({"type": "p"})}, []),
        ({}, []),
    ],
    ids=["description", "paragraph", "invalid", "object", "empty"],
)
async def test_overview_article_descriptions(crawl_page: CrawlPage, detail: JsonValue, expected: List[str]) -> None:
    meta: Dict[str, JsonValue] = {TencentCloudCrawler.DOC_ARTICLE: ALB_DOC_URL, TencentCloudCrawler.PRODUCT_NAME: "ALB"}

    results = await crawl_page(TencentCloudCrawler(), doc_page(ALB_OVERVIEW_URL, {"detailContent": detail}, meta))

    assert names(results) == expected


async def test_documentation_product_already_streamed(crawl_page: CrawlPage) -> None:
    crawler = TencentCloudCrawler()
    meta: Dict[str, JsonValue] = {TencentCloudCrawler.DOC_ARTICLE: ALB_DOC_URL, TencentCloudCrawler.PRODUCT_NAME: "ALB"}
    response = doc_page(ALB_OVERVIEW_URL, {"detailContent": {"description": "ALB balances traffic."}}, meta)

    first, second = await crawl_page(crawler, response), await crawl_page(crawler, response)

    assert (names(first), second) == (["ALB"], [])


async def test_listed_names_remember_their_documentation_names(crawl_page: CrawlPage) -> None:
    crawler = TencentCloudCrawler()
    await crawl_page(crawler, page(PRODUCTS_URL, card("/products/tdsqlc", "Cloud Native Database TDSQL-C", "MySQL")))
    leaves: JsonValue = [{"title": "Database", "children": [{"title": "TDSQL-C for MySQL", "slug": "cynosdb"}]}]

    assert await crawl_page(crawler, docs_page(leaves)) == []
