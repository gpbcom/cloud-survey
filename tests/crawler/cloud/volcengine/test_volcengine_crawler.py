from __future__ import annotations

import logging
from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.volcengine.crawler import VolcanoEngineCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
CATALOGUE_URL = "https://www.volcengine.com/product/list"


def page(content: str) -> Response:
    return Response(
        url=CATALOGUE_URL, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}
    )


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = VolcanoEngineCrawler()

    assert crawler.name == "volcengine"
    assert VolcanoEngineCrawler.catalogue_url == CATALOGUE_URL
    assert VolcanoEngineCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"www.volcengine.com"}
    assert VolcanoEngineCrawler.name_prefixes == ("火山引擎", "Volcano Engine ")


async def test_catalogue_request_waits_for_the_product_cards() -> None:
    requests = [request async for request in VolcanoEngineCrawler().start_requests()]

    assert [(request.url, request.priority, request._session_kwargs) for request in requests] == [
        (
            CATALOGUE_URL,
            VolcanoEngineCrawler.PRIMARY_PRIORITY,
            {"wait_selector": 'div[class*="product-card-"] > a', "network_idle": True},
        )
    ]


async def test_extracts_the_product_cards(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(VolcanoEngineCrawler(), make_response(CATALOGUE_URL, "volcengine_product_list.html"))

    assert names(results) == ["豆包大模型", "火山方舟", "OpenViking Context", "云服务器", "数据闪送服务", "对象存储"]
    assert results[1] == {
        "name": "火山方舟",
        "description": "火山方舟是火山引擎推出的一站式大模型服务平台。平台提供模型精调、推理、评测等全方位功能与服务"
        "\uff0c提供丰富插件生态\uff0c通过安全可信方案\uff0c专业算法服务\uff0c全方位保障企业级 AI 应用落地",
        "pricing_policy": [],
        "url": "https://www.volcengine.com/product/ark",
        "catalogue_categories": ["人工智能", "模型平台与服务"],
    }


async def test_products_carry_their_category_and_sub_category(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(VolcanoEngineCrawler(), make_response(CATALOGUE_URL, "volcengine_product_list.html"))

    assert {result["name"]: result["catalogue_categories"] for result in results if isinstance(result, dict)} == {
        "豆包大模型": ["人工智能", "模型平台与服务"],
        "火山方舟": ["人工智能", "模型平台与服务"],
        "OpenViking Context": ["人工智能", "AI应用开发"],
        "云服务器": ["计算", "弹性计算"],
        "数据闪送服务": ["存储", "数据迁移与工具"],
        "对象存储": ["存储", "基础存储服务"],
    }


async def test_products_listed_in_several_groups_get_all_of_them(crawl_page: CrawlPage) -> None:
    card = (
        '<div class="product-card-a1"><a href="/product/vke?utm_source=list">'
        '<div class="product-title-c3">容器服务</div><div class="product-description-b2">Kubernetes</div></a></div>'
    )
    blocks = "".join(
        f'<div class="block-x1"><div class="tabs-title-y2">{category}</div>'
        f'<div class="secondLevel-z3"><div class="secondLevel-title-w4">{sub_category}</div>{card}</div></div>'
        for category, sub_category in (("容器与中间件", "容器服务"), ("人工智能", "AI 基础设施"))
    )

    results = await crawl_page(VolcanoEngineCrawler(), page(f"<html><body>{blocks}</body></html>"))

    assert [result.get("catalogue_categories") for result in results if isinstance(result, dict)] == [
        ["容器与中间件", "容器服务", "人工智能", "AI 基础设施"]
    ]


async def test_query_strings_are_removed(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(VolcanoEngineCrawler(), make_response(CATALOGUE_URL, "volcengine_product_list.html"))

    assert [result["url"] for result in results if isinstance(result, dict)][2] == (
        "https://www.volcengine.com/product/openviking-service"
    )


@pytest.mark.parametrize("excluded", ["API Explorer", "CLI 工具", "开源镜像站", "访问控制"])
async def test_tools_and_console_cards_are_filtered_out(
    make_response: MakeResponse, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, excluded: str
) -> None:
    caplog.set_level(logging.DEBUG, logger="scrapling.spiders.volcengine")

    results = await crawl_page(VolcanoEngineCrawler(), make_response(CATALOGUE_URL, "volcengine_product_list.html"))

    assert excluded not in names(results)
    assert any(record.getMessage().startswith(f"Skipping the card {excluded!r}") for record in caplog.records)


async def test_duplicated_cards_are_streamed_once(
    make_response: MakeResponse, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    await crawl_page(VolcanoEngineCrawler(), make_response(CATALOGUE_URL, "volcengine_product_list.html"))

    assert caplog.records[-1].getMessage() == (
        f"volcengine catalogue page {CATALOGUE_URL} parsed: 6 new products, 4 duplicates skipped."
    )


async def test_cards_without_title_or_description_are_skipped(crawl_page: CrawlPage) -> None:
    cards = (
        '<div class="product-card-a1"><a href="/product/vke"><div class="product-description-b2">容器</div></a></div>'
        '<div class="product-card-a1"><a href="/product/cr"><div class="product-title-c3">镜像仓库</div></a></div>'
        '<div class="product-card-a1"><a><div class="product-title-c3">无链接</div>'
        '<div class="product-description-b2">无</div></a></div>'
        '<div class="product-card-a1"><a href="/product/vpc"><div class="product-title-c3">私有网络</div>'
        '<div class="product-description-b2">虚拟网络</div></a></div>'
    )

    results = await crawl_page(VolcanoEngineCrawler(), page(f"<html><body>{cards}</body></html>"))

    assert names(results) == ["私有网络"]


async def test_page_without_card_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(VolcanoEngineCrawler(), page("<html><body><div>Loading</div></body></html>"))

    assert caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].getMessage() == f"The volcengine catalogue page {CATALOGUE_URL} holds no product."
