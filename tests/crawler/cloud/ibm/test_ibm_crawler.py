from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.ibm.crawler import IBMCloudCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
CATALOGUE_URL = "https://cloud.ibm.com/catalog"
PRODUCTS_URL = (
    "https://www.ibm.com/content/adobe-cms/us/en/products/jcr:content/root/table_of_contents/"
    "product_search_1183165654.search-full.html?field_hierarchy_07[0][0]=IBM%20Cloud&size=100&page=1"
)


def page(url: str, content: str) -> Response:
    return Response(url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def state_page(state: JsonValue) -> Response:
    return page(CATALOGUE_URL, f"<script>window.__PRELOADED_STATE__ = {json.dumps(state)};</script>")


def offer(name: str, url: JsonValue = None, **fields: JsonValue) -> Dict[str, JsonValue]:
    return {"id": name, "tag": "ibm_created", "type": "service", "name": name, "description": f"{name}.", **fields} | (
        {"catalogUrl": url} if url is not None else {}
    )


def catalogue(*items: JsonValue) -> Response:
    return state_page({"model": {"categories": [{"id": "all", "items": list(items)}]}})


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = IBMCloudCrawler()

    assert crawler.name == "ibm"
    assert IBMCloudCrawler.catalogue_url == CATALOGUE_URL
    assert IBMCloudCrawler.complement_urls == (PRODUCTS_URL,)
    assert crawler.allowed_domains == {"cloud.ibm.com", "www.ibm.com"}
    assert IBMCloudCrawler.name_prefixes == ("IBM Cloud ", "IBM ", "Cloud ")


async def test_starts_with_the_catalogue_then_the_product_search() -> None:
    requests = [request async for request in IBMCloudCrawler().start_requests()]

    assert [(request.url, request.priority) for request in requests] == [
        (CATALOGUE_URL, IBMCloudCrawler.PRIMARY_PRIORITY),
        (PRODUCTS_URL, 0),
    ]


async def test_extracts_the_catalogue_products(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(IBMCloudCrawler(), make_response(CATALOGUE_URL, "ibm_catalog.html"))

    assert names(results) == [
        "DataStage",
        "Bare Metal Server for Classic",
        "Virtual Server for Classic",
        "VCF as a Service",
        "Power Virtual Server",
        "Code Engine",
        "Container Registry",
        "Kubernetes Service",
        "Red Hat OpenShift on IBM Cloud",
        "DNS Services",
        "Public Address Range",
        "Virtual Private Cloud",
        "Transit Gateway",
        "Key Protect",
    ]
    assert results[0] == {
        "name": "DataStage",
        "description": "Create ETL and data pipeline services for real-time, micro-batch, and batch data "
        "orchestration.",
        "pricing_policy": [],
        "url": "https://cloud.ibm.com/catalog/services/datastage",
        "updated_at": "2026-07-31T17:50:20.900074Z",
        "updated_caveat": "catalogue-entry",
        "catalogue_categories": ["Analytics"],
    }


async def test_catalogue_products_are_filed_under_their_categories(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(IBMCloudCrawler(), make_response(CATALOGUE_URL, "ibm_catalog.html"))

    categories = {result["name"]: result["catalogue_categories"] for result in results if isinstance(result, dict)}
    assert categories["Power Virtual Server"] == ["Compute"]
    assert categories["Code Engine"] == ["Containers"]
    assert categories["Transit Gateway"] == ["Networking"]
    assert categories["Key Protect"] == ["Security"]


async def test_catalogue_products_are_dated_by_their_last_modification(
    make_response: MakeResponse, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    results = await crawl_page(IBMCloudCrawler(), make_response(CATALOGUE_URL, "ibm_catalog.html"))

    dates = {result["name"]: result.get("updated_at") for result in results if isinstance(result, dict)}
    assert dates["DataStage"] == "2026-07-31T17:50:20.900074Z"
    assert dates["Code Engine"] == "2026-09-14T08:02:47.135290Z"
    assert dates["Key Protect"] is None
    assert dates["Container Registry"] is None
    assert not any("added_at" in result for result in results if isinstance(result, dict))
    assert any("unreadable date 'unknown'" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    "excluded",
    [
        "Streaming Analytics",
        "Quantum Compute",
        "Hyper Protect Crypto Services",
        "Container Security Services",
        "Core Security Services",
    ],
    ids=["deprecated", "beta", "deprecated-security", "consulting", "content"],
)
async def test_catalogue_non_products_are_filtered_out(
    make_response: MakeResponse, crawl_page: CrawlPage, excluded: str
) -> None:
    results = await crawl_page(IBMCloudCrawler(), make_response(CATALOGUE_URL, "ibm_catalog.html"))

    assert excluded not in names(results)


async def test_catalogue_third_party_and_invalid_offers_are_filtered_out(crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        IBMCloudCrawler(),
        catalogue(
            offer("Partner tool", tag="ibm_third_party"), offer("Undescribed", description=""), offer("Key Protect")
        ),
    )

    assert names(results) == ["Key Protect"]


async def test_catalogue_links(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(IBMCloudCrawler(), make_response(CATALOGUE_URL, "ibm_catalog.html"))

    urls = {result["name"]: result["url"] for result in results if isinstance(result, dict)}
    assert (
        urls["Red Hat OpenShift on IBM Cloud"]
        == "https://cloud.ibm.com/kubernetes/catalog/create?platformType=openshift"
    )
    assert urls["Kubernetes Service"] == "https://cloud.ibm.com/kubernetes/catalog/create"
    assert urls["Public Address Range"] == "https://cloud.ibm.com/infrastructure/provision/vpc"
    assert urls["Virtual Private Cloud"] is None
    assert urls["VCF as a Service"] is None


async def test_offers_listed_in_several_categories_are_read_once(crawl_page: CrawlPage) -> None:
    state: JsonValue = {
        "model": {
            "categories": [
                {"id": "storage", "name": "Storage", "items": [offer("Object Storage", "/objectstorage/create")]},
                {"id": "security", "name": "Security", "items": [offer("Object Storage", "/objectstorage/create")]},
                {"id": "unnamed", "items": [offer("Object Storage", "/objectstorage/create"), "not an offer"]},
                {"id": "again", "name": "Storage", "items": [offer("Object Storage", "/objectstorage/create")]},
                {"id": "empty", "name": "Empty", "items": None},
                "not a category",
            ]
        }
    }

    results = await crawl_page(IBMCloudCrawler(), state_page(state))

    assert results == [
        {
            "name": "Object Storage",
            "description": "Object Storage.",
            "pricing_policy": [],
            "url": "https://cloud.ibm.com/objectstorage/create",
            "catalogue_categories": ["Storage", "Security"],
        }
    ]


async def test_product_search_completes_the_catalogue(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = IBMCloudCrawler()
    await crawl_page(crawler, make_response(CATALOGUE_URL, "ibm_catalog.html"))

    results = await crawl_page(crawler, make_response(PRODUCTS_URL, "ibm_products.html"))

    assert names(results) == ["Hybrid Cloud Mesh", "Cloud Paks"]
    assert results[0] == {
        "name": "Hybrid Cloud Mesh",
        "description": "Expedite and streamline application connectivity across hybrid environments with IBM "
        "Hybrid Cloud Mesh app-first connectivity that accelerates development, enhances security and improves "
        "performance and resilience",
        "pricing_policy": [],
        "url": "https://www.ibm.com/products/hybrid-cloud-mesh",
    }


async def test_product_search_aliases_only_apply_to_streamed_products(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(IBMCloudCrawler(), make_response(PRODUCTS_URL, "ibm_products.html"))

    assert names(results) == [
        "Cloud Code Engine",
        "IBM Red Hat OpenShift",
        "Hybrid Cloud Mesh",
        "Cloud Paks",
        "DNS",
        "Transit Gateway",
    ]


async def test_product_search_incomplete_cards(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    cards = (
        '<div class="ibm-search__results__card"><div class="bx--card__copy">No heading</div></div>'
        '<div class="ibm-search__results__card"><div class="bx--card__heading">No description</div></div>'
        '<div class="ibm-search__results__card"><div class="bx--card__heading">Cloud Sync</div>'
        '<div class="bx--card__copy">DNS synchronization.</div></div>'
    )

    results = await crawl_page(IBMCloudCrawler(), page(PRODUCTS_URL, cards))

    assert results == [{"name": "Cloud Sync", "description": "DNS synchronization.", "pricing_policy": [], "url": None}]
    skipped = [record for record in caplog.records if "invalid catalogue entry" in record.getMessage()]
    assert [record.levelno for record in skipped] == [logging.WARNING]


@pytest.mark.parametrize(
    ("url", "key"),
    [
        (
            "https://cloud.ibm.com/kubernetes/catalog/create?platformType=openshift",
            "cloud.ibm.com/kubernetes/catalog/create?platformtype=openshift",
        ),
        ("https://cloud.ibm.com/catalog/services/db2/", "cloud.ibm.com/catalog/services/db2"),
        ("https://www.ibm.com/products/dns?lnk=flathl", "ibm.com/products/dns"),
    ],
)
def test_url_keys(url: str, key: str) -> None:
    assert IBMCloudCrawler()._url_key(url) == key


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("<html><body>No catalogue data</body></html>", "data is missing"),
        ("<script>window.__PRELOADED_STATE__</script>", "data is missing"),
        ("<script>window.__PRELOADED_STATE__ = {broken;</script>", "not JSON"),
        ("<script>window.__PRELOADED_STATE__ = [1, 2];</script>", "not a JSON object"),
        ('<script>window.__PRELOADED_STATE__ = {"model": {"categories": {}}};</script>', "not a list"),
    ],
    ids=["no-marker", "no-assignment", "not-json", "not-object", "no-categories"],
)
async def test_invalid_catalogue_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, content: str, reason: str
) -> None:
    with pytest.raises(CatalogueFormatError, match=reason):
        await crawl_page(IBMCloudCrawler(), page(CATALOGUE_URL, content))

    assert [record.levelno for record in caplog.records if record.levelno >= logging.ERROR] == [logging.ERROR]
    assert CATALOGUE_URL in caplog.records[-1].getMessage()


async def test_catalogue_without_product_is_an_error(crawl_page: CrawlPage) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(IBMCloudCrawler(), catalogue(offer("Guide", type="content")))
