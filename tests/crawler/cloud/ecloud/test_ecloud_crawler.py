from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.ecloud.crawler import ChinaMobileCloudCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
MENU_URL = "https://ecloud.10086.cn/api/query/menu/v4/menu/tree?situationCode=product"
TEMPLATE_URL = "https://ecloud.10086.cn/api/query/template-delivery/application/detail?group=product-gray&type=hotCase"
CLAW_URL = "https://ecloud.10086.cn/portal/product/hotCase"
TEMPLATE_META: Dict[str, JsonValue] = {
    ChinaMobileCloudCrawler.TEMPLATE_PRODUCT: CLAW_URL,
    ChinaMobileCloudCrawler.PRODUCT_NAME: "MobileClaw",
    BaseCloudCrawler.PRODUCT_CATEGORIES: ["MaaS"],
}


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def menu_page(*nodes: JsonValue) -> Response:
    menu = {"state": "OK", "body": [{"situationCode": "product", "bindData": list(nodes)}]}
    return page(MENU_URL, json.dumps(menu, ensure_ascii=False))


def node(name: str, *metadata: JsonValue, children: Optional[List[JsonValue]] = None, kind: str = "") -> JsonValue:
    return {"name": name, "type": kind or None, "bindMetadatas": list(metadata), "children": children or []}


def entry(name: str, slug: Optional[str], description: str = "产品介绍", **fields: str) -> Dict[str, JsonValue]:
    return {"id": f"id-{name}", "name": name, "type": slug, "sDesc": description, **fields}


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def test_configuration() -> None:
    crawler = ChinaMobileCloudCrawler()

    assert crawler.name == "ecloud"
    assert ChinaMobileCloudCrawler.catalogue_url == MENU_URL
    assert ChinaMobileCloudCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"ecloud.10086.cn"}
    assert crawler.download_delay == 3.0
    assert ChinaMobileCloudCrawler.name_prefixes == ("移动云", "中国移动", "和云")


async def test_extracts_the_menu_products(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(ChinaMobileCloudCrawler(), make_response(MENU_URL, "ecloud_menu.json"))

    assert names(results) == [
        "AIGC内容创作平台 Art Studio",
        "科学智能算力服务",
        "云主机 ECS",
        "移动模型服务平台MoMA",
        "AI原生行业智能体",
        "桌面垂类智能体",
        "云电脑",
        "智能体枢纽",
        "AI巡考服务",
        "文字识别OCR",
        "弹性伸缩 EAS",
        "裸金属服务器 BMS",
        "云电脑\uff08办公型\uff09",
        "云电脑\uff08行业型\uff09",
        "云电脑硬件终端",
        "云迁移中心",
        "云监控",
        "云审计 Audit",
        "云日志",
        "中国移动CDN",
        "边缘智能云EIC",
        "边缘智能小站EIS",
        "数字内容生产线MetaStudio",
        "弹性伸缩",
        "镜像服务 IMS",
        "IPsec VPN",
        "云解析服务DNS",
    ]
    assert results[2] == {
        "name": "云主机 ECS",
        "description": "通过虚拟化技术整合IT 资源\uff0c为客户提供按需使用的计算资源服务",
        "pricing_policy": [],
        "url": "https://ecloud.10086.cn/portal/product/vm",
        "catalogue_categories": ["弹性计算", "云服务器"],
    }


async def test_menu_products_carry_the_categories_of_every_place_they_are_listed_in(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(ChinaMobileCloudCrawler(), make_response(MENU_URL, "ecloud_menu.json"))

    categories = {result["name"]: result.get("catalogue_categories") for result in results if isinstance(result, dict)}
    assert categories["移动模型服务平台MoMA"] == ["MaaS"]
    assert categories["云电脑"] == ["AI SaaS"]
    assert categories["云电脑\uff08办公型\uff09"] == ["弹性计算", "云电脑"]
    assert categories["云审计 Audit"] == ["开发与运维", "管理与监控"]
    assert categories["数字内容生产线MetaStudio"] == ["和云"]
    assert categories["IPsec VPN"] == ["和云", "云网络"]
    assert categories["AIGC内容创作平台 Art Studio"] is None


async def test_entries_without_identifier_are_merged_by_name(crawl_page: CrawlPage) -> None:
    gpu: JsonValue = {"name": "GPU云主机", "type": "gpu", "sDesc": "GPU算力"}
    menu = menu_page(
        node("弹性计算", children=[node("云服务器", gpu)]),
        node("人工智能", children=[node("智算", gpu)]),
    )

    results = await crawl_page(ChinaMobileCloudCrawler(), menu)

    assert [result.get("catalogue_categories") for result in results if isinstance(result, dict)] == [
        ["弹性计算", "云服务器", "人工智能", "智算"]
    ]


@pytest.mark.parametrize(
    ("name", "url", "description"),
    [
        ("云电脑", "https://ecloud.10086.cn/portal/product/computer", "智慧赋能、即开即用、全域安全"),
        ("云迁移中心", "https://ecloud.10086.cn/portal/product/cmc", None),
        ("云解析服务DNS", "https://heyun.cmecloud.cn/#/product/dns", None),
    ],
    ids=["placeholder-description", "relative-link", "co-branded"],
)
async def test_menu_entry_fields(
    make_response: MakeResponse, crawl_page: CrawlPage, name: str, url: str, description: Optional[str]
) -> None:
    results = await crawl_page(ChinaMobileCloudCrawler(), make_response(MENU_URL, "ecloud_menu.json"))

    product = next(result for result in results if isinstance(result, dict) and result["name"] == name)
    assert product["url"] == url
    assert description is None or product["description"] == description


@pytest.mark.parametrize("excluded", ["中国移动安全专区", "中国移动信创专区", "MobileClaw"])
async def test_promotions_and_placeholders_are_not_streamed(
    make_response: MakeResponse, crawl_page: CrawlPage, excluded: str
) -> None:
    results = await crawl_page(ChinaMobileCloudCrawler(), make_response(MENU_URL, "ecloud_menu.json"))

    assert excluded not in names(results)


async def test_recommended_products_are_streamed_once(
    make_response: MakeResponse, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="scrapling.spiders.ecloud")

    results = await crawl_page(ChinaMobileCloudCrawler(), make_response(MENU_URL, "ecloud_menu.json"))

    assert (names(results).count("云主机 ECS"), names(results).count("移动模型服务平台MoMA")) == (1, 1)
    assert "Skipping the menu entry '云主机 ECS', already listed." in [record.getMessage() for record in caplog.records]


async def test_requests_the_templates_of_the_placeholder_products(
    make_response: MakeResponse, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    results = await crawl_page(ChinaMobileCloudCrawler(), make_response(MENU_URL, "ecloud_menu.json"))

    assert [(request.url, request.meta) for request in requests(results)] == [(TEMPLATE_URL, TEMPLATE_META)]
    assert caplog.records[-1].getMessage() == "1 ecloud page templates to read for the products without description."


async def test_template_product(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(TEMPLATE_URL, "ecloud_template.json")
    response.meta.update(TEMPLATE_META)

    results = await crawl_page(ChinaMobileCloudCrawler(), response)

    products = [result for result in results if isinstance(result, dict)]
    assert (len(results), [(product["name"], product["url"]) for product in products]) == (
        1,
        [("MobileClaw", CLAW_URL)],
    )
    assert str(products[0]["description"]).startswith("一位住在您设备里的全能数字员工")
    assert products[0]["catalogue_categories"] == ["MaaS"]
    assert "added_at" not in products[0]


async def test_template_dates(crawl_page: CrawlPage) -> None:
    template = json.dumps(
        {
            "body": {
                "seoDescription": "个人AI操作系统",
                "createDate": "2025-03-01 10:00:00",
                "updateDate": 1760000000000,
            }
        },
        ensure_ascii=False,
    )

    results = await crawl_page(ChinaMobileCloudCrawler(), page(TEMPLATE_URL, template, TEMPLATE_META))

    assert [
        (result.get("added_at"), result.get("added_caveat"), result.get("updated_caveat"))
        for result in results
        if isinstance(result, dict)
    ] == [("2025-03-01T10:00:00Z", "page-published", "page-modified")]


async def test_unknown_template_is_skipped(
    make_response: MakeResponse, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="scrapling.spiders.ecloud")
    response = make_response(TEMPLATE_URL, "ecloud_template_unknown.json")
    response.meta.update(TEMPLATE_META)

    assert await crawl_page(ChinaMobileCloudCrawler(), response) == []
    assert caplog.records[-1].getMessage() == (
        f"Skipping the product 'MobileClaw', its page template {TEMPLATE_URL} is unknown."
    )


async def test_template_of_a_streamed_product_is_skipped(crawl_page: CrawlPage) -> None:
    crawler = ChinaMobileCloudCrawler()
    template = '{"state": "OK", "body": {"seoDescription": "个人AI操作系统"}}'
    await crawl_page(crawler, page(TEMPLATE_URL, template, TEMPLATE_META))

    assert await crawl_page(crawler, page(TEMPLATE_URL, template, TEMPLATE_META)) == []


async def test_template_requests_are_deduplicated(crawl_page: CrawlPage) -> None:
    crawler = ChinaMobileCloudCrawler()
    crawler._remember(["已发布"])
    menu = menu_page(
        node(
            "推荐产品",
            entry("云主机 ECS", "vm"),
            {"name": "无标识产品", "type": "noid", "sDesc": "没有标识的产品"},
            entry("MobileClaw", "hotCase", "热门产品\uff0c展示推荐菜单"),
            {**entry("MobileClaw", "hotCase", "热门产品\uff0c展示推荐菜单"), "id": "other-id"},
            entry("云电脑", "computer", "云电脑产品总介绍页", brief="产品菜单"),
            entry("云主机", "vm", "", introduceUrl="/portal/product/vm"),
            entry("已发布", "published", ""),
            entry("", "nameless", ""),
            entry("无类型", None, "", introduceUrl="https://ecloud.10086.cn/portal/product/notype"),
        )
    )

    results = await crawl_page(crawler, menu)

    assert names(results) == ["云主机 ECS", "无标识产品"]
    assert [(request.url, request.meta[ChinaMobileCloudCrawler.PRODUCT_NAME]) for request in requests(results)] == [
        (TEMPLATE_URL, "MobileClaw"),
        (TEMPLATE_URL.replace("hotCase", "computer"), "云电脑"),
    ]


async def test_co_branded_node_is_processed_last(crawl_page: CrawlPage) -> None:
    menu = menu_page(
        node(
            "和云", entry("弹性伸缩", "h-autoscaling", introduceUrl="https://heyun.cmecloud.cn/#/product/autoscaling")
        ),
        node(
            "弹性计算",
            children=[node("云服务器", entry("弹性伸缩", "autoscaling"), entry("云主机", "vm"))],
        ),
        node("和云", entry("云主机", "h-vm", introduceUrl="https://heyun.cmecloud.cn/#/product/vm")),
    )

    results = await crawl_page(ChinaMobileCloudCrawler(), menu)

    assert [(result["name"], result["url"]) for result in results if isinstance(result, dict)] == [
        ("弹性伸缩", "https://ecloud.10086.cn/portal/product/autoscaling"),
        ("云主机", "https://ecloud.10086.cn/portal/product/vm"),
    ]


@pytest.mark.parametrize(
    ("first", "second", "same"),
    [
        ("https://heyun.cmecloud.cn/#/product/vm", "https://heyun.cmecloud.cn/#/product/gpu", False),
        ("https://heyun.cmecloud.cn/#/product/vm/", "https://heyun.cmecloud.cn/#/product/VM", True),
        ("https://ecloud.10086.cn/portal/product/vm#price", "https://ecloud.10086.cn/portal/product/vm", True),
    ],
)
def test_url_keys_keep_the_fragment_routes(first: str, second: str, same: bool) -> None:
    crawler = ChinaMobileCloudCrawler()

    assert (crawler._url_key(first) == crawler._url_key(second)) is same


@pytest.mark.parametrize(
    ("first", "second", "same"),
    [
        ("云电脑\uff08办公型\uff09", "云电脑\uff08行业型\uff09", False),
        ("云电脑(办公型)", "云电脑", False),
        ("移动云 云主机", "和云云主机", True),
        ("移动模型服务平台MoMA", "模型服务平台MoMA", False),
    ],
)
def test_names_keep_their_edition_and_the_short_brands(first: str, second: str, same: bool) -> None:
    crawler = ChinaMobileCloudCrawler()

    assert (crawler._name_key(first) == crawler._name_key(second)) is same


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("", "the page is not JSON"),
        ("<html><body>Bad gateway</body></html>", "the page is not JSON"),
        ("[]", "the page is not a JSON object"),
    ],
    ids=["dropped", "html", "array"],
)
@pytest.mark.parametrize("meta", [{}, TEMPLATE_META], ids=["menu", "template"])
async def test_empty_or_invalid_response_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, content: str, reason: str, meta: Dict[str, JsonValue]
) -> None:
    url = TEMPLATE_URL if meta else MENU_URL

    with pytest.raises(CatalogueFormatError, match=reason):
        await crawl_page(ChinaMobileCloudCrawler(), page(url, content, dict(meta)))

    assert caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].getMessage().startswith(f"The ecloud page {url} is not")


@pytest.mark.parametrize(
    "menu",
    [
        {"state": "OK"},
        {"state": "OK", "body": {"situationCode": "product"}},
        {"state": "OK", "body": [{"situationCode": "solution", "bindData": [{"name": "解决方案"}]}]},
        {"state": "OK", "body": [{"situationCode": "product", "bindData": []}]},
    ],
    ids=["no-body", "body-object", "no-product-situation", "empty"],
)
async def test_menu_without_product_nodes_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, menu: JsonValue
) -> None:
    with pytest.raises(CatalogueFormatError, match="product menu nodes"):
        await crawl_page(ChinaMobileCloudCrawler(), page(MENU_URL, json.dumps(menu)))

    assert caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].getMessage() == f"The ecloud menu {MENU_URL} has no product nodes (`bindData`)."


async def test_menu_without_product_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    menu = menu_page(
        node("营销活动", entry("安全专区", None, introduceUrl="/portal/act/anquanzhuanqu"), kind="card"),
        {"name": "空", "bindMetadatas": None, "children": None},
        node("推荐产品", "not an entry", entry("", "empty")),
    )

    with pytest.raises(EmptyCatalogueError):
        await crawl_page(ChinaMobileCloudCrawler(), menu)

    assert caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].getMessage() == f"The ecloud catalogue page {MENU_URL} holds no product."
