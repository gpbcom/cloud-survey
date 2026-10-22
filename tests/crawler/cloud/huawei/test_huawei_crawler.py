from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.huawei.crawler import HuaweiCloudCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
ONEACCESS_URL = "https://support.huaweicloud.com/intl/en-us/productdesc-oneaccess/oneaccess_01_0001.html"


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def docs(data: JsonValue) -> Response:
    return page(HuaweiCloudCrawler.DOCS_URL, json.dumps({"data": data, "status": True}))


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = HuaweiCloudCrawler()

    assert crawler.name == "huawei"
    assert HuaweiCloudCrawler.catalogue_url == "https://www.huaweicloud.com/intl/en-us/product/"
    assert HuaweiCloudCrawler.complement_urls == (
        "https://portal.huaweicloud.com/rest/cbc/portaldocdataservice/v1/books/items?appId=INTL-EN_US",
    )
    assert crawler.allowed_domains == {"www.huaweicloud.com", "portal.huaweicloud.com", "support.huaweicloud.com"}


async def test_extracts_the_desktop_product_cards(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(HuaweiCloudCrawler.catalogue_url, "huawei_products.html")

    results = await crawl_page(HuaweiCloudCrawler(), response)

    assert len(response.css("a.card")) > len(response.css(HuaweiCloudCrawler.PRODUCT_CARDS)) == 33
    assert names(results) == [
        "CodeArts Agent",
        "MaaS",
        "ModelArts",
        "Huawei Cloud Stack",
        "Huawei Cloud Flexus",
        "Elastic Cloud Server (ECS)",
        "RDS for MySQL",
        "Object Storage Service (OBS)",
        "PanguLargeModels",
        "Huawei HiLens (HiLens)",
        "Graph Engine Service (GES)",
        "Question Answering Bot (QABot)",
        "Image Recognition",
        "Content Moderation",
        "Optical Character Recognition (OCR)",
        "Short Sentence Recognition",
        "EIHealth",
        "Video Intelligent Analysis Service",
        "Message & SMS",
        "Workspace",
        "IoT Device Access (IoTDA)",
        "Elastic Volume Service (EVS)",
        "Cloud Backup and Recovery (CBR)",
        "Scalable File Service (SFS)",
        "Scalable File Service Turbo (SFS Turbo)",
        "Dedicated Distributed Storage Service (DSS)",
        "Business Recovery Service (BRS)",
        "Volume Backup Service (VBS)",
        "Cloud Server Backup Service (CSBS)",
        "Data Express Service (DES)",
    ]
    assert results[5] == {
        "name": "Elastic Cloud Server (ECS)",
        "description": "Get your own secure, scalable virtual servers in the cloud",
        "pricing_policy": [],
        "url": "https://www.huaweicloud.com/intl/en-us/product/ecs.html",
    }


async def test_cards_carry_their_categories(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        HuaweiCloudCrawler(), make_response(HuaweiCloudCrawler.catalogue_url, "huawei_products.html")
    )

    categories = {result["name"]: result.get("catalogue_categories") for result in results if isinstance(result, dict)}
    assert categories["MaaS"] == ["AI"]
    assert categories["Object Storage Service (OBS)"] == ["Storage"]
    assert categories["Message & SMS"] == ["Business Applications"]
    assert categories["IoT Device Access (IoTDA)"] == ["Business Applications", "Internet of Things"]
    assert categories["Elastic Cloud Server (ECS)"] is None


async def test_cards_listed_in_several_categories_get_all_of_them(crawl_page: CrawlPage) -> None:
    card = (
        '<a class="card" href="/intl/en-us/product/ecs.html"><div class="card-title">ECS</div>'
        '<div class="card-description">Servers</div></a>'
    )
    sections = "".join(
        f'<div class="first-content"><div class="first-title"><span>{title}</span></div>'
        f'<div class="second-content second-pc"><div class="second-flex">{card}</div></div></div>'
        for title in ("Featured", "Compute", "Containers &amp; Middleware")
    )

    results = await crawl_page(HuaweiCloudCrawler(), page(HuaweiCloudCrawler.catalogue_url, sections))

    assert [result.get("catalogue_categories") for result in results if isinstance(result, dict)] == [
        ["Compute", "Containers & Middleware"]
    ]


async def test_docs_add_the_missing_services(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = HuaweiCloudCrawler()
    await crawl_page(crawler, make_response(HuaweiCloudCrawler.catalogue_url, "huawei_products.html"))

    results = await crawl_page(crawler, make_response(HuaweiCloudCrawler.DOCS_URL, "huawei_docs.json"))

    assert names(results) == [
        "Face Recognition Service",
        "Conversational Bot Service",
        "Speech Interaction Service",
        "PanguBot",
        "CodeArts Repo",
        "Huawei Cloud Astro Canvas",
        "Koo Command Line Interface",
        "Identity and Access Management",
        "Tag Management Service",
    ]
    assert results[0] == {
        "name": "Face Recognition Service",
        "description": "Can be used for Identity verification, e-Attendance and customer attribute analysis",
        "pricing_policy": [],
        "url": "https://support.huaweicloud.com/intl/en-us/face/index.html",
        "catalogue_categories": ["AI"],
    }
    assert [(request.url, request.meta) for request in results if isinstance(request, Request)] == [
        (ONEACCESS_URL, {HuaweiCloudCrawler.PRODUCT_PAGE: ONEACCESS_URL, HuaweiCloudCrawler.PRODUCT_NAME: "OneAccess"})
    ]


@pytest.mark.parametrize(
    "excluded",
    ["AI Decisions", "SDK Developer Guide", "API Request Signing Guide", "SAP Cloud", "Billing Center", "Common FAQs"],
)
async def test_docs_non_services_are_skipped(make_response: MakeResponse, crawl_page: CrawlPage, excluded: str) -> None:
    results = await crawl_page(HuaweiCloudCrawler(), make_response(HuaweiCloudCrawler.DOCS_URL, "huawei_docs.json"))

    assert excluded not in names(results)


async def test_docs_page_of_a_service_without_description(crawl_page: CrawlPage) -> None:
    head = (
        '<meta name="description" content="OneAccess is an identity management service.">'
        '<meta property="og:title" content="What Is OneAccess_OneAccess-Huawei Cloud">'
    )
    meta: Dict[str, JsonValue] = {
        HuaweiCloudCrawler.PRODUCT_PAGE: ONEACCESS_URL,
        HuaweiCloudCrawler.PRODUCT_NAME: "OneAccess",
    }

    results = await crawl_page(HuaweiCloudCrawler(), page(ONEACCESS_URL, f"<html><head>{head}</head></html>", meta))

    assert results == [
        {
            "name": "OneAccess",
            "description": "OneAccess is an identity management service.",
            "pricing_policy": [],
            "url": ONEACCESS_URL,
        }
    ]


async def test_docs_pages_are_only_requested_for_new_services(crawl_page: CrawlPage) -> None:
    crawler = HuaweiCloudCrawler()
    crawler.seen_urls.add(crawler._url_key("https://support.huaweicloud.com/intl/en-us/km/index.html"))
    crawler._remember(["Huawei Cloud OneAccess"])
    entries: JsonValue = [
        {"code": "vpc", "title": "Virtual Private Cloud", "description": "Networks", "uri": "https://x.example/vpc"},
        {"code": "oneaccess", "title": "OneAccess", "description": None, "uri": ONEACCESS_URL},
        {
            "code": "km",
            "title": "Knowledge Management",
            "description": "",
            "uri": "https://support.huaweicloud.com/intl/en-us/km/index.html",
        },
        {"code": "untitled", "title": None, "description": None, "uri": "https://support.huaweicloud.com/x.html"},
        {"code": "nolink", "title": "No link", "description": None},
        {
            "code": "dws",
            "title": "Data Warehouse",
            "description": " ",
            "uri": "https://support.huaweicloud.com/dws.html",
        },
    ]

    results = await crawl_page(crawler, docs([{"name": "Compute", "products": entries}]))

    assert names(results) == ["Virtual Private Cloud"]
    assert [request.url for request in results if isinstance(request, Request)] == [
        "https://support.huaweicloud.com/dws.html"
    ]


async def test_docs_services_get_all_their_categories(crawl_page: CrawlPage) -> None:
    entry: JsonValue = {"code": "vpc", "title": "VPC", "description": "Networks", "uri": "https://x.example/vpc"}

    results = await crawl_page(
        HuaweiCloudCrawler(),
        docs([{"name": "Networking", "products": [entry]}, {"name": "Compute", "products": [entry]}]),
    )

    assert [result.get("catalogue_categories") for result in results if isinstance(result, dict)] == [
        ["Networking", "Compute"]
    ]


async def test_docs_skip_malformed_categories(crawl_page: CrawlPage) -> None:
    entry: JsonValue = {"code": "vpc", "title": "VPC", "description": "Networks", "uri": "https://x.example/vpc"}

    results = await crawl_page(
        HuaweiCloudCrawler(), docs(["category", {"name": "Network", "products": "none"}, {"products": [entry, 3]}])
    )

    assert names(results) == ["VPC"]


@pytest.mark.parametrize(
    ("body", "reason"),
    [("<html>Not found</html>", "is not JSON"), (json.dumps({"data": None}), "has no `data` list")],
    ids=["not json", "no data"],
)
async def test_malformed_docs_are_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, body: str, reason: str
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(CatalogueFormatError):
        await crawl_page(HuaweiCloudCrawler(), page(HuaweiCloudCrawler.DOCS_URL, body))

    assert any(record.levelno == logging.ERROR and reason in record.getMessage() for record in caplog.records)


async def test_skips_incomplete_cards(crawl_page: CrawlPage) -> None:
    cards = (
        '<a class="card" href="/intl/en-us/product/x.html"><div class="card-description">No title</div></a>'
        '<a class="card" href="/intl/en-us/product/y.html"><div class="card-title">No description</div></a>'
        '<a class="card" href="/intl/en-us/product/vpc.html"><div class="card-title">VPC</div>'
        '<div class="card-description">Networks</div></a>'
    )
    content = f'<div class="second-content second-pc">{cards}</div>'

    results = await crawl_page(HuaweiCloudCrawler(), page(HuaweiCloudCrawler.catalogue_url, content))

    assert results == [
        {
            "name": "VPC",
            "description": "Networks",
            "pricing_policy": [],
            "url": "https://www.huaweicloud.com/intl/en-us/product/vpc.html",
        }
    ]


@pytest.mark.parametrize(
    "response",
    [
        page(HuaweiCloudCrawler.catalogue_url, '<div class="second-content second-mb"><a class="card"></a></div>'),
        docs([{"name": "Others", "products": [{"title": "Common FAQs", "description": "FAQ", "uri": "https://a.b"}]}]),
    ],
    ids=["products page", "docs"],
)
async def test_page_without_products_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, response: Response
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(EmptyCatalogueError):
        await crawl_page(HuaweiCloudCrawler(), response)

    assert any(
        record.levelno == logging.ERROR and "holds no product" in record.getMessage() for record in caplog.records
    )
