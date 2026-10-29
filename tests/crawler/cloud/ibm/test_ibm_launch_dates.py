from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Awaitable, Callable, Dict, List, Union
from unittest.mock import MagicMock

from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.ibm.crawler import IBMCloudCrawler
from models.cloud.enums import DateCaveat
from models.cloud.launch.launch_catalog import LaunchCatalog

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]


def products(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    """Keep the products a crawler yielded (its follow-up requests left out)."""
    return [result for result in results if isinstance(result, dict)]


CATALOGUE_URL = "https://cloud.ibm.com/catalog"
CARD = (
    '<div class="ibm-search__results__card"><div class="bx--card__heading">{name}</div>'
    '<div class="bx--card__copy">A product.</div><a href="/products/x"></a></div>'
)
CODE_ENGINE_ID = "2ad2fdd0-bba5-11ea-8966-5d6402fed1c7"


def page(url: str, content: str, status: int = 200) -> Response:
    return Response(url=url, content=content, status=status, reason="OK", cookies={}, headers={}, request_headers={})


def resource(catalog_id: str, display_name: str, created: JsonValue) -> Dict[str, JsonValue]:
    return {
        "id": catalog_id,
        "name": catalog_id.lower(),
        "kind": "service",
        "created": created,
        "updated": "2026-01-01T00:00:00Z",
        "overview_ui": {"en": {"display_name": display_name, "description": "A service."}},
    }


def resource_page(entry: Dict[str, JsonValue]) -> Response:
    return page(f"{IBMCloudCrawler.GLOBAL_CATALOG_URL}/{entry['id']}", json.dumps(entry))


def search_page(*entries: Dict[str, JsonValue]) -> Response:
    count = len(entries)
    payload = {"offset": 0, "limit": 200, "count": count, "resource_count": count, "resources": list(entries)}
    return page(IBMCloudCrawler.GLOBAL_CATALOG_URL, json.dumps(payload))


def missing_page(url: str) -> Response:
    return page(url, '{"message":"Object does not exists","code":404}', status=404)


def catalogue(*items: Dict[str, JsonValue]) -> Response:
    state = {"model": {"categories": [{"id": "all", "name": "All", "items": list(items)}]}}
    return page(CATALOGUE_URL, f"<script>window.__PRELOADED_STATE__ = {json.dumps(state)};</script>")


def offer(catalog_id: str, name: str) -> Dict[str, JsonValue]:
    return {
        "id": catalog_id,
        "name": name,
        "tag": "ibm_created",
        "type": "service",
        "description": f"{name}.",
        "catalogUrl": f"/catalog/services/{catalog_id}",
    }


def test_configuration() -> None:
    assert IBMCloudCrawler.dates_launches is True
    assert IBMCloudCrawler.launch_feed_start is None
    assert IBMCloudCrawler.GLOBAL_CATALOG_URL == "https://globalcatalog.cloud.ibm.com/api/v1"


async def test_catalogue_product_is_dated_by_its_resource(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    dated_source.get.return_value = resource_page(resource(CODE_ENGINE_ID, "Code Engine", "2020-07-14T13:45:48Z"))

    results = products(await crawl_page(IBMCloudCrawler(), catalogue(offer(CODE_ENGINE_ID, "Code Engine"))))

    assert results[0]["added_at"] == "2020-07-14T13:45:48Z"
    assert results[0]["added_caveat"] == "catalogue-entry"
    assert dated_source.get.call_count == 1
    assert dated_source.get.call_args.args[0] == f"{IBMCloudCrawler.GLOBAL_CATALOG_URL}/{CODE_ENGINE_ID}"


async def test_each_product_fetches_its_own_resource_once(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    entries = {
        CODE_ENGINE_ID: resource(CODE_ENGINE_ID, "Code Engine", "2020-07-14T13:45:48Z"),
        "is.vpc": resource("is.vpc", "Virtual Private Cloud", "2018-11-20T23:04:00Z"),
    }
    dated_source.get.side_effect = lambda url, **kwargs: resource_page(entries[url.rsplit("/", 1)[-1]])

    results = products(
        await crawl_page(
            IBMCloudCrawler(), catalogue(offer(CODE_ENGINE_ID, "Code Engine"), offer("is.vpc", "Virtual Private Cloud"))
        )
    )

    assert {result["name"]: result["added_at"] for result in results if isinstance(result, dict)} == {
        "Code Engine": "2020-07-14T13:45:48Z",
        "Virtual Private Cloud": "2018-11-20T23:04:00Z",
    }
    assert dated_source.get.call_count == 2


async def test_unknown_identifier_falls_back_to_the_name_search(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    found = search_page(resource("toolchain", "Toolchain", "2018-07-16T17:32:05Z"))
    dated_source.get.side_effect = lambda url, **kwargs: (
        found if url == IBMCloudCrawler.GLOBAL_CATALOG_URL else missing_page(url)
    )

    results = products(await crawl_page(IBMCloudCrawler(), catalogue(offer("unknown-id", "Toolchain"))))

    assert results[0]["added_at"] == "2018-07-16T17:32:05Z"
    assert dated_source.get.call_args.kwargs["params"] == {"q": "Toolchain", "_limit": "200"}


async def test_an_answer_for_another_resource_is_not_the_product(
    crawl_page: CrawlPage, dated_source: MagicMock
) -> None:
    other = resource_page(resource("another-id", "Another service", "2016-01-01T00:00:00Z"))
    dated_source.get.side_effect = lambda url, **kwargs: (
        search_page() if url == IBMCloudCrawler.GLOBAL_CATALOG_URL else other
    )
    crawler = IBMCloudCrawler()

    results = products(await crawl_page(crawler, catalogue(offer("my-id", "Key Protect"))))

    assert "added_at" not in results[0]
    assert crawler.undated == {"Key Protect"}


async def test_card_product_is_searched_by_display_name(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    dated_source.get.return_value = search_page(
        resource("cpdaas", "Cloud Pak for Data Plugin", "2020-01-01T00:00:00Z"),
        resource("cp4d", "IBM Cloud Pak for Data", "2021-01-07T17:00:53Z"),
        resource("cp4d-new", "Cloud Pak for Data", "2023-05-01T00:00:00Z"),
    )

    results = products(
        await crawl_page(IBMCloudCrawler(), page(IBMCloudCrawler.PRODUCTS_URL, CARD.format(name="Cloud Pak for Data")))
    )

    assert results[0]["added_at"] == "2021-01-07T17:00:53Z"
    assert results[0]["added_caveat"] == "catalogue-entry"
    assert dated_source.get.call_args.args[0] == IBMCloudCrawler.GLOBAL_CATALOG_URL


def test_earliest_readable_match_wins() -> None:
    payload: JsonValue = {
        "resources": [
            resource("a", "MQ", "2019-01-01T00:00:00Z"),
            resource("b", "MQ", "not a date"),
            resource("c", "MQ", "2017-11-28T15:39:18.123456789-04:00"),
            resource("d", "Messages for RabbitMQ", "2015-01-01T00:00:00Z"),
            "not a resource",
        ]
    }

    created = IBMCloudCrawler()._earliest_match(payload, ["mq"], "MQ")

    assert created == datetime(2017, 11, 28, 19, 39, 18, 123456, tzinfo=UTC)


def test_search_without_resources_gives_no_launch() -> None:
    crawler = IBMCloudCrawler()

    assert crawler._earliest_match({"message": "maintenance"}, ["mq"], "MQ") is None
    assert crawler._earliest_match([], ["mq"], "MQ") is None
    assert crawler._earliest_match({"resources": []}, ["mq"], "MQ") is None


def test_migration_day_is_a_website_record_and_no_date_is_feed_start() -> None:
    crawler = IBMCloudCrawler()
    migrated = datetime(2017, 8, 24, 18, 16, 39, tzinfo=UTC)
    early = datetime(2014, 3, 1, tzinfo=UTC)

    assert crawler._created_caveat(migrated) == (migrated, DateCaveat.WEBSITE_RECORD)
    assert crawler._created_caveat(early) == (early, DateCaveat.CATALOGUE_ENTRY)


async def test_renamed_product_is_searched_under_its_alias(
    crawl_page: CrawlPage, dated_source: MagicMock, bundled_launches: MagicMock
) -> None:
    bundled_launches.return_value.launches.return_value = LaunchCatalog.model_validate(
        {"aliases": [{"crawler": "ibm", "name": "watsonx.ai Studio", "feed_name": "Watson Studio"}]}
    )
    dated_source.get.return_value = search_page(resource("dsx", "Watson Studio", "2017-05-24T18:39:56Z"))

    results = products(
        await crawl_page(IBMCloudCrawler(), page(IBMCloudCrawler.PRODUCTS_URL, CARD.format(name="watsonx.ai Studio")))
    )

    assert dated_source.get.call_args.kwargs["params"]["q"] == "Watson Studio"
    assert results[0]["added_at"] == "2017-05-24T18:39:56Z"


async def test_a_product_without_resource_is_streamed_undated(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    dated_source.get.return_value = search_page(resource("other", "Another service", "2019-01-01T00:00:00Z"))
    crawler = IBMCloudCrawler()

    results = products(
        await crawl_page(crawler, page(IBMCloudCrawler.PRODUCTS_URL, CARD.format(name="Hybrid Cloud Mesh")))
    )

    assert results[0]["name"] == "Hybrid Cloud Mesh"
    assert "added_at" not in results[0]
    assert crawler.undated == {"Hybrid Cloud Mesh"}


async def test_an_answer_which_is_not_json_leaves_the_product_undated(
    crawl_page: CrawlPage, dated_source: MagicMock
) -> None:
    dated_source.get.return_value = page(IBMCloudCrawler.GLOBAL_CATALOG_URL, "<html>maintenance</html>")
    crawler = IBMCloudCrawler()

    results = products(await crawl_page(crawler, catalogue(offer(CODE_ENGINE_ID, "Code Engine"))))

    assert "added_at" not in results[0]
    assert crawler.undated == {"Code Engine"}


async def test_catalogue_identifiers_are_forgotten_unless_resuming() -> None:
    crawler = IBMCloudCrawler()
    crawler.catalog_ids["codeengine"] = CODE_ENGINE_ID

    await crawler.on_start(resuming=True)
    assert crawler.catalog_ids == {"codeengine": CODE_ENGINE_ID}

    await crawler.on_start(resuming=False)
    assert crawler.catalog_ids == {}
