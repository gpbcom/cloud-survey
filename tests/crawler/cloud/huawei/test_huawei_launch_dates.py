from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Awaitable, Callable, Dict, List, Union
from unittest.mock import MagicMock

from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.huawei.crawler import HuaweiCloudCrawler
from models.cloud.enums import DateCaveat
from models.cloud.launch.launch_catalog import LaunchCatalog
from models.cloud.products.product import CloudProduct

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]


def products(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    """Keep the products a crawler yielded (its follow-up requests left out)."""
    return [result for result in results if isinstance(result, dict)]


CN = "https://support.huaweicloud.com/wtsnew-{code}/index.html"
INTL = "https://support.huaweicloud.com/intl/en-us/wtsnew-{code}/index.html"
MISSING = "<html><head><title>-</title></head><body><div class='help-center'>Help Center</div></body></html>"


def page(url: str, content: str, status: int = 200) -> Response:
    return Response(url=url, content=content, status=status, reason="OK", cookies={}, headers={}, request_headers={})


def whats_new(title: str, *months: str) -> str:
    sections = "".join(
        f'<div class="section"><h4 class="sectiontitle">{month}</h4><div class="tablenoborder">'
        '<table class="wtsnewtable"><tbody><tr><td><p>1</p></td><td><p>Feature</p></td></tr></tbody></table>'
        "</div></div>"
        for month in months
    )
    return f"<html><head><title>{title}</title></head><body>{sections}</body></html>"


def catalogue() -> str:
    entries = [
        {"code": "ecs", "title": "Elastic Cloud Server", "uri": "https://support.huaweicloud.com/intl/en-us/ecs/"},
        {"code": "nosql", "title": "GeminiDB", "uri": "https://support.huaweicloud.com/intl/en-us/nosql/"},
        {"code": "sdk", "title": "SDK Reference", "uri": "https://support.huaweicloud.com/intl/en-us/sdk/"},
    ]
    return json.dumps({"data": [{"name": "Compute", "products": entries}], "status": True})


def cards(*names: str) -> str:
    links = "".join(
        f'<a class="card" href="/intl/en-us/product/{index}.html"><div class="card-title">{name}</div>'
        '<div class="card-description">A service.</div></a>'
        for index, name in enumerate(names)
    )
    return (
        '<div class="first-content"><div class="first-title">Compute</div><div class="second-content second-pc">'
        f'<div class="second-flex">{links}</div></div></div>'
    )


def serve(dated_source: MagicMock, pages: Dict[str, str]) -> None:
    served = {HuaweiCloudCrawler.DOCS_URL: catalogue(), **pages}
    dated_source.get.side_effect = lambda url, **_: page(url, served[url]) if url in served else page(url, MISSING)


def fetched(dated_source: MagicMock) -> List[str]:
    return [call.args[0] for call in dated_source.get.call_args_list]


def test_launch_is_the_earliest_month_heading() -> None:
    crawler = HuaweiCloudCrawler()
    chinese = whats_new("最新动态_弹性云服务器 ECS-华为云", "2018年01月", "2017年11月", "2017年10月", "其他")
    english = whats_new("What&#39;s New_Elastic Cloud Server-Huawei Cloud", "April 2018", "March 2018", "Others")

    assert crawler._earliest_month(page(CN.format(code="ecs"), chinese)) == datetime(2017, 10, 1, tzinfo=UTC)
    assert crawler._earliest_month(page(INTL.format(code="ecs"), english)) == datetime(2018, 3, 1, tzinfo=UTC)
    assert crawler._earliest_month(page(CN.format(code="ecs"), whats_new("Title", "其他"))) is None


def test_missing_page_served_with_http_200_dates_nothing() -> None:
    crawler = HuaweiCloudCrawler()
    placeholder = whats_new("-", "2017年10月").replace("<title>-</title>", "<title> - </title>")

    assert crawler._is_missing_page(page(CN.format(code="nope"), MISSING))
    assert crawler._earliest_month(page(CN.format(code="nope"), placeholder)) is None
    assert crawler._earliest_month(page(CN.format(code="nope"), whats_new("", "2017年10月"))) is None


def test_products_are_matched_to_their_docs_code_by_name_or_alias() -> None:
    crawler = HuaweiCloudCrawler()
    codes = crawler._docs_codes(page(HuaweiCloudCrawler.DOCS_URL, catalogue()))
    crawler.launch_aliases = {crawler._name_key("GeminiDB for Cassandra"): "GeminiDB"}

    assert codes == {"elasticcloudserver": "ecs", "geminidb": "nosql"}
    assert crawler._whats_new_code(CloudProduct(name="Elastic Cloud Server (ECS)", description="x"), codes) == "ecs"
    assert crawler._whats_new_code(CloudProduct(name="Huawei Cloud GeminiDB", description="x"), codes) == "nosql"
    assert crawler._whats_new_code(CloudProduct(name="GeminiDB for Cassandra", description="x"), codes) == "nosql"
    assert crawler._whats_new_code(CloudProduct(name="SDK Reference", description="x"), codes) is None
    assert crawler._whats_new_code(CloudProduct(name="WeLink", description="x"), codes) is None


async def test_launch_is_the_earliest_month_of_both_websites(dated_source: MagicMock) -> None:
    serve(
        dated_source,
        {
            CN.format(code="nosql"): whats_new("最新动态_GeminiDB-华为云", "2025年01月", "2024年11月"),
            INTL.format(code="nosql"): whats_new("What&#39;s New_GeminiDB-Huawei Cloud", "July 2020", "May 2020"),
        },
    )

    launch = await HuaweiCloudCrawler()._launch_source(CloudProduct(name="GeminiDB", description="x"))

    assert launch == (datetime(2020, 5, 1, tzinfo=UTC), DateCaveat.FIRST_ANNOUNCEMENT)


async def test_crawler_dates_the_cards_from_their_docs_code(
    crawl_page: CrawlPage, dated_source: MagicMock, bundled_launches: MagicMock
) -> None:
    bundled_launches.return_value.launches.return_value = LaunchCatalog.model_validate(
        {"aliases": [{"crawler": "huawei", "name": "GeminiDB for Cassandra", "feed_name": "GeminiDB"}]}
    )
    serve(
        dated_source,
        {
            CN.format(code="ecs"): whats_new("最新动态_弹性云服务器 ECS-华为云", "2018年01月", "2017年10月"),
            INTL.format(code="ecs"): whats_new("What&#39;s New_Elastic Cloud Server-Huawei Cloud", "January 2018"),
            INTL.format(code="nosql"): whats_new("What&#39;s New_GeminiDB-Huawei Cloud", "June 2018", "April 2018"),
        },
    )
    crawler = HuaweiCloudCrawler()
    content = cards("Elastic Cloud Server (ECS)", "GeminiDB for Cassandra", "HUAWEI CLOUD WeLink")

    results = products(await crawl_page(crawler, page(HuaweiCloudCrawler.catalogue_url, content)))

    named = {result["name"]: result for result in results}
    assert named["Elastic Cloud Server (ECS)"]["added_at"] == "2017-10-01T00:00:00Z"
    assert named["Elastic Cloud Server (ECS)"]["added_caveat"] == "feed-start"
    assert named["GeminiDB for Cassandra"]["added_at"] == "2018-04-01T00:00:00Z"
    assert named["GeminiDB for Cassandra"]["added_caveat"] == "first-announcement"
    assert "added_at" not in named["HUAWEI CLOUD WeLink"]
    assert crawler.undated == {"HUAWEI CLOUD WeLink"}
    assert fetched(dated_source) == [
        HuaweiCloudCrawler.DOCS_URL,
        CN.format(code="ecs"),
        INTL.format(code="ecs"),
        CN.format(code="nosql"),
        INTL.format(code="nosql"),
    ]


async def test_docs_catalogue_is_fetched_once_per_crawl(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    serve(dated_source, {})
    crawler = HuaweiCloudCrawler()

    products(
        await crawl_page(crawler, page(HuaweiCloudCrawler.catalogue_url, cards("Elastic Cloud Server", "GeminiDB")))
    )
    products(
        await crawl_page(crawler, page(HuaweiCloudCrawler.catalogue_url, cards("Elastic Cloud Server", "GeminiDB")))
    )

    assert fetched(dated_source).count(HuaweiCloudCrawler.DOCS_URL) == 1
    assert crawler.undated == {"Elastic Cloud Server", "GeminiDB"}

    await crawler.on_start(resuming=True)
    assert crawler.whats_new_codes == {"elasticcloudserver": "ecs", "geminidb": "nosql"}
    await crawler.on_start()
    assert crawler.whats_new_codes is None


async def test_unreadable_docs_catalogue_leaves_the_products_undated(
    crawl_page: CrawlPage, dated_source: MagicMock
) -> None:
    crawler = HuaweiCloudCrawler()

    results = products(
        await crawl_page(crawler, page(HuaweiCloudCrawler.catalogue_url, cards("Elastic Cloud Server", "OBS")))
    )

    assert len(results) == 2
    assert crawler.undated == {"Elastic Cloud Server", "OBS"}
    assert fetched(dated_source) == [HuaweiCloudCrawler.DOCS_URL]
    assert crawler.whats_new_codes == {}
