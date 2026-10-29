from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Dict, List, Optional, Sequence, Tuple
from unittest.mock import MagicMock

import pytest
from pydantic import JsonValue
from scrapling.spiders import Response

from crawler.cloud.aws.crawler import AWSCrawler
from models.cloud.enums import DateCaveat
from models.cloud.products.product import CloudProduct

Announcement = Tuple[str, str, Sequence[str]]
ANNOUNCEMENTS: Tuple[Announcement, ...] = (
    ("Amazon S3 adds a feature", "2006-07-11T20:00:00Z", ()),
    ("Introducing Amazon Cognito", "2014-07-10T08:00:00Z", ()),
    ("Amazon Cognito now supports SAML", "2014-11-06T08:00:00Z", ("amazon-cognito",)),
    ("AWS App Mesh is now generally available", "2019-03-27T17:00:00Z", ()),
    ("AWS App Mesh adds TLS", "2019-10-30T17:00:00Z", ("aws-app-mesh",)),
    ("Announcing Amazon Athena", "2016-11-30T17:00:00Z", ("amazon-athena",)),
    ("Amazon Athena adds federated queries", "2019-11-26T17:00:00Z", ("amazon-athena",)),
    ("A broken one", "yesterday", ("aws-broken",)),
)


def directory(year: int) -> str:
    items: List[JsonValue] = []
    for headline, posted, tags in ANNOUNCEMENTS:
        if not posted.startswith(str(year)) and posted != "yesterday":
            continue
        items.append(
            {
                "item": {"additionalFields": {"headline": headline, "postDateTime": posted}},
                "tags": [{"name": tag, "tagNamespaceId": "whats-new-v2#general-products"} for tag in tags],
            }
        )
    return json.dumps({"metadata": {"totalHits": len(items)}, "items": items})


async def serve(url: str, params: Optional[Dict[str, str]] = None, **_: JsonValue) -> Response:
    query = params or {}
    if query.get("page") != "0":
        return Response(url=url, content=b"", status=404, reason="", cookies={}, headers={}, request_headers={})
    year = int(query["tags.id"].rsplit("#", 1)[-1])
    return Response(
        url=url, content=directory(year), status=200, reason="OK", cookies={}, headers={}, request_headers={}
    )


@pytest.fixture
def crawler(dated_source: MagicMock) -> AWSCrawler:
    dated_source.get.side_effect = serve
    return AWSCrawler()


def product(name: str, url: str, year: Optional[int] = None) -> CloudProduct:
    added = datetime(year, 1, 1, tzinfo=UTC) if year else None
    return CloudProduct(
        name=name,
        description="A service.",
        url=url,
        added_at=added,
        added_caveat=DateCaveat.YEAR_ONLY if year else None,
    )


async def test_an_undated_product_takes_its_first_tagged_announcement(crawler: AWSCrawler) -> None:
    dated = await crawler._dated(product("Amazon Athena", "https://aws.amazon.com/athena/"))

    assert dated.added_at == datetime(2016, 11, 30, 17, tzinfo=UTC)
    assert dated.added_caveat is DateCaveat.FIRST_ANNOUNCEMENT


async def test_a_launch_year_takes_the_day_of_that_year(crawler: AWSCrawler) -> None:
    cognito = await crawler._dated(product("Amazon Cognito", "https://aws.amazon.com/cognito/", 2014))
    mesh = await crawler._dated(product("AWS App Mesh", "https://aws.amazon.com/app-mesh/", 2019))

    assert cognito.added_at == datetime(2014, 7, 10, 8, tzinfo=UTC), "tagged before 2015: the headline dates it"
    assert mesh.added_at == datetime(2019, 3, 27, 17, tzinfo=UTC), "an earlier headline beats a later tag"


async def test_a_launch_year_is_kept_out_of_its_year_or_at_the_feed_start(crawler: AWSCrawler) -> None:
    athena = await crawler._dated(product("Amazon Athena", "https://aws.amazon.com/athena/", 2015))
    s3 = await crawler._dated(product("Amazon S3", "https://aws.amazon.com/s3/", 2006))

    assert athena.added_at == datetime(2015, 1, 1, tzinfo=UTC)
    assert athena.added_caveat is DateCaveat.YEAR_ONLY
    assert s3.added_at == datetime(2006, 1, 1, tzinfo=UTC), "the first months of the feed are sparse"


async def test_what_s_new_is_read_once_year_by_year(crawler: AWSCrawler, dated_source: MagicMock) -> None:
    await crawler._dated(product("Amazon Athena", "https://aws.amazon.com/athena/"))
    await crawler._dated(product("Amazon Cognito", "https://aws.amazon.com/cognito/"))

    years = {call.kwargs["params"]["tags.id"] for call in dated_source.get.call_args_list}
    assert "whats-new-v2#year#2004" in years
    assert f"whats-new-v2#year#{datetime.now(UTC).year}" in years
    assert len(years) == datetime.now(UTC).year - 2004 + 1
    assert crawler.whats_new is not None
    assert "aws-broken" not in crawler.whats_new
