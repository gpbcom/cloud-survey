from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, ClassVar, Dict, Iterator, List, Union
from unittest.mock import MagicMock, patch

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response
from scrapling.spiders.session import SessionManager

from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import ParseNotImplementedError
from crawler.stats.base import BaseStatsCrawler
from models.cloud.enums import MarketRegion, MarketSegment
from models.stats.market_report import MarketReport

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
ARTICLE = "https://stats.example.com/articles/q2"


class DummyStatsCrawler(BaseStatsCrawler):
    """Statistics crawler relying on every default of the base class."""


class JsonStatsCrawler(BaseStatsCrawler):
    """Statistics crawler reading a JSON list of market reports."""

    name = "json-stats"
    source: ClassVar[str] = "Example Research"
    catalogue_url: ClassVar[str] = ARTICLE

    def extract_reports(self, response: Response) -> Iterator[MarketReport]:
        for entry in json.loads(response.body):
            yield MarketReport.model_validate(entry)


def report(period: str = "2026Q2", **fields: JsonValue) -> JsonValue:
    values: Dict[str, JsonValue] = {
        "period": period,
        "region": "worldwide",
        "segment": "cloud-infrastructure-services",
        "source_url": ARTICLE,
        "title": "Q2",
        "published": "2026-07-30",
    }
    values.update(fields)
    return values


def page(reports: List[JsonValue]) -> Response:
    return Response(
        url=ARTICLE, content=json.dumps(reports), status=200, reason="OK", cookies={}, headers={}, request_headers={}
    )


def test_defaults() -> None:
    crawler = JsonStatsCrawler()

    assert (BaseStatsCrawler.source, BaseStatsCrawler.lazy_browser, crawler.reports) == ("", True, {})
    assert crawler._session_manager.default_session_id == "json-stats-http"


def test_sessions(stealth_session_cls: MagicMock) -> None:
    manager = MagicMock(spec=SessionManager)
    crawler = JsonStatsCrawler()

    with patch("crawler.stats.base.FetcherSession", autospec=True) as http_cls:
        crawler.configure_sessions(manager)

    assert [call.args[0] for call in manager.add.call_args_list] == ["json-stats-session", "json-stats-http"]
    http_cls.assert_called_once_with(impersonate="chrome", timeout=60, retries=3, retry_delay=1)


async def test_streams_new_reports(crawl_page: CrawlPage) -> None:
    results = await crawl_page(JsonStatsCrawler(), page([report(market_size_bn=143.4), report("2026Q1")]))

    assert [item["period"] for item in results if isinstance(item, dict)] == ["2026Q2", "2026Q1"]


async def test_more_complete_reports_replace_the_previous_ones(crawl_page: CrawlPage) -> None:
    crawler = JsonStatsCrawler()
    await crawl_page(crawler, page([report(market_size_bn=143.4)]))

    same = await crawl_page(crawler, page([report(market_size_bn=143.4)]))
    richer = await crawl_page(
        crawler, page([report(market_size_bn=143.4, shares=[{"player": "amazon", "share_pct": 28}])])
    )

    assert same == []
    assert len(richer) == 1
    assert len(crawler.reports[("2026Q2", MarketRegion.WORLDWIDE, MarketSegment.CLOUD_INFRASTRUCTURE)].shares) == 1


async def test_articles_without_figures(crawl_page: CrawlPage) -> None:
    assert await crawl_page(JsonStatsCrawler(), page([])) == []


async def test_extraction_must_be_implemented(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(ParseNotImplementedError):
        await crawl_page(DummyStatsCrawler(), page([]))

    assert any(record.levelno == logging.ERROR for record in caplog.records)


async def test_lifecycle(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    crawler = JsonStatsCrawler()
    key = ("2026Q2", MarketRegion.WORLDWIDE, MarketSegment.CLOUD_INFRASTRUCTURE)
    crawler.reports[key] = MarketReport.model_validate(report())

    await crawler.on_start(resuming=True)
    assert len(crawler.reports) == 1
    await crawler.on_close()
    await crawler.on_start()

    assert crawler.reports == {}
    assert "The json-stats statistics crawl is over: 1 market reports." in caplog.messages
