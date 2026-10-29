from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.baidu.crawler import BaiduAICloudCrawler
from crawler.cloud.base import PriceItem
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]


async def read(crawler: BaiduAICloudCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> BaiduAICloudCrawler:
    crawler = BaiduAICloudCrawler()
    crawler.use_prices(CloudProvider.BAIDU, {}, 2.0)
    return crawler


@pytest.fixture
async def calls(crawler: BaiduAICloudCrawler, price_page: PricePage) -> List[Request]:
    [beijing, _] = [request async for request in crawler._price_requests() if crawler.REGION_META in request.meta]
    results = await read(crawler, price_page(beijing.url, "baidu-bcc-flavors.json", beijing.meta))
    return [request for request in results if isinstance(request, Request)]


def call(calls: List[Request], crawler: BaiduAICloudCrawler, spec: str, kind: str, months: int) -> Request:
    return next(
        request
        for request in calls
        if request.meta[crawler.FLAVOR_META]["spec"] == spec
        and request.meta[crawler.FLAVOR_META]["productType"] == kind
        and request.meta[crawler.MONTHS_META] == months
    )


async def test_each_region_lists_its_flavors(crawler: BaiduAICloudCrawler) -> None:
    requests = [request async for request in crawler._price_requests() if crawler.REGION_META in request.meta]

    assert [request._session_kwargs["json"]["region"] for request in requests] == ["bj", "hkg"]
    assert crawler.price_pending == 2


async def test_each_flavor_is_priced_once_postpaid_and_per_prepaid_length(
    crawler: BaiduAICloudCrawler, calls: List[Request]
) -> None:
    economy = call(calls, crawler, "bcc.e2.c2m2", "prepay", 12)
    instance = economy._session_kwargs["json"]["bcc"]

    assert len(calls) == 3 + 3 * 3
    assert (instance["spec"], instance["specId"], instance["cpu"], instance["memory"]) == ("bcc.e2.c2m2", "e2", 2, 2)
    assert (economy._session_kwargs["json"]["purchaseLength"], economy._session_kwargs["json"]["region"]) == (12, "bj")
    gpu = call(calls, crawler, "bcc.gn3.c8m64.1v100-32g", "postpay", 1)._session_kwargs["json"]["bcc"]
    assert (gpu["gpuCount"], gpu["rootDiskStorageType"]) == (1, "enhanced_ssd_pl1")


async def test_a_postpaid_flavor_is_priced_by_the_minute(
    crawler: BaiduAICloudCrawler, calls: List[Request], price_page: PricePage
) -> None:
    request = call(calls, crawler, "bcc.e2.c2m2", "postpay", 1)
    [price] = prices(
        await read(crawler, price_page(request.url, "baidu-bcc-price-postpay.json", request.meta))
    ).values()

    assert (price.sku_key, price.price, price.unit, price.model) == (
        "bj/bcc.e2.c2m2/postpay/0",
        Decimal("0.00086806"),
        PriceUnit.MINUTE,
        PriceModel.ON_DEMAND,
    )
    assert (price.service, price.currency, price.vcpu, price.memory_gib) == ("云服务器 BCC", "CNY", 2, Decimal(2))


async def test_a_prepaid_flavor_is_priced_for_its_months(
    crawler: BaiduAICloudCrawler, calls: List[Request], price_page: PricePage
) -> None:
    request = call(calls, crawler, "bcc.e2.c2m2", "prepay", 12)
    [price] = prices(await read(crawler, price_page(request.url, "baidu-bcc-price-prepay.json", request.meta))).values()

    assert (price.sku_key, price.price, price.unit, price.unit_factor, price.term, price.model) == (
        "bj/bcc.e2.c2m2/prepay/12",
        Decimal("165.0"),
        PriceUnit.MONTH,
        Decimal(12),
        PriceTerm.ONE_YEAR,
        PriceModel.COMMITMENT,
    )
    assert price.attributes["catalogPrice"] == 300.0


async def test_a_gpu_flavor_is_a_gpu_instance(
    crawler: BaiduAICloudCrawler, calls: List[Request], price_page: PricePage
) -> None:
    request = call(calls, crawler, "bcc.gn3.c8m64.1v100-32g", "postpay", 1)
    [price] = prices(
        await read(crawler, price_page(request.url, "baidu-bcc-price-postpay.json", request.meta))
    ).values()

    assert (price.service, price.attributes["gpuCardType"]) == ("GPU云服务器", "nTeslaV100-32")


async def test_a_refused_flavor_is_skipped_and_the_api_recorded_once_every_call_is_answered(
    crawler: BaiduAICloudCrawler, calls: List[Request], price_page: PricePage
) -> None:
    crawler.price_pending -= 1
    found = 0
    for index, request in enumerate(calls):
        fixture = "baidu-bcc-price-refused.json" if index == 0 else "baidu-bcc-price-postpay.json"
        found += len(prices(await read(crawler, price_page(request.url, fixture, request.meta))))
    source = crawler.price_reads[crawler.PRICES_URL]

    assert (found, crawler.price_failures) == (len(calls) - 1, set())
    assert (source.status, source.rows) == (PriceSourceStatus.FETCHED, found)


async def test_the_price_navigation_leads_to_the_product_price_pages(
    crawler: BaiduAICloudCrawler, price_page: PricePage
) -> None:
    [navigation] = [request async for request in crawler._price_requests() if crawler.NAV_META in request.meta]
    pages = [
        request
        for request in await read(crawler, price_page(navigation.url, "baidu-price-nav.json", navigation.meta))
        if isinstance(request, Request)
    ]
    cfc = next(page for page in pages if page.url.endswith("/product-price/cfc.html"))

    assert all("/product-price/" in page.url for page in pages)
    assert len(pages) > 60
    found = prices(await read(crawler, price_page(cfc.url, "baidu-price-cfc.html", cfc.meta)))
    assert {price.service for price in found.values()} == {cfc.meta[crawler.PRODUCT_PAGE_META]}
    assert {price.currency for price in found.values()} == {"CNY"}
    assert crawler.price_reads[cfc.url].rows == len(found) > 10
