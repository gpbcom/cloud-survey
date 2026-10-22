from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.tencent.marketplace import TencentMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parents[3] / "fixtures" / "marketplace"
HOST = "https://www.tencentcloud.com"
CLASSES_URL = f"{HOST}/market/api/mid/listProductClassDics"
PRODUCTS_URL = f"{HOST}/market/api/mid/listProduct?preview=0&pageIndex={{page}}&pageSize=100"


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


@pytest.fixture
def crawler(classifier: SoftwareClassifier) -> TencentMarketplaceCrawler:
    return TencentMarketplaceCrawler(classifier=classifier)


@pytest.fixture(autouse=True)
def no_page_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(TencentMarketplaceCrawler, "page_limit", None)


def page(url: str, content: Union[str, bytes], meta: Dict[str, JsonValue]) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta
    )


def fixture(name: str) -> bytes:
    return (FIXTURES / f"tencent_{name}").read_bytes()


def classes_page(content: Optional[Union[str, bytes]] = None) -> Response:
    return page(CLASSES_URL, fixture("classes.json") if content is None else content, {"source": "classes"})


def products_page(content: Optional[JsonValue] = None, number: int = 1) -> Response:
    body = fixture("products.json") if content is None else json.dumps(content).encode()
    return page(PRODUCTS_URL.format(page=number), body, {"source": "products", "page": number})


def market_page(content: Optional[Union[str, bytes]] = None) -> Response:
    meta: Dict[str, JsonValue] = {"source": "goods", "may_be_empty": True}
    return page(f"{HOST}/market", fixture("market.html") if content is None else content, meta)


def next_data(goods: JsonValue) -> str:
    data = json.dumps({"props": {"pageProps": {"goodsInfo": goods}}})
    return f'<html><script id="__NEXT_DATA__" type="application/json">{data}</script></html>'


def product(name: str, **fields: JsonValue) -> Dict[str, JsonValue]:
    entry: Dict[str, JsonValue] = {
        "prdID": f"P{len(name)}",
        "prdName": name,
        "introduce": f"{name}.",
        "categoryID": "1",
    }
    return entry | fields


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def software(results: List[Union[Dict[str, JsonValue], Request]]) -> Dict[str, Dict[str, JsonValue]]:
    return {str(result["name"]): result for result in results if isinstance(result, dict)}


async def classified(crawler: TencentMarketplaceCrawler, crawl_page: CrawlPage) -> TencentMarketplaceCrawler:
    await crawl_page(crawler, classes_page())
    return crawler


def test_configuration(crawler: TencentMarketplaceCrawler) -> None:
    assert crawler.name == "tencent-marketplace"
    assert TencentMarketplaceCrawler.catalogue_url == CLASSES_URL
    assert TencentMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"www.tencentcloud.com"}
    assert (crawler.class_families, crawler.listed_names) == ({}, set())


async def test_starts_with_the_product_classes_in_the_browser(crawler: TencentMarketplaceCrawler) -> None:
    started = [request async for request in crawler.start_requests()]

    assert [(request.url, request.sid, request.priority, request.meta) for request in started] == [
        (CLASSES_URL, "tencent-marketplace-session", 10, {"source": "classes"})
    ]
    assert started[0]._session_kwargs == {"network_idle": True}


async def test_reads_the_classes_then_requests_the_product_list(
    crawler: TencentMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    found = await crawl_page(crawler, classes_page())

    assert [(request.url, request.sid, request.meta) for request in requests(found)] == [
        (PRODUCTS_URL.format(page=1), "tencent-marketplace-session", {"source": "products", "page": 1})
    ]
    assert len(found) == 1
    assert crawler.class_families["Assessments"] == "Professional Services"
    assert crawler.class_families["web service"] == "web service / web app"
    assert crawler.class_families["Data Infra"] == "Web3"


@pytest.mark.parametrize(
    ("content", "message", "logged"),
    [
        ("<html>challenge</html>", "the page is not JSON", "is not JSON"),
        ('{"code": 1}', "the `data` list is missing", "have no `data` list"),
    ],
)
async def test_raises_on_malformed_classes(
    crawler: TencentMarketplaceCrawler,
    crawl_page: CrawlPage,
    caplog: pytest.LogCaptureFixture,
    content: str,
    message: str,
    logged: str,
) -> None:
    with pytest.raises(CatalogueFormatError, match=message):
        await crawl_page(crawler, classes_page(content))

    assert any(record.levelno == logging.ERROR and logged in record.message for record in caplog.records)


async def test_extracts_the_saas_products_then_requests_the_home_page(
    crawler: TencentMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    await classified(crawler, crawl_page)

    results = await crawl_page(crawler, products_page())

    found = software(results)
    assert list(found) == [
        "Solana Archive RPC service",
        "Onelook rpc firewall",
        "Aqtra Platform",
        "Automated Face Detection & Identification",
        "Matrix AI",
        "BaseKit whitelable e-commerce solution for small business'es",
        "Sentry.io",
    ]
    assert {key: found["Sentry.io"][key] for key in ("url", "publisher", "delivery", "marketplace_categories")} == {
        "url": f"{HOST}/market/product/P20220225101551630226421",
        "publisher": None,
        "delivery": "saas",
        "marketplace_categories": ["DevOps", "Issue & Bug Tracking"],
    }
    assert found["Sentry.io"]["marketplace_category_paths"] == [
        {"path": ["DevOps", "Issue & Bug Tracking"], "id": "2230"}
    ]
    assert found["Solana Archive RPC service"]["marketplace_category_paths"] == [
        {"path": ["Web3", "Data Infra"], "id": "9068"}
    ]
    assert found["BaseKit whitelable e-commerce solution for small business'es"]["marketplace_category_paths"] == [
        {"path": ["web service / web app", "web service"], "id": "9071"}
    ]
    assert found["Sentry.io"]["added_at"] == "2022-02-25T02:15:51Z"
    assert found["Solana Archive RPC service"]["added_at"] == "2025-09-25T08:32:10Z"
    assert found["Solana Archive RPC service"]["added_caveat"] == "assumed-timezone"
    assert [(request.url, request.meta) for request in requests(results)] == [
        (f"{HOST}/market", {"source": "goods", "may_be_empty": True})
    ]
    assert "Skipping the product 'Cloud Native Build' (category '3', a service)." in caplog.text
    assert "Skipping the product 'Monthe Managed Security' (professional service)." in caplog.text
    assert "Skipping the product 'Monthe Managed Security' (also listed as a service)." in caplog.text


async def test_merges_the_classes_of_a_product_listed_twice(
    crawler: TencentMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    await classified(crawler, crawl_page)
    listings: List[JsonValue] = [
        product("Site", prdID="P1", classNames="Security"),
        product("Site", prdID="P2", classNames="Productivity"),
    ]

    found = [item for item in await crawl_page(crawler, products_page({"prdList": listings})) if isinstance(item, dict)]

    assert [(item["url"], item["marketplace_categories"]) for item in found] == [
        (f"{HOST}/market/product/P1", ["Infrastructure Software", "Security"]),
        (f"{HOST}/market/product/P1", ["Infrastructure Software", "Security", "DevOps", "Productivity"]),
    ]
    assert found[1]["marketplace_category_paths"] == [
        {"path": ["Infrastructure Software", "Security"], "id": "69"},
        {"path": ["DevOps", "Productivity"], "id": "9060"},
    ]
    assert all("added_at" not in item for item in found)


async def test_reads_the_creation_date_from_the_product_identifier(
    crawler: TencentMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    await classified(crawler, crawl_page)
    listings: List[JsonValue] = [
        product("Dated", prdID="P20251231233000630227958"),
        product("Bad month", prdID="P20251331233000630227958"),
        product("Short", prdID="P20251231233000"),
        product("Anonymous", prdID=None),
    ]

    found = software(await crawl_page(crawler, products_page({"prdList": listings})))

    assert {name: item.get("added_at") for name, item in found.items()} == {
        "Dated": "2025-12-31T15:30:00Z",
        "Bad month": None,
        "Short": None,
        "Anonymous": None,
    }
    assert (
        "Ignoring the invalid creation date of the product 'Bad month' identifier 'P20251331233000630227958'."
        in caplog.text
    )
    assert "The product 'Short' identifier 'P20251231233000' holds no creation date." in caplog.text
    assert "The product 'Anonymous' identifier None holds no creation date." in caplog.text


@pytest.mark.parametrize(
    ("name", "audiences"), [("Sentry.io", ["developer-tool"]), ("Onelook rpc firewall", ["developer-tool"])]
)
async def test_classifies_the_products(
    crawler: TencentMarketplaceCrawler, crawl_page: CrawlPage, name: str, audiences: List[str]
) -> None:
    await classified(crawler, crawl_page)

    assert software(await crawl_page(crawler, products_page()))[name]["categories"] == audiences


async def test_names_the_publisher_of_a_real_vendor(crawler: TencentMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    entry = product("Tool", vendorID="1", vendorName="Acme", classNames="Unknown, Storage", prdID=None)

    found = software(
        await crawl_page(
            crawler, products_page({"prdList": [entry, "x", product("Mute", introduce="")], "pageCount": 3})
        )
    )

    assert {key: found["Tool"][key] for key in ("url", "publisher", "marketplace_categories")} == {
        "url": None,
        "publisher": "Acme",
        "marketplace_categories": ["Unknown", "Storage"],
    }
    assert found["Tool"]["marketplace_category_paths"] == [
        {"path": ["Unknown"], "id": None},
        {"path": ["Storage"], "id": None},
    ]


@pytest.mark.parametrize(
    ("count", "total", "number", "limit", "expected"),
    [
        (2, 5, 1, None, 2),
        (2, "5", 2, None, 3),
        (2, 4, 2, None, None),
        (2, 5, 1, 1, None),
        (1, 5, 1, None, None),
        (2, None, 1, None, None),
    ],
)
async def test_requests_the_next_product_list_page_while_pages_are_full(
    crawler: TencentMarketplaceCrawler,
    crawl_page: CrawlPage,
    monkeypatch: pytest.MonkeyPatch,
    count: int,
    total: JsonValue,
    number: int,
    limit: Optional[int],
    expected: Optional[int],
) -> None:
    monkeypatch.setattr(TencentMarketplaceCrawler, "PAGE_SIZE", 2)
    monkeypatch.setattr(TencentMarketplaceCrawler, "page_limit", limit)
    products: List[JsonValue] = [product(f"Tool {n}", prdID=f"P{number}{n}") for n in range(count)]

    found = requests(await crawl_page(crawler, products_page({"prdList": products, "pageCount": total}, number)))

    if expected is None:
        assert [(request.url, request.meta) for request in found] == [
            (f"{HOST}/market", {"source": "goods", "may_be_empty": True})
        ]
    else:
        next_url = f"{HOST}/market/api/mid/listProduct?preview=0&pageIndex={expected}&pageSize=2"
        assert [(request.url, request.meta) for request in found] == [
            (next_url, {"source": "products", "page": expected, "may_be_empty": True})
        ]


async def test_a_next_product_list_page_may_be_empty(crawler: TencentMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    empty = page(
        PRODUCTS_URL.format(page=2), '{"prdList": []}', {"source": "products", "page": 2, "may_be_empty": True}
    )

    found = await crawl_page(crawler, empty)

    assert [request.url for request in requests(found)] == [f"{HOST}/market"]


async def test_raises_when_the_first_product_list_page_is_empty(
    crawler: TencentMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(crawler, products_page({"prdList": [product("Help", categoryID="3")]}))

    assert any(record.levelno == logging.ERROR and "holds no software" in record.message for record in caplog.records)


async def test_raises_on_a_malformed_product_list(
    crawler: TencentMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(CatalogueFormatError, match="the `prdList` list is missing"):
        await crawl_page(crawler, products_page({"prdList": None}))

    assert any(
        record.levelno == logging.ERROR and "has no `prdList` list" in record.message for record in caplog.records
    )


async def test_extracts_the_goods_not_listed_yet(
    crawler: TencentMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    await crawl_page(crawler, products_page({"prdList": [product("Cloud Native Build")]}))

    found = software(await crawl_page(crawler, market_page()))

    assert list(found) == [
        "WeTest App Hardening",
        "AutoMQ for Kafka (Offline License Edition)",
        "eCopilot Introduction",
        "Vividime",
        "HyperBDR License",
    ]
    assert {key: found["Vividime"][key] for key in ("url", "publisher", "delivery", "marketplace_categories")} == {
        "url": f"{HOST}/market/detail/SPU_BHIEHJFHHA8834",
        "publisher": "vividata",
        "delivery": "other",
        "marketplace_categories": ["数据智能", "工具软件", "其他"],
    }
    assert found["Vividime"]["marketplace_category_paths"] == [
        {"path": ["数据智能"], "id": "26"},
        {"path": ["工具软件"], "id": "27"},
        {"path": ["其他"], "id": "29"},
    ]
    assert "Skipping the goods 'Cloud Native Build' (already listed)." in caplog.text


async def test_skips_the_goods_not_on_sale_and_tolerates_malformed_ones(
    crawler: TencentMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    goods: JsonValue = [
        {"GoodsBasicInfo": {"Status": "offlined"}, "GoodsDetailInfo": {"GoodsName": "Retired"}},
        {"GoodsDetailInfo": {"GoodsName": "Bare", "GoodsDescription": "Bare.", "CategoryList": [{"CategoryName": 1}]}},
        {"GoodsDetailInfo": {"GoodsName": "Mute"}},
        "x",
    ]

    found = software(await crawl_page(crawler, market_page(next_data(goods))))

    assert list(found) == ["Bare"]
    assert (found["Bare"]["url"], found["Bare"]["publisher"], found["Bare"]["marketplace_categories"]) == (
        None,
        None,
        [],
    )
    assert "marketplace_category_paths" not in found["Bare"]
    assert "Skipping the goods 'Retired' (status 'offlined')." in caplog.text


async def test_raises_without_goods_list(
    crawler: TencentMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(CatalogueFormatError, match="is not a list"):
        await crawl_page(crawler, market_page(next_data(None)))

    assert any(
        record.levelno == logging.ERROR and "has no `goodsInfo` list" in record.message for record in caplog.records
    )
