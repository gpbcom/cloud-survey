from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.krystal.crawler import KrystalCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]


async def read(crawler: KrystalCrawler, response: Response) -> Dict[str, ServicePrice]:
    results: List[Union[PriceItem, Request]] = [result async for result in crawler._parse_prices(response)]
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> KrystalCrawler:
    crawler = KrystalCrawler()
    crawler.use_prices(CloudProvider.KRYSTAL, {}, 2.0)
    return crawler


@pytest.fixture
async def cloud(crawler: KrystalCrawler, price_page: PricePage) -> Dict[str, ServicePrice]:
    return await read(crawler, price_page(crawler.CLOUD_URL, "krystal-cloud-pricing.html", {}))


async def test_a_package_is_priced_per_month_without_its_storage(
    crawler: KrystalCrawler, cloud: Dict[str, ServicePrice]
) -> None:
    package = cloud["packages/cpu-optimised/C-1"]

    assert (package.price, package.currency, package.unit) == (Decimal("8.5"), "GBP", PriceUnit.MONTH)
    assert (package.vcpu, package.memory_gib, package.storage_gib) == (Decimal(1), Decimal(1), Decimal(10))
    block = cloud["price/blockStorage"]
    assert (block.price, block.unit) == (Decimal("0.15"), PriceUnit.GIB_MONTH)
    assert package.price is not None and package.storage_gib is not None and block.price is not None
    assert package.price + package.storage_gib * block.price == Decimal("10.00")
    assert crawler.price_reads[crawler.CLOUD_URL].status is PriceSourceStatus.FETCHED


@pytest.mark.parametrize(
    ("key", "unit"),
    [
        ("price/dataTransfer", PriceUnit.GIB),
        ("price/ipAddress", PriceUnit.UNIT_MONTH),
        ("price/objectStorage.base", PriceUnit.MONTH),
        ("price/objectStorage.usage", PriceUnit.GIB_MONTH),
    ],
)
async def test_the_resources_have_their_units(cloud: Dict[str, ServicePrice], key: str, unit: PriceUnit) -> None:
    assert cloud[key].unit is unit


async def test_a_gpu_is_priced_per_month(cloud: Dict[str, ServicePrice]) -> None:
    assert (cloud["gpus/Nvidia T4"].price, cloud["gpus/Nvidia T4"].service) == (Decimal("201.6"), "Katapult GPUs")


async def test_a_hosting_plan_is_priced_per_period(crawler: KrystalCrawler, price_page: PricePage) -> None:
    found = await read(crawler, price_page(crawler.HOSTING_URL, "krystal-hosting.html", {}))

    monthly, yearly = found["plans/amethyst/monthly"], found["plans/amethyst/annually"]
    assert (monthly.price, monthly.model, monthly.vcpu, monthly.memory_gib) == (
        Decimal(7),
        PriceModel.ON_DEMAND,
        Decimal(1),
        Decimal(2),
    )
    assert (yearly.price, yearly.unit_factor, yearly.term, yearly.model) == (
        Decimal(70),
        Decimal(12),
        PriceTerm.ONE_YEAR,
        PriceModel.COMMITMENT,
    )
    assert crawler.price_reads[crawler.HOSTING_URL].rows == 18
