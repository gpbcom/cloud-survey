from __future__ import annotations

import logging
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.deep.crawler import DEEPCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
SERVICES_URL = "https://www.deep.eu/en/accueil/services"
MANAGED_DB_URL = f"{SERVICES_URL}/cloud/managed-services/managed-db"
CARD = '<div class="card card-product"><h3>{name}</h3><p>{description}</p>{link}</div>'
MENU_LINK = '<li><a class="menu_final_link" href="{href}">{label}</a></li>'


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def cloud_page(menu: str, cards: str = "") -> Response:
    cards = cards or CARD.format(name="Sovereign Cloud", description="A sovereign Cloud.", link="")
    return page(DEEPCrawler.catalogue_url, f'<ul class="navigation-accordion">{menu}</ul>{cards}')


def service_page(head: str, body: str) -> Response:
    meta: Dict[str, JsonValue] = {DEEPCrawler.PRODUCT_PAGE: MANAGED_DB_URL, DEEPCrawler.PRODUCT_NAME: "Managed DB"}
    return page(MANAGED_DB_URL, f"<html><head>{head}</head><body>{body}</body></html>", meta)


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def requests_of(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def test_configuration() -> None:
    crawler = DEEPCrawler()

    assert crawler.name == "deep"
    assert DEEPCrawler.catalogue_url == "https://www.deep.eu/en/accueil/services/cloud"
    assert DEEPCrawler.complement_urls == ()
    assert DEEPCrawler.name_prefixes == ("DEEP ", "POST ")
    assert crawler.allowed_domains == {"www.deep.eu"}


async def test_extracts_the_cloud_product_cards(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(DEEPCrawler(), make_response(DEEPCrawler.catalogue_url, "deep_cloud.html"))

    assert names(results) == ["Trusted Cloud", "Managed Services", "Cloud consulting"]
    assert results[1] == {
        "name": "Managed Services",
        "description": "Entrust the monitoring, support, and optimization of your environments to our managed "
        "cloud and cloud management services.",
        "pricing_policy": [],
        "url": f"{SERVICES_URL}/cloud/managed-services",
        "catalogue_categories": ["Cloud", "Managed Services"],
    }


async def test_cards_carry_their_menu_categories(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(DEEPCrawler(), make_response(DEEPCrawler.catalogue_url, "deep_cloud.html"))

    assert [result.get("catalogue_categories") for result in results if isinstance(result, dict)] == [
        ["Cloud", "Solutions"],
        ["Cloud", "Managed Services"],
        ["Cloud"],
    ]


async def test_services_menu_requests_the_service_pages(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(DEEPCrawler(), make_response(DEEPCrawler.catalogue_url, "deep_cloud.html"))

    requests = requests_of(results)
    assert results[-len(requests) :] == requests
    assert [(request.url, request.meta[DEEPCrawler.PRODUCT_NAME]) for request in requests] == [
        (MANAGED_DB_URL, "Managed DB"),
        (f"{SERVICES_URL}/cloud/consulting-cloud/services-cloud-operes", "Operated Cloud services"),
        (f"{SERVICES_URL}/cybersecurite/securite-offensive-pentesting", "Offensive Security"),
        (f"{SERVICES_URL}/cybersecurite/detection-et-reponse", "Attack detection and response"),
        (f"{SERVICES_URL}/telecom/internet/hostpack", "Web host"),
    ]
    assert requests[0].meta == {
        DEEPCrawler.PRODUCT_PAGE: MANAGED_DB_URL,
        DEEPCrawler.PRODUCT_NAME: "Managed DB",
        BaseCloudCrawler.PRODUCT_CATEGORIES: ["Cloud", "Managed Services"],
    }
    assert [request.meta[BaseCloudCrawler.PRODUCT_CATEGORIES] for request in requests[1:]] == [
        ["Cloud", "Cloud Consulting", "Cloud", "Cloud Consulting"],
        ["Cybersecurity", ""],
        ["Cybersecurity", ""],
        ["Telecom", "Internet"],
    ]


async def test_menu_links_listed_in_several_groups_get_all_their_categories(crawl_page: CrawlPage) -> None:
    link = MENU_LINK.format(href="/en/accueil/services/cloud/consulting-cloud/services-cloud-operes", label="Operated")
    groups = "".join(
        f'<div class="navigation-level-2-wrapper"><div class="navigation-level-header"><span class="title">Cloud</span>'
        f'</div><ul><li class="navigation-collapse"><button class="btn-collapse">{sub_category}</button>'
        f"<ul>{link}</ul></li></ul></div>"
        for sub_category in ("Solutions", "Cloud Consulting")
    )
    crawler = DEEPCrawler()

    requests = requests_of(await crawl_page(crawler, cloud_page(groups)))
    service = page(
        requests[0].url,
        '<html><head><meta name="description" content="Operated services."></head></html>',
        requests[0].meta,
    )

    streamed = [result for result in await crawl_page(crawler, service) if isinstance(result, dict)]
    assert [result.get("catalogue_categories") for result in streamed] == [
        ["Cloud", "Solutions", "Cloud Consulting"]
    ]


@pytest.mark.parametrize(
    ("href", "label"),
    [
        ("/en/accueil/services/cybersecurite", "Our Cybersecurity offer"),
        ("/en/accueil/services/telecom/mobile/forfaits-mobiles/reengagement", "Renewal"),
        ("/en/accueil/services/telecom/reseaux/reseaux-du-futur", "Network of the future"),
        ("/en/accueil/pme/produits-et-solutions/internet", "Internet"),
        ("/en/ressources/articles-blog/cybersecurite/technical-corner", "Technical corner"),
        ("/en/accueil/services/data-et-ia/data-governance", " "),
        ("/en/accueil/services/cloud/solutions/containers-as-a-service", "Containers again"),
    ],
    ids=["category", "renewal", "network outlook", "sme page", "blog", "unnamed", "duplicate"],
)
async def test_non_service_menu_links_are_skipped(crawl_page: CrawlPage, href: str, label: str) -> None:
    menu = MENU_LINK.format(href="/en/accueil/services/cloud/solutions/containers-as-a-service", label="Containers")
    menu += MENU_LINK.format(href=href, label=label)

    requests = requests_of(await crawl_page(DEEPCrawler(), cloud_page(menu)))

    assert [request.url for request in requests] == [f"{SERVICES_URL}/cloud/solutions/containers-as-a-service"]


async def test_service_page_is_named_after_the_menu(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(MANAGED_DB_URL, "deep_service_page.html")
    response.meta.update({DEEPCrawler.PRODUCT_PAGE: MANAGED_DB_URL, DEEPCrawler.PRODUCT_NAME: "Managed DB"})

    results = await crawl_page(DEEPCrawler(), response)

    assert results == [
        {
            "name": "Managed DB",
            "description": "Entrust your databases to our experts: a fully managed 24/7 service, high-performance and "
            "secure, for simplified and worry-free IT.",
            "pricing_policy": [],
            "url": MANAGED_DB_URL,
        }
    ]


async def test_service_page_carries_the_menu_categories_of_its_request(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    response = make_response(MANAGED_DB_URL, "deep_service_page.html")
    response.meta.update(
        {
            DEEPCrawler.PRODUCT_PAGE: MANAGED_DB_URL,
            DEEPCrawler.PRODUCT_NAME: "Managed DB",
            BaseCloudCrawler.PRODUCT_CATEGORIES: ["Cloud", "Managed Services", "Cloud", ""],
        }
    )

    results = await crawl_page(DEEPCrawler(), response)

    assert [result.get("catalogue_categories") for result in results if isinstance(result, dict)] == [
        ["Cloud", "Managed Services"]
    ]


@pytest.mark.parametrize(
    ("head", "body", "expected"),
    [
        (
            '<meta name="description" content="Description en français.">',
            '<div class="jumbotron-text-wrapper"><h1>Managed DB</h1><p> </p><p>Managed databases.</p></div>',
            ["Managed databases."],
        ),
        ('<meta name="description" content="Choose the right smartphones.">', "", ["Choose the right smartphones."]),
        ("", '<div class="jumbotron-text-wrapper"><h1>Managed DB</h1></div>', []),
    ],
    ids=["introduction", "meta description", "no description"],
)
async def test_service_page_descriptions(crawl_page: CrawlPage, head: str, body: str, expected: List[str]) -> None:
    results = await crawl_page(DEEPCrawler(), service_page(head, body))

    assert [result["description"] for result in results if isinstance(result, dict)] == expected


async def test_service_pages_already_streamed_are_not_requested(crawl_page: CrawlPage) -> None:
    cards = CARD.format(
        name="Containers as a Service",
        description="A ready-to-use container environment.",
        link='<a class="stretched-link" href="/en/accueil/services/cloud/solutions/containers-as-a-service">More</a>',
    )
    menu = MENU_LINK.format(href="/en/accueil/services/cloud/solutions/containers-as-a-service", label="CaaS")

    results = await crawl_page(DEEPCrawler(), cloud_page(menu, cards))

    assert (names(results), requests_of(results)) == (["Containers as a Service"], [])


async def test_cards_without_name_or_description_are_skipped(crawl_page: CrawlPage) -> None:
    cards = '<div class="card-product"><h3>No description</h3></div><div class="card-product"><p>No name</p></div>'
    cards += CARD.format(name="x" * 201, description="Too long", link="")
    cards += CARD.format(name="FinOps", description="Optimise your Cloud costs.", link="")

    results = await crawl_page(DEEPCrawler(), cloud_page("", cards))

    assert results == [
        {"name": "FinOps", "description": "Optimise your Cloud costs.", "pricing_policy": [], "url": None}
    ]


@pytest.mark.parametrize(("first", "second"), [("DEEP Sovereign Cloud", "Sovereign Cloud"), ("POST Mail", "Mail")])
async def test_brand_prefixes_are_ignored(crawl_page: CrawlPage, first: str, second: str) -> None:
    cards = CARD.format(name=first, description="One", link="") + CARD.format(name=second, description="Two", link="")

    assert names(await crawl_page(DEEPCrawler(), cloud_page("", cards))) == [first]


async def test_page_without_cards_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    menu = MENU_LINK.format(href="/en/accueil/services/cloud/solutions/containers-as-a-service", label="Containers")

    with caplog.at_level(logging.ERROR), pytest.raises(EmptyCatalogueError):
        await crawl_page(DEEPCrawler(), page(DEEPCrawler.catalogue_url, f"<ul>{menu}</ul>"))

    assert any(
        record.levelno == logging.ERROR and "holds no product" in record.getMessage() for record in caplog.records
    )
