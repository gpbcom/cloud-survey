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
from crawler.cloud.baidu.marketplace import BaiduMarketplaceCrawler
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parents[3] / "fixtures" / "marketplace"
SITE = "https://market.baidu.com"
CATEGORY_URL = f"{SITE}/api/market/web/get_category"
SITEMAP_URL = f"{SITE}/sitemap.xml"
LOGGER = "scrapling.spiders.baidu-marketplace"
PIDS = {
    "crm": "3042dd83-9efa-4382-b6dd-5099c13622fe",
    "image": "02cba765-e935-4d63-8f4e-dbe7b85847a8",
    "ai_api": "02c40594-ad03-432f-b2dc-a43c60456862",
    "data_api": "cb248839-caa3-4846-af75-f9d5cd037443",
    "company_service": "948d79d6-6c65-4e1f-961a-64a8181fc787",
    "security_service": "7fbb08c7-62c5-4d47-b08c-dbc7848debf5",
    "on_premises": "810cc861-590d-464e-86e7-4c48f73e10a5",
    "delisted": "d4a8a8d3-f902-4b4b-af9a-6f29c50ba8cf",
}


@pytest.fixture(scope="module")
def crawler() -> BaiduMarketplaceCrawler:
    return BaiduMarketplaceCrawler(classifier=SoftwareClassifier())


@pytest.fixture
def fresh(crawler: BaiduMarketplaceCrawler) -> BaiduMarketplaceCrawler:
    crawler.software_categories.clear()
    crawler.requested_products.clear()
    return crawler


def response(url: str, content: Union[str, bytes], meta: Dict[str, JsonValue], status: int = 200) -> Response:
    return Response(
        url=url, content=content, status=status, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta
    )


def detail_url(pid: str) -> str:
    return f"{SITE}/api/market/web/product/{pid}/detail"


def detail_page(name: str, content: Optional[str] = None, status: int = 200) -> Response:
    pid = PIDS.get(name, name)
    body = content if content is not None else (FIXTURES / f"baidu_detail_{name}.json").read_text()
    return response(detail_url(pid), body, {"kind": "detail", "product": pid, "may_be_empty": True}, status)


def page(url: str, fixture: str, kind: str, extra: Optional[Dict[str, JsonValue]] = None) -> Response:
    return response(url, (FIXTURES / fixture).read_bytes(), {"kind": kind, **(extra or {})})


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def test_configuration(crawler: BaiduMarketplaceCrawler) -> None:
    assert crawler.name == "baidu-marketplace"
    assert BaiduMarketplaceCrawler.catalogue_url == CATEGORY_URL
    assert BaiduMarketplaceCrawler.complement_urls == (SITEMAP_URL,)
    assert crawler.allowed_domains == {"market.baidu.com"}


async def test_start_requests(crawler: BaiduMarketplaceCrawler) -> None:
    categories, sitemap = [request async for request in crawler.start_requests()]

    assert (categories.url, categories.priority, categories.meta) == (CATEGORY_URL, 10, {"kind": "categories"})
    assert (sitemap.url, sitemap.priority, sitemap.meta) == (SITEMAP_URL, 0, {"kind": "sitemap"})


async def test_category_tree_requests_the_software_categories(
    fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    results = await crawl_page(fresh, page(CATEGORY_URL, "baidu_categories.json", "categories"))

    urls = [request.url for request in requests(results)]
    assert len(results) == len(urls) == 60
    assert urls[:2] == [f"{SITE}/api/market/web/list/110001/products", f"{SITE}/api/market/web/list/110003/products"]
    assert f"{SITE}/api/market/web/list/130009/products" in urls
    for excluded in ("102001", "150001", "145001", "135002", "120015", "130001", "101002", "101015", "101003"):
        assert f"{SITE}/api/market/web/list/{excluded}/products" not in urls
    assert {(request.priority, json.dumps(request.meta)) for request in requests(results)} == {(8, '{"kind": "list"}')}
    assert "Not requesting the baidu-marketplace category 上云服务/环境部署." in caplog.messages


async def test_page_limit_shares_the_details_between_the_categories(
    fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    with patch.object(BaiduMarketplaceCrawler, "page_limit", 2):
        results = await crawl_page(fresh, page(CATEGORY_URL, "baidu_categories.json", "categories"))
        listed = await crawl_page(
            fresh, page(f"{SITE}/api/market/web/list/135001/products", "baidu_list_products.json", "list", {"share": 1})
        )

    assert {json.dumps(request.meta) for request in requests(results)} == {'{"kind": "list", "share": 1}'}
    assert [request.url for request in requests(listed)] == [detail_url(PIDS["on_premises"])]


@pytest.mark.parametrize("content", ['{"result": []}', '{"result": {"children": []}}', "<html></html>"])
async def test_unexpected_category_tree_is_an_error(
    fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, content: str
) -> None:
    with pytest.raises(CatalogueFormatError, match="unexpected catalogue format"):
        await crawl_page(fresh, response(CATEGORY_URL, content, {"kind": "categories"}))

    assert any(record.levelname == "ERROR" for record in caplog.records)


async def test_malformed_categories_are_skipped(fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    tree = {"result": [{"name": "软件工具", "children": [{"cid": "118001", "name": "服务组件"}, "child"]}, "category"]}

    assert await crawl_page(fresh, response(CATEGORY_URL, json.dumps(tree), {"kind": "categories"})) == []


async def test_category_page_requests_the_details(fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    listed = page(f"{SITE}/api/market/web/list/135001/products", "baidu_list_products.json", "list")

    results = await crawl_page(fresh, listed)

    assert [request.url for request in requests(results)] == [
        detail_url(PIDS["on_premises"]),
        detail_url("0783334b-a723-4054-a4e9-ccf4ffd97abf"),
        detail_url("4b24447a-70b9-49c4-95a9-f2bbfda4dae3"),
        detail_url("bd88c402-b217-4950-90eb-be5bb628eb54"),
    ]
    assert requests(results)[0].meta == {"kind": "detail", "product": PIDS["on_premises"], "may_be_empty": True}
    assert {request.priority for request in requests(results)} == {6}
    assert await crawl_page(fresh, listed) == []


async def test_sitemap_requests_the_product_details(fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    fresh.requested_products.add("0034ef1f-e7ec-49c8-92ac-7326722aa88c")

    results = await crawl_page(fresh, page(SITEMAP_URL, "baidu_sitemap.xml", "sitemap"))

    assert [request.url for request in requests(results)] == [
        detail_url("000376f4-0466-446c-b371-978af19f7283"),
        detail_url("002e10cc-a531-4929-8f74-d6fc866fcfd8"),
    ]
    assert {request.priority for request in requests(results)} == {0}


async def test_streams_the_software_then_requests_its_related_products(
    fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(fresh, detail_page("crm"))

    assert items(results) == [
        {
            "name": "CRM客户管理",
            "description": json.loads((FIXTURES / "baidu_detail_crm.json").read_text())["result"]["product"][
                "productInfo"
            ]["digest"],
            "publisher": "上海美橙科技信息发展有限公司",
            "url": f"{SITE}/detail/{PIDS['crm']}",
            "delivery": "saas",
            "marketplace_categories": ["企业应用", "销售管理"],
            "marketplace_category_paths": [{"path": ["企业应用", "销售管理"], "id": "115004"}],
            "categories": ["end-user-software"],
        }
    ]
    (related,) = requests(results)
    assert results[-1] is related
    assert (related.url, related.priority) == (f"{SITE}/api/market/web/product/{PIDS['crm']}/related", 4)
    assert related.meta == {"kind": "related", "product": PIDS["crm"]}


@pytest.mark.parametrize(
    ("name", "delivery", "categories", "audiences", "cid"),
    [
        ("image", "virtual-machine", ["镜像环境", "基础环境"], ["developer-tool"], "110001"),
        ("ai_api", "api", ["API服务", "人工智能"], ["developer-tool", "end-user-software"], "130009"),
        ("on_premises", "download", ["人工智能", "软件服务"], ["developer-tool", "end-user-software"], "135001"),
    ],
)
async def test_delivery_and_audiences(
    fresh: BaiduMarketplaceCrawler,
    crawl_page: CrawlPage,
    name: str,
    delivery: str,
    categories: List[str],
    audiences: List[str],
    cid: str,
) -> None:
    (software,) = items(await crawl_page(fresh, detail_page(name)))

    assert (software["delivery"], software["marketplace_categories"], software["categories"]) == (
        delivery,
        categories,
        audiences,
    )
    assert software["marketplace_category_paths"] == [{"path": categories, "id": cid}]


@pytest.mark.parametrize(
    ("name", "message"),
    [
        (
            "data_api",
            "Skipping the baidu-marketplace product '今日油价 全国油价查询 汽油价格查询 柴油价格查询', not a ",
        ),
        (
            "company_service",
            "Skipping the baidu-marketplace product '濮阳公司注册商标高新企业IDC证文网文ISO环境质量体系",
        ),
        ("security_service", "Skipping the baidu-marketplace product '系统安全优化  木马病毒清除', a security service"),
        ("delisted", f"Skipping the baidu-marketplace product {PIDS['delisted']}, delisted."),
    ],
)
async def test_services_data_apis_and_delisted_products_are_skipped(
    fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, name: str, message: str
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    assert await crawl_page(fresh, detail_page(name)) == []
    assert any(record.startswith(message) for record in caplog.messages)


async def test_missing_details_are_skipped(
    fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    assert await crawl_page(fresh, detail_page("missing", "Not found", status=404)) == []
    assert await crawl_page(fresh, detail_page("empty", '{"result": {"errCode": "", "product": {}}}')) == []
    assert "Skipping the baidu-marketplace product missing (HTTP 404)." in caplog.messages
    assert "Skipping the baidu-marketplace product empty, no detail ()." in caplog.messages


async def test_malformed_details(fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    bare = {"result": {"product": {"productInfo": {"title": "Bare", "digest": "Bare product"}, "crumbInfo": [3]}}}
    odd = {"result": {"product": {"productInfo": {"title": "Odd", "digest": "Odd", "deliveryMethod": "TELEPORT"}}}}

    results = await crawl_page(fresh, detail_page("bare", json.dumps(bare)))
    results += await crawl_page(fresh, response(f"{SITE}/x", json.dumps(odd), {"kind": "detail"}))

    assert [(item["name"], item["url"], item["delivery"], item["publisher"]) for item in items(results)] == [
        ("Bare", f"{SITE}/detail/bare", "other", None),
        ("Odd", None, "other", None),
    ]
    assert [request.url for request in requests(results)] == [f"{SITE}/api/market/web/product/bare/related"]
    assert all("marketplace_category_paths" not in item for item in items(results))


async def test_not_json_detail_is_an_error(
    fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(CatalogueFormatError, match="unexpected catalogue format"):
        await crawl_page(fresh, detail_page("broken", "<html></html>"))

    assert any(record.levelname == "ERROR" for record in caplog.records)


async def test_related_products_are_requested(fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    fresh.requested_products.add("e571382b-2913-4b9e-a36b-c71cc0b3bcee")
    related = page(f"{SITE}/api/market/web/product/{PIDS['crm']}/related", "baidu_related.json", "related")

    results = await crawl_page(fresh, related)

    assert [request.url for request in requests(results)] == [
        detail_url("fe9f23ef-9f20-4c20-ac0a-329cd2cde40f"),
        detail_url("f9719c1f-9fcf-4475-89eb-8b8a5254e075"),
        detail_url("c657cf73-cd35-409e-b072-637bd8f0640f"),
        detail_url("65be7c72-9604-4161-a24c-62a9767f0df5"),
        detail_url("fc95b2ea-bd9a-45b4-a2b8-67eb51a170b8"),
    ]
    assert {request.priority for request in requests(results)} == {6}


async def test_page_limit_caps_the_details(
    fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    fresh.requested_products.update(str(number) for number in range(49))

    with patch.object(BaiduMarketplaceCrawler, "page_limit", 1):
        results = await crawl_page(fresh, page(SITEMAP_URL, "baidu_sitemap.xml", "sitemap"))
        detail = await crawl_page(fresh, detail_page("crm"))

    assert len(requests(results)) == 1
    assert len(items(detail)) == 1
    assert requests(detail) == []
    assert any(
        message.startswith("Page limit (1) reached: the baidu-marketplace product") for message in caplog.messages
    )


async def test_failed_responses_request_nothing(
    fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    failed = response(SITEMAP_URL, "Server error", {"kind": "sitemap"}, status=500)

    assert await crawl_page(fresh, failed) == []
    assert "The baidu-marketplace sitemap response https://market.baidu.com/sitemap.xml failed (HTTP 500)." in [
        record.message for record in caplog.records if record.levelname == "WARNING"
    ]


async def test_unknown_responses_request_nothing(fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    assert await crawl_page(fresh, response(f"{SITE}/home", "<html></html>", {})) == []


@pytest.mark.parametrize("content", ['{"result": []}', "{}"])
async def test_empty_lists_request_nothing(fresh: BaiduMarketplaceCrawler, crawl_page: CrawlPage, content: str) -> None:
    listed = await crawl_page(fresh, response(f"{SITE}/api/market/web/list/1/products", content, {"kind": "list"}))
    related = await crawl_page(
        fresh, response(f"{SITE}/api/market/web/product/1/related", content, {"kind": "related"})
    )

    assert listed == related == []


async def test_on_start_forgets_the_requested_products(fresh: BaiduMarketplaceCrawler) -> None:
    fresh.requested_products.add("pid")

    await fresh.on_start(resuming=True)
    assert fresh.requested_products == {"pid"}
    await fresh.on_start()
    assert fresh.requested_products == set()
