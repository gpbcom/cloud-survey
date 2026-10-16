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
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.gcp.marketplace import GoogleCloudMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
Results = List[Union[Dict[str, JsonValue], Request]]
FIXTURES = Path(__file__).parent / "fixtures" / "marketplace"
API = (
    "https://cloudconsole-pa.clients6.google.com/v3/entityServices/MarketplaceEntityService/entities/"
    "MARKETPLACE_BROWSE_PRODUCTS:get?key=AIzaSyCI-zsRP85UVOi0DjtiCwWBwQ1djDy741g&alt=json&prettyPrint=false"
)
PRODUCT = "https://console.cloud.google.com/marketplace/product/"


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


@pytest.fixture
def crawler(classifier: SoftwareClassifier) -> GoogleCloudMarketplaceCrawler:
    return GoogleCloudMarketplaceCrawler(classifier=classifier)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def browse_page(
    content: Union[bytes, str], page: int = 1, facet: Optional[str] = None, label: Optional[str] = None
) -> Response:
    meta: Dict[str, JsonValue] = {"page": page, "facet": facet, "label": label}
    if facet and page == 1:
        meta["may_be_empty"] = True
    return Response(
        url=API,
        content=content,
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
        meta=meta,
    )


def card(title: Optional[str] = "Acme CRM", **extra: JsonValue) -> Dict[str, JsonValue]:
    entry: Dict[str, JsonValue] = {
        "productDisplayName": "acme-public/acme-crm",
        "title": title,
        "subtitle": "Acme",
        "description": "Manage your customer relationships.",
        "productType": "SaaS & APIs",
        "familyType": "ManagedService",
    }
    entry.update(extra)
    return entry


def results_of(cards: List[JsonValue], token: str = "", facets: Optional[List[JsonValue]] = None) -> str:
    browse: Dict[str, JsonValue] = {
        "facetValueLinkLists": list(facets or []),
        "totalCount": len(cards),
        "nextPageToken": token,
        "searchResult": {"cards": list(cards)},
    }
    return json.dumps([{"successfulResult": {"resultData": {"marketplaceBrowseProducts": browse}}}])


def software(results: Results) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def requests(results: Results) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def types(item: Dict[str, JsonValue]) -> List[str]:
    values = item["types"]
    assert isinstance(values, list)
    return [str(value) for value in values]


def parameters_of(request: Request) -> Dict[str, JsonValue]:
    body = request._session_kwargs["json"]
    assert isinstance(body, dict)
    entity = body["entityRequest"]
    assert isinstance(entity, dict)
    payload = entity["requestPayload"]
    assert isinstance(payload, dict)
    parameters = payload["parameters"]
    assert isinstance(parameters, dict)
    return parameters


def test_configuration(crawler: GoogleCloudMarketplaceCrawler) -> None:
    assert crawler.name == "gcp-marketplace"
    assert GoogleCloudMarketplaceCrawler.catalogue_url == API
    assert GoogleCloudMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"cloudconsole-pa.clients6.google.com"}


async def test_starts_with_every_product(crawler: GoogleCloudMarketplaceCrawler) -> None:
    [request] = [request async for request in crawler.start_requests()]

    assert (request.url, request.sid, request.priority, request.dont_filter) == (
        API,
        "gcp-marketplace-http",
        GoogleCloudMarketplaceCrawler.PRIMARY_PRIORITY,
        True,
    )
    assert request.meta == {"page": 1, "facet": None, "label": None}
    assert request._session_kwargs["method"] == "POST"
    assert request._session_kwargs["headers"] == {
        "content-type": "application/json",
        "origin": "https://console.cloud.google.com",
        "referer": "https://console.cloud.google.com/marketplace/browse",
    }
    assert request._session_kwargs["json"] == {
        "entityRequest": {
            "entityName": "MARKETPLACE_BROWSE_PRODUCTS",
            "requestPayload": {
                "parameters": {
                    "locale": "en_US",
                    "solutionScopeId": "LAUNCHER",
                    "selectedFacetValues": [],
                    "query": "*",
                    "pageToken": "",
                    "isPrivateCatalog": False,
                    "responseType": "SEARCH_RESULTS",
                },
                "@type": "type.googleapis.com/google.internal.cloud.console.clientapi.marketplace."
                "BrowseProductsRequest",
            },
        },
        "requestContext": {"pagePath": "/marketplace/browse"},
    }


async def test_extracts_the_software_products(crawler: GoogleCloudMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, browse_page(fixture("gcp_browse.json")))

    found = software(results)
    assert [(item["name"], item["delivery"]) for item in found] == [
        ("XFCE Desktop on Ubuntu 24.04", "virtual-machine"),
        ("Google Cloud Data Catalog API", "saas"),
        ("Torch", "virtual-machine"),
        ("Geneva OS SaaS", "saas"),
        ("Deepgram Voice AI", "kubernetes"),
        ("Falco", "container"),
        ("Code Llama", "ai-model"),
        ("Transportation Planner", "saas"),
    ]
    xfce = found[0]
    assert xfce["url"] == f"{PRODUCT}cloud-infrastructure-services/xfce-desktop-ubuntu-24-04"
    assert xfce["publisher"] == "Cloud Infrastructure Services"
    assert xfce["marketplace_categories"] == []
    assert str(xfce["description"]).startswith("XFCE desktop environment and xRDP")
    assert "ai-ml" in types(found[6])


async def test_skips_the_services_datasets_and_google_cloud_products(
    crawler: GoogleCloudMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    names = [item["name"] for item in software(await crawl_page(crawler, browse_page(fixture("gcp_browse.json"))))]

    for excluded in (
        "Execute Agent – Automation Agent",  # noqa: RUF001
        "Cloud Datastore",
        "Provisioned Throughput with xAI's Grok models",
        "google-books-ngrams-2020",
    ):
        assert excluded not in names
    assert any(
        "not software (Professional Services, ProfessionalServicesProduct)" in message for message in caplog.messages
    )


async def test_first_page_requests_the_next_page_then_the_categories(
    crawler: GoogleCloudMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(crawler, browse_page(fixture("gcp_browse.json")))

    sent = requests(results)
    assert results[-len(sent) :] == sent
    next_page, *categories = sent
    assert next_page.meta == {"page": 2, "facet": None, "label": None}
    assert next_page.priority == GoogleCloudMarketplaceCrawler.PRIMARY_PRIORITY
    assert (
        parameters_of(next_page)["pageToken"]
        == json.loads(fixture("gcp_browse.json"))[0]["successfulResult"]["resultData"]["marketplaceBrowseProducts"][
            "nextPageToken"
        ]
    )
    assert [(request.meta, request.priority) for request in categories] == [
        ({"page": 1, "facet": "analytics", "label": "Analytics", "may_be_empty": True}, 0),
        ({"page": 1, "facet": "crm", "label": "CRM", "may_be_empty": True}, 0),
        ({"page": 1, "facet": "developer-tools", "label": "DevOps", "may_be_empty": True}, 0),
    ]
    assert parameters_of(categories[1])["selectedFacetValues"] == [{"facetId": "category", "facetValueId": "crm"}]
    assert parameters_of(categories[1])["pageToken"] == ""


async def test_category_query_labels_the_products(
    crawler: GoogleCloudMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(crawler, browse_page(fixture("gcp_browse_category.json"), 1, "crm", "CRM"))

    found = software(results)
    assert [(item["name"], item["marketplace_categories"]) for item in found] == [
        ("Labra Cloud Commerce Platform", ["CRM"]),
        ("BeYourMarket on Windows server 2019", ["CRM"]),
        ("Netsuite Connector by Windsor.ai", ["CRM"]),
        ("Sarvam Samvaad (Conversational AI Agents)", ["CRM"]),
    ]
    assert {"crm"} <= set(types(found[0]))
    assert str(found[0]["description"]).startswith("With the Labra Cloud Commerce Management Platform")
    [next_page] = requests(results)
    assert next_page.meta == {"page": 2, "facet": "crm", "label": "CRM"}
    assert next_page.priority == 0
    assert parameters_of(next_page)["selectedFacetValues"] == [{"facetId": "category", "facetValueId": "crm"}]


async def test_category_query_streams_known_products_again(
    crawler: GoogleCloudMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    first = await crawl_page(crawler, browse_page(fixture("gcp_browse_category.json"), 1, "crm", "CRM"))
    tagged = await crawl_page(crawler, browse_page(fixture("gcp_browse_category.json"), 1, "analytics", "Analytics"))
    again = await crawl_page(crawler, browse_page(fixture("gcp_browse_category.json"), 1, "analytics", "Analytics"))

    assert len(software(first)) == 4
    assert {
        tuple(map(str, categories))
        for categories in (item["marketplace_categories"] for item in software(tagged))
        if isinstance(categories, list)
    } == {("CRM", "Analytics")}
    assert software(again) == []


async def test_last_page(crawler: GoogleCloudMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, browse_page(fixture("gcp_browse_last.json"), 1, "education", "Education"))

    assert results == []


async def test_later_pages_do_not_request_the_categories(
    crawler: GoogleCloudMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(crawler, browse_page(fixture("gcp_browse.json"), 2))

    assert [request.meta for request in requests(results)] == [{"page": 3, "facet": None, "label": None}]


async def test_page_limit_applies_per_query(crawler: GoogleCloudMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    with patch.object(GoogleCloudMarketplaceCrawler, "page_limit", 2):
        beyond = await crawl_page(crawler, browse_page(results_of([card()], "token-3"), 2))
        other_query = await crawl_page(crawler, browse_page(results_of([card()], "token-2"), 1, "crm", "CRM"))

    assert requests(beyond) == []
    assert [request.meta["page"] for request in requests(other_query)] == [2]


async def test_no_category_facet(crawler: GoogleCloudMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    facets: List[JsonValue] = [
        {"facetId": "price", "facetValueLinks": [{"facetBinding": {"facetId": "price", "facetValueId": "free"}}]},
        {"facetId": "category", "facetValueLinks": "bad"},
        {"facetId": "category", "facetValueLinks": ["bad", {"facetBinding": {"facetValueId": "maps"}}]},
    ]

    results = await crawl_page(crawler, browse_page(results_of([card()], "", facets)))

    assert [request.meta for request in requests(results)] == [
        {"page": 1, "facet": "maps", "label": "maps", "may_be_empty": True}
    ]


async def test_malformed_cards(
    crawler: GoogleCloudMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    cards: List[JsonValue] = [
        "not a card",
        card(None, productDisplayName="acme/untitled"),
        card("Acme No Page", productDisplayName=None, productType="Desktop apps"),
        card("Acme No Text", productDisplayName="acme/no-text", description=None),
    ]

    results = await crawl_page(
        crawler,
        browse_page(
            json.dumps(
                [
                    {
                        "successfulResult": {
                            "resultData": {
                                "marketplaceBrowseProducts": {
                                    "facetValueLinkLists": "bad",
                                    "searchResult": {"cards": cards},
                                }
                            }
                        }
                    }
                ]
            )
        ),
    )

    assert [(item["name"], item["url"], item["delivery"]) for item in software(results)] == [
        ("Acme No Page", None, "other"),
    ]
    assert any(record.levelno == logging.WARNING for record in caplog.records)
    assert "Unknown gcp-marketplace product type 'Desktop apps' of 'Acme No Page': delivery other." in caplog.messages


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        "{}",
        json.dumps([{"successfulResult": {"resultData": {"marketplaceBrowseProducts": {"searchResult": {}}}}}]),
        json.dumps([{"failedResult": {"error": "PERMISSION_DENIED"}}]),
    ],
)
async def test_page_without_cards(
    crawler: GoogleCloudMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, content: str
) -> None:
    with pytest.raises(CatalogueFormatError, match=r"`marketplaceBrowseProducts.searchResult.cards` missing"):
        await crawl_page(crawler, browse_page(content))

    assert any(
        record.levelno == logging.ERROR and "searchResult.cards" in record.getMessage() for record in caplog.records
    )


async def test_empty_page_of_every_product_is_an_error(
    crawler: GoogleCloudMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(crawler, browse_page(results_of([])))

    assert any(record.levelno == logging.ERROR for record in caplog.records)
