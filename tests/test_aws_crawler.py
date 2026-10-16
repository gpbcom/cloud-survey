from __future__ import annotations

import json
from typing import Awaitable, Callable, Dict, List, Optional, Union
from unittest.mock import AsyncMock

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.aws.crawler import AWSCrawler
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
API = "https://aws.amazon.com/api/dirs/items/search"
QUERY = (
    "item.directoryId=products-cards-interactive-aws-products-ams&item.locale=en_US"
    "&sort_by=item.additionalFields.title&sort_order=asc&size=500"
)


def json_page(data: JsonValue, page: int = 0) -> Response:
    return Response(
        url=f"{API}?{QUERY}&page={page}",
        content=json.dumps(data),
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
    )


def item(title: JsonValue, body: JsonValue, link: JsonValue = None) -> JsonValue:
    return {"item": {"additionalFields": {"title": title, "body": body, "ctaLink": link}}}


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = AWSCrawler()

    assert crawler.name == "aws"
    assert AWSCrawler.catalogue_url == f"{API}?{QUERY}&page=0"
    assert AWSCrawler.complement_urls == ("https://docs.aws.amazon.com/",)
    assert crawler.allowed_domains == {"aws.amazon.com", "docs.aws.amazon.com"}


async def test_starts_with_the_directory_then_the_documentation() -> None:
    requests = [request async for request in AWSCrawler().start_requests()]

    assert [(request.url, request.priority) for request in requests] == [
        (AWSCrawler.catalogue_url, AWSCrawler.PRIMARY_PRIORITY),
        ("https://docs.aws.amazon.com/", 0),
    ]


async def test_extracts_the_directory_products(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(AWSCrawler(), make_response(AWSCrawler.catalogue_url, "aws_products.json"))

    assert results[0] == {
        "name": "AWS Amplify",
        "description": "Build, deploy, host, and manage scalable web and mobile apps",
        "pricing_policy": [],
        "url": "https://aws.amazon.com/amplify/?did=ap_card&trk=ap_card",
        "added_at": "2017-11-21T08:00:00Z",
        "updated_at": "2026-07-07T19:52:54Z",
    }
    assert names(results) == ["AWS Amplify", "AWS Amplify Studio", "AWS App Mesh", "AWS Data Transfer Terminal"]


async def test_directory_products_are_dated(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(AWSCrawler(), make_response(AWSCrawler.catalogue_url, "aws_products.json"))

    assert [
        (result["name"], result.get("added_at"), result.get("updated_at"))
        for result in results
        if isinstance(result, dict)
    ] == [
        ("AWS Amplify", "2017-11-21T08:00:00Z", "2026-07-07T19:52:54Z"),
        ("AWS Amplify Studio", None, "2026-01-23T03:54:32Z"),
        ("AWS App Mesh", "2019-03-27T07:00:00Z", "2026-07-07T19:50:07Z"),
        ("AWS Data Transfer Terminal", None, "2025-06-17T15:19:03Z"),
    ]


async def test_unreadable_directory_dates_are_dropped(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    entry: JsonValue = {
        "item": {
            "dateCreated": "2025-05-23T11:15:32+0000",
            "dateUpdated": "yesterday",
            "additionalFields": {"title": "Amazon EC2", "body": "Virtual servers", "publishedDate": "2006-08-25"},
        }
    }

    results = await crawl_page(AWSCrawler(), json_page({"items": [entry]}))

    assert results == [
        {
            "name": "Amazon EC2",
            "description": "Virtual servers",
            "pricing_policy": [],
            "url": None,
            "added_at": "2006-08-25T00:00:00Z",
        }
    ]
    assert any("unreadable date 'yesterday'" in record.getMessage() for record in caplog.records)


async def test_documentation_completes_the_directory(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = AWSCrawler()
    await crawl_page(crawler, make_response(AWSCrawler.catalogue_url, "aws_products.json"))

    results = await crawl_page(crawler, make_response(AWSCrawler.DOCS_URL, "aws_docs.html"))

    assert results == [
        {
            "name": "EC2 Image Builder",
            "description": 'Automate lifecycle management of "golden" server images',
            "pricing_policy": [],
            "url": "https://docs.aws.amazon.com/imagebuilder/?icmpid=docs_homepage_compute",
        },
        {
            "name": "AWS CloudShell",
            "description": "Command line access to AWS resources and tools directly from a browser",
            "pricing_policy": [],
            "url": "https://docs.aws.amazon.com/cloudshell/?icmpid=docs_homepage_devtools",
        },
    ]


async def test_documentation_skips_guides_sdks_and_featured_sections(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(AWSCrawler(), make_response(AWSCrawler.DOCS_URL, "aws_docs.html"))

    assert names(results) == ["AWS Amplify", "EC2 Image Builder", "AWS CloudShell"]


async def test_documentation_matches_the_product_page_of_its_slug(crawl_page: CrawlPage) -> None:
    crawler = AWSCrawler()
    await crawl_page(crawler, json_page({"items": [item("Amazon EC2", "Virtual servers", "/ec2/")]}))
    docs = Response(
        url=AWSCrawler.DOCS_URL,
        content=(
            '<li class="awsdocs-card-list-item"><a class="awsdocs-link" href="/ec2/?icmpid=docs_homepage_compute">'
            'Amazon Elastic Compute Cloud</a><span class="awsdocs-card-list-abstract">Virtual servers</span></li>'
            '<li class="awsdocs-card-list-item"><a class="awsdocs-link" href="/batch/?icmpid=docs_homepage_compute">'
            'AWS Batch</a><span class="awsdocs-card-list-abstract">Batch jobs</span></li>'
        ),
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
    )

    assert names(await crawl_page(crawler, docs)) == ["AWS Batch"]


@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("https://docs.aws.amazon.com/ec2/?icmpid=docs_homepage_compute", "aws.amazon.com/ec2"),
        ("https://aws.amazon.com/ec2/?trk=card", "aws.amazon.com/ec2"),
        ("https://aws.amazon.com/q/developer/", "aws.amazon.com/q/developer"),
        ("https://docs.aws.amazon.com/", "docs.aws.amazon.com"),
    ],
)
def test_url_keys(url: str, key: str) -> None:
    assert AWSCrawler()._url_key(url) == key


async def test_requests_the_next_page(crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        AWSCrawler(), json_page({"items": [item("Amazon EC2", "Virtual servers")], "metadata": {"totalHits": 1200}}, 1)
    )

    request = results[-1]
    assert isinstance(request, Request)
    assert request.url == f"{API}?{QUERY}&page=2"
    assert request.priority == AWSCrawler.PRIMARY_PRIORITY
    assert results[:-1] == [{"name": "Amazon EC2", "description": "Virtual servers", "pricing_policy": [], "url": None}]


@pytest.mark.parametrize(("total", "page"), [(500, 0), (1000, 1), ("1000", 0), (None, 0)])
async def test_stops_on_the_last_page(crawl_page: CrawlPage, total: JsonValue, page: int) -> None:
    results = await crawl_page(
        AWSCrawler(),
        json_page({"items": [item("Amazon EC2", "Virtual servers")], "metadata": {"totalHits": total}}, page),
    )

    assert not any(isinstance(result, Request) for result in results)


async def test_documentation_page_has_no_next_page(crawl_page: CrawlPage, make_response: MakeResponse) -> None:
    results = await crawl_page(AWSCrawler(), make_response(AWSCrawler.DOCS_URL, "aws_docs.html"))

    assert not any(isinstance(result, Request) for result in results)


async def test_skips_malformed_items(crawl_page: CrawlPage) -> None:
    items: JsonValue = [
        "not an item",
        {"item": None},
        item(5, "Numeric title"),
        item("Amazon S3", None),
        item("Amazon EC2", "<p>Virtual <b>servers</b></p>", "/ec2/?trk=card"),
    ]

    results = await crawl_page(AWSCrawler(), json_page({"items": items, "metadata": {"totalHits": 5}}))

    assert results == [
        {
            "name": "Amazon EC2",
            "description": "Virtual servers",
            "pricing_policy": [],
            "url": "https://aws.amazon.com/ec2/?trk=card",
        }
    ]


@pytest.mark.parametrize(
    ("link", "url"), [("#", None), ("", None), (None, None), ("/ec2/", "https://aws.amazon.com/ec2/")]
)
def test_product_links(link: Optional[str], url: Optional[str]) -> None:
    assert AWSCrawler()._product_link(link) == url


async def test_items_without_product_link_are_kept(crawl_page: CrawlPage) -> None:
    items: JsonValue = [item("AWS IoT FleetWise", "Vehicle data", "#"), item("Amazon EC2", "Virtual servers", "#")]

    results = await crawl_page(AWSCrawler(), json_page({"items": items}))

    assert names(results) == ["AWS IoT FleetWise", "Amazon EC2"]


@pytest.mark.parametrize(
    ("content", "reason"),
    [("<html>Blocked</html>", "is not JSON"), ("[1, 2]", "is not a JSON object"), ('{"items": {}}', "is not a list")],
)
async def test_rejects_unexpected_pages(
    crawl_page: CrawlPage, content: str, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    response = Response(
        url=AWSCrawler.catalogue_url,
        content=content,
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
    )

    with pytest.raises(CatalogueFormatError, match=reason):
        await crawl_page(AWSCrawler(), response)

    assert [record.levelname for record in caplog.records].count("ERROR") == 1


async def test_empty_page_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(AWSCrawler(), json_page({"items": [], "metadata": {"totalHits": 0}}))

    assert any(record.levelname == "ERROR" and "holds no product" in record.getMessage() for record in caplog.records)


async def test_documentation_entries_without_link_or_abstract_are_skipped(crawl_page: CrawlPage) -> None:
    docs = Response(
        url=AWSCrawler.DOCS_URL,
        content=(
            '<li class="awsdocs-card-list-item"><span class="awsdocs-card-list-abstract">No link</span></li>'
            '<li class="awsdocs-card-list-item"><a class="awsdocs-link" href="/batch/">AWS Batch</a></li>'
            '<li class="awsdocs-card-list-item"><a class="awsdocs-link" href="/lambda/">AWS Lambda</a>'
            '<span class="awsdocs-card-list-abstract">Serverless functions</span></li>'
        ),
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
    )

    assert names(await crawl_page(AWSCrawler(), docs)) == ["AWS Lambda"]


@pytest.mark.parametrize(
    ("fragment", "text"), [(None, None), ("Plain", "Plain"), ("<p>A <b>bold</b> text</p>", "A bold text")]
)
def test_html_to_text(fragment: Optional[str], text: Optional[str]) -> None:
    assert AWSCrawler()._html_to_text(fragment) == text


async def test_invalid_documentation_entries_are_skipped(crawl_page: CrawlPage) -> None:
    name = "x" * 201
    docs = Response(
        url=AWSCrawler.DOCS_URL,
        content=(
            f'<li class="awsdocs-card-list-item"><a class="awsdocs-link" href="/x/">{name}</a>'
            '<span class="awsdocs-card-list-abstract">Too long</span></li>'
            '<li class="awsdocs-card-list-item"><a class="awsdocs-link" href="/batch/">AWS Batch</a>'
            '<span class="awsdocs-card-list-abstract">Batch jobs</span></li>'
        ),
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
    )

    assert names(await crawl_page(AWSCrawler(), docs)) == ["AWS Batch"]


async def test_documentation_request_keeps_the_server_rendered_list() -> None:
    crawler = AWSCrawler()

    request = crawler._complement_request(AWSCrawler.DOCS_URL)

    assert request.url == AWSCrawler.DOCS_URL
    assert request._session_kwargs == {"page_setup": crawler._keep_server_rendered_list}


async def test_documentation_script_is_blocked() -> None:
    crawler = AWSCrawler()
    page, route = AsyncMock(), AsyncMock()

    await crawler._keep_server_rendered_list(page)
    await crawler._abort(route)

    page.route.assert_awaited_once_with("**/awsdocs-main-landing-page*.js", crawler._abort)
    route.abort.assert_awaited_once_with()
