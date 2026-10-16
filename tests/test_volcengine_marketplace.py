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
from crawler.cloud.volcengine.marketplace import VolcanoEngineMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parent / "fixtures" / "marketplace"
API = "https://market.volcengine.com/eco_apis_sinf/agw/marketplace_portal"
LIST_URL = f"{API}/ListProduct?Action=ListProduct&Version=2025-01-01"
CATEGORY_URL = f"{API}/QueryFrontCategory?Action=QueryFrontCategory&Version=2025-01-01"
LOGGER = "scrapling.spiders.volcengine-marketplace"


@pytest.fixture(scope="module")
def crawler() -> VolcanoEngineMarketplaceCrawler:
    return VolcanoEngineMarketplaceCrawler(classifier=SoftwareClassifier())


@pytest.fixture
def fresh(crawler: VolcanoEngineMarketplaceCrawler) -> VolcanoEngineMarketplaceCrawler:
    crawler.software_categories.clear()
    crawler.category_names.clear()
    return crawler


def response(content: Union[str, bytes], meta: Optional[Dict[str, JsonValue]] = None, url: str = LIST_URL) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def fixture_page(fixture: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return response((FIXTURES / fixture).read_bytes(), meta)


def products_page(
    products: List[JsonValue], total: JsonValue = 2, meta: Optional[Dict[str, JsonValue]] = None
) -> Response:
    return response(json.dumps({"Result": {"List": products, "Total": total}}), meta)


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [item["name"] for item in items(results)]


def test_configuration(crawler: VolcanoEngineMarketplaceCrawler) -> None:
    assert crawler.name == "volcengine-marketplace"
    assert VolcanoEngineMarketplaceCrawler.catalogue_url == LIST_URL
    assert VolcanoEngineMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"market.volcengine.com"}


async def test_start_requests(crawler: VolcanoEngineMarketplaceCrawler) -> None:
    categories, first = [request async for request in crawler.start_requests()]

    assert (categories.url, categories.priority, categories.meta) == (
        CATEGORY_URL,
        11,
        {"categories": True, "may_be_empty": True},
    )
    assert categories._session_kwargs == {"method": "POST", "json": {}, "headers": None}
    assert (first.url, first.priority, first.meta, first.sid) == (
        LIST_URL,
        10,
        {"page": 1},
        "volcengine-marketplace-http",
    )
    assert first._session_kwargs == {"method": "POST", "json": {"Offset": 0, "Limit": 100}, "headers": None}


async def test_extracts_the_software(fresh: VolcanoEngineMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, fixture_page("volcengine_products_page1.json", {"page": 1}))

    assert names(results) == [
        "CentOS_7.9_64位",
        "掌乐爆款游戏创作平台-SAAS",
        "OceanBase 软件订阅产品",
        "WordPress_V6.9_企业建站博客系统_宝塔_v10.0.2_LTS_Ubuntu_24.04_LTS",
        "物流轨迹实时查询与订阅推送API",
        "【快递100MCP】",
        "【墨迹天气气象】插件",
        "【领星ERP】",
    ]
    assert items(results)[0] == {
        "name": "CentOS_7.9_64位",
        "description": (
            "镜像系统是CentOS 7.9 64位\uff0c预装了火山云平台密码重置插件\uff0c云助手插件和云监控插件\uff0c"
            "可以免费使用\uff0c"
            "免费镜像不提供技术支持。客服QQ 2848896073"
        ),
        "publisher": "四川早耕鸟科技有限公司",
        "url": "https://market.volcengine.com/goods/detail?goodsId=wysf9000307",
        "delivery": "virtual-machine",
        "marketplace_categories": ["镜像专区", "操作系统"],
        "categories": ["developer-tool"],
        "types": ["operating-system"],
        "added_at": "2026-09-23T14:40:10Z",
    }
    assert "added_at" not in items(results)[1]


async def test_services_are_excluded(
    fresh: VolcanoEngineMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    results = await crawl_page(fresh, fixture_page("volcengine_products_page1.json"))

    assert "开源软件部署与配置服务" not in names(results)
    assert "Skipping the volcengine-marketplace product '开源软件部署与配置服务', a service." in caplog.messages


@pytest.mark.parametrize(
    ("name", "delivery", "types"),
    [
        ("掌乐爆款游戏创作平台-SAAS", "saas", ["ai-ml"]),
        ("OceanBase 软件订阅产品", "download", ["database"]),
        (
            "WordPress_V6.9_企业建站博客系统_宝塔_v10.0.2_LTS_Ubuntu_24.04_LTS",
            "virtual-machine",
            ["cms", "devops"],
        ),
        ("物流轨迹实时查询与订阅推送API", "api", ["supply-chain", "api-management"]),
        ("【快递100MCP】", "api", ["api-management"]),
        ("【墨迹天气气象】插件", "api", ["api-management"]),
        ("【领星ERP】", "saas", ["erp", "ecommerce"]),
    ],
)
async def test_delivery_and_types(
    fresh: VolcanoEngineMarketplaceCrawler, crawl_page: CrawlPage, name: str, delivery: str, types: List[str]
) -> None:
    results = await crawl_page(fresh, fixture_page("volcengine_products_page1.json"))
    software = next(item for item in items(results) if item["name"] == name)

    actual = software["types"]
    assert software["delivery"] == delivery
    assert isinstance(actual, list)
    assert [kind for kind in types if kind not in actual] == [], actual


async def test_requests_the_next_page(fresh: VolcanoEngineMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, fixture_page("volcengine_products_page1.json", {"page": 1}))

    (request,) = requests(results)
    assert results[-1] is request
    assert (request.url, request.priority, request.meta) == (LIST_URL, 10, {"page": 2, "may_be_empty": True})
    assert request._session_kwargs == {"method": "POST", "json": {"Offset": 100, "Limit": 100}, "headers": None}


async def test_last_page_requests_nothing(fresh: VolcanoEngineMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, fixture_page("volcengine_products_last.json", {"page": 3, "may_be_empty": True}))

    assert names(results) == ["【千机盒】电商财务管理系统", "【网易七鱼客服机器人】全链路产品"]
    assert requests(results) == []


async def test_page_limit_stops_the_pagination(fresh: VolcanoEngineMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    with patch.object(VolcanoEngineMarketplaceCrawler, "page_limit", 1):
        results = await crawl_page(fresh, fixture_page("volcengine_products_page1.json", {"page": 1}))

    assert requests(results) == []
    assert len(items(results)) == 8


async def test_reads_the_category_tree(fresh: VolcanoEngineMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        fresh, response((FIXTURES / "volcengine_categories.json").read_bytes(), {"categories": True}, CATEGORY_URL)
    )

    assert results == []
    assert len(fresh.category_names) == 55
    assert (fresh.category_names[10006], fresh.category_names[20030]) == ("镜像专区", "操作系统")


async def test_categories_are_named_from_the_tree(
    fresh: VolcanoEngineMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    await crawl_page(fresh, response((FIXTURES / "volcengine_categories.json").read_bytes(), {"categories": True}))
    product: JsonValue = {
        "ProductBasic": {
            "Product": "wysf1",
            "ProductTitle": "Acme",
            "ProductDesc": "Acme OS image",
            "FrontendCategoryL1": 10006,
            "FrontendCategoryL2": 99999,
            "DeliverType": 5,
        },
        "ProductInfo": {"Shop": {"SrvAccountVerifyName": " ", "Shop": "Acme Shop"}},
    }

    (software,) = items(await crawl_page(fresh, products_page([product], total=1)))

    assert (software["marketplace_categories"], software["publisher"], software["delivery"]) == (
        ["镜像专区"],
        "Acme Shop",
        "virtual-machine",
    )


async def test_malformed_products(fresh: VolcanoEngineMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        fresh,
        products_page(
            [
                {
                    "ProductBasic": {
                        "ZhName": "Bare",
                        "ProductDesc": "Bare product",
                        "DeliverType": 9,
                        "CreatedTime": "someday",
                    }
                },
                {
                    "ProductBasic": {"ProductTitle": "Odd", "ProductDesc": "Odd product", "DeliverType": "1"},
                    "ProductInfo": {"CreatedTime": 1790000000},
                },
                {"ProductBasic": {"ProductTitle": "No description"}, "ProductInfo": {"Product": "wysf2"}},
                "not a product",
            ],
            total="2",
        ),
    )

    assert [(item["name"], item["delivery"], item["url"], item["publisher"]) for item in items(results)] == [
        ("Bare", "other", None, None),
        ("Odd", "other", None, None),
    ]
    assert [item.get("added_at") for item in items(results)] == [None, "2026-09-21T14:13:20Z"]
    assert requests(results) == []


async def test_empty_first_page_is_an_error(
    fresh: VolcanoEngineMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError, match="no product found"):
        await crawl_page(fresh, products_page([], total=0))

    assert any(record.levelname == "ERROR" and "holds no software" in record.message for record in caplog.records)


async def test_empty_next_page_is_the_end(fresh: VolcanoEngineMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    assert await crawl_page(fresh, products_page([], total=500, meta={"page": 2, "may_be_empty": True})) == []


@pytest.mark.parametrize("content", ['{"Result": {"Total": 228}}', "[]", "<html></html>"])
@pytest.mark.parametrize("meta", [{}, {"categories": True}])
async def test_unexpected_response_is_an_error(
    fresh: VolcanoEngineMarketplaceCrawler,
    crawl_page: CrawlPage,
    caplog: pytest.LogCaptureFixture,
    content: str,
    meta: Dict[str, JsonValue],
) -> None:
    with pytest.raises(CatalogueFormatError, match="unexpected catalogue format"):
        await crawl_page(fresh, response(content, meta))

    assert any(record.levelname == "ERROR" for record in caplog.records)


async def test_on_start_forgets_the_categories(fresh: VolcanoEngineMarketplaceCrawler) -> None:
    fresh.category_names[1] = "Old"

    await fresh.on_start(resuming=True)
    assert fresh.category_names == {1: "Old"}
    await fresh.on_start()
    assert fresh.category_names == {}


async def test_malformed_categories_are_ignored(fresh: VolcanoEngineMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    children: JsonValue = [{"ID": 3, "CategoryNameCN": "Leaf"}]
    tree = {
        "Result": {
            "List": [{"ID": "1", "CategoryNameCN": "Text"}, {"ID": 2, "CategoryNameCN": " ", "Children": children}]
        }
    }

    assert await crawl_page(fresh, response(json.dumps(tree), {"categories": True}, CATEGORY_URL)) == []
    assert fresh.category_names == {3: "Leaf"}


@pytest.mark.parametrize(
    ("title", "kept"),
    [
        ("开源软件部署与配置服务", False),
        ("服务器代维服务", False),
        ("Websoft9多应用托管平台-运维面板-服务器管理", True),
        ("中国天气智能体MCP服务", True),
    ],
)
async def test_service_titles(
    fresh: VolcanoEngineMarketplaceCrawler, crawl_page: CrawlPage, title: str, kept: bool
) -> None:
    product: JsonValue = {"ProductBasic": {"ProductTitle": title, "ProductDesc": "Description"}}

    results = await crawl_page(fresh, products_page([product], total=1, meta={"may_be_empty": True}))

    assert names(results) == ([title] if kept else [])
