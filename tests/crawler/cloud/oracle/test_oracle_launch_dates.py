from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Awaitable, Callable, Dict, List, Optional, Tuple, Union
from unittest.mock import MagicMock

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.oracle.crawler import OracleCloudCrawler
from models.cloud.enums import DateCaveat

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]


def products(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    """Keep the products a crawler yielded (its follow-up requests left out)."""
    return [result for result in results if isinstance(result, dict)]


SERVICES_URL = "https://docs.oracle.com/en-us/iaas/releasenotes/services.json"
NOTES_URL = "https://docs.oracle.com/en-us/iaas/releasenotes/services/{}/index.htm"
SERVICES = json.dumps(
    [
        {"s": "audit", "t": "Audit", "id": "1868"},
        {"s": "container-registry", "t": "Container Registry", "id": "1898"},
        {"s": "nosql-database-cloud", "t": "NoSQL Database Cloud", "id": "1945"},
        {"s": "compute", "t": "Compute", "id": "1894"},
    ]
)
NOTE = (
    '<article class="vl-releasenote uk-card" role="article"><h2><a href="/iaas/releasenotes/changes/1/index.htm">'
    'Note</a></h2><div class="rnsummarymeta"><ul class="vl-rndata"><li><strong>Release Date: </strong>'
    '<span class="vl-relnotedate">{}</span></li></ul></div><div class="rnsummarydesc"><p>Mentions January 1, 2010.'
    "</p></div></article>"
)


def notes(title: str, *days: str) -> str:
    articles = "".join(NOTE.format(day) for day in days)
    return (
        f'<html><body><article class="releasenotes" id="rn-x"><h1 id="rntitle">{title}</h1>'
        f"<p>{len(days)} Release Notes</p>{articles}</article></body></html>"
    )


def page(url: str, content: str, status: int = 200) -> Response:
    return Response(url=url, content=content, status=status, reason="OK", cookies={}, headers={}, request_headers={})


def product_page(url: str, name: str) -> Response:
    meta: Dict[str, JsonValue] = {OracleCloudCrawler.PRODUCT_PAGE: url, OracleCloudCrawler.PRODUCT_NAME: name}
    content = f'<html><head><meta name="Description" content="{name} service."></head><body></body></html>'
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta
    )


def serve(dated_source: MagicMock, served: Dict[str, str]) -> None:
    dated_source.get.side_effect = lambda url, **_: (
        page(url, served[url]) if url in served else page(url, notes("All Services", "October 20, 2026"))
    )


def json_services() -> List[Tuple[str, str]]:
    return [(service["s"], service["t"]) for service in json.loads(SERVICES)]


def test_configuration() -> None:
    assert OracleCloudCrawler.dates_launches is True
    assert OracleCloudCrawler.launch_feed_start == datetime(2017, 6, 1, tzinfo=UTC)
    assert OracleCloudCrawler.RELEASE_NOTES_SERVICES_URL == SERVICES_URL
    assert OracleCloudCrawler.RELEASE_NOTES_URL.format(slug="audit") == NOTES_URL.format("audit")


def test_launch_is_the_earliest_release_date() -> None:
    crawler = OracleCloudCrawler()
    content = notes("Audit", "October 19, 2017", "Not a date", "February 21, 2017", "November 28, 2018")

    assert crawler._earliest_note(page(NOTES_URL.format("audit"), content), "Audit") == datetime(
        2017, 2, 21, tzinfo=UTC
    )
    assert crawler._earliest_note(page(NOTES_URL.format("audit"), notes("Audit")), "Audit") is None


def test_the_all_services_page_of_an_unknown_slug_is_ignored() -> None:
    crawler = OracleCloudCrawler()
    soft_404 = page(NOTES_URL.format("unknown"), notes("All Services", "October 20, 2026"))

    assert crawler._earliest_note(soft_404, "Audit") is None
    assert crawler._earliest_note(page(NOTES_URL.format("audit"), "<html><body></body></html>"), "Audit") is None


@pytest.mark.parametrize(
    ("name", "service"),
    [
        ("Audit", ("audit", "Audit")),
        ("OCI Audit", ("audit", "Audit")),
        ("Oracle Cloud Infrastructure Audit", ("audit", "Audit")),
        ("Registry", ("container-registry", "Container Registry")),
        ("NoSQL", ("nosql-database-cloud", "NoSQL Database Cloud")),
        ("Virtual Machines", ("compute", "Compute")),
        ("FastConnect", None),
    ],
)
def test_products_are_matched_by_title_or_alias(name: str, service: Optional[Tuple[str, str]]) -> None:
    crawler = OracleCloudCrawler()
    services = {crawler._name_key(title): (slug, title) for slug, title in json_services()}

    assert crawler._release_notes_service(name, services) == service


def test_launch_dates_catalogue_alias_is_tried_first() -> None:
    crawler = OracleCloudCrawler()
    crawler.launch_aliases = {crawler._name_key("Monitoring Probes"): "Audit"}
    services = {crawler._name_key(title): (slug, title) for slug, title in json_services()}

    assert crawler._release_notes_service("Monitoring Probes", services) == ("audit", "Audit")


async def test_product_is_dated_from_its_release_notes(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    serve(
        dated_source,
        {
            SERVICES_URL: SERVICES,
            NOTES_URL.format("container-registry"): notes("Container Registry", "May 07, 2018", "June 01, 2020"),
        },
    )
    crawler = OracleCloudCrawler()

    results = products(await crawl_page(crawler, product_page("https://www.oracle.com/cloud/registry/", "Registry")))

    assert results[0]["added_at"] == "2018-05-07T00:00:00Z"
    assert results[0]["added_caveat"] == DateCaveat.FIRST_ANNOUNCEMENT
    assert crawler.undated == set()


async def test_notes_of_the_first_months_are_feed_start(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    serve(dated_source, {SERVICES_URL: SERVICES, NOTES_URL.format("audit"): notes("Audit", "February 21, 2017")})

    results = products(
        await crawl_page(OracleCloudCrawler(), product_page("https://www.oracle.com/cloud/audit/", "Audit"))
    )

    assert results[0]["added_at"] == "2017-02-21T00:00:00Z"
    assert results[0]["added_caveat"] == DateCaveat.FEED_START


async def test_product_without_release_notes_is_streamed_undated(
    crawl_page: CrawlPage, dated_source: MagicMock
) -> None:
    serve(dated_source, {SERVICES_URL: SERVICES})
    crawler = OracleCloudCrawler()

    results = products(
        await crawl_page(crawler, product_page("https://www.oracle.com/cloud/fastconnect/", "FastConnect"))
    )

    assert results[0]["name"] == "FastConnect"
    assert results[0].get("added_at") is None
    assert crawler.undated == {"FastConnect"}


async def test_soft_404_leaves_the_product_undated(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    serve(dated_source, {SERVICES_URL: SERVICES})
    crawler = OracleCloudCrawler()

    results = products(await crawl_page(crawler, product_page("https://www.oracle.com/cloud/audit/", "Audit")))

    assert [call.args[0] for call in dated_source.get.call_args_list] == [SERVICES_URL, NOTES_URL.format("audit")]
    assert results[0].get("added_at") is None
    assert crawler.undated == {"Audit"}


async def test_services_list_is_fetched_once_per_crawl(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    serve(
        dated_source,
        {
            SERVICES_URL: SERVICES,
            NOTES_URL.format("audit"): notes("Audit", "October 19, 2017"),
            NOTES_URL.format("compute"): notes("Compute", "January 04, 2017"),
        },
    )
    crawler = OracleCloudCrawler()

    products(await crawl_page(crawler, product_page("https://www.oracle.com/cloud/audit/", "Audit")))
    products(await crawl_page(crawler, product_page("https://www.oracle.com/cloud/compute/", "Virtual Machines")))

    assert [call.args[0] for call in dated_source.get.call_args_list] == [
        SERVICES_URL,
        NOTES_URL.format("audit"),
        NOTES_URL.format("compute"),
    ]


async def test_services_list_is_read_again_by_a_new_crawl(dated_source: MagicMock) -> None:
    serve(dated_source, {SERVICES_URL: SERVICES})
    crawler = OracleCloudCrawler()
    await crawler._release_notes_index()

    await crawler.on_start(resuming=True)
    assert crawler.release_notes_services is not None
    await crawler.on_start()
    assert crawler.release_notes_services is None


async def test_missing_services_list_dates_nothing(dated_source: MagicMock) -> None:
    crawler = OracleCloudCrawler()
    product_name = "Audit"

    assert await crawler._release_notes_index() == {}
    assert crawler._release_notes_service(product_name, crawler.release_notes_services or {}) is None
    assert dated_source.get.call_count == 1
