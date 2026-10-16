from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, Dict, List, Optional, Tuple, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.civo.crawler import CivoCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
KONSTRUCT_URL = "https://www.civo.com/konstruct"


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def ld_page(url: str, *scripts: str, body: str = "") -> Response:
    tags = "".join(f'<script type="application/ld+json">{script}</script>' for script in scripts)
    return page(url, f"<html><head>{tags}</head><body>{body}</body></html>")


def offers(*items: JsonValue) -> str:
    return json.dumps({"@type": "Service", "name": "Hub", "hasOfferCatalog": {"itemListElement": list(items)}})


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Tuple[str, Dict[str, JsonValue]]]:
    return [(result.url, result.meta) for result in results if isinstance(result, Request)]


def test_configuration() -> None:
    crawler = CivoCrawler()

    assert crawler.name == "civo"
    assert CivoCrawler.catalogue_url == "https://www.civo.com/public-cloud"
    assert CivoCrawler.complement_urls == (
        "https://www.civo.com/private-cloud",
        "https://www.civo.com/ai",
        "https://www.civo.com/pricing",
    )
    assert crawler.allowed_domains == {"www.civo.com"}


async def test_extracts_the_offer_catalogue_of_a_hub(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(CivoCrawler(), make_response(CivoCrawler.catalogue_url, "civo_public_cloud.html"))

    assert names(results) == [
        "Civo Managed Kubernetes",
        "Civo Compute",
        "Civo Managed Databases",
        "Civo Load Balancers",
    ]
    assert results[2] == {
        "name": "Civo Managed Databases",
        "description": "Civo Databases is a managed database service supporting PostgreSQL with high availability, "
        "automated backups, and up to five replicas. It handles provisioning, patching, and recovery with no extra "
        "fees, enabling teams to focus on building applications.",
        "pricing_policy": [],
        "url": "https://www.civo.com/public-cloud/databases",
    }
    assert requests(results) == []


async def test_ai_hub_lists_the_offers_then_the_gpu_models(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(CivoCrawler(), make_response(CivoCrawler.AI_URL, "civo_ai.html"))

    assert names(results) == [
        "Civo GPU Compute",
        "Civo GPU Kubernetes",
        "relaxAI",
        "Vera Rubin NVL72",
        "B300 Blackwell Ultra",
        "B200 Blackwell",
        "A100",
        "H100",
        "H200",
        "L40s",
    ]
    assert results[6] == {
        "name": "A100",
        "description": "All-round GPU for a variety of workloads, including AI & data analytics",
        "pricing_policy": [],
        "url": "https://www.civo.com/ai/a100-gpu",
    }


async def test_ai_hub_footer_requests_the_missing_product_pages(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = CivoCrawler()
    await crawl_page(crawler, make_response(CivoCrawler.catalogue_url, "civo_public_cloud.html"))

    results = await crawl_page(crawler, make_response(CivoCrawler.AI_URL, "civo_ai.html"))

    assert [(url, meta[CivoCrawler.PRODUCT_NAME]) for url, meta in requests(results)] == [
        (KONSTRUCT_URL, "Konstruct"),
        ("https://www.civo.com/public-cloud/block-storage", "Block storage"),
        ("https://www.civo.com/private-cloud/civostack-enterprise", "CivoStack Enterprise"),
        ("https://www.civo.com/private-cloud/flexcore", "FlexCore"),
        ("https://www.civo.com/private-cloud/vmware-service-providers", "VMware for service providers"),
        ("https://www.civo.com/private-cloud/vmware-alternative", "VMware alternative"),
        ("https://www.civo.com/private-cloud/vmware-migration-tool", "VMware migration"),
        ("https://www.civo.com/uk-sovereign-cloud", "UK Sovereign Cloud"),
        ("https://www.civo.com/india", "India Sovereign Cloud"),
        ("https://www.civo.com/ai/cloud-gpu", "Cloud GPU"),
        ("https://www.civo.com/ai/sovereign", "Sovereign AI"),
        ("https://www.civo.com/ai/private", "Private AI"),
    ]


async def test_footer_is_only_read_on_the_ai_hub(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    footer = make_response(CivoCrawler.AI_URL, "civo_ai.html").body.decode()

    results = await crawl_page(CivoCrawler(), page(CivoCrawler.PRIVATE_CLOUD_URL, footer))

    assert len(names(results)) == 10
    assert requests(results) == []


async def test_pricing_adds_the_services_without_product_page(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(CivoCrawler(), make_response(CivoCrawler.PRICING_URL, "civo_pricing.html"))

    assert results == [
        {
            "name": "Object Store",
            "description": "An S3 compatible object storage solution.",
            "pricing_policy": [],
            "url": "https://www.civo.com/pricing#object-store",
        }
    ]


async def test_product_page_is_named_after_the_footer_label(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(KONSTRUCT_URL, "civo_product_konstruct.html")
    response.meta.update({CivoCrawler.PRODUCT_PAGE: KONSTRUCT_URL, CivoCrawler.PRODUCT_NAME: "Konstruct"})

    results = await crawl_page(CivoCrawler(), response)

    assert results == [
        {
            "name": "Konstruct",
            "description": "Deploy a complete Internal Developer Platform in minutes, not months. Konstruct gives you "
            "GitOps ownership with no vendor lock-in. Own your platform. Build for more.",
            "pricing_policy": [],
            "url": KONSTRUCT_URL,
        }
    ]


async def test_product_page_reached_through_a_short_path_is_kept(crawl_page: CrawlPage) -> None:
    head = '<meta name="description" content="Managed PostgreSQL.">'
    meta: Dict[str, JsonValue] = {
        CivoCrawler.PRODUCT_PAGE: "https://www.civo.com/databases",
        CivoCrawler.PRODUCT_NAME: "Databases",
    }

    results = await crawl_page(
        CivoCrawler(), page("https://www.civo.com/public-cloud/databases", f"<html><head>{head}</head></html>", meta)
    )

    assert names(results) == ["Databases"]


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("https://www.civo.com/databases", "https://www.civo.com/public-cloud/databases/"),
        ("https://www.civo.com/ai/compute", "https://civo.com/ai/gpu-compute?ref=footer"),
        ("https://www.civo.com/features/block-storage", "https://www.civo.com/public-cloud/block-storage"),
        ("https://www.civo.com/konstruct#features", "https://www.civo.com/konstruct"),
    ],
)
def test_url_keys_follow_the_short_paths(first: str, second: str) -> None:
    crawler = CivoCrawler()

    assert crawler._url_key(first) == crawler._url_key(second)


def test_url_keys_keep_the_pricing_anchors() -> None:
    crawler = CivoCrawler()

    assert crawler._url_key("https://www.civo.com/pricing#object-store") == "civo.com/pricing#object-store"
    assert crawler._url_key("https://www.civo.com/pricing") == "civo.com/pricing"


@pytest.mark.parametrize(
    ("link", "url"),
    [
        ("https://www.civo.com/load-balancers", "https://www.civo.com/public-cloud/load-balancers"),
        ("/vmware-alternative/", "https://www.civo.com/private-cloud/vmware-alternative"),
        ("/ai/relaxai", "https://www.civo.com/ai/relaxai"),
    ],
)
def test_canonical_urls(link: str, url: str) -> None:
    assert CivoCrawler()._canonical_url(link) == url


async def test_skips_malformed_offers(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="scrapling.spiders.civo")
    response = ld_page(
        CivoCrawler.catalogue_url,
        "{not json",
        json.dumps({"@type": "BreadcrumbList", "itemListElement": [{"name": "Home", "item": "/"}]}),
        offers("not an offer", {"name": "Snapshots", "description": "Volume snapshots."}, {"name": "Untold"}),
    )

    results = await crawl_page(CivoCrawler(), response)

    assert results == [{"name": "Snapshots", "description": "Volume snapshots.", "pricing_policy": [], "url": None}]
    assert any("is not JSON" in record.getMessage() for record in caplog.records)


async def test_skips_incomplete_gpu_cards(crawl_page: CrawlPage) -> None:
    cards = "".join(
        f'<div data-card=""><article><a href="/ai/{slug}">{content}</a></article></div>'
        for slug, content in (
            ("x", "<p>No title</p>"),
            ("y", "<h3>No description</h3>"),
            ("t4", "<h3>T4</h3><p>GPU</p>"),
        )
    )

    results = await crawl_page(CivoCrawler(), ld_page(CivoCrawler.AI_URL, offers(), body=cards))

    assert results == [{"name": "T4", "description": "GPU", "pricing_policy": [], "url": "https://www.civo.com/ai/t4"}]


async def test_skips_incomplete_pricing_entries(crawl_page: CrawlPage) -> None:
    entries = "".join(
        f'<a class="pricing-nav-item" href="{anchor}">{content}</a>'
        for anchor, content in (
            ("#a", "<p>No title</p>"),
            ("#b", "<h4>No description</h4>"),
            ("#c", "<h4>C</h4><p>D</p>"),
        )
    )

    results = await crawl_page(
        CivoCrawler(), page(CivoCrawler.PRICING_URL, f'<aside class="pricing-nav">{entries}</aside>')
    )

    assert results == [{"name": "C", "description": "D", "pricing_policy": [], "url": "https://www.civo.com/pricing#c"}]


@pytest.mark.parametrize(
    "response",
    [
        ld_page(CivoCrawler.catalogue_url, json.dumps({"@type": "Organization", "name": "Civo"})),
        page(CivoCrawler.PRICING_URL, '<aside class="pricing-nav"><a class="pricing-nav-item" href="#volumes">V</a>'),
    ],
    ids=["hub", "pricing"],
)
async def test_page_without_products_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, response: Response
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(EmptyCatalogueError):
        await crawl_page(CivoCrawler(), response)

    assert any(
        record.levelno == logging.ERROR and "holds no product" in record.getMessage() for record in caplog.records
    )
