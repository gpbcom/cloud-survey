from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import partial
from typing import Awaitable, Callable, Dict, List, Optional, Union
from unittest.mock import MagicMock

from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.ctyun.crawler import ChinaTelecomCloudCrawler

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]


def products(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    """Keep the products a crawler yielded (its follow-up requests left out)."""
    return [result for result in results if isinstance(result, dict)]


CATALOGUE_URL = "https://www.ctyun.cn/products/"
MENU = (
    '<nav><a href="https://www.ctyun.cn/document/10000038/10000049">Help</a>'
    '<a href="https://www.ctyun.cn/document/10011391">Video</a>'
    '<a href="https://www.ctyun.cn/document/10011391/10011392">Video</a>'
    '<a href="https://www.ctyun.cn/document/">Docs</a><a href="https://www.ctyun.cn/document/novice">Novice</a></nav>'
)
CARD = (
    '<a class="link" target="_blank" href="https://www.ctyun.cn/products/{slug}"><div class="product-main">'
    '<div class="product-name" title="{name}">{name}</div><div class="product-note" title="A product.">'
    "A product.</div></div></a>"
)
CATALOGUE = '<section class="list"><div class="title"><span class="name">中间件</span></div><ul>{cards}</ul></section>'


def page(url: str, content: str, status: int = 200) -> Response:
    return Response(url=url, content=content, status=status, reason="OK", cookies={}, headers={}, request_headers={})


def product_page(book: str, title: str = "分布式消息服务MQTT_价格详情_功能优势_解决方案 -天翼云") -> str:
    links = "".join(
        f'<a href="https://www.ctyun.cn/document/{book}/{section}">{section}</a>'
        for section in ("%E5%BF%AB%E9%80%9F%E5%85%A5%E9%97%A8", "10818221", "10295030")
    )
    relative = f'<a href="/document/{book}">Docs</a>'
    return f"<html><head><title>{title}</title></head><body>{MENU}{links}{relative}</body></html>"


def updates(*entries: Dict[str, JsonValue], code: str = "core.ok") -> str:
    return json.dumps({"reason": "服务调用成功", "code": code, "list": list(entries)})


def update(release: str, kind: str, title: str = "支持IPv6") -> Dict[str, JsonValue]:
    return {"releaseDate": release, "title": title, "type": kind, "content": "…", "bookId": "10005536"}


def catalogue(*products: Dict[str, str]) -> Response:
    return page(CATALOGUE_URL, CATALOGUE.format(cards="".join(CARD.format(**product) for product in products)))


def answer(
    pages: Dict[str, str], books: Dict[str, str], url: str, params: Optional[Dict[str, str]] = None, **_: JsonValue
) -> Response:
    if url == ChinaTelecomCloudCrawler.DYNAMIC_URL:
        return page(url, books.get((params or {}).get("objectId", ""), updates()))
    if url in pages:
        return page(url, pages[url])
    return page(url, "<html><head><title>404页面 - 天翼云</title></head></html>", status=404)


def serve(dated_source: MagicMock, pages: Dict[str, str], books: Dict[str, str]) -> None:
    dated_source.get.side_effect = partial(answer, pages, books)


def test_book_is_the_one_the_product_page_links_the_most() -> None:
    url = "https://www.ctyun.cn/products/mqtt"

    assert ChinaTelecomCloudCrawler()._book_id(page(url, product_page("10005536"))) == "10005536"


def test_menu_links_and_missing_pages_give_no_book() -> None:
    url = "https://www.ctyun.cn/products/fujian"
    crawler = ChinaTelecomCloudCrawler()

    assert crawler._book_id(page(url, f"<html><head><title>云专线</title></head><body>{MENU}</body></html>")) is None
    assert crawler._book_id(page(url, product_page("10005536", title="404页面 - 天翼云"))) is None


def test_launch_is_the_earliest_launch_update_else_the_earliest_update() -> None:
    crawler = ChinaTelecomCloudCrawler()
    launched = json.loads(
        updates(
            update("2025-01-18", "2"),
            update("2019-09-19", "1", "分布式消息服务MQTT推广使用"),
            update("2020-03-12", "2", "监控告警"),
            update("2023-12-29", "1", "分布式消息服务MQTT公测转商"),
        )
    )
    renamed = json.loads(updates(update("2016-05-01", "2"), update("2021-03-02", "1", "XSTOR上线")))
    unlaunched = json.loads(updates(update("2022-12-07", "3"), update("not a date", "1"), update("1989-01-01", "2")))

    assert crawler._first_update(launched, "10005536") == datetime(2019, 9, 19, tzinfo=UTC)
    assert crawler._first_update(renamed, "10306929") == datetime(2021, 3, 2, tzinfo=UTC)
    assert crawler._first_update(unlaunched, "10026756") == datetime(2022, 12, 7, tzinfo=UTC)


def test_no_update_or_a_failed_call_gives_no_launch() -> None:
    crawler = ChinaTelecomCloudCrawler()
    failed = json.loads(updates(update("2021-03-02", "1"), code="core.e1300"))

    assert crawler._first_update(json.loads(updates()), "99999999") is None
    assert crawler._first_update(failed, "10306929") is None
    assert crawler._first_update(json.loads(updates(update("yesterday", "1"))), "10306929") is None
    assert crawler._first_update({"unexpected": True}, "10306929") is None


async def test_crawler_dates_each_product_from_the_book_of_its_page(
    crawl_page: CrawlPage, dated_source: MagicMock
) -> None:
    serve(
        dated_source,
        {
            "https://www.ctyun.cn/products/xstor": product_page("10306929"),
            "https://www.ctyun.cn/products/elb": product_page("10026756"),
        },
        {
            "10306929": updates(update("2021-03-02", "1", "XSTOR上线")),
            "10026756": updates(update("2022-12-07", "2"), update("2023-04-01", "3")),
        },
    )
    crawler = ChinaTelecomCloudCrawler()

    results = products(
        await crawl_page(
            crawler, catalogue({"slug": "xstor", "name": "海量文件服务"}, {"slug": "elb", "name": "弹性负载均衡"})
        )
    )

    assert [(result["name"], result["added_at"], result["added_caveat"]) for result in results] == [
        ("海量文件服务", "2021-03-02T00:00:00Z", "first-announcement"),
        ("弹性负载均衡", "2022-12-07T00:00:00Z", "first-announcement"),
    ]
    calls = [(call.args[0], call.kwargs["params"]) for call in dated_source.get.call_args_list]
    assert calls == [
        ("https://www.ctyun.cn/products/xstor", {}),
        (ChinaTelecomCloudCrawler.DYNAMIC_URL, {"objectType": "book", "objectId": "10306929"}),
        ("https://www.ctyun.cn/products/elb", {}),
        (ChinaTelecomCloudCrawler.DYNAMIC_URL, {"objectType": "book", "objectId": "10026756"}),
    ]
    assert crawler.undated == set()


async def test_a_launch_at_the_start_of_the_updates_may_be_older(
    crawl_page: CrawlPage, dated_source: MagicMock
) -> None:
    serve(
        dated_source,
        {"https://www.ctyun.cn/products/mqtt": product_page("10005536")},
        {"10005536": updates(update("2019-09-19", "1", "分布式消息服务MQTT推广使用"))},
    )

    results = products(
        await crawl_page(ChinaTelecomCloudCrawler(), catalogue({"slug": "mqtt", "name": "分布式消息服务MQTT"}))
    )

    assert results[0]["added_at"] == "2019-09-19T00:00:00Z"
    assert results[0]["added_caveat"] == "feed-start"


async def test_a_book_without_update_leaves_the_product_undated(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    serve(dated_source, {"https://www.ctyun.cn/products/domain": product_page("10025221")}, {})
    crawler = ChinaTelecomCloudCrawler()

    results = products(await crawl_page(crawler, catalogue({"slug": "domain", "name": "新域名服务"})))

    assert results[0]["name"] == "新域名服务"
    assert "added_at" not in results[0]
    assert crawler.undated == {"新域名服务"}


async def test_a_missing_product_page_dates_nothing(crawl_page: CrawlPage, dated_source: MagicMock) -> None:
    soft_missing = product_page("10005536", title="404页面 - 天翼云")
    serve(dated_source, {"https://www.ctyun.cn/products/gone": soft_missing}, {"10005536": updates()})
    crawler = ChinaTelecomCloudCrawler()

    results = products(
        await crawl_page(
            crawler, catalogue({"slug": "gone", "name": "已下线产品"}, {"slug": "removed", "name": "已删除产品"})
        )
    )

    assert [result["name"] for result in results] == ["已下线产品", "已删除产品"]
    assert all("added_at" not in result for result in results)
    assert crawler.undated == {"已下线产品", "已删除产品"}
    assert ChinaTelecomCloudCrawler.DYNAMIC_URL not in [call.args[0] for call in dated_source.get.call_args_list]


async def test_an_updates_answer_which_is_not_json_leaves_the_product_undated(
    crawl_page: CrawlPage, dated_source: MagicMock
) -> None:
    serve(
        dated_source,
        {"https://www.ctyun.cn/products/eip": product_page("10026753")},
        {"10026753": "<html>maintenance</html>"},
    )
    crawler = ChinaTelecomCloudCrawler()

    results = products(await crawl_page(crawler, catalogue({"slug": "eip", "name": "弹性IP"})))

    assert "added_at" not in results[0]
    assert crawler.undated == {"弹性IP"}
