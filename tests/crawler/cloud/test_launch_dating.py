from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Awaitable, Callable, Dict, List, Union
from unittest.mock import MagicMock

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.azure.crawler import AzureCrawler
from crawler.cloud.baidu.crawler import BaiduAICloudCrawler
from crawler.cloud.base import BaseCloudCrawler
from models.cloud.enums import DateCaveat
from models.cloud.launch.launch_catalog import LaunchCatalog
from models.cloud.products.product import CloudProduct

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]


def products(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    """Keep the products a crawler yielded (its follow-up requests left out)."""
    return [result for result in results if isinstance(result, dict)]


CARD = (
    '<div class="card"><div class="card-body"><h3>{name}</h3>'
    "<div data-oc-token-text><p>A product.</p></div></div></div>"
)
SOURCE = "https://azure.microsoft.com/en-us/blog/announcing-a-product/"


def page(url: str, content: str, status: int = 200) -> Response:
    return Response(url=url, content=content, status=status, reason="OK", cookies={}, headers={}, request_headers={})


def catalogue(*names: str) -> Response:
    cards = "".join(CARD.format(name=name) for name in names)
    return page(AzureCrawler.catalogue_url, f'<h2>Compute</h2><div class="content-card-list">{cards}</div>')


def curate(loader: MagicMock, *launches: Dict[str, JsonValue]) -> None:
    loader.return_value.launches.return_value = LaunchCatalog.model_validate({"launches": list(launches)})


def updates(month: str) -> Response:
    return page(AzureCrawler.UPDATES_URL, json.dumps({"value": [{"previewAvailabilityDate": month}]}))


async def test_a_curated_launch_wins_over_the_dated_source(
    crawl_page: CrawlPage, dated_source: MagicMock, bundled_launches: MagicMock
) -> None:
    launch: Dict[str, JsonValue] = {"crawler": "azure", "name": "Virtual Machines", "launched": "2012-06-07"}
    curate(bundled_launches, {**launch, "source": SOURCE})
    dated_source.get.return_value = updates("2014-01")

    results = products(await crawl_page(AzureCrawler(), catalogue("Azure Virtual Machines")))

    assert results[0]["added_at"] == "2012-06-07T00:00:00Z"
    assert results[0]["added_caveat"] == "curated"
    dated_source.get.assert_not_called()


async def test_a_curated_year_is_marked_year_only(crawl_page: CrawlPage, bundled_launches: MagicMock) -> None:
    curate(bundled_launches, {"crawler": "azure", "name": "Azure Storage", "launched": 2010, "source": SOURCE})

    results = products(await crawl_page(AzureCrawler(), catalogue("Azure Storage")))

    assert results[0]["added_at"] == "2010-01-01T00:00:00Z"
    assert results[0]["added_caveat"] == "year-only"


async def test_a_known_gap_is_left_undated_without_being_reported(
    crawl_page: CrawlPage, dated_source: MagicMock, bundled_launches: MagicMock
) -> None:
    curate(bundled_launches, {"crawler": "azure", "name": "Azure IoT", "reason": "An umbrella page."})
    crawler = AzureCrawler()

    results = products(await crawl_page(crawler, catalogue("Azure IoT")))

    assert "added_at" not in results[0]
    assert crawler.undated == set()
    dated_source.get.assert_not_called()


async def test_curated_launches_apply_to_the_crawler_named_only(
    crawl_page: CrawlPage, bundled_launches: MagicMock
) -> None:
    curate(bundled_launches, {"crawler": "gcp", "name": "Azure Storage", "launched": "2010", "source": SOURCE})
    crawler = AzureCrawler()

    results = products(await crawl_page(crawler, catalogue("Azure Storage")))

    assert "added_at" not in results[0]
    assert crawler.undated == {"Azure Storage"}


async def test_a_fetch_failure_leaves_the_product_undated_but_streamed(
    crawl_page: CrawlPage, dated_source: MagicMock
) -> None:
    dated_source.get.side_effect = OSError("connection reset")
    crawler = AzureCrawler()

    results = products(await crawl_page(crawler, catalogue("Azure Functions", "Azure Batch")))

    assert [result["name"] for result in results] == ["Azure Functions", "Azure Batch"]
    assert crawler.undated == {"Azure Functions", "Azure Batch"}


async def test_a_duplicated_product_is_dated_once(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    dated_source.get.return_value = updates("2016-03")
    crawler = AzureCrawler()

    products(await crawl_page(crawler, catalogue("Azure Functions")))
    results = products(
        await crawl_page(crawler, page(AzureCrawler.catalogue_url + "?again", catalogue("Functions").body.decode()))
    )

    assert results == []
    assert dated_source.get.call_count == 1


async def test_a_crawler_without_dated_source_reads_nothing(dated_source: MagicMock) -> None:
    crawler = BaiduAICloudCrawler()

    assert BaiduAICloudCrawler.dates_launches is False
    assert crawler.undated == set()
    dated_source.get.assert_not_called()


async def test_a_crawler_without_dated_source_reports_its_undated_products(dated_source: MagicMock) -> None:
    crawler = BaiduAICloudCrawler()

    dated = await crawler._dated(CloudProduct(name="Qianfan Agent", description="A product."))
    listed = await crawler._dated(recorded("Object Storage"))

    assert dated.added_at is None
    assert listed.added_at == datetime(2020, 1, 1, tzinfo=UTC)
    assert crawler.undated == {"Qianfan Agent"}
    dated_source.get.assert_not_called()


async def test_the_crawl_summary_reports_the_undated_products(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    crawler = AzureCrawler()
    products(await crawl_page(crawler, catalogue("Azure Functions", "Azure Batch")))

    with caplog.at_level(logging.WARNING):
        await crawler.on_close()

    assert "2 azure products have no launch date" in caplog.text
    assert "Azure Batch, Azure Functions" in caplog.text


def recorded(name: str) -> CloudProduct:
    return CloudProduct(
        name=name,
        description="A product.",
        added_at=datetime(2020, 1, 1, tzinfo=UTC),
        added_caveat=DateCaveat.WEBSITE_RECORD,
    )


async def test_a_record_date_is_replaced_by_the_dated_source(dated_source: MagicMock) -> None:
    dated_source.get.return_value = updates("2016-03")

    dated = await AzureCrawler()._dated(recorded("Azure Functions"))

    assert dated.added_at == datetime(2016, 3, 1, tzinfo=UTC)
    assert dated.added_caveat is DateCaveat.FIRST_ANNOUNCEMENT


async def test_a_record_date_is_kept_when_the_source_has_none() -> None:
    crawler = AzureCrawler()

    dated = await crawler._dated(recorded("Azure Functions"))

    assert dated.added_at == datetime(2020, 1, 1, tzinfo=UTC)
    assert dated.added_caveat is DateCaveat.WEBSITE_RECORD
    assert crawler.undated == set()


async def test_a_first_entry_in_the_first_months_of_the_feed_may_be_older(dated_source: MagicMock) -> None:
    dated_source.get.return_value = updates("2014-01")

    results = await AzureCrawler()._dated(recorded("Azure Virtual Machines"))

    assert results.added_caveat is DateCaveat.FEED_START


def test_curated_launch_of_a_stored_name(bundled_launches: MagicMock) -> None:
    curate(
        bundled_launches, {"crawler": "azure", "name": "Virtual Machines", "launched": "2012-06", "source": SOURCE}
    )
    crawler = AzureCrawler()

    assert crawler.curated_launch("Azure Virtual Machines") == (datetime(2012, 6, 1, tzinfo=UTC), DateCaveat.CURATED)
    assert crawler.curated_launch("Azure Batch") is None
