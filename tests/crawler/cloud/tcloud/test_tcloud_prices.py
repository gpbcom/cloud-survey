from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.tcloud.crawler import TCloudPublicCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
FIRST = TCloudPublicCrawler.PRICES_URL.format(offset=0)
SECOND = TCloudPublicCrawler.PRICES_URL.format(offset=500)


async def read(crawler: TCloudPublicCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> TCloudPublicCrawler:
    crawler = TCloudPublicCrawler()
    crawler.use_prices(CloudProvider.TCLOUD, {}, 2.0)
    return crawler


@pytest.fixture
async def pages(crawler: TCloudPublicCrawler, price_page: PricePage) -> List[Union[PriceItem, Request]]:
    first = await read(crawler, price_page(FIRST, "tcloud-prices-page-1.json", {crawler.PRICE_OFFSET: 0}))
    return first + await read(crawler, price_page(SECOND, "tcloud-prices-page-2.json", {crawler.PRICE_OFFSET: 500}))


async def test_the_first_page_requests_the_others(crawler: TCloudPublicCrawler, price_page: PricePage) -> None:
    first = await read(crawler, price_page(FIRST, "tcloud-prices-page-1.json", {crawler.PRICE_OFFSET: 0}))

    assert [request.url for request in first if isinstance(request, Request)] == [SECOND]
    assert FIRST not in crawler.price_reads


async def test_the_api_is_recorded_once_every_page_is_read(
    crawler: TCloudPublicCrawler, pages: List[Union[PriceItem, Request]]
) -> None:
    source = crawler.price_reads[FIRST]

    assert (source.status, source.rows) == (PriceSourceStatus.FETCHED, len(prices(pages)))


async def test_a_record_has_its_reserved_prices(pages: List[Union[PriceItem, Request]]) -> None:
    found = prices(pages)

    hourly = found["OTC_APIG_D_PLAT"]
    assert (hourly.price, hourly.unit, hourly.currency, hourly.region) == (
        Decimal("11.25"),
        PriceUnit.HOUR,
        "EUR",
        "eu-de",
    )
    reserved = found["OTC_APIG_D_PLAT/R12"]
    assert (reserved.price, reserved.unit, reserved.model, reserved.term) == (
        Decimal(6239),
        PriceUnit.MONTH,
        PriceModel.RESERVED,
        PriceTerm.ONE_YEAR,
    )
    assert found["OTC_APIG_D_PLAT/RU24"].attributes["upfront"] is True
    assert "OTC_APIG_D_PLAT/R36" not in found


async def test_a_tiered_record_has_its_bounds(pages: List[Union[PriceItem, Request]]) -> None:
    found = prices(pages)

    assert (found["OTC_CWAF_DOMAIN_1"].tier_start, found["OTC_CWAF_DOMAIN_1"].tier_end) == (Decimal(0), Decimal(730))
    assert (found["OTC_CWAF_DOMAIN_2"].tier_start, found["OTC_CWAF_DOMAIN_2"].tier_end) == (Decimal(731), None)


async def test_a_flavor_has_its_hardware(pages: List[Union[PriceItem, Request]]) -> None:
    flavor = prices(pages)["OTC_C7T28XL4_P_LI"]

    assert (flavor.instance_type, flavor.vcpu, flavor.memory_gib, flavor.tier_start, flavor.tier_end) == (
        "c7t.28xl",
        Decimal(112),
        Decimal(512),
        Decimal(0),
        None,
    )


async def test_a_storage_record_is_per_gib_month(pages: List[Union[PriceItem, Request]]) -> None:
    assert prices(pages)["OTC_OBCBRCRR_OUTB"].unit is PriceUnit.GIB_MONTH
