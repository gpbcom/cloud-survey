from __future__ import annotations

from datetime import UTC, datetime
from typing import Awaitable, Callable, Dict, List, Optional, Tuple, Union
from unittest.mock import MagicMock

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.stackit.crawler import STACKITCrawler
from models.cloud.enums import DateCaveat
from models.cloud.launch.launch_catalog import LaunchCatalog
from models.cloud.products.product import CloudProduct

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]


def products(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    """Keep the products a crawler yielded (its follow-up requests left out)."""
    return [result for result in results if isinstance(result, dict)]


NOTE = (
    '<li><article class="release-note astro-ke74tdgr"><div class="not-content release-note__top astro-ke74tdgr">'
    '<div class="release-note__badges astro-ke74tdgr"><span class="astro-badge neutral">announcement</span>'
    '<span class="astro-badge neutral">storage</span></div><div class="sl-heading-wrapper level-h2">'
    '<h2 id="note" class="release-note__title astro-ke74tdgr">{title}</h2></div>'
    '<time class="release-note__date astro-ke74tdgr" datetime="{date}T00:00:00.000Z">{date}</time></div>'
    "<p>Released on 1 January 2010, per its text.</p></article></li>"
)
NOTES: List[Tuple[str, str]] = [
    ("2026-05-21", "STACKIT File Storage now available with Snapshot Scheduling and Immutable Snapshots"),
    ("2026-02-03", "STACKIT File Storage - Stable release"),
    ("2026-01-14", "STACKIT File Storage - Beta release"),
    ("2025-12-31", "End of public preview: Dedicated Cloud Foundry on STACKIT Kubernetes Engine"),
    ("2025-11-19", "STACKIT Content Delivery Network (CDN) now available in beta"),
    ("2025-07-18", "New STACKIT Git-10 Subscription"),
    ("2025-05-08", "STACKIT MariaDB 10.6 is now available"),
    ("2025-04-25", "STACKIT RabbitMQ 4.0 is now available"),
    ("2025-04-01", "STACKIT Git is now available"),
    ("2024-09-20", "STACKIT PostgreSQL Flex \N{EN DASH} Version 16 & pgvector is now available"),
    ("2023-09-23", "STACKIT RabbitMQ 3.10 is now available"),
    ("2023-05-02", "STACKIT PostgreSQL Flex is now available"),
    ("2023-03-23", "Red Hat Enterprise Linux images are now available in region EU02"),
    ("2022-10-18", "MariaDB is now available with SSL"),
    ("2026-06-30", "Automation Service now available in Beta"),
    ("2026-01-09", "Release of the Telemetry Router documentation"),
    ("2026-04-07", "Release of the Telemetry Router Public Preview"),
    ("2021-10-13", "STACKIT Server Backup is now Beta"),
    ("not-a-date", "STACKIT Quantum is now available"),
]


def page(url: str, content: str, status: int = 200) -> Response:
    return Response(url=url, content=content, status=status, reason="OK", cookies={}, headers={}, request_headers={})


def release_notes(notes: List[Tuple[str, str]]) -> Response:
    items = "".join(NOTE.format(title=title, date=date) for date, title in notes)
    return page(STACKITCrawler.RELEASE_NOTES_URL, f'<ul class="release-note-list">{items}</ul>')


def product(name: str) -> CloudProduct:
    return CloudProduct(name=name, description="A product.", url="https://stackit.com/en/products/x/stackit-x")


def tiles(*names: str) -> Response:
    content = "".join(
        f'<article class="digits-base-tile"><a class="digits-base-tile__link" href="/en/products/x/{index}"></a>'
        f'<h3><span class="digits-tile__title-line">{name}</span></h3><p class="digits-tile__details">A product.</p>'
        "</article>"
        for index, name in enumerate(names)
    )
    return page(STACKITCrawler.catalogue_url, content)


def test_release_notes_are_read_the_earliest_first() -> None:
    notes = STACKITCrawler()._release_note_entries(release_notes(NOTES))

    assert len(notes) == len(NOTES) - 1
    assert notes[0] == (datetime(2021, 10, 13, tzinfo=UTC), "STACKIT Server Backup is now Beta")
    assert notes == sorted(notes)


@pytest.mark.parametrize(
    ("name", "launched"),
    [
        ("STACKIT File Storage", datetime(2026, 1, 14, tzinfo=UTC)),
        ("STACKIT Git", datetime(2025, 4, 1, tzinfo=UTC)),
        ("STACKIT CDN", datetime(2025, 11, 19, tzinfo=UTC)),
        ("STACKIT PostgreSQL Flex", datetime(2023, 5, 2, tzinfo=UTC)),
        ("STACKIT Automation Service", datetime(2026, 6, 30, tzinfo=UTC)),
        ("STACKIT Telemetry Router", datetime(2026, 4, 7, tzinfo=UTC)),
        ("STACKIT RabbitMQ", None),
        ("STACKIT MariaDB", None),
        ("STACKIT Cloud Foundry", None),
        ("STACKIT Red Hat Enterprise Linux", None),
        ("STACKIT Quantum", None),
        ("STACKIT Workflows", None),
    ],
)
def test_launch_is_the_earliest_note_announcing_the_product(name: str, launched: Optional[datetime]) -> None:
    crawler = STACKITCrawler()
    notes = crawler._release_note_entries(release_notes(NOTES))

    assert crawler._first_launch(notes, product(name)) == launched


def test_titles_name_the_product_without_its_brand_nor_a_version() -> None:
    mentions = STACKITCrawler()._mentions(["Git"])

    assert STACKITCrawler()._is_launch("STACKIT Git is now available", mentions)
    assert STACKITCrawler()._is_launch("Git now Generally Available (GA)", mentions)
    assert not STACKITCrawler()._is_launch("New STACKIT Git-10 Subscription is now available", mentions)
    assert not STACKITCrawler()._is_launch("STACKIT Git 2.0 is now available", mentions)
    assert not STACKITCrawler()._is_launch("STACKIT GitLab is now available", mentions)
    assert not STACKITCrawler()._is_launch("One SSH address for all STACKIT Git instances", mentions)


async def test_crawler_dates_the_products_from_one_fetch(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    dated_source.get.return_value = release_notes(NOTES)
    crawler = STACKITCrawler()

    results = products(await crawl_page(crawler, tiles("STACKIT File Storage", "STACKIT Git")))

    assert [(result["name"], result["added_at"], result["added_caveat"]) for result in results] == [
        ("STACKIT File Storage", "2026-01-14T00:00:00Z", "first-announcement"),
        ("STACKIT Git", "2025-04-01T00:00:00Z", "first-announcement"),
    ]
    assert dated_source.get.call_count == 1
    assert dated_source.get.call_args.args[0] == STACKITCrawler.RELEASE_NOTES_URL
    assert crawler.undated == set()


async def test_a_note_before_the_feed_start_may_postdate_the_launch(dated_source: MagicMock) -> None:
    dated_source.get.return_value = release_notes(NOTES)

    launch = await STACKITCrawler()._launch_source(product("STACKIT Server Backup"))

    assert launch == (datetime(2021, 10, 13, tzinfo=UTC), DateCaveat.FEED_START)


async def test_crawler_looks_a_renamed_product_up_under_its_alias(
    crawl_page: CrawlPage, dated_source: MagicMock, bundled_launches: MagicMock
) -> None:
    bundled_launches.return_value.launches.return_value = LaunchCatalog.model_validate(
        {"aliases": [{"crawler": "stackit", "name": "STACKIT Server Backup Management", "feed_name": "Server Backup"}]}
    )
    dated_source.get.return_value = release_notes(NOTES)

    results = products(await crawl_page(STACKITCrawler(), tiles("STACKIT Server Backup Management")))

    assert results[0]["added_at"] == "2021-10-13T00:00:00Z"
    assert results[0]["added_caveat"] == "feed-start"


async def test_a_product_without_launch_note_is_streamed_undated(
    crawl_page: CrawlPage, dated_source: MagicMock
) -> None:
    dated_source.get.return_value = release_notes(NOTES)
    crawler = STACKITCrawler()

    results = products(await crawl_page(crawler, tiles("STACKIT RabbitMQ")))

    assert results[0]["name"] == "STACKIT RabbitMQ"
    assert "added_at" not in results[0]
    assert crawler.undated == {"STACKIT RabbitMQ"}


@pytest.mark.parametrize(
    "served",
    [
        page(STACKITCrawler.RELEASE_NOTES_URL, "<h1>Page not found</h1><p>STACKIT Git is now available</p>"),
        page(STACKITCrawler.RELEASE_NOTES_URL, "", status=404),
    ],
)
async def test_a_missing_release_notes_page_dates_nothing(
    crawl_page: CrawlPage, dated_source: MagicMock, served: Response
) -> None:
    dated_source.get.return_value = served
    crawler = STACKITCrawler()

    results = products(await crawl_page(crawler, tiles("STACKIT Git", "STACKIT File Storage")))

    assert all("added_at" not in result for result in results)
    assert crawler.undated == {"STACKIT Git", "STACKIT File Storage"}
    assert dated_source.get.call_count == 1


async def test_a_new_crawl_reads_the_release_notes_again() -> None:
    crawler = STACKITCrawler()
    crawler.release_notes = [(datetime(2025, 4, 1, tzinfo=UTC), "STACKIT Git is now available")]

    await crawler.on_start(resuming=True)
    assert crawler.release_notes is not None

    await crawler.on_start()
    assert crawler.release_notes is None
