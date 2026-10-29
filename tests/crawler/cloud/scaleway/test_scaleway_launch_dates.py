from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Awaitable, Callable, Dict, List, Optional, Tuple, Union
from unittest.mock import MagicMock

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.scaleway.crawler import ScalewayCrawler
from models.cloud.enums import DateCaveat
from models.cloud.launch.launch_catalog import LaunchCatalog
from models.cloud.products.product import CloudProduct

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]


def products(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    """Keep the products a crawler yielded (its follow-up requests left out)."""
    return [result for result in results if isinstance(result, dict)]


ITEM = (
    "<item><title><![CDATA[{title}]]></title><description><![CDATA[<p>A change.</p>]]></description>"
    "<link>https://www.scaleway.com/en/docs/changelog/#a-change</link><category><![CDATA[security]]></category>"
    "<pubDate>{date}</pubDate></item>"
)
FEED_ITEMS: Tuple[Tuple[str, str], ...] = (
    ("Secret-manager | Secret versions can be disabled", "Tue, 11 Apr 2023 00:00:00 GMT"),
    ("Secret-manager | Secret Manager is now in public beta", "Mon, 06 Mar 2023 00:00:00 GMT"),
    ("Secret-manager | A later change", "Wed, 03 Jan 2024 00:00:00 GMT"),
    ("Instances | New Ubuntu images", "Sun, 02 Jan 2022 00:00:00 GMT"),
    ("Gpu-instances | H100 GPU Instances are available", "Sun, 01 May 2022 00:00:00 GMT"),
    ("Webhosting | New control panel", "Thu, 15 Feb 2024 00:00:00 GMT"),
    ("Redistm | Redis 7 is available", "Tue, 26 Jul 2022 00:00:00 GMT"),
    ("Topics-and-events | Topics and Events is in beta", "Thu, 08 Sep 2022 00:00:00 GMT"),
    ("Apple-silicon | Mac mini M2 is available", "Mon, 02 Oct 2023 00:00:00 GMT"),
    ("A full 3-AZ Region in Milan!", "Mon, 03 Mar 2025 00:00:00 GMT"),
    ("Cockpit | An entry with a bad date", "yesterday"),
)


def page(url: str, content: str, status: int = 200) -> Response:
    return Response(url=url, content=content, status=status, reason="OK", cookies={}, headers={}, request_headers={})


def feed(*items: Tuple[str, str]) -> Response:
    entries = "".join(ITEM.format(title=title, date=date) for title, date in items)
    channel = f"<channel><title><![CDATA[Scaleway Changelog]]></title><ttl>60</ttl>{entries}</channel>"
    content = f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0">{channel}</rss>'
    return page(ScalewayCrawler.CHANGELOG_URL, content)


def catalogue(*names: str) -> Response:
    items: List[JsonValue] = [
        {"title": name, "description": "A product.", "link": {"url": None, "page": {"path": f"/{name.lower()}/"}}}
        for name in names
    ]
    blocks: List[JsonValue] = [{"__component": "blocks.generic-columns", "title": "Cloud", "items": items}]
    script = json.dumps({"props": {"pageProps": {"page": {"blocks": blocks}}}})
    content = f'<script id="__NEXT_DATA__" type="application/json">{script}</script>'
    return page(ScalewayCrawler.catalogue_url, content)


def product(name: str, url: Optional[str] = None) -> CloudProduct:
    return CloudProduct(name=name, description="A product.", url=url)


def test_launch_is_the_earliest_entry_of_each_label() -> None:
    launches = ScalewayCrawler()._changelog_launches(feed(*FEED_ITEMS))

    assert launches["Secret-manager"] == datetime(2023, 3, 6, tzinfo=UTC)
    assert launches["Instances"] == datetime(2022, 1, 2, tzinfo=UTC)
    assert "Cockpit" not in launches
    assert "A full 3-AZ Region in Milan!" not in launches
    assert len(launches) == 7


def test_a_page_without_entries_dates_nothing() -> None:
    url = ScalewayCrawler.CHANGELOG_URL

    assert ScalewayCrawler()._changelog_launches(page(url, "<html><h1>Page not found</h1></html>")) == {}


@pytest.mark.parametrize(
    ("name", "url", "label"),
    [
        ("Secret Manager", "https://www.scaleway.com/en/secret-manager/", "Secret-manager"),
        ("Scaleway Secret Manager", None, "Secret-manager"),
        ("General Purpose Instances", "https://www.scaleway.com/en/general-purpose-instances/", "Instances"),
        ("L4 GPU Instance", "https://www.scaleway.com/en/l4-gpu-instance/", "Gpu-instances"),
        ("Web Hosting", "https://www.scaleway.com/en/web-hosting/", "Webhosting"),
        ("Managed Database for Redis™", "https://www.scaleway.com/en/managed-database-for-redistm/", "Redistm"),
        ("Topics & Events", "https://www.scaleway.com/en/topics-and-events/", "Topics-and-events"),
        ("Mac mini M2", "https://www.scaleway.com/en/mac-mini-m2/", None),
        ("Secret Vault", None, None),
    ],
)
def test_products_match_the_longest_label_of_their_name_or_slug(name: str, url: Optional[str], label: str) -> None:
    crawler = ScalewayCrawler()
    labels = crawler._changelog_launches(feed(*FEED_ITEMS))

    assert crawler._changelog_label(crawler._product_names(product(name, url)), labels) == label


async def test_launch_source_qualifies_the_feed_start(dated_source: MagicMock) -> None:
    dated_source.get.return_value = feed(*FEED_ITEMS)
    crawler = ScalewayCrawler()

    assert await crawler._launch_source(product("Development Instances")) == (
        datetime(2022, 1, 2, tzinfo=UTC),
        DateCaveat.FEED_START,
    )
    assert await crawler._launch_source(product("Secret Manager")) == (
        datetime(2023, 3, 6, tzinfo=UTC),
        DateCaveat.FIRST_ANNOUNCEMENT,
    )
    assert await crawler._launch_source(product("Cockpit")) is None


async def test_crawler_looks_a_renamed_product_up_under_its_alias(
    dated_source: MagicMock, bundled_launches: MagicMock
) -> None:
    bundled_launches.return_value.launches.return_value = LaunchCatalog.model_validate(
        {"aliases": [{"crawler": "scaleway", "name": "Mac mini M2", "feed_name": "Apple-silicon"}]}
    )
    dated_source.get.return_value = feed(*FEED_ITEMS)

    launch = await ScalewayCrawler()._launch_source(product("Mac mini M2"))

    assert launch == (datetime(2023, 10, 2, tzinfo=UTC), DateCaveat.FIRST_ANNOUNCEMENT)


async def test_crawler_replaces_the_record_date_and_reads_the_feed_once(
    crawl_page: CrawlPage, dated_source: MagicMock
) -> None:
    dated_source.get.return_value = feed(*FEED_ITEMS)
    crawler = ScalewayCrawler()

    results = products(await crawl_page(crawler, catalogue("Secret Manager", "Kubernetes Kapsule", "Web Hosting")))

    assert [call.args[0] for call in dated_source.get.call_args_list] == [ScalewayCrawler.CHANGELOG_URL]
    dated = [
        (item["name"], item.get("added_at"), item.get("added_caveat")) for item in results if isinstance(item, dict)
    ]
    assert dated == [
        ("Secret Manager", "2023-03-06T00:00:00Z", "first-announcement"),
        ("Kubernetes Kapsule", None, None),
        ("Web Hosting", "2024-02-15T00:00:00Z", "first-announcement"),
    ]
    assert crawler.undated == {"Kubernetes Kapsule"}


async def test_a_record_date_is_kept_when_the_feed_does_not_name_the_product(
    crawl_page: CrawlPage, dated_source: MagicMock
) -> None:
    dated_source.get.return_value = feed(*FEED_ITEMS)
    link: JsonValue = {"url": None, "page": {"path": "/glacier/", "createdAt": "2022-04-11T10:00:00.000Z"}}
    blocks: List[JsonValue] = [
        {
            "__component": "blocks.generic-columns",
            "title": "Storage",
            "items": [{"title": "Glacier", "description": "Cold storage.", "link": link}],
        }
    ]
    script = json.dumps({"props": {"pageProps": {"page": {"blocks": blocks}}}})
    response = page(
        ScalewayCrawler.catalogue_url, f'<script id="__NEXT_DATA__" type="application/json">{script}</script>'
    )
    crawler = ScalewayCrawler()

    results = products(await crawl_page(crawler, response))

    assert results[0]["added_at"] == "2022-04-11T10:00:00Z"
    assert results[0]["added_caveat"] == "website-record"
    assert crawler.undated == set()


async def test_a_missing_feed_leaves_the_products_undated(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    crawler = ScalewayCrawler()

    results = products(await crawl_page(crawler, catalogue("Secret Manager", "Web Hosting")))

    assert [item.get("added_at") for item in results if isinstance(item, dict)] == [None, None]
    assert dated_source.get.call_count == 1
    assert crawler.undated == {"Secret Manager", "Web Hosting"}


async def test_a_new_crawl_reads_the_feed_again() -> None:
    crawler = ScalewayCrawler()
    crawler.changelog = {"Instances": datetime(2022, 1, 2, tzinfo=UTC)}

    await crawler.on_start(resuming=True)
    assert crawler.changelog is not None
    await crawler.on_start()
    assert crawler.changelog is None
