from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.metrics.edgar.crawler import EdgarCrawler
from models.cloud.enums import CloudProvider
from models.drivers.collectors.collector_catalog import CollectorCatalog
from models.drivers.facts.capex_fact import CapexFact

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MetricPage = Callable[[str, str, Dict[str, JsonValue]], Response]
MICROSOFT = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json"


async def test_one_request_per_filer_with_the_sec_user_agent(
    metric_catalog: CollectorCatalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(metric_catalog.sec_user_agent_env, "Research admin@example.org")

    requests = [request async for request in EdgarCrawler(metric_catalog).start_requests()]

    filers = [entry for entry in metric_catalog.entries if entry.cik]
    assert [request.url for request in requests] == [EdgarCrawler.URL.format(cik=entry.cik) for entry in filers]
    assert [request.meta["metric_provider"] for request in requests] == [entry.provider.value for entry in filers]
    assert {request._session_kwargs["headers"]["User-Agent"] for request in requests} == {"Research admin@example.org"}


async def test_without_a_contact_the_catalogue_user_agent_is_sent(
    metric_catalog: CollectorCatalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(metric_catalog.sec_user_agent_env, raising=False)

    requests = [request async for request in EdgarCrawler(metric_catalog).start_requests()]

    assert requests[0]._session_kwargs["headers"]["User-Agent"] == metric_catalog.user_agent


async def test_the_capex_facts_are_streamed_as_filed(
    metric_catalog: CollectorCatalog, metric_page: MetricPage, crawl_page: CrawlPage
) -> None:
    page = metric_page(MICROSOFT, "edgar-microsoft.json", {"metric_provider": CloudProvider.AZURE.value})

    facts = [
        CapexFact.model_validate(item)
        for item in await crawl_page(EdgarCrawler(metric_catalog), page)
        if isinstance(item, dict)
    ]

    assert {fact.provider for fact in facts} == {CloudProvider.AZURE}
    assert {fact.concept for fact in facts} == {"PaymentsToAcquirePropertyPlantAndEquipment"}
    year_to_date = [
        fact for fact in facts if (fact.start.isoformat(), fact.end.isoformat()) == ("2024-07-01", "2025-03-31")
    ]
    assert year_to_date
    assert year_to_date[0].value == 47_472_000_000, "the nine months, as filed"
    assert all(fact.form.startswith(("10-Q", "10-K")) and fact.source_url == MICROSOFT for fact in facts)


async def test_the_later_concept_is_read_too(
    metric_catalog: CollectorCatalog, metric_page: MetricPage, crawl_page: CrawlPage
) -> None:
    page = metric_page(
        EdgarCrawler.URL.format(cik="0001018724"), "edgar-amazon.json", {"metric_provider": "amazon-web-services"}
    )

    facts = [item for item in await crawl_page(EdgarCrawler(metric_catalog), page) if isinstance(item, dict)]

    assert {item["concept"] for item in facts} == {metric_catalog.capex_concepts[1]}, "Amazon files the later concept"


async def test_a_document_without_provider_gives_nothing(
    metric_catalog: CollectorCatalog, metric_page: MetricPage, crawl_page: CrawlPage
) -> None:
    assert await crawl_page(EdgarCrawler(metric_catalog), metric_page(MICROSOFT, "edgar-microsoft.json", {})) == []
