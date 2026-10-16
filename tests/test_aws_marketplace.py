from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Union
from unittest.mock import patch

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.aws.marketplace import AWSMarketplaceCrawler
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
Results = List[Union[Dict[str, JsonValue], Request]]
FIXTURES = Path(__file__).parent / "fixtures" / "marketplace"
API = "https://aws.amazon.com/marketplace/api/awsmpdiscovery"
BROWSE = "https://aws.amazon.com/marketplace/b/579164ab-a400-4924-9c9c-590e45580b7d"
OPTIONS = [
    "SAAS",
    "AMAZON_MACHINE_IMAGE",
    "CONTAINER",
    "HELM",
    "EKS_ADD_ON",
    "CLOUDFORMATION_TEMPLATE",
    "EC2_IMAGE_BUILDER_COMPONENT",
    "SAGEMAKER_MODEL",
    "SAGEMAKER_ALGORITHM",
    "API",
]


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


@pytest.fixture
def crawler(classifier: SoftwareClassifier) -> AWSMarketplaceCrawler:
    return AWSMarketplaceCrawler(classifier=classifier)


def response(url: str, content: Union[bytes, str], meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url,
        content=content,
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
        meta=meta or {},
    )


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def search_page(
    content: Union[bytes, str], option: str = "SAAS", page: int = 1, integration: Optional[str] = "integ-test"
) -> Response:
    meta: Dict[str, JsonValue] = {"fulfillment_option": option, "page": page, "integration_id": integration}
    if page == 1:
        meta["may_be_empty"] = True
    return response(API, content, meta)


def listing(
    title: Optional[str] = "Acme Monitor",
    options: Optional[List[str]] = None,
    **extra: JsonValue,
) -> Dict[str, JsonValue]:
    fulfillment: List[JsonValue] = [{"Value": option} for option in (options or ["SAAS"])]
    entry: Dict[str, JsonValue] = {
        "Id": "prodview-acme",
        "DisplayAttributes": {"Title": title, "ShortDescription": "Monitor your cloud servers and logs."},
        "ListingCreator": {"DisplayName": "Acme"},
        "Categories": [],
        "FulfillmentOptionTypes": fulfillment,
    }
    entry.update(extra)
    return entry


def page_of(listings: List[Dict[str, JsonValue]], token: Optional[str] = None) -> str:
    data: Dict[str, JsonValue] = {"ListingSummaries": list(listings), "TotalResults": len(listings)}
    if token:
        data["NextToken"] = token
    return json.dumps(data)


def software(results: Results) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def types(item: Dict[str, JsonValue]) -> List[str]:
    values = item["types"]
    assert isinstance(values, list)
    return [str(value) for value in values]


def requests(results: Results) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def content_of(request: Request) -> Dict[str, JsonValue]:
    envelope = request._session_kwargs["json"]
    assert isinstance(envelope, dict)
    content = json.loads(str(envelope["contentString"]))
    assert isinstance(content, dict)
    return content


def test_configuration(crawler: AWSMarketplaceCrawler) -> None:
    assert crawler.name == "aws-marketplace"
    assert AWSMarketplaceCrawler.catalogue_url == BROWSE
    assert AWSMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"aws.amazon.com"}
    assert list(AWSMarketplaceCrawler.DELIVERIES) == OPTIONS


async def test_starts_with_the_browse_page(crawler: AWSMarketplaceCrawler) -> None:
    started = [request async for request in crawler.start_requests()]

    assert [(request.url, request.priority, request.sid) for request in started] == [
        (BROWSE, AWSMarketplaceCrawler.PRIMARY_PRIORITY, "")
    ]


async def test_browse_page_requests_each_fulfillment_option(
    crawler: AWSMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(crawler, response(BROWSE, fixture("aws_browse.html")))

    sent = requests(results)
    assert len(results) == len(sent) == len(OPTIONS)
    assert [request.meta for request in sent] == [
        {"fulfillment_option": option, "page": 1, "integration_id": "integ-kzv5xkq73lzjw", "may_be_empty": True}
        for option in OPTIONS
    ]
    first = sent[0]
    assert (first.url, first.sid, first.dont_filter, first.priority) == (API, "aws-marketplace-http", True, 0)
    assert first._session_kwargs["method"] == "POST"
    assert first._session_kwargs["headers"] == {"content-type": "application/json"}
    envelope = first._session_kwargs["json"]
    assert isinstance(envelope, dict)
    assert {key: value for key, value in envelope.items() if key != "contentString"} == {
        "region": "us-east-1",
        "headers": {
            "Accept": "application/json",
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSMPDiscoveryService.SearchListings",
        },
        "method": "POST",
        "operation": "SearchListings",
        "path": "/",
    }
    assert content_of(first) == {
        "MaxResults": 100,
        "RequestContext": {"IntegrationId": "integ-kzv5xkq73lzjw"},
        "Filters": [{"Type": "FULFILLMENT_OPTION_TYPE", "Values": ["SAAS"]}],
    }


async def test_browse_page_without_integration_id_uses_the_known_one(
    crawler: AWSMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    results = await crawl_page(crawler, response(BROWSE, "<html><head><title>AWS</title></head></html>"))

    assert {
        content_of(request)["RequestContext"] == {"IntegrationId": "integ-kzv5xkq73lzjw"}
        for request in requests(results)
    } == {True}
    assert any(record.levelno == logging.WARNING for record in caplog.records)


async def test_extracts_the_software_listings(crawler: AWSMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, search_page(fixture("aws_search_saas.json")))

    found = software(results)
    assert [item["name"] for item in found] == [
        "Claude Enterprise",
        "Claude Platform",
        "MongoDB Atlas (pay-as-you-go)",
        "Cloud Next-Generation Firewall as a Service (30-Day Free Trial to PAYG)",
        "IBM Db2 Standard Edition Hourly License Subscription for Amazon RDS",
    ]
    claude = found[0]
    assert claude["url"] == "https://aws.amazon.com/marketplace/pp/prodview-nnvi6wff6ef6m"
    assert claude["publisher"] == "Anthropic"
    assert claude["delivery"] == "saas"
    assert claude["marketplace_categories"] == [
        "AI Agents & Tools",
        "Content Creation",
        "Software Development",
        "Research",
    ]
    assert str(claude["description"]).startswith("Claude Enterprise gives every employee access to Claude Chat")
    assert "ai-ml" in types(claude)
    assert "database" in types(found[2])
    assert "security" in types(found[3])


async def test_skips_the_services_and_data_products(
    crawler: AWSMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    names = [item["name"] for item in software(await crawl_page(crawler, search_page(fixture("aws_search_saas.json"))))]

    assert "Unit 42 Retainer" not in names
    assert "Intelligent Event data sample - Non attended events, Seattle" not in names
    assert "Skipping the aws-marketplace listing 'Unit 42 Retainer', not software." in caplog.messages


async def test_delivery_of_the_first_software_option(crawler: AWSMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, search_page(fixture("aws_search_eks.json"), "EKS_ADD_ON"))

    assert [(item["name"], item["delivery"]) for item in software(results)] == [
        ("Datadog Operator", "kubernetes"),
        ("NetApp Trident", "kubernetes"),
        ("Dynatrace Operator", "kubernetes"),
        ("Buoyant Enterprise for Linkerd", "kubernetes"),
    ]
    assert "monitoring" in types(software(results)[0])
    assert "storage" in types(software(results)[1])


@pytest.mark.parametrize(
    ("options", "delivery"),
    [
        (["PROFESSIONAL_SERVICES", "AMAZON_MACHINE_IMAGE"], "virtual-machine"),
        (["CLOUDFORMATION_TEMPLATE"], "virtual-machine"),
        (["EC2_IMAGE_BUILDER_COMPONENT"], "virtual-machine"),
        (["CONTAINER"], "container"),
        (["HELM"], "kubernetes"),
        (["SAGEMAKER_MODEL"], "ai-model"),
        (["SAGEMAKER_ALGORITHM"], "ai-model"),
        (["API"], "api"),
    ],
)
async def test_delivery_mapping(
    crawler: AWSMarketplaceCrawler, crawl_page: CrawlPage, options: List[str], delivery: str
) -> None:
    results = await crawl_page(crawler, search_page(page_of([listing(options=options)])))

    assert [item["delivery"] for item in software(results)] == [delivery]


async def test_publisher_falls_back_to_the_manufacturer(crawler: AWSMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    entities: List[JsonValue] = ["bad", {"Product": {}}, {"Manufacturer": {"DisplayName": "Acme Labs"}}]
    entries = [
        listing("Acme One", ListingCreator={}, AssociatedEntities=entities, Id="prodview-one"),
        listing("Acme Two", ListingCreator=None, AssociatedEntities="bad", Id="prodview-two"),
    ]

    results = await crawl_page(crawler, search_page(page_of(entries)))

    assert [(item["name"], item["publisher"]) for item in software(results)] == [
        ("Acme One", "Acme Labs"),
        ("Acme Two", None),
    ]


async def test_malformed_listings(
    crawler: AWSMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    long_only = listing("Acme Long", Id="prodview-long", Categories="bad")
    long_only["DisplayAttributes"] = {"Title": "Acme Long", "LongDescription": "A long description of Acme."}
    entries: List[JsonValue] = [
        "not a listing",
        listing(None, Id="prodview-untitled"),
        listing("Acme Options", FulfillmentOptionTypes="bad", Id="prodview-options"),
        listing("Acme No Id", Id=None, Categories=["bad", {"DisplayName": "Security", "ParentValue": "unknown"}]),
        long_only,
    ]

    results = await crawl_page(crawler, search_page(json.dumps({"ListingSummaries": entries})))

    assert [
        (item["name"], item["url"], item["description"], item["marketplace_categories"]) for item in software(results)
    ] == [
        ("Acme No Id", None, "Monitor your cloud servers and logs.", ["Security"]),
        ("Acme Long", "https://aws.amazon.com/marketplace/pp/prodview-long", "A long description of Acme.", []),
    ]
    assert any(record.levelno == logging.WARNING for record in caplog.records)


async def test_requests_the_next_page(crawler: AWSMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, search_page(fixture("aws_search_saas.json")))

    [next_page] = requests(results)
    assert results[-1] is next_page
    assert next_page.meta == {"fulfillment_option": "SAAS", "page": 2, "integration_id": "integ-test"}
    content = content_of(next_page)
    assert content["NextToken"] == json.loads(fixture("aws_search_saas.json"))["NextToken"]
    assert content["RequestContext"] == {"IntegrationId": "integ-test"}


async def test_next_page_without_integration_meta(crawler: AWSMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, search_page(page_of([listing()], "token-2"), page=3, integration=None))

    [next_page] = requests(results)
    assert next_page.meta["page"] == 4
    assert content_of(next_page)["RequestContext"] == {"IntegrationId": "integ-kzv5xkq73lzjw"}


@pytest.mark.parametrize(
    "content",
    [
        fixture("aws_search_eks.json"),
        page_of([], "token-2"),
    ],
)
async def test_last_page(crawler: AWSMarketplaceCrawler, crawl_page: CrawlPage, content: Union[bytes, str]) -> None:
    assert requests(await crawl_page(crawler, search_page(content, "EKS_ADD_ON"))) == []


async def test_page_limit(crawler: AWSMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    with patch.object(AWSMarketplaceCrawler, "page_limit", 2):
        within = requests(await crawl_page(crawler, search_page(page_of([listing()], "token-2"))))
        beyond = requests(await crawl_page(crawler, search_page(page_of([listing()], "token-3"), page=2)))

    assert [request.meta["page"] for request in within] == [2]
    assert beyond == []


async def test_page_without_listings_list(
    crawler: AWSMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(CatalogueFormatError, match="`ListingSummaries` is not a list"):
        await crawl_page(crawler, search_page(json.dumps({"Message": "throttled"})))

    assert any(
        record.levelno == logging.ERROR and "ListingSummaries" in record.getMessage() for record in caplog.records
    )


async def test_empty_next_page_is_an_error(
    crawler: AWSMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(crawler, search_page(page_of([]), page=2))

    assert any(record.levelno == logging.ERROR for record in caplog.records)


async def test_listings_streamed_once_across_options(crawler: AWSMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    first = await crawl_page(crawler, search_page(fixture("aws_search_eks.json"), "EKS_ADD_ON"))
    again = await crawl_page(crawler, search_page(fixture("aws_search_eks.json"), "HELM"))

    assert len(software(first)) == 4
    assert software(again) == []
