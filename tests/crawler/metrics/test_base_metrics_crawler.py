from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Awaitable, Callable, ClassVar, Dict, Iterator, List, Union
from unittest.mock import MagicMock, patch

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response
from scrapling.spiders.session import SessionManager

from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CollectorCatalogError, ParseNotImplementedError
from crawler.metrics.base import BaseMetricsCrawler, MetricFact
from crawler.metrics.catalog_loader import CollectorCatalogLoader
from models.cloud.enums import CloudProvider
from models.drivers.collectors.collector_catalog import CollectorCatalog
from models.drivers.enums import MetricSource
from models.drivers.facts.repository_fact import RepositoryFact

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
DOCUMENT = "https://api.example.com/stars"


class DummyMetricsCrawler(BaseMetricsCrawler):
    """Metrics crawler relying on every default of the base class."""

    name = "dummy-metrics"


class JsonMetricsCrawler(BaseMetricsCrawler):
    """Metrics crawler reading a JSON list of repository facts."""

    name = "json-metrics"
    source: ClassVar[MetricSource] = MetricSource.GITHUB
    catalogue_url: ClassVar[str] = DOCUMENT

    def extract_facts(self, response: Response) -> Iterator[MetricFact]:
        for entry in json.loads(response.body):
            yield RepositoryFact.model_validate(entry)


def page(content: JsonValue, meta: Dict[str, JsonValue]) -> Response:
    return Response(
        url=DOCUMENT,
        content=json.dumps(content),
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
        meta=meta,
    )


def fact(stars: int) -> JsonValue:
    return {
        "provider": "scaleway",
        "repository": "scaleway/terraform-provider-scaleway",
        "stars": stars,
        "source_url": DOCUMENT,
    }


def test_defaults(metric_catalog: CollectorCatalog) -> None:
    crawler = JsonMetricsCrawler(metric_catalog)

    assert (crawler.facts, crawler.lazy_browser, crawler.allowed_domains) == (0, True, {"api.example.com"})
    assert crawler._session_manager.default_session_id == "json-metrics-http"
    assert len(crawler.catalog.entries) >= 25


def test_the_shipped_catalogue_is_loaded_by_default(metric_catalog: CollectorCatalog) -> None:
    assert JsonMetricsCrawler().catalog == metric_catalog


def test_a_broken_catalogue_is_reported(tmp_path: Path) -> None:
    broken = tmp_path / "collectors.yaml"
    broken.write_text("user_agent: x\nentries: [{provider: nowhere}]\n", encoding="utf-8")

    with pytest.raises(CollectorCatalogError):
        CollectorCatalogLoader().load(broken)
    with pytest.raises(CollectorCatalogError):
        CollectorCatalogLoader().load(tmp_path / "missing.yaml")


def test_sessions(stealth_session_cls: MagicMock, metric_catalog: CollectorCatalog) -> None:
    manager = MagicMock(spec=SessionManager)
    crawler = JsonMetricsCrawler(metric_catalog)

    with (
        patch("crawler.metrics.base.FetcherSession", autospec=True) as http_cls,
        patch("crawler.metrics.base.CaBundle", autospec=True),
    ):
        crawler.configure_sessions(manager)

    assert [call.args[0] for call in manager.add.call_args_list] == ["json-metrics-session", "json-metrics-http"]
    http_cls.assert_called_once_with(impersonate="chrome", stealthy_headers=False, timeout=60, retries=3, retry_delay=1)


def test_requests_carry_the_provider_and_their_own_user_agent(metric_catalog: CollectorCatalog) -> None:
    crawler = JsonMetricsCrawler(metric_catalog)

    request = crawler._metric_request(DOCUMENT, crawler._headers("application/json"), CloudProvider.SCALEWAY, page=2)

    assert request.sid == "json-metrics-http"
    assert request.meta == {"page": 2, "metric_provider": "scaleway"}
    assert request._session_kwargs["headers"]["User-Agent"] == crawler.catalog.user_agent


async def test_streams_the_facts(crawl_page: CrawlPage, metric_catalog: CollectorCatalog) -> None:
    crawler = JsonMetricsCrawler(metric_catalog)

    results = await crawl_page(crawler, page([fact(3), fact(4)], {}))

    assert [item["stars"] for item in results if isinstance(item, dict)] == [3, 4]
    assert crawler.facts == 2


async def test_extraction_must_be_implemented(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, metric_catalog: CollectorCatalog
) -> None:
    with pytest.raises(ParseNotImplementedError):
        await crawl_page(DummyMetricsCrawler(metric_catalog), page([], {}))

    assert any(record.levelno == logging.ERROR for record in caplog.records)


def test_an_unknown_provider_is_ignored(metric_catalog: CollectorCatalog) -> None:
    crawler = JsonMetricsCrawler(metric_catalog)

    assert crawler._provider(page([], {"metric_provider": "nowhere"})) is None
    assert crawler._provider(page([], {"metric_provider": "civo"})) is CloudProvider.CIVO


async def test_lifecycle(caplog: pytest.LogCaptureFixture, metric_catalog: CollectorCatalog) -> None:
    caplog.set_level(logging.INFO)
    crawler = JsonMetricsCrawler(metric_catalog)
    crawler.facts = 3

    await crawler.on_start(resuming=True)
    assert crawler.facts == 3
    await crawler.on_close()
    await crawler.on_start()

    assert crawler.facts == 0
    assert "The json-metrics metrics crawl is over: 3 facts." in caplog.messages
