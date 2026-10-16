from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.aruba.crawler import ArubaCloudCrawler
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
MENU_LINK = '<a class="nav-link" href="{href}"><span><strong>{name}</strong></span>{description}</a>'
PRICING_CARD = '<div class="card"><div class="card-body">{heading}{body}</div></div>'


NETWORK_URL = "https://www.arubacloud.com/public-cloud/network/"


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = ArubaCloudCrawler()

    assert crawler.name == "aruba"
    assert ArubaCloudCrawler.catalogue_url == "https://www.arubacloud.com/"
    assert ArubaCloudCrawler.complement_urls == ("https://www.arubacloud.com/pricing",)
    assert ArubaCloudCrawler.name_prefixes == ("Aruba Cloud ", "Aruba ")
    assert crawler.allowed_domains == {"www.arubacloud.com"}


async def test_extracts_the_menu_products(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(ArubaCloudCrawler(), make_response(ArubaCloudCrawler.catalogue_url, "aruba_home.html"))

    assert names(results) == [
        "Dedicated Servers",
        "VPS - Virtual Private Server",
        "Smart Storage",
        "Cloud Backup",
        "Aruba Managed Kubernetes",
        "Hyper Hosting",
        "AI Tools",
    ]
    assert results[5] == {
        "name": "Hyper Hosting",
        "description": "Cloud Hosting for high-traffic websites and apps.",
        "pricing_policy": [],
        "url": "https://hosting.aruba.it/en/web-hosting/cloud-hosting/",
    }


@pytest.mark.parametrize("excluded", ["Sovereign Cloud", "Private Cloud", "Database as a Service"])
async def test_menu_solutions_and_links_without_description_are_skipped(
    make_response: MakeResponse, crawl_page: CrawlPage, excluded: str
) -> None:
    results = await crawl_page(ArubaCloudCrawler(), make_response(ArubaCloudCrawler.catalogue_url, "aruba_home.html"))

    assert excluded not in names(results)


async def test_pricing_cards_complete_the_menu(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = ArubaCloudCrawler()
    await crawl_page(crawler, make_response(ArubaCloudCrawler.catalogue_url, "aruba_home.html"))

    results = await crawl_page(crawler, make_response(ArubaCloudCrawler.PRICING_URL, "aruba_pricing.html"))

    assert results == [
        {
            "name": "Database as a Service (DBaaS)",
            "description": "Services for fast and secure management of the major relational databases (MySQL, "
            "Microsoft SQL Server).",
            "pricing_policy": [],
            "url": "https://www.arubacloud.com/pricing/public-cloud/database-as-a-service",
        },
        {
            "name": "Domains and DNS",
            "description": "Register your domain on Aruba Cloud and see the registration and transfer pricing. You "
            "also have access to additional services such as DNS and Whois Privacy.",
            "pricing_policy": [],
            "url": "https://www.arubacloud.com/pricing/domains-and-DNS/domains-and-DNS",
        },
    ]


async def test_aliased_pricing_cards_are_renamed(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(ArubaCloudCrawler(), make_response(ArubaCloudCrawler.PRICING_URL, "aruba_pricing.html"))

    assert names(results) == [
        "Dedicated Servers",
        "VPS - Virtual Private Server",
        "Database as a Service (DBaaS)",
        "AI Tools",
        "Domains and DNS",
    ]


@pytest.mark.parametrize(
    "path",
    ["https://www.arubacloud.com/pricing", "https://www.arubacloud.com/pricing/"],
)
async def test_pricing_cards_without_heading_link_or_description(crawl_page: CrawlPage, path: str) -> None:
    content = PRICING_CARD.format(heading="", body="<p>No heading</p>")
    content += PRICING_CARD.format(heading="<div><h3>Nested heading</h3></div>", body="<p>Not a product card</p>")
    content += PRICING_CARD.format(heading="<h3>No description</h3>", body="")
    content += PRICING_CARD.format(heading="<h3>Cloud Monitoring</h3>", body="<p>A monitoring system.</p>")

    results = await crawl_page(ArubaCloudCrawler(), page(path, f"<section>{content}</section>"))

    assert results == [
        {"name": "Cloud Monitoring", "description": "A monitoring system.", "pricing_policy": [], "url": None}
    ]


async def test_menu_link_without_name_is_skipped(crawl_page: CrawlPage) -> None:
    content = '<a class="nav-link" href="/storage/"><span class="description">No name</span></a>'
    content += MENU_LINK.format(href="/vps/", name="VPS", description='<span class="description">Servers.</span>')

    results = await crawl_page(ArubaCloudCrawler(), page(ArubaCloudCrawler.catalogue_url, content))

    assert names(results) == ["VPS"]


@pytest.mark.parametrize(
    ("first", "second"),
    [("Aruba Block Storage", "Block Storage"), ("Aruba Cloud Object Storage", "Object Storage")],
)
async def test_brand_prefixes_are_ignored(crawl_page: CrawlPage, first: str, second: str) -> None:
    content = "".join(
        MENU_LINK.format(href=f"/{index}/", name=name, description='<span class="description">Storage.</span>')
        for index, name in enumerate((first, second))
    )

    results = await crawl_page(ArubaCloudCrawler(), page(ArubaCloudCrawler.catalogue_url, content))

    assert names(results) == [first]


async def test_page_without_menu_is_an_error(crawl_page: CrawlPage) -> None:
    content = MENU_LINK.format(href="/vps/", name="VPS", description="")

    with pytest.raises(EmptyCatalogueError):
        await crawl_page(ArubaCloudCrawler(), page(ArubaCloudCrawler.catalogue_url, content))


async def test_menu_entries_described_in_italian_are_read_from_their_page(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = ArubaCloudCrawler()

    results = await crawl_page(crawler, make_response(ArubaCloudCrawler.catalogue_url, "aruba_home.html"))

    assert "Network Services" not in names(results)
    assert [(request.url, request.meta) for request in results if isinstance(request, Request)] == [
        (NETWORK_URL, {ArubaCloudCrawler.PRODUCT_PAGE: NETWORK_URL, ArubaCloudCrawler.PRODUCT_NAME: "Network Services"})
    ]
    assert isinstance(results[-1], Request)
    assert crawler.untranslated == []


async def test_product_page_gives_the_english_description(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(NETWORK_URL, "aruba_product_page.html")
    response.meta.update(
        {ArubaCloudCrawler.PRODUCT_PAGE: NETWORK_URL, ArubaCloudCrawler.PRODUCT_NAME: "Network Services"}
    )

    results = await crawl_page(ArubaCloudCrawler(), response)

    assert results == [
        {
            "name": "Network Services",
            "description": "Discover the Aruba Cloud network ecosystem. Connect Cloud Servers, Kubernetes, and DBaaS "
            "in secure, scalable architectures via VPC, Peering, and VPN.",
            "pricing_policy": [],
            "url": NETWORK_URL,
        }
    ]


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (
            '<meta name="description" content="Private Cloud powered by Vates.&lt;br/&gt;&lt;br/&gt;">',
            ["Private Cloud powered by Vates."],
        ),
        ("", []),
    ],
    ids=["html tags", "no description"],
)
async def test_product_page_descriptions(crawl_page: CrawlPage, head: str, expected: List[str]) -> None:
    url = "https://www.arubacloud.com/private-and-hybrid-cloud/vates-open-source/"
    meta: Dict[str, JsonValue] = {ArubaCloudCrawler.PRODUCT_PAGE: url, ArubaCloudCrawler.PRODUCT_NAME: "Vates VMS"}

    results = await crawl_page(ArubaCloudCrawler(), page(url, f"<html><head>{head}</head><body></body></html>", meta))

    assert [result["description"] for result in results if isinstance(result, dict)] == expected


@pytest.mark.parametrize(
    ("description", "requested"),
    [
        ("Cloud privato Vates, open source e sviluppato in Europa.", True),
        ("Open source private cloud, developed in Europe (e-mail support).", False),
    ],
    ids=["italian", "english"],
)
async def test_italian_menu_descriptions_are_detected(crawl_page: CrawlPage, description: str, requested: bool) -> None:
    content = MENU_LINK.format(
        href="/vates/", name="Vates VMS", description=f'<span class="description">{description}</span>'
    )
    content += MENU_LINK.format(href="/vps/", name="VPS", description='<span class="description">Servers.</span>')

    results = await crawl_page(ArubaCloudCrawler(), page(ArubaCloudCrawler.catalogue_url, content))

    assert ("Vates VMS" not in names(results)) is requested
    assert len([result for result in results if isinstance(result, Request)]) == int(requested)


async def test_untranslated_pages_already_streamed_are_not_requested(crawl_page: CrawlPage) -> None:
    crawler = ArubaCloudCrawler()
    crawler.seen_urls.add("arubacloud.com/vates")
    content = MENU_LINK.format(
        href="/vates/", name="Vates VMS", description='<span class="description">Cloud privato e sviluppato.</span>'
    )
    content += MENU_LINK.format(href="/vps/", name="VPS", description='<span class="description">Servers.</span>')

    results = await crawl_page(crawler, page(ArubaCloudCrawler.catalogue_url, content))

    assert results == [
        {"name": "VPS", "description": "Servers.", "pricing_policy": [], "url": "https://www.arubacloud.com/vps/"}
    ]
