from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.metrics.peeringdb.crawler import PeeringdbCrawler
from models.cloud.enums import CloudProvider
from models.drivers.collectors.collector_catalog import CollectorCatalog
from models.drivers.facts.network_fact import NetworkFact

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MetricPage = Callable[[str, str, Dict[str, JsonValue]], Response]


async def test_every_network_in_one_request(metric_catalog: CollectorCatalog, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(metric_catalog.peeringdb_key_env, raising=False)

    (request,) = [request async for request in PeeringdbCrawler(metric_catalog).start_requests()]

    asns = sorted({asn for entry in metric_catalog.entries for asn in entry.asns})
    assert request.url == PeeringdbCrawler.URL.format(asns=",".join(map(str, asns)))
    assert "16509" in request.url
    assert "Authorization" not in request._session_kwargs["headers"]


async def test_the_api_key_is_sent(metric_catalog: CollectorCatalog, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(metric_catalog.peeringdb_key_env, "key-123")

    (request,) = [request async for request in PeeringdbCrawler(metric_catalog).start_requests()]

    assert request._session_kwargs["headers"]["Authorization"] == "Api-Key key-123"


async def test_a_fact_per_network_with_its_links(
    metric_catalog: CollectorCatalog, metric_page: MetricPage, crawl_page: CrawlPage
) -> None:
    page = metric_page("https://www.peeringdb.com/api/net", "peeringdb-net.json", {})

    facts = {
        fact.provider: fact
        for fact in (
            NetworkFact.model_validate(item)
            for item in await crawl_page(PeeringdbCrawler(metric_catalog), page)
            if isinstance(item, dict)
        )
    }

    assert set(facts) == {CloudProvider.AWS, CloudProvider.SCALEWAY, CloudProvider.YANDEX_CLOUD}
    assert facts[CloudProvider.SCALEWAY].asn == 12876
    assert len(facts[CloudProvider.SCALEWAY].facilities) == 12
    assert facts[CloudProvider.YANDEX_CLOUD].facilities == []
    assert len(facts[CloudProvider.AWS].exchanges) > 100
