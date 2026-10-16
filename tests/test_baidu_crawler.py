from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.baidu.crawler import BaiduAICloudCrawler
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
CATALOGUE_URL = "https://cloud.baidu.com/products/index.html"
BODY_URL = "https://cloud.baidu.com/product/body"
AVATAR_URL = "https://cloud.baidu.com/product/huiboxing-api.html"


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def catalogue_page(groups: JsonValue) -> Response:
    script = json.dumps({"props": {"pageProps": {"newProductsList": groups}}}, ensure_ascii=False)
    return page(CATALOGUE_URL, f'<html><body><script id="__NEXT_DATA__" type="application/json">{script}</script>')


def sub_categories(*entries: JsonValue) -> JsonValue:
    return [{"name": "云计算", "categories": [{"category": "计算", "list": list(entries)}]}]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def test_configuration() -> None:
    crawler = BaiduAICloudCrawler()

    assert crawler.name == "baidu"
    assert BaiduAICloudCrawler.catalogue_url == CATALOGUE_URL
    assert BaiduAICloudCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"cloud.baidu.com"}
    assert BaiduAICloudCrawler.name_prefixes == ("百度智能云", "百度", "Baidu AI Cloud ", "Baidu ")


async def test_extracts_the_catalogue_products(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(BaiduAICloudCrawler(), make_response(CATALOGUE_URL, "baidu_products.html"))

    assert names(results) == [
        "百度千帆·大模型服务及Agent开发平台",
        "百度胜算·数据智能平台",
        "视觉应用平台",
        "AgentWorks",
        "百度伐谋",
        "秒哒",
        "RedClaw",
        "百度智能云福宝",
        "端到端语音语言大模型",
        "大模型声音复刻",
        "大模型语音合成",
        "AI翻译配音",
        "呼叫中心语音解决方案",
        "语音私有化部署方案",
        "短文本语音合成",
        "智慧招采",
        "GPU云服务器",
        "云服务器 BCC",
        "轻量应用服务器",
        "对象存储 BOS",
        "云磁盘",
    ]
    assert results[17] == {
        "name": "云服务器 BCC",
        "description": "构建可弹性伸缩云计算服务\uff0c提供超高效费比的高性能云服务器",
        "pricing_policy": [],
        "url": "https://cloud.baidu.com/product/bcc.html",
    }


@pytest.mark.parametrize(
    "excluded",
    ["智能语音会议解决方案", "有声阅读解决方案", "合同审查", "文档抽取", "NineData SQL 开发", "技能开发平台"],
)
async def test_non_products_and_duplicates_are_filtered_out(
    make_response: MakeResponse, crawl_page: CrawlPage, excluded: str
) -> None:
    results = await crawl_page(BaiduAICloudCrawler(), make_response(CATALOGUE_URL, "baidu_products.html"))

    assert excluded not in names(results)


async def test_requests_the_pages_of_the_sub_categories_without_products(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(BaiduAICloudCrawler(), make_response(CATALOGUE_URL, "baidu_products.html"))

    assert [(request.url, request.meta) for request in requests(results)] == [
        (
            AVATAR_URL,
            {BaiduAICloudCrawler.PRODUCT_PAGE: AVATAR_URL, BaiduAICloudCrawler.PRODUCT_NAME: "百度一镜数字人"},
        ),
        (BODY_URL, {BaiduAICloudCrawler.PRODUCT_PAGE: BODY_URL, BaiduAICloudCrawler.PRODUCT_NAME: "人体与行为分析"}),
    ]


async def test_skipped_page_requests_are_logged(
    make_response: MakeResponse, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="scrapling.spiders.baidu")

    await crawl_page(BaiduAICloudCrawler(), make_response(CATALOGUE_URL, "baidu_products.html"))

    messages = [record.getMessage() for record in caplog.records]
    assert "Not requesting the product page https://www.miaoda.cn/ of '秒哒', outside of the website." in messages
    assert "2 baidu product pages to read for the sub-categories." in messages


async def test_padded_links_are_trimmed(crawl_page: CrawlPage) -> None:
    entries: List[JsonValue] = [
        {
            "type": "语音",
            "link": "",
            "products": [
                {
                    "name": "长文本语音合成",
                    "desc": "长文本",
                    "link": " %20https://cloud.baidu.com/product/SPEECH/long_tts.html%20 ",
                }
            ],
        },
        {"type": "语音识别", "link": "%20https://cloud.baidu.com/product/SPEECH/vpr.html "},
    ]

    results = await crawl_page(BaiduAICloudCrawler(), catalogue_page(sub_categories(*entries)))

    assert [result["url"] for result in results if isinstance(result, dict)] == [
        "https://cloud.baidu.com/product/SPEECH/long_tts.html"
    ]
    assert [request.url for request in requests(results)] == ["https://cloud.baidu.com/product/SPEECH/vpr.html"]


async def test_sub_categories_without_link_or_with_a_solution_link_are_not_requested(crawl_page: CrawlPage) -> None:
    entries: List[JsonValue] = [
        {"type": "云服务器", "link": "", "products": [{"name": "云服务器 BCC", "desc": "弹性计算", "link": None}]},
        {"type": "专属服务器", "link": "", "products": [{"name": "专属服务器", "desc": "", "link": None}]},
        {"type": "边缘计算", "link": "https://cloud.baidu.com/solution/bianyuanjisuan.html"},
        {"type": "智能硬件", "link": None},
        {"type": "合同审查", "link": "https://console.bce.baidu.com/textmind/"},
        "not a sub-category",
    ]

    results = await crawl_page(BaiduAICloudCrawler(), catalogue_page(sub_categories(*entries)))

    assert (names(results), requests(results)) == (["云服务器 BCC"], [])
    assert [result["url"] for result in results if isinstance(result, dict)] == [None]


async def test_product_page(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(BODY_URL, "baidu_product_page.html")
    response.meta.update(
        {BaiduAICloudCrawler.PRODUCT_PAGE: BODY_URL, BaiduAICloudCrawler.PRODUCT_NAME: "人体与行为分析"}
    )

    results = await crawl_page(BaiduAICloudCrawler(), response)

    assert results == [
        {
            "name": "人体与行为分析",
            "description": "百度AI人体分析,准确识别图像中的人体相关信息,提供人体检测与追踪,关键点定位,人流量统计,"
            "属性识别,行为分析,人像分割,手势识别等能力.",
            "pricing_policy": [],
            "url": BODY_URL,
        }
    ]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("云服务器BCC_云主机_虚拟主机_弹性服务器-百度智能云", "云服务器BCC"),
        ("对象存储 BOS -百度智能云", "对象存储 BOS"),
        ("云磁盘", "云磁盘"),
    ],
)
async def test_product_page_title_without_listing_name(crawl_page: CrawlPage, title: str, expected: str) -> None:
    head = f'<meta property="og:title" content="{title}"><meta name="description" content="A product.">'
    response = page(BODY_URL, f"<html><head>{head}</head></html>", {BaiduAICloudCrawler.PRODUCT_PAGE: BODY_URL})

    assert names(await crawl_page(BaiduAICloudCrawler(), response)) == [expected]


@pytest.mark.parametrize(
    "groups",
    [[], {"name": "人工智能"}, None],
    ids=["empty", "object", "missing"],
)
async def test_page_without_catalogue_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, groups: JsonValue
) -> None:
    with pytest.raises(CatalogueFormatError, match="`newProductsList` catalogue is missing"):
        await crawl_page(BaiduAICloudCrawler(), catalogue_page(groups))

    assert caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].getMessage() == f"The baidu page {CATALOGUE_URL} has no `newProductsList` catalogue."


async def test_page_without_next_data_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(CatalogueFormatError, match="`__NEXT_DATA__` script is missing"):
        await crawl_page(BaiduAICloudCrawler(), page(CATALOGUE_URL, "<html><body></body></html>"))

    assert caplog.records[-1].levelno == logging.ERROR


async def test_catalogue_without_product_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    groups: JsonValue = [{"name": "云计算", "categories": ["not a category", {"category": "计算", "list": None}]}]

    with pytest.raises(EmptyCatalogueError):
        await crawl_page(BaiduAICloudCrawler(), catalogue_page(groups))

    assert caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].getMessage() == f"The baidu catalogue page {CATALOGUE_URL} holds no product."
