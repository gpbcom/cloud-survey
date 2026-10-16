from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.ibm.marketplace import IBMMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parent / "fixtures" / "marketplace"
CATALOGUE_URL = "https://cloud.ibm.com/catalog"


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


@pytest.fixture
def crawler(classifier: SoftwareClassifier) -> IBMMarketplaceCrawler:
    return IBMMarketplaceCrawler(classifier=classifier)


def page(content: Union[str, bytes]) -> Response:
    return Response(
        url=CATALOGUE_URL, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}
    )


def fixture_page() -> Response:
    return page((FIXTURES / "ibm_catalog.html").read_bytes())


def state_page(state: JsonValue) -> Response:
    return page(f"<script>window.__PRELOADED_STATE__ = {json.dumps(state)};</script>")


def offer(name: str, **fields: JsonValue) -> Dict[str, JsonValue]:
    return {"id": name, "tag": "ibm_third_party", "kind": "service", "name": name, "description": f"{name}."} | fields


def catalogue(*items: JsonValue) -> Response:
    return state_page({"model": {"categories": [{"id": "ai", "name": "AI / Machine Learning", "items": list(items)}]}})


def software(results: List[Union[Dict[str, JsonValue], Request]]) -> Dict[str, Dict[str, JsonValue]]:
    return {str(result["name"]): result for result in results if isinstance(result, dict)}


def test_configuration(crawler: IBMMarketplaceCrawler) -> None:
    assert crawler.name == "ibm-marketplace"
    assert IBMMarketplaceCrawler.catalogue_url == CATALOGUE_URL
    assert IBMMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"cloud.ibm.com"}


async def test_starts_with_the_catalogue_through_the_http_session(crawler: IBMMarketplaceCrawler) -> None:
    requests = [request async for request in crawler.start_requests()]

    assert [(request.url, request.sid, request.priority) for request in requests] == [
        (CATALOGUE_URL, "", IBMMarketplaceCrawler.PRIMARY_PRIORITY)
    ]


async def test_extracts_the_third_party_software(crawler: IBMMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    found = software(await crawl_page(crawler, fixture_page()))

    assert list(found) == [
        "Dynamiq GenAI platform",
        "FlowX.AI Platform",
        "Intel Gaudi 3 AI Accelerator OS Ubuntu24.04",
        "Alice",
        "Compliance and Customer Experience Automation",
        "Bespoken Automated Testing For IVR and Chat",
        "Vantage on VMware Analytics Bundle",
        "LAMP",
        "Email Delivery, powered by Sendgrid",
        "Red Hat 3scale API Management - BYOL",
    ]
    dynamiq = found["Dynamiq GenAI platform"]
    assert dynamiq["publisher"] == "Dynamiq Technologies, Inc."
    assert dynamiq["url"] == (
        "https://cloud.ibm.com/catalog/content/dynamiq-0c5d67b5-dd30-4756-8225-8eb9804e5a8e-global"
    )
    assert dynamiq["description"] == (
        "Dynamiq is an enterprise platform for building GenAI apps with on-premise control, LLM fine-tuning, RAG "
        "integration, and security."
    )
    assert dynamiq["updated_at"] == "2026-07-31T17:50:20.900074Z"
    assert "added_at" not in dynamiq
    assert found["LAMP"]["publisher"] is None
    assert "updated_at" not in found["LAMP"]


async def test_merges_the_categories_of_an_offer(crawler: IBMMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    found = software(await crawl_page(crawler, fixture_page()))

    assert found["Compliance and Customer Experience Automation"]["marketplace_categories"] == [
        "AI / Machine Learning",
        "Analytics",
        "Integration",
    ]
    assert found["FlowX.AI Platform"]["marketplace_categories"] == ["AI / Machine Learning", "Financial services"]


@pytest.mark.parametrize(
    ("name", "delivery"),
    [
        ("Dynamiq GenAI platform", "kubernetes"),
        ("Red Hat 3scale API Management - BYOL", "kubernetes"),
        ("Intel Gaudi 3 AI Accelerator OS Ubuntu24.04", "virtual-machine"),
        ("Vantage on VMware Analytics Bundle", "virtual-machine"),
        ("Alice", "saas"),
        ("LAMP", "other"),
        ("Email Delivery, powered by Sendgrid", "other"),
    ],
)
async def test_maps_the_offer_kind_to_the_delivery(
    crawler: IBMMarketplaceCrawler, crawl_page: CrawlPage, name: str, delivery: str
) -> None:
    found = software(await crawl_page(crawler, fixture_page()))

    assert found[name]["delivery"] == delivery


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Dynamiq GenAI platform", "ai-ml"),
        ("Vantage on VMware Analytics Bundle", "business-intelligence"),
        ("Red Hat 3scale API Management - BYOL", "api-management"),
    ],
)
async def test_classifies_the_software(
    crawler: IBMMarketplaceCrawler, crawl_page: CrawlPage, name: str, kind: str
) -> None:
    found = software(await crawl_page(crawler, fixture_page()))

    types = found[name]["types"]

    assert isinstance(types, list)
    assert kind in types


@pytest.mark.parametrize(
    ("item", "reason"),
    [
        (offer("Watson", tag="ibm_created"), "tag 'ibm_created'"),
        (offer("Advisory", isConsulting=True), "consulting offer"),
        (offer("Pro", kind="content", allTags=["professional_service"]), "professional service"),
        (offer("Acme Managed Services for VPC"), "service offer"),
        (offer("Acme Migration Services"), "service offer"),
        (offer("Old", allTags=["ibm_deprecated"]), "deprecated or beta"),
        (offer("New", allTags=["ibm_beta", 3]), "deprecated or beta"),
    ],
)
async def test_skips_the_offers_which_are_not_software(
    crawler: IBMMarketplaceCrawler,
    crawl_page: CrawlPage,
    caplog: pytest.LogCaptureFixture,
    item: Dict[str, JsonValue],
    reason: str,
) -> None:
    caplog.set_level(logging.DEBUG)

    found = software(await crawl_page(crawler, catalogue(item, offer("Kept", tag="ibm_community"))))

    assert list(found) == ["Kept"]
    assert f"Skipping the catalogue offer {item['name']!r} ({reason})." in caplog.text


async def test_keeps_a_content_offer_without_the_service_tag(
    crawler: IBMMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    found = software(await crawl_page(crawler, catalogue(offer("Stack", kind="content", allTags="terraform"))))

    assert found["Stack"]["delivery"] == "other"


async def test_ignores_an_unreadable_update_date(crawler: IBMMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    found = software(await crawl_page(crawler, catalogue(offer("Stale", lastModified="last week"))))

    assert "updated_at" not in found["Stale"]


async def test_tolerates_malformed_entries(crawler: IBMMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    state: JsonValue = {
        "model": {
            "categories": [
                "not a category",
                {"name": "Empty", "items": "none"},
                {"items": [offer("Unnamed category", catalogUrl=None), "not an offer", offer("", id=None)]},
                {"name": "Invalid", "items": [offer("No description", description="")]},
                {"name": "Again", "items": [offer("Unnamed category", catalogUrl=None)]},
            ]
        }
    }

    found = software(await crawl_page(crawler, state_page(state)))

    assert list(found) == ["Unnamed category"]
    assert found["Unnamed category"]["url"] is None
    assert found["Unnamed category"]["marketplace_categories"] == ["Again"]


async def test_raises_when_every_offer_is_skipped(
    crawler: IBMMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(crawler, catalogue(offer("Watson", tag="ibm_created")))

    assert any(record.levelno == logging.ERROR and "holds no software" in record.message for record in caplog.records)


@pytest.mark.parametrize(
    ("content", "message", "logged"),
    [
        ("<html>No state</html>", "data is missing", "has no `window.__PRELOADED_STATE__`"),
        ("<script>window.__PRELOADED_STATE__ = {broken</script>", "is not JSON", "is not JSON"),
        ("<script>window.__PRELOADED_STATE__ = [1];</script>", "is not a JSON object", "is not a JSON object"),
        (
            '<script>window.__PRELOADED_STATE__ = {"model": {}};</script>',
            "is not a list",
            "has no `model.categories` list",
        ),
    ],
)
async def test_raises_on_a_malformed_catalogue(
    crawler: IBMMarketplaceCrawler,
    crawl_page: CrawlPage,
    caplog: pytest.LogCaptureFixture,
    content: str,
    message: str,
    logged: str,
) -> None:
    with pytest.raises(CatalogueFormatError, match=message):
        await crawl_page(crawler, page(content))

    assert any(record.levelno == logging.ERROR and logged in record.message for record in caplog.records)
