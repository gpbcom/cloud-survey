from __future__ import annotations

import logging
from typing import Awaitable, Callable, Dict, List, Tuple, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.combell.crawler import CombellCrawler
from crawler.exception import CatalogueFormatError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
SITE = "https://www.combell.com/en/"
OPENSTACK_URL = "https://www.combell.com/en/openstack-cloud"


def page(url: str, content: str) -> Response:
    return Response(url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def requested(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Tuple[str, JsonValue]]:
    return [
        (result.url, result.meta.get(CombellCrawler.PRODUCT_NAME)) for result in results if isinstance(result, Request)
    ]


def categories(results: List[Union[Dict[str, JsonValue], Request]]) -> Dict[str, JsonValue]:
    return {
        str(result.meta.get(CombellCrawler.PRODUCT_NAME)): result.meta.get(BaseCloudCrawler.PRODUCT_CATEGORIES)
        for result in results
        if isinstance(result, Request)
    }


def test_configuration() -> None:
    crawler = CombellCrawler()

    assert crawler.name == "combell"
    assert CombellCrawler.catalogue_url == "https://www.combell.com/en/"
    assert CombellCrawler.complement_urls == ("https://www.combell.com/en/managed-services",)
    assert crawler.allowed_domains == {"www.combell.com"}


async def test_menu_requests_the_product_pages(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(CombellCrawler(), make_response(CombellCrawler.catalogue_url, "combell_home.html"))

    assert requested(results) == [
        (f"{SITE}domain-names/registering-a-domain-name", "Domain name registration"),
        (f"{SITE}ssl-certificates", "SSL certificates"),
        (f"{SITE}hosting/web-hosting", "Web hosting"),
        (f"{SITE}hosting/dedicated-webhosting", "Dedicated web hosting server"),
        (f"{SITE}microsoft-365", "Microsoft 365"),
        (f"{SITE}cloud-server", "Cloud servers"),
        (f"{SITE}private-cloud-server", "Private cloud"),
        (f"{SITE}managed-kubernetes", "Managed Kubernetes"),
        (OPENSTACK_URL, "OpenStack"),
        (f"{SITE}managed-cloud", "Managed cloud"),
    ]
    assert isinstance(results[0], Request)
    assert (results[0].priority, results[0].meta[CombellCrawler.PRODUCT_PAGE]) == (
        0,
        f"{SITE}domain-names/registering-a-domain-name",
    )


async def test_menu_requests_carry_their_menu_entries(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(CombellCrawler(), make_response(CombellCrawler.catalogue_url, "combell_home.html"))

    found = categories(results)
    assert found["SSL certificates"] == ["Domains"]
    assert found["Microsoft 365"] == ["E-mail"]
    assert found["OpenStack"] == ["Servers"]
    assert found["Dedicated web hosting server"] == ["Hosting", "Servers"]
    assert found["Managed Kubernetes"] == ["Servers", "Managed Services"]


@pytest.mark.parametrize(
    "excluded",
    [
        "domain-names",
        "domain-names/prices",
        "business-name-generator",
        "hosting",
        "managed-services#solutions",
        "technology",
        "reseller-hosting",
        "affiliate",
    ],
)
async def test_menu_non_products_are_skipped(make_response: MakeResponse, crawl_page: CrawlPage, excluded: str) -> None:
    results = await crawl_page(CombellCrawler(), make_response(CombellCrawler.catalogue_url, "combell_home.html"))

    assert f"{SITE}{excluded}" not in [url for url, _ in requested(results)]


async def test_solutions_request_the_product_pages(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(CombellCrawler.MANAGED_SERVICES_URL, "combell_managed_services.html")

    results = await crawl_page(CombellCrawler(), response)

    assert requested(results) == [
        (f"{SITE}managed-cloud", "Managed cloud"),
        (f"{SITE}multi-data-center-service", "Multi-data centre"),
        (f"{SITE}dedicated-connectivity-vpn", "Dedicated connectivity"),
        (f"{SITE}cloud-storage", "Cloud storage"),
        (f"{SITE}autoscaling-scale-up-and-down-flexibly", "Autoscaling"),
        (f"{SITE}ai-infrastructure", "AI infrastructure"),
        (f"{SITE}managed-kubernetes", "Managed Kubernetes"),
        (f"{SITE}gpu-as-a-service", "GPU as a Service"),
        (f"{SITE}managed-odoo-hosting", "Managed Odoo"),
        (f"{SITE}managed-container-services", "Managed container services"),
    ]
    found = categories(results)
    assert found["Managed cloud"] == ["Cloud & infrastructure"]
    assert found["Managed Kubernetes"] == ["AI, Containers & Platforms"]


async def test_product_pages_already_streamed_are_not_requested(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = CombellCrawler()
    product = make_response(f"{SITE}managed-cloud", "combell_product_page.html")
    product.meta.update({CombellCrawler.PRODUCT_PAGE: product.url, CombellCrawler.PRODUCT_NAME: "Managed cloud"})
    await crawl_page(crawler, product)

    results = await crawl_page(crawler, make_response(CombellCrawler.catalogue_url, "combell_home.html"))

    assert f"{SITE}managed-cloud" not in [url for url, _ in requested(results)]


async def test_links_keep_their_most_descriptive_label(crawl_page: CrawlPage) -> None:
    content = '<a class="dropdown__link" id="sel-nav-vps" href="/en/servers/vps"> </a>'
    content += '<a class="dropdown__link" id="sel-nav-colocation" href="/en/colocation"><b>Colocation</b></a>'
    content += '<a class="dropdown__link" id="sel-nav-k8s" href="/en/k8s">Scaling <small>with Kubernetes</small></a>'
    content += '<a class="dropdown__link" id="sel-nav-managed-k8s" href="/en/k8s/">Managed Kubernetes</a>'
    content += '<a class="dropdown__link" id="sel-nav-mob-k8s" href="/en/k8s">Kubernetes <small>New</small></a>'

    results = await crawl_page(CombellCrawler(), page(CombellCrawler.catalogue_url, content))

    assert requested(results) == [(f"{SITE}colocation", "Colocation"), (f"{SITE}k8s", "Managed Kubernetes")]


@pytest.mark.parametrize(
    ("url", "content", "selector"),
    [
        (CombellCrawler.catalogue_url, '<a class="dropdown__link" href="/en/vps">VPS</a>', "dropdown__link"),
        (CombellCrawler.MANAGED_SERVICES_URL, '<div id="faq"><a href="/en/vps">VPS</a></div>', "#solutions"),
    ],
)
async def test_page_without_product_links_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, url: str, content: str, selector: str
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(CatalogueFormatError, match=selector):
        await crawl_page(CombellCrawler(), page(url, content))

    assert "has no product links" in caplog.text


async def test_product_page(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(OPENSTACK_URL, "combell_product_page.html")
    response.meta.update({CombellCrawler.PRODUCT_PAGE: OPENSTACK_URL, CombellCrawler.PRODUCT_NAME: "OpenStack"})

    results = await crawl_page(CombellCrawler(), response)

    assert results == [
        {
            "name": "OpenStack",
            "description": "Quickly build your own cloud environment with OpenStack from Combell. Launch servers in "
            "minutes, with full control, European data centres and flexible pricing.",
            "pricing_policy": [],
            "url": OPENSTACK_URL,
        }
    ]


async def test_product_page_is_filed_under_its_categories(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(OPENSTACK_URL, "combell_product_page.html")
    response.meta.update(
        {
            CombellCrawler.PRODUCT_PAGE: OPENSTACK_URL,
            CombellCrawler.PRODUCT_NAME: "OpenStack",
            BaseCloudCrawler.PRODUCT_CATEGORIES: ["Servers"],
        }
    )

    results = await crawl_page(CombellCrawler(), response)

    assert [(result["name"], result["catalogue_categories"]) for result in results if isinstance(result, dict)] == [
        ("OpenStack", ["Servers"])
    ]


@pytest.mark.parametrize(
    "path", ["performance-optimisation", "digital-collaboration", "tailored-security", "avoid-downtime", "vps?x=1"]
)
async def test_business_needs_and_query_links_are_skipped(crawl_page: CrawlPage, path: str) -> None:
    content = f'<a class="dropdown__link" id="sel-nav-need" href="/en/{path}">Need</a>'
    content += '<a class="dropdown__link" id="sel-nav-it-outsourcing" href="/en/it-outsourcing">IT outsourcing</a>'

    results = await crawl_page(CombellCrawler(), page(CombellCrawler.catalogue_url, content))

    assert requested(results) == [(f"{SITE}it-outsourcing", "IT outsourcing")]
