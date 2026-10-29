from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Awaitable, Callable, Dict, List, Union
from unittest.mock import MagicMock

from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.azure.crawler import AzureCrawler
from crawler.cloud.base import BaseCloudCrawler
from models.cloud.enums import DateCaveat
from models.cloud.launch.launch_catalog import LaunchCatalog

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]


def products(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    """Keep the products a crawler yielded (its follow-up requests left out)."""
    return [result for result in results if isinstance(result, dict)]


CARD = (
    '<h2 class="h4">Databases</h2><div class="content-card-list"><div class="card"><div class="card-body">'
    "<h3>{name}</h3><div data-oc-token-text><p>A product.</p></div></div></div></div>"
)


def page(url: str, content: str, status: int = 200) -> Response:
    return Response(url=url, content=content, status=status, reason="OK", cookies={}, headers={}, request_headers={})


def updates(*entries: Dict[str, JsonValue]) -> Response:
    return page(AzureCrawler.UPDATES_URL, json.dumps({"value": list(entries)}))


def reader() -> AzureCrawler:
    return AzureCrawler()


def test_query_names_the_product_with_and_without_its_brand() -> None:
    params = reader()._updates_query("Azure Cosmos DB")

    assert params["$filter"] == (
        "products/any(p: p eq 'Azure Cosmos DB' or p eq 'Cosmos DB' or p eq 'Microsoft Cosmos DB' "
        "or p eq 'Azure AI Cosmos DB')"
    )
    assert params["$orderby"] == "created asc"
    assert params["$top"] == "10"
    assert params["$select"] == "products,generalAvailabilityDate,previewAvailabilityDate,created"


def test_query_adds_the_alias_and_quotes_the_names() -> None:
    params = reader()._updates_query("Translator in Foundry Tools", "Azure AI Translator")

    assert "p eq 'Azure AI Translator'" in params["$filter"]
    assert "p eq 'Partner''s Hub'" in reader()._updates_query("Partner's Hub")["$filter"]


def test_launch_is_the_earliest_availability_or_publication() -> None:
    payload: JsonValue = {
        "value": [
            {"previewAvailabilityDate": None, "generalAvailabilityDate": "2017-05", "created": "2016-11-01T19:50:35Z"},
            {"previewAvailabilityDate": "2016-03", "generalAvailabilityDate": None, "created": "2016-11-02T10:00:00Z"},
        ]
    }

    assert reader()._first_update(payload, "Azure Functions") == (
        datetime(2016, 3, 1, tzinfo=UTC),
        DateCaveat.FIRST_ANNOUNCEMENT,
    )


def test_a_launch_at_the_start_of_the_feed_may_be_older() -> None:
    payload: JsonValue = {"value": [{"generalAvailabilityDate": "2013-11", "created": "2013-11-21T22:40:12.0000000Z"}]}

    launch = reader()._first_update(payload, "Traffic Manager")

    assert launch == (datetime(2013, 11, 1, tzinfo=UTC), DateCaveat.FEED_START)


def test_no_update_or_no_readable_date_gives_no_launch() -> None:
    assert reader()._first_update({"value": []}, "Azure SRE Agent") is None
    unreadable: JsonValue = {"value": [{"created": "yesterday", "previewAvailabilityDate": "1999-01"}]}
    assert reader()._first_update(unreadable, "X") is None
    assert reader()._first_update({"unexpected": True}, "X") is None


async def test_crawler_dates_each_product_from_the_feed(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    dated_source.get.return_value = updates({"previewAvailabilityDate": "2014-08", "created": "2014-08-21T17:30:52Z"})

    results = products(
        await crawl_page(AzureCrawler(), page(AzureCrawler.catalogue_url, CARD.format(name="Azure Cosmos DB")))
    )

    assert results[0]["added_at"] == "2014-08-01T00:00:00Z"
    assert results[0]["added_caveat"] == "first-announcement"
    url, kwargs = dated_source.get.call_args.args[0], dated_source.get.call_args.kwargs
    assert url == AzureCrawler.UPDATES_URL
    assert "p eq 'Azure Cosmos DB'" in kwargs["params"]["$filter"]


async def test_crawler_looks_a_renamed_product_up_under_its_alias(
    crawl_page: CrawlPage, dated_source: MagicMock, bundled_launches: MagicMock
) -> None:
    bundled_launches.return_value.launches.return_value = LaunchCatalog.model_validate(
        {"aliases": [{"crawler": "azure", "name": "Foundry Models", "feed_name": "Azure AI Studio"}]}
    )
    dated_source.get.return_value = updates({"previewAvailabilityDate": "2023-11", "created": "2023-11-15T00:00:00Z"})

    results = products(
        await crawl_page(AzureCrawler(), page(AzureCrawler.catalogue_url, CARD.format(name="Foundry Models")))
    )

    assert "p eq 'Azure AI Studio'" in dated_source.get.call_args.kwargs["params"]["$filter"]
    assert results[0]["added_at"] == "2023-11-01T00:00:00Z"


async def test_a_product_the_feed_does_not_name_is_streamed_undated(
    crawl_page: CrawlPage, dated_source: MagicMock
) -> None:
    dated_source.get.return_value = updates()
    crawler = AzureCrawler()

    results = products(await crawl_page(crawler, page(AzureCrawler.catalogue_url, CARD.format(name="Azure SRE Agent"))))

    assert results[0]["name"] == "Azure SRE Agent"
    assert "added_at" not in results[0]
    assert crawler.undated == {"Azure SRE Agent"}


async def test_a_feed_answer_which_is_not_json_leaves_the_product_undated(
    crawl_page: CrawlPage, dated_source: MagicMock
) -> None:
    dated_source.get.return_value = page(AzureCrawler.UPDATES_URL, "<html>maintenance</html>")
    crawler = AzureCrawler()

    results = products(await crawl_page(crawler, page(AzureCrawler.catalogue_url, CARD.format(name="Azure Cosmos DB"))))

    assert results[0]["name"] == "Azure Cosmos DB"
    assert "added_at" not in results[0]
    assert crawler.undated == {"Azure Cosmos DB"}
