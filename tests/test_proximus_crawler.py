from __future__ import annotations

import logging
from typing import Awaitable, Callable, Dict, List, Optional, Tuple, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.proximus.crawler import ProximusNXTCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
SITE = "https://www.proximus.be/en/"
SECTION = "companies-and-public-sector/ict-for-large-companies"
DATA_URL = f"{SITE}id_catl_data_ai/{SECTION}/data-and-ai-solutions.html"


def page(url: str, content: str) -> Response:
    return Response(url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def card(heading: str, text: Optional[str], href: Optional[str], level: int = 3) -> str:
    title = f"<h{level}>{heading}</h{level}>" if heading else ""
    paragraph = f"<p>{text}</p>" if text is not None else ""
    link = f'<a href="{href}">More info</a>' if href else ""
    return f'<div class="rs-mediabox">{title}{paragraph}{link}</div>'


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def requests_of(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Tuple[str, int]]:
    return [(result.url, result.priority) for result in results if isinstance(result, Request)]


def test_configuration() -> None:
    crawler = ProximusNXTCrawler()

    assert crawler.name == "proximus"
    assert ProximusNXTCrawler.catalogue_url == f"{SITE}id_catl_itcloud/{SECTION}/cloud-solutions.html"
    assert ProximusNXTCrawler.complement_urls == (
        f"{SITE}id_catl_itservices/{SECTION}.html",
        f"{SITE}id_catl_networks/companies-and-public-sector/network-solutions-for-large-companies.html",
        f"{SITE}id_catl_telephony/companies-and-public-sector/telephony-for-large-companies.html",
    )
    assert crawler.allowed_domains == {"www.proximus.be"}


async def test_extracts_the_cloud_cards(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        ProximusNXTCrawler(), make_response(ProximusNXTCrawler.catalogue_url, "proximus_cloud.html")
    )

    assert requests_of(results) == []
    assert names(results) == ["Hybrid cloud", "Private cloud"]
    assert results[1] == {
        "name": "Private cloud",
        "description": "Run your apps and store data in a dedicated, fully secure Belgian environment. Perfect for "
        "sensitive workloads and regulated sectors.",
        "pricing_policy": [],
        "url": f"{SITE}id_cl_privatecloud/{SECTION}/cloud-solutions/private-cloud-for-enterprises.html",
    }


@pytest.mark.parametrize(
    "excluded",
    [
        "A stronger foundation for sovereign cloud",
        "Missed our webinar on the cloud trap?",
        "Our private cloud offer has evolved",
        "Subscribe to Proximus NXT Newsroom",
        "Not sure which cloud setup best suits your business needs?",
        "Jo Leemans",
    ],
)
async def test_cloud_non_product_cards_are_skipped(
    make_response: MakeResponse, crawl_page: CrawlPage, excluded: str
) -> None:
    results = await crawl_page(
        ProximusNXTCrawler(), make_response(ProximusNXTCrawler.catalogue_url, "proximus_cloud.html")
    )

    assert excluded not in names(results)


async def test_ict_page_requests_the_categories(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(ProximusNXTCrawler(), make_response(ProximusNXTCrawler.ICT_URL, "proximus_ict.html"))

    assert requests_of(results) == [
        (ProximusNXTCrawler.catalogue_url, 0),
        (f"{SITE}id_catl_security/{SECTION}/cybersecurity.html", 0),
        (DATA_URL, 0),
        (f"{SITE}id_catl_customer_interactions/{SECTION}/customer-interactions.html", 0),
        (f"{SITE}id_catl_workplace/{SECTION}/digital-workplace.html", 0),
    ]
    assert names(results) == ["ICT Services"]


async def test_extracts_the_category_cards(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(ProximusNXTCrawler(), make_response(DATA_URL, "proximus_data.html"))

    assert names(results) == [
        "Business intelligence (BI) solutions",
        "Internet of Things (IoT)",
        "Electronic smart labels",
    ]
    assert "Enterprise AI solutions" not in names(results)


async def test_page_listing_categories_only(crawl_page: CrawlPage) -> None:
    url = f"{SITE}id_catl_telephony/companies-and-public-sector/telephony.html"
    content = card("Mobile", "Mobile plans.", "/en/id_catl_mobile/companies-and-public-sector/telephony/mobile.html")

    results = await crawl_page(ProximusNXTCrawler(), page(url, content))

    assert len(results) == 1
    assert requests_of(results) == [(f"{SITE}id_catl_mobile/companies-and-public-sector/telephony/mobile.html", 0)]


@pytest.mark.parametrize(
    "content",
    [
        "",
        card("", "No heading.", f"/en/id_cl_iot/{SECTION}/cloud-solutions/iot.html"),
        card("IoT", None, f"/en/id_cl_iot/{SECTION}/cloud-solutions/iot.html"),
        card("IoT", "No link.", None),
        card("IoT", " ", f"/en/id_cl_iot/{SECTION}/cloud-solutions/iot.html"),
        card("Legal", "Legal information.", "/en/legal.html"),
        card("Contact", "Contact us.", f"/en/id_cl_contact/{SECTION}-support/contact.html"),
    ],
    ids=["no card", "no heading", "no description", "no link", "blank description", "no page id", "other section"],
)
async def test_page_without_product_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, content: str
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(EmptyCatalogueError):
        await crawl_page(ProximusNXTCrawler(), page(ProximusNXTCrawler.catalogue_url, content))

    assert "holds no product" in caplog.text


async def test_best_card_of_a_page_is_kept(crawl_page: CrawlPage) -> None:
    href = f"/en/id_cl_iot/{SECTION}/cloud-solutions/iot.html"
    content = card("News about IoT", "News.", href, level=4) + card("IoT", "Internet of Things.", href, level=2)
    content += card("Edge", "Edge computing.", f"/en/id_cl_edge/{SECTION}/cloud-solutions/edge.html", level=4)
    content += card("IoT again", "Internet of Things.", href, level=4)
    content += card("Edge news", "News.", f"/en/id_cl_edge/{SECTION}/cloud-solutions/edge.html", level=5)

    results = await crawl_page(ProximusNXTCrawler(), page(ProximusNXTCrawler.catalogue_url, content))

    assert names(results) == ["IoT", "Edge"]


async def test_invalid_card_is_skipped(crawl_page: CrawlPage) -> None:
    content = card("x" * 201, "Too long.", f"/en/id_cl_long/{SECTION}/cloud-solutions/long.html")
    content += card("Edge", "Edge computing.", f"/en/id_cl_edge/{SECTION}/cloud-solutions/edge.html")

    results = await crawl_page(ProximusNXTCrawler(), page(ProximusNXTCrawler.catalogue_url, content))

    assert names(results) == ["Edge"]


async def test_networks_page_requests_the_categories(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    networks = f"{SITE}{{}}/companies-and-public-sector/network-solutions-for-large-companies{{}}.html"
    response = make_response(ProximusNXTCrawler.NETWORKS_URL, "proximus_networks.html")

    results = await crawl_page(ProximusNXTCrawler(), response)

    assert requests_of(results) == [
        (networks.format("id_catl_corporatenetworks", "/corporate-networks"), 0),
        (networks.format("id_catl_mobilenetworks", "/mobile-networks"), 0),
        (networks.format("id_catl_internetnetworks", "/internet"), 0),
    ]
    assert names(results) == ["Fiber"]
    assert results[-1] == {
        "name": "Fiber",
        "description": "Enjoy ultra-fast, reliable connectivity that supports digital growth and keeps your business "
        "competitive.",
        "pricing_policy": [],
        "url": networks.format("id_cl_opticalfiber", "/optical-fiber"),
    }


async def test_telephony_rate_pages_are_skipped(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    url = f"{SITE}id_catl_mobile/companies-and-public-sector/telephony-for-large-companies/mobile.html"

    results = await crawl_page(ProximusNXTCrawler(), make_response(url, "proximus_mobile.html"))

    assert names(results) == [
        "Mobile subscriptions",
        "Fleet management",
        "Outsourced fleet management",
        "Call management",
        "Leasing mobile devices",
        "Mobile Voice Recording",
        "Benefit in kind",
    ]
