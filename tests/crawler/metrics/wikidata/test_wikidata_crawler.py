from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Union

from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.metrics.wikidata.crawler import WikidataCrawler
from models.cloud.enums import CloudProvider
from models.drivers.collectors.collector_catalog import CollectorCatalog
from models.drivers.facts.company_fact import CompanyFact

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MetricPage = Callable[[str, str, Dict[str, JsonValue]], Response]


async def test_one_entity_document_per_item(metric_catalog: CollectorCatalog) -> None:
    requests = [request async for request in WikidataCrawler(metric_catalog).start_requests()]

    items = [entry for entry in metric_catalog.entries if entry.wikidata]
    assert [request.url for request in requests] == [WikidataCrawler.URL.format(item=entry.wikidata) for entry in items]
    assert requests[0].url == "https://www.wikidata.org/wiki/Special:EntityData/Q456157.json"
    assert [request.meta["metric_provider"] for request in requests] == [entry.provider.value for entry in items]


async def test_the_founding_date_and_the_dated_employees(
    metric_catalog: CollectorCatalog, metric_page: MetricPage, crawl_page: CrawlPage
) -> None:
    page = metric_page(
        WikidataCrawler.URL.format(item="Q568183"), "wikidata-Q568183.json", {"metric_provider": "ovh-cloud"}
    )

    facts = [
        CompanyFact.model_validate(item)
        for item in await crawl_page(WikidataCrawler(metric_catalog), page)
        if isinstance(item, dict)
    ]

    founding, staff = facts
    assert founding.provider is CloudProvider.OVH
    assert founding.inception is not None
    assert founding.inception.date().isoformat() == "1999-10-15"
    assert staff.employees == 3074
    assert staff.employees_at is not None
    assert staff.employees_at.date().isoformat() == "2025-08-31"
    assert {fact.source_url for fact in facts} == {"https://www.wikidata.org/wiki/Q568183"}


async def test_an_item_without_employees(
    metric_catalog: CollectorCatalog, metric_page: MetricPage, crawl_page: CrawlPage
) -> None:
    page = metric_page(
        WikidataCrawler.URL.format(item="Q456157"), "wikidata-Q456157.json", {"metric_provider": "amazon-web-services"}
    )

    (fact,) = await crawl_page(WikidataCrawler(metric_catalog), page)

    assert isinstance(fact, dict)
    assert (fact["provider"], fact["employees"]) == ("amazon-web-services", None)
    assert str(fact["inception"]).startswith("2006-03-01")


def test_a_date_known_to_the_year_only(metric_catalog: CollectorCatalog) -> None:
    snak: JsonValue = {"datavalue": {"value": {"time": "+1999-00-00T00:00:00Z"}}}

    assert WikidataCrawler(metric_catalog)._time(snak) == "1999-01-01T00:00:00Z"
    assert WikidataCrawler(metric_catalog)._time({"snaktype": "somevalue"}) is None
