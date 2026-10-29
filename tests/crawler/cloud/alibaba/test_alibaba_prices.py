from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.alibaba.crawler import AlibabaCloudCrawler
from crawler.cloud.base import PriceItem
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.stored.price_source import PriceSource

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
BASE = "https://g.alicdn.com/aliyun/ecs-price-info-intl/{version}price/js_price/"
INSTANCES = BASE.format(version="2.0.421/") + "filter_price/instanceTypePrice_2.js"
VM = "instances/cn-heyuan/linux/ecs-8/vpc/ecs.c9ae.large"


async def read(crawler: AlibabaCloudCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


def crawler_knowing(sources: Dict[str, PriceSource]) -> AlibabaCloudCrawler:
    crawler = AlibabaCloudCrawler()
    crawler.use_prices(CloudProvider.ALIBABA, sources, 2.0)
    return crawler


@pytest.fixture
def crawler() -> AlibabaCloudCrawler:
    return crawler_knowing({})


async def file_prices(
    crawler: AlibabaCloudCrawler, price_page: PricePage, url: str, fixture: str
) -> Dict[str, ServicePrice]:
    meta: Dict[str, JsonValue] = {crawler.PRICE_FILE: url.rsplit("/", 1)[-1], crawler.PRICE_VERSION: "2.0.421"}
    return prices(await read(crawler, price_page(url, fixture, meta)))


async def test_the_loader_requests_the_price_files(crawler: AlibabaCloudCrawler, price_page: PricePage) -> None:
    results = await read(crawler, price_page(crawler.PRICE_LOADER_URL, "alibaba-price-loader.js", {}))

    names = [request.meta[crawler.PRICE_FILE] for request in results if isinstance(request, Request)]
    assert names == ["instanceTypePrice_1.js", "instanceTypePrice_2.js", "diskPrice.js", "bandWidthPrice.js"]


async def test_an_unchanged_file_is_not_requested(price_page: PricePage) -> None:
    source = BASE.format(version="") + "filter_price/instanceTypePrice_2.js"
    known = PriceSource(
        provider=CloudProvider.ALIBABA, source_key=source, version="2.0.421", rows=1, status=PriceSourceStatus.FETCHED
    )
    crawler = crawler_knowing({source: known})
    results = await read(crawler, price_page(crawler.PRICE_LOADER_URL, "alibaba-price-loader.js", {}))

    assert "instanceTypePrice_2.js" not in [
        request.meta[crawler.PRICE_FILE] for request in results if isinstance(request, Request)
    ]


async def test_an_instance_has_its_periods(crawler: AlibabaCloudCrawler, price_page: PricePage) -> None:
    found = await file_prices(crawler, price_page, INSTANCES, "alibaba-instances.js")

    hourly, monthly, yearly = found[f"{VM}/0"], found[f"{VM}/1"], found[f"{VM}/2"]
    assert (hourly.price, hourly.unit, hourly.currency, hourly.os) == (
        Decimal("0.0555"),
        PriceUnit.HOUR,
        "USD",
        "linux",
    )
    assert (hourly.vcpu, hourly.memory_gib, hourly.region) == (Decimal(2), Decimal(4), "cn-heyuan")
    assert (monthly.price, monthly.unit, monthly.model) == (Decimal("26.63"), PriceUnit.MONTH, PriceModel.ON_DEMAND)
    assert (yearly.price, yearly.unit_factor, yearly.model, yearly.term) == (
        Decimal("223.68"),
        Decimal(12),
        PriceModel.COMMITMENT,
        PriceTerm.ONE_YEAR,
    )
    source = crawler.price_reads[BASE.format(version="") + "filter_price/instanceTypePrice_2.js"]
    assert (source.version, source.rows) == ("2.0.421", 14)


async def test_a_disk_is_priced_per_100_gb(crawler: AlibabaCloudCrawler, price_page: PricePage) -> None:
    url = BASE.format(version="2.0.421/") + "disk_price/diskPrice.js"
    found = await file_prices(crawler, price_page, url, "alibaba-disks.js")

    monthly = next(price for price in found.values() if price.unit is PriceUnit.GIB_MONTH)
    assert (monthly.unit_factor, monthly.price) == (Decimal(100), Decimal("4.60"))


async def test_a_bandwidth_is_priced_per_mbps_or_per_gb(crawler: AlibabaCloudCrawler, price_page: PricePage) -> None:
    url = BASE.format(version="2.0.421/") + "bandwidth_price/bandWidthPrice.js"
    found = await file_prices(crawler, price_page, url, "alibaba-bandwidth.js")

    assert found["bandwidth/cn-heyuan/Month/1"].unit is PriceUnit.UNIT_MONTH
    assert found["bandwidth/cn-heyuan/Hour/1"].unit is PriceUnit.UNIT_HOUR
    assert (found["bandwidth/cn-heyuan/GB/1"].unit, found["bandwidth/cn-heyuan/GB/1"].price) == (
        PriceUnit.GIB,
        Decimal("0.123"),
    )


async def test_the_pricing_directory_leads_to_the_product_pricing_pages(
    crawler: AlibabaCloudCrawler, price_page: PricePage
) -> None:
    meta: Dict[str, JsonValue] = {crawler.DIRECTORY_META: True}
    pages = [
        request
        for request in await read(
            crawler, price_page(crawler.PRICING_DIRECTORY_URL, "alibaba-pricing-directory.html", meta)
        )
        if isinstance(request, Request)
    ]
    services = {request.url: request.meta[crawler.PRODUCT_PAGE_META] for request in pages}

    assert len(pages) > 150
    assert services["https://www.alibabacloud.com/en/product/swas/pricing"] == "Simple Application Server"


async def test_model_tokens_are_priced_per_million(crawler: AlibabaCloudCrawler, price_page: PricePage) -> None:
    meta: Dict[str, JsonValue] = {crawler.PRODUCT_PAGE_META: crawler.MODEL_SERVICE}
    found = prices(await read(crawler, price_page(crawler.MODEL_PRICES_URL, "alibaba-model-pricing.html", meta)))
    tokens = [price for price in found.values() if price.unit == PriceUnit.TOKEN]

    assert tokens
    assert all(price.unit_factor == 1_000_000 and price.currency == "USD" for price in tokens)
    assert {price.service for price in found.values()} == {"Model Studio"}
