from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Awaitable, Callable, Dict, List, Optional, Union
from unittest.mock import MagicMock

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.gcp.crawler import GoogleCloudPlatformCrawler

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]


def products(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    """Keep the products a crawler yielded (its follow-up requests left out)."""
    return [result for result in results if isinstance(result, dict)]


NOTES = "<h1>Spanner release notes</h1>" + "".join(
    f'<h2 id="{day}" data-text="{day}">{day}</h2><p>Mentions January 1, 2010 in its text.</p>'
    for day in ("June 15, 2017", "February 14, 2017", "Not a date")
)


def page(url: str, content: str, status: int = 200) -> Response:
    return Response(url=url, content=content, status=status, reason="OK", cookies={}, headers={}, request_headers={})


@pytest.mark.parametrize(
    ("url", "pages"),
    [
        (
            "https://cloud.google.com/spanner",
            [
                "https://cloud.google.com/spanner/docs/release-notes-archive",
                "https://cloud.google.com/spanner/docs/release-notes",
            ],
        ),
        (
            "https://docs.cloud.google.com/profiler/docs",
            [
                "https://cloud.google.com/profiler/docs/release-notes-archive",
                "https://cloud.google.com/profiler/docs/release-notes",
            ],
        ),
        (
            "https://cloud.google.com/security/products/access-transparency",
            [
                "https://cloud.google.com/access-transparency/docs/release-notes-archive",
                "https://cloud.google.com/access-transparency/docs/release-notes",
            ],
        ),
        (
            "https://docs.cloud.google.com/vertex-ai/docs/vector-search/overview",
            [
                "https://cloud.google.com/vertex-ai/vector-search/docs/release-notes-archive",
                "https://cloud.google.com/vertex-ai/vector-search/docs/release-notes",
            ],
        ),
        ("https://firebase.google.com/products/storage", []),
        ("https://cloud.google.com/", []),
        (None, []),
    ],
)
def test_release_notes_are_looked_up_under_the_whole_product_path(url: Optional[str], pages: List[str]) -> None:
    assert GoogleCloudPlatformCrawler()._release_notes_pages(url) == pages


def test_launch_is_the_earliest_dated_heading() -> None:
    url = "https://cloud.google.com/spanner/docs/release-notes"

    assert GoogleCloudPlatformCrawler()._earliest_note(page(url, NOTES)) == datetime(2017, 2, 14, tzinfo=UTC)
    assert GoogleCloudPlatformCrawler()._earliest_note(page(url, "<h1>Page not found</h1>")) is None


async def test_crawler_reads_the_archive_first_then_the_release_notes(
    crawl_page: CrawlPage, dated_source: MagicMock
) -> None:
    served = {"https://cloud.google.com/spanner/docs/release-notes": page("https://x", NOTES)}
    dated_source.get.side_effect = lambda url, **_: served.get(url, page(url, "", status=404))
    entry: List[JsonValue] = ["0f2b7a3c-1d2e-4f5a-8b9c-0d1e2f3a4b5c", [None, None, "/spanner"], None, None, None, None]
    entry += ["Spanner", "Cloud-native relational database."]
    data = json.dumps([[entry]])
    content = f"<script>AF_initDataCallback({{key: 'ds:1', hash: '1', data:{data}, sideChannel: {{}}}});</script>"

    crawler = GoogleCloudPlatformCrawler()
    results = products(await crawl_page(crawler, page("https://cloud.google.com/products?pds=CAE", content)))

    assert [call.args[0] for call in dated_source.get.call_args_list] == [
        "https://cloud.google.com/spanner/docs/release-notes-archive",
        "https://cloud.google.com/spanner/docs/release-notes",
    ]
    assert results[0]["added_at"] == "2017-02-14T00:00:00Z"
    assert results[0]["added_caveat"] == "first-announcement"
    assert crawler.undated == set()
