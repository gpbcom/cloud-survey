from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Union
from unittest.mock import patch

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.ctyun.marketplace import ChinaTelecomMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parents[3] / "fixtures" / "marketplace"
LIST_URL = "https://market.ctyun.cn/gw/offer/catalog/Query?offset=0&limit=50"
CLASS_URL = "https://market.ctyun.cn/gw/util/class/GetDetail"
LOGGER = "scrapling.spiders.ctyun-marketplace"


@pytest.fixture(scope="module")
def crawler() -> ChinaTelecomMarketplaceCrawler:
    return ChinaTelecomMarketplaceCrawler(classifier=SoftwareClassifier())


@pytest.fixture
def fresh(crawler: ChinaTelecomMarketplaceCrawler) -> ChinaTelecomMarketplaceCrawler:
    crawler.software_categories.clear()
    crawler.class_names = dict(ChinaTelecomMarketplaceCrawler.CLASS_NAMES)
    return crawler


def response(content: Union[str, bytes], meta: Optional[Dict[str, JsonValue]] = None, url: str = LIST_URL) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def fixture_page(fixture: str, meta: Optional[Dict[str, JsonValue]] = None, url: str = LIST_URL) -> Response:
    return response((FIXTURES / fixture).read_bytes(), meta, url)


def offers_page(
    offers: List[JsonValue], total: JsonValue = "2", meta: Optional[Dict[str, JsonValue]] = None
) -> Response:
    return response(json.dumps({"code": "core.ok", "data": {"item": offers, "total": total}}), meta)


def fixture_offer(name: str) -> Dict[str, JsonValue]:
    offers = json.loads((FIXTURES / "ctyun_catalog.json").read_bytes())["data"]["item"]
    found: Dict[str, JsonValue] = next(entry for entry in offers if entry["name"] == name)
    return found


def offer(name: str, **fields: JsonValue) -> JsonValue:
    entry: Dict[str, JsonValue] = {"name": name, "note": f"{name} description", "state": "online", "display": "true"}
    entry.update(fields)
    return entry


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [item["name"] for item in items(results)]


def test_configuration(crawler: ChinaTelecomMarketplaceCrawler) -> None:
    assert crawler.name == "ctyun-marketplace"
    assert ChinaTelecomMarketplaceCrawler.catalogue_url == LIST_URL
    assert ChinaTelecomMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"market.ctyun.cn"}


async def test_start_requests(crawler: ChinaTelecomMarketplaceCrawler) -> None:
    classes, first = [request async for request in crawler.start_requests()]

    assert (classes.url, classes.priority, classes.meta) == (CLASS_URL, 11, {"classes": True, "may_be_empty": True})
    assert (first.url, first.priority, first.meta, first.sid) == (LIST_URL, 10, {"page": 1}, "ctyun-marketplace-http")
    assert first._session_kwargs == {"method": "GET", "json": None, "headers": None}


async def test_extracts_the_software_with_the_class_names(
    fresh: ChinaTelecomMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    assert await crawl_page(fresh, fixture_page("ctyun_classes.json", {"classes": True}, CLASS_URL)) == []

    results = await crawl_page(fresh, fixture_page("ctyun_catalog.json", {"page": 1}))

    assert names(results) == [
        "智能组网-组网集成服务",
        "SSL证书",
        "翼备份\uff08SaaS版\uff09100G",
        "安全邮箱\uff08央企SaaS版\uff09",
        "WPS 365",
        "翼建站",
        "智擎思政平台\uff08旗舰版\uff09",
    ]
    assert items(results)[4] == {
        "name": "WPS 365",
        "description": fixture_offer("WPS 365")["note"],
        "publisher": "天翼云甄选商城",
        "url": "https://market.ctyun.cn/market/mallproduct/13887356",
        "delivery": "saas",
        "marketplace_categories": ["企业应用", "办公协同"],
        "marketplace_category_paths": [{"path": ["企业应用", "办公协同"], "id": "3000"}],
        "categories": ["end-user-software"],
    }


@pytest.mark.parametrize(
    ("name", "categories", "audiences", "subclass"),
    [
        ("SSL证书", ["建站工具", "网站服务"], ["developer-tool", "end-user-software"], "9000"),
        ("翼备份\uff08SaaS版\uff09100G", ["开发运维", "灾备迁移"], ["developer-tool"], "10050"),
        ("安全邮箱\uff08央企SaaS版\uff09", ["企业应用", "办公协同"], ["developer-tool", "end-user-software"], "3000"),
        ("智擎思政平台\uff08旗舰版\uff09", ["行业应用", "教育"], ["end-user-software"], "8030"),
    ],
)
async def test_categories_and_audiences(
    fresh: ChinaTelecomMarketplaceCrawler,
    crawl_page: CrawlPage,
    name: str,
    categories: List[str],
    audiences: List[str],
    subclass: str,
) -> None:
    await crawl_page(fresh, fixture_page("ctyun_classes.json", {"classes": True}, CLASS_URL))

    results = await crawl_page(fresh, fixture_page("ctyun_catalog.json"))
    software = next(item for item in items(results) if item["name"] == name)

    assert (software["marketplace_categories"], software["categories"]) == (categories, audiences)
    assert software["marketplace_category_paths"] == [{"path": categories, "id": subclass}]


async def test_menu_class_names_without_the_class_tree(
    fresh: ChinaTelecomMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(fresh, fixture_page("ctyun_catalog.json"))

    assert items(results)[0]["marketplace_categories"] == ["开发运维"]
    assert items(results)[0]["marketplace_category_paths"] == [{"path": ["开发运维"], "id": "devops"}]


async def test_offline_delivered_services_are_excluded(
    fresh: ChinaTelecomMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    results = await crawl_page(fresh, fixture_page("ctyun_catalog.json"))

    assert "智能组网" not in names(results)
    assert "Skipping the ctyun-marketplace offer '智能组网', a service (线下交付类)." in caplog.messages


@pytest.mark.parametrize(
    ("entry", "reason"),
    [
        (offer("Course", **{"class": "course", "subclass": "7000"}), "not a software (course/7000)"),
        (offer("Consulting", **{"class": "devops", "subclass": "10060"}), "not a software (devops/10060)"),
        (offer("Terminal", **{"class": "application", "subclass": "3030"}), "not a software (application/3030)"),
        (offer("Retired", state="offline"), "not online (offline)"),
        (offer("Hidden", display="false"), "not online (online)"),
    ],
)
async def test_courses_services_hardware_and_offline_offers_are_excluded(
    fresh: ChinaTelecomMarketplaceCrawler,
    crawl_page: CrawlPage,
    caplog: pytest.LogCaptureFixture,
    entry: JsonValue,
    reason: str,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    assert await crawl_page(fresh, offers_page([entry], meta={"may_be_empty": True})) == []
    assert any(message.endswith(f", {reason}.") for message in caplog.messages)


@pytest.mark.parametrize(
    ("mode", "delivery"),
    [("saas", "saas"), ("image", "virtual-machine"), ("API", "api"), ("license", "download"), ("other", "other")],
)
async def test_delivery_modes(
    fresh: ChinaTelecomMarketplaceCrawler, crawl_page: CrawlPage, mode: str, delivery: str
) -> None:
    (software,) = items(await crawl_page(fresh, offers_page([offer("Acme", deliverMode=mode)])))

    assert software["delivery"] == delivery


async def test_malformed_offers(fresh: ChinaTelecomMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        fresh,
        offers_page(
            [
                offer("Bare", **{"class": "unknown", "detailUrl": "http://market.ctyun.cn/market/mallproduct/1?"}),
                {"name": "No description", "state": "online"},
                {"name": "No state", "note": "No state"},
                "not an offer",
            ]
        ),
    )

    assert [
        (item["name"], item["url"], item["publisher"], item["marketplace_categories"]) for item in items(results)
    ] == [("Bare", "https://market.ctyun.cn/market/mallproduct/1", None, [])]
    assert "marketplace_category_paths" not in items(results)[0]


async def test_requests_the_next_page(fresh: ChinaTelecomMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, offers_page([offer("Acme")], total="120", meta={"page": 2, "may_be_empty": True}))

    (request,) = requests(results)
    assert results[-1] is request
    assert (request.url, request.priority) == ("https://market.ctyun.cn/gw/offer/catalog/Query?offset=100&limit=50", 10)
    assert request.meta == {"page": 3, "may_be_empty": True}


@pytest.mark.parametrize("total", ["29", 29, "many", None])
async def test_single_page_requests_nothing(
    fresh: ChinaTelecomMarketplaceCrawler, crawl_page: CrawlPage, total: JsonValue
) -> None:
    results = await crawl_page(fresh, offers_page([offer("Acme")], total=total, meta={"page": 1}))

    assert names(results) == ["Acme"]
    assert requests(results) == []


async def test_page_limit_stops_the_pagination(fresh: ChinaTelecomMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    with patch.object(ChinaTelecomMarketplaceCrawler, "page_limit", 1):
        results = await crawl_page(fresh, offers_page([offer("Acme")], total="120"))

    assert requests(results) == []


async def test_empty_first_page_is_an_error(
    fresh: ChinaTelecomMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError, match="no product found"):
        await crawl_page(fresh, offers_page([], total="0"))

    assert any(record.levelname == "ERROR" and "holds no software" in record.message for record in caplog.records)


async def test_empty_next_page_is_the_end(fresh: ChinaTelecomMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    assert await crawl_page(fresh, offers_page([], total="120", meta={"page": 2, "may_be_empty": True})) == []


async def test_malformed_classes_are_ignored(fresh: ChinaTelecomMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    classes: JsonValue = [
        {"classId": "x", "name": " "},
        {"classId": 3, "name": "Number"},
        {"subclassId": "9", "name": "Nine"},
    ]

    await crawl_page(fresh, response(json.dumps({"data": {"list": classes}}), {"classes": True}, CLASS_URL))

    assert fresh.class_names == {**ChinaTelecomMarketplaceCrawler.CLASS_NAMES, "9": "Nine"}


@pytest.mark.parametrize("content", ['{"data": {"total": "29"}}', "[]", "<html></html>"])
@pytest.mark.parametrize("meta", [{}, {"classes": True}])
async def test_unexpected_response_is_an_error(
    fresh: ChinaTelecomMarketplaceCrawler,
    crawl_page: CrawlPage,
    caplog: pytest.LogCaptureFixture,
    content: str,
    meta: Dict[str, JsonValue],
) -> None:
    with pytest.raises(CatalogueFormatError, match="unexpected catalogue format"):
        await crawl_page(fresh, response(content, meta))

    assert any(record.levelname == "ERROR" for record in caplog.records)


async def test_on_start_resets_the_class_names(fresh: ChinaTelecomMarketplaceCrawler) -> None:
    fresh.class_names["9"] = "Nine"

    await fresh.on_start(resuming=True)
    assert fresh.class_names["9"] == "Nine"
    await fresh.on_start()
    assert fresh.class_names == ChinaTelecomMarketplaceCrawler.CLASS_NAMES
