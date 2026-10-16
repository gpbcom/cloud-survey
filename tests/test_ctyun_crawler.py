from __future__ import annotations

import logging
from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.ctyun.crawler import ChinaTelecomCloudCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
CATALOGUE_URL = "https://www.ctyun.cn/products/"
HOME_URL = "https://www.ctyun.cn/"


def page(url: str, content: str) -> Response:
    return Response(url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = ChinaTelecomCloudCrawler()

    assert crawler.name == "ctyun"
    assert ChinaTelecomCloudCrawler.catalogue_url == CATALOGUE_URL
    assert ChinaTelecomCloudCrawler.complement_urls == (HOME_URL,)
    assert crawler.allowed_domains == {"www.ctyun.cn"}
    assert ChinaTelecomCloudCrawler.name_prefixes == ("天翼云", "中国电信", "eSurfing Cloud ")


async def test_extracts_the_products_page_cards(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(ChinaTelecomCloudCrawler(), make_response(CATALOGUE_URL, "ctyun_products.html"))

    assert names(results) == [
        "弹性云主机 ECS",
        "物理机 DPS",
        "Web应用防火墙",
        "云防火墙\uff08原生版\uff09",
        "云防火墙",
        "新域名服务",
        "专属云\uff08计算独享型\uff09",
        "专属云\uff08存储独享型\uff09",
    ]
    assert results[0] == {
        "name": "弹性云主机 ECS",
        "description": "随时自助获取、弹性伸缩的云服务器资源",
        "pricing_policy": [],
        "url": "https://www.ctyun.cn/products/ecs",
    }


async def test_marketplace_offers_are_filtered_out(
    make_response: MakeResponse, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="scrapling.spiders.ctyun")

    results = await crawl_page(ChinaTelecomCloudCrawler(), make_response(CATALOGUE_URL, "ctyun_products.html"))

    assert "SSL证书" not in names(results)
    assert "Skipping the card 'SSL证书', http://market.ctyun.cn/market/mallproduct/10192117 is not a product page." in [
        record.getMessage() for record in caplog.records
    ]


async def test_home_page_completes_the_catalogue(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = ChinaTelecomCloudCrawler()
    await crawl_page(crawler, make_response(CATALOGUE_URL, "ctyun_products.html"))

    results = await crawl_page(crawler, make_response(HOME_URL, "ctyun_home.html"))

    assert names(results) == ["天翼云息壤一体化智算服务平台", "一站式智算服务平台", "Web应用防火墙\uff08边缘云版\uff09"]
    assert results[0] == {
        "name": "天翼云息壤一体化智算服务平台",
        "description": "天翼云统一的智算品牌和产品能力",
        "pricing_policy": [],
        "url": "https://ctxirang.ctyun.cn/",
    }


@pytest.mark.parametrize(
    ("first", "second", "same"),
    [
        ("云防火墙\uff08原生版\uff09", "云防火墙", False),
        ("专属云\uff08计算独享型\uff09", "专属云 (存储独享型)", False),
        ("天翼云 云电脑", "云电脑", True),
        ("中国电信SD-WAN", "SD WAN", True),
    ],
)
def test_names_keep_their_edition(first: str, second: str, same: bool) -> None:
    crawler = ChinaTelecomCloudCrawler()

    assert (crawler._name_key(first) == crawler._name_key(second)) is same


@pytest.mark.parametrize(
    "href",
    [
        "https://www.ctyun.cn/products/topic/ai",
        "https://www.ctyun.cn/products/news",
        "/products/poly-storage",
        "https://market.ctyun.cn/market/mallproduct/13887356",
    ],
)
async def test_non_product_links_are_skipped(crawl_page: CrawlPage, href: str) -> None:
    cards = (
        f'<a class="product-card" href="{href}"><span class="product-card__title">专题</span>'
        '<div class="product-card__intro">专题页面</div></a>'
        '<a class="product-card" href="/products/vpc"><span class="product-card__title">虚拟私有云 VPC</span>'
        '<div class="product-card__intro">隔离的虚拟网络环境</div></a>'
    )

    results = await crawl_page(ChinaTelecomCloudCrawler(), page(HOME_URL, f"<html><body>{cards}</body></html>"))

    assert [(result["name"], result["url"]) for result in results if isinstance(result, dict)] == [
        ("虚拟私有云 VPC", "https://www.ctyun.cn/products/vpc")
    ]


async def test_cards_without_title_attributes_or_link(crawl_page: CrawlPage) -> None:
    cards = (
        '<a class="link"><div class="product-name">云硬盘 EVS</div><div class="product-note">块存储</div></a>'
        '<a class="link" href="/products/zos"><div class="product-name" title="对象存储 ZOS">对象存储...</div></a>'
    )

    results = await crawl_page(ChinaTelecomCloudCrawler(), page(CATALOGUE_URL, f"<html><body>{cards}</body></html>"))

    assert results == [{"name": "云硬盘 EVS", "description": "块存储", "pricing_policy": [], "url": None}]


@pytest.mark.parametrize("url", [CATALOGUE_URL, HOME_URL])
async def test_page_without_product_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, url: str
) -> None:
    content = '<html><body><a class="link" href="/products/news">了解最新产品动态</a></body></html>'

    with pytest.raises(EmptyCatalogueError):
        await crawl_page(ChinaTelecomCloudCrawler(), page(url, content))

    assert caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].getMessage() == f"The ctyun catalogue page {url} holds no product."
