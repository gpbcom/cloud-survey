from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.huawei.crawler import HuaweiCloudCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
VM = "ecs/ap-southeast-1/ec2_vm/m9.6xlarge.8.linux"


async def read(crawler: HuaweiCloudCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> HuaweiCloudCrawler:
    crawler = HuaweiCloudCrawler()
    crawler.use_prices(CloudProvider.HUAWEI, {}, 2.0)
    return crawler


@pytest.fixture
async def menu(crawler: HuaweiCloudCrawler, price_page: PricePage) -> List[Request]:
    [request] = [request async for request in crawler._price_requests()]
    return [
        result
        for result in await read(crawler, price_page(request.url, "huawei-menu.json", {}))
        if isinstance(result, Request)
    ]


@pytest.fixture
async def ecs(crawler: HuaweiCloudCrawler, menu: List[Request], price_page: PricePage) -> Dict[str, ServicePrice]:
    request = next(request for request in menu if request.meta[crawler.REGION_META] == "ap-southeast-1")
    return prices(await read(crawler, price_page(request.url, "huawei-ecs.json", request.meta)))


async def test_the_menu_requests_each_service_in_each_region(crawler: HuaweiCloudCrawler, menu: List[Request]) -> None:
    assert [request.meta[crawler.REGION_META] for request in menu] == ["ap-southeast-1", "af-south-1"]
    assert "urlPath=ecs" in menu[0].url
    assert "region=ap-southeast-1" in menu[0].url
    assert crawler.price_pending == 2


async def test_the_calculator_is_recorded_once_every_call_is_answered(
    crawler: HuaweiCloudCrawler, menu: List[Request], price_page: PricePage
) -> None:
    for request in menu:
        await read(crawler, price_page(request.url, "huawei-ecs.json", request.meta))

    source = crawler.price_reads[crawler.MENU_URL]
    assert (source.status, source.rows, crawler.price_pending) == (PriceSourceStatus.FETCHED, crawler.price_rows, 0)


async def test_an_instance_has_its_plans(ecs: Dict[str, ServicePrice]) -> None:
    hourly = next(price for key, price in ecs.items() if key.startswith(f"{VM}/ONDEMAND/1//"))
    yearly = next(price for key, price in ecs.items() if key.startswith(f"{VM}/YEARLY/1//"))

    assert (hourly.price, hourly.unit, hourly.currency, hourly.region) == (
        Decimal("1.7232"),
        PriceUnit.HOUR,
        "USD",
        "ap-southeast-1",
    )
    assert (hourly.vcpu, hourly.memory_gib, hourly.instance_type, hourly.service) == (
        Decimal(24),
        Decimal(192),
        "m9.6xlarge.8.linux",
        "Elastic Cloud Server",
    )
    assert (yearly.unit, yearly.unit_factor, yearly.model, yearly.term) == (
        PriceUnit.MONTH,
        Decimal(12),
        PriceModel.COMMITMENT,
        PriceTerm.ONE_YEAR,
    )


async def test_a_reserved_instance_keeps_its_effective_hourly_price(ecs: Dict[str, ServicePrice]) -> None:
    reserved = [price for price in ecs.values() if price.model is PriceModel.RESERVED]

    assert reserved
    assert {price.unit for price in reserved} == {PriceUnit.HOUR}
    assert Decimal("0.0595") in {price.price for price in reserved}


async def test_a_volume_is_priced_per_gib(ecs: Dict[str, ServicePrice]) -> None:
    volume = [price for price in ecs.values() if "/ebs_volume/" in price.sku_key]

    assert {price.unit for price in volume} == {PriceUnit.GIB_HOUR, PriceUnit.GIB_MONTH}


async def test_a_bandwidth_has_its_tiers(ecs: Dict[str, ServicePrice]) -> None:
    tiers = sorted(
        (price.tier_start, price.tier_end, price.price)
        for price in ecs.values()
        if "/vpc_bandwidth/" in price.sku_key and "/MONTHLY/" in price.sku_key
    )

    assert tiers == [(Decimal(0), Decimal(5), Decimal("4.86")), (Decimal(5), None, Decimal("16.2"))]


@pytest.mark.parametrize(
    ("measure", "sized", "unit", "factor"),
    [
        (4, False, PriceUnit.HOUR, Decimal(1)),
        (4, True, PriceUnit.GIB_HOUR, Decimal(1)),
        (111, False, PriceUnit.TOKEN, Decimal(1_000_000)),
        (31, False, PriceUnit.REQUEST, Decimal(1000)),
        (99999, False, PriceUnit.OTHER, Decimal(1)),
    ],
)
def test_the_measures(crawler: HuaweiCloudCrawler, measure: int, sized: bool, unit: PriceUnit, factor: Decimal) -> None:
    assert crawler._measure_unit(measure, sized) == (unit, factor)


async def test_the_plans_of_a_resource_are_told_apart_by_offer_and_usage(ecs: Dict[str, ServicePrice]) -> None:
    keys = list(ecs)

    assert len(keys) == len(set(keys))
    assert all(price.attributes.get("productId") for price in ecs.values() if price.model is PriceModel.ON_DEMAND)


def test_a_tier_spanning_two_units_keeps_its_end_as_an_attribute(crawler: HuaweiCloudCrawler) -> None:
    base: Dict[str, JsonValue] = {
        "service": "Live",
        "region": "ap-southeast-3",
        "currency": "USD",
        "attributes": {},
        "source_url": "https://portal-intl.huaweicloud.com/api/calculator",
        "source_kind": "calculator",
    }
    plan: Dict[str, JsonValue] = {
        "billingMode": "ONDEMAND",
        "measureUnit": 10,
        "productId": "live-1",
        "divisionList": [
            {"amount": 0.1, "division": {"beginUnit": 9, "endUnit": 9, "beginValue": 0, "endValue": 100}},
            {"amount": 0.08, "division": {"beginUnit": 9, "endUnit": 10, "beginValue": 100, "endValue": 1}},
        ],
    }

    first, second = crawler._plan_prices(base, "live/ap-southeast-3/cdn", plan, sized=True)

    assert (first.tier_start, first.tier_end) == (Decimal(0), Decimal(100))
    assert (second.tier_start, second.tier_end) == (Decimal(100), None)
    assert (second.attributes["endValue"], second.attributes["endUnit"]) == (1, 10)
