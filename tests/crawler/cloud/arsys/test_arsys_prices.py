from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.arsys.crawler import ArsysCrawler
from crawler.cloud.base import PriceItem
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
VPS_URL = "https://www.arsys.net/servers/vps"


async def read(crawler: ArsysCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> ArsysCrawler:
    crawler = ArsysCrawler()
    crawler.use_prices(CloudProvider.ARSYS, {}, 2.0)
    return crawler


async def test_the_price_list_and_the_menu_product_pages_are_requested(
    crawler: ArsysCrawler, price_page: PricePage
) -> None:
    [price_list, home] = [request async for request in crawler._price_requests()]
    pages = [
        request
        for request in await read(crawler, price_page(home.url, "../crawler/arsys_home.html", home.meta))
        if isinstance(request, Request)
    ]

    assert (price_list.url, home.url) == (crawler.PRICES_URL, crawler.catalogue_url)
    assert len(pages) == 16
    assert all(isinstance(page.meta[crawler.SERVICE_META], str) and page.meta[crawler.SERVICE_META] for page in pages)


async def test_a_resource_of_the_price_list_is_priced_by_its_unit(crawler: ArsysCrawler, price_page: PricePage) -> None:
    found = prices(
        await read(crawler, price_page(crawler.PRICES_URL, "arsys-cloud-prices.html", {crawler.SERVICE_META: ""}))
    )
    ram = found["cloud/Cloud Servers/Calculation/Dedicated RAM"]
    hdd = found["cloud/Cloud Servers/Storage/HDD"]

    assert (ram.price, ram.unit, ram.currency, ram.region) == (Decimal("0.0045"), PriceUnit.GIB_HOUR, "EUR", "es")
    assert (hdd.unit, hdd.attributes["vat"]) == (PriceUnit.GIB_MONTH, "excluded")


async def test_transfer_tiers_are_usage_ranges(crawler: ArsysCrawler, price_page: PricePage) -> None:
    found = prices(
        await read(crawler, price_page(crawler.PRICES_URL, "arsys-cloud-prices.html", {crawler.SERVICE_META: ""}))
    )
    tiers = [price for key, price in found.items() if "Outgoing transfer" in key]

    assert [(price.price, price.tier_start, price.tier_end) for price in tiers] == [
        (Decimal(0), Decimal(0), Decimal(2048)),
        (Decimal("0.03"), Decimal(2048), Decimal(10240)),
        (Decimal("0.025"), Decimal(10240), Decimal(51200)),
        (Decimal("0.02"), Decimal(51200), Decimal(153600)),
        (Decimal("0.015"), Decimal(153600), None),
    ]
    assert tiers[0].model == PriceModel.FREE


async def test_a_product_offer_per_billing_cycle(crawler: ArsysCrawler, price_page: PricePage) -> None:
    meta: Dict[str, JsonValue] = {crawler.SERVICE_META: "VPS", crawler.FAMILY_META: "Servers"}
    found = prices(await read(crawler, price_page(VPS_URL, "arsys-vps.html", meta)))
    monthly, yearly = found["servers/vps/VPS 1_2_60/1"], found["servers/vps/VPS 1_2_60/12"]

    assert (monthly.price, monthly.unit, monthly.model, monthly.vcpu, monthly.memory_gib) == (
        Decimal(7),
        PriceUnit.MONTH,
        PriceModel.ON_DEMAND,
        1,
        Decimal(2),
    )
    assert (yearly.price, yearly.unit_factor, yearly.term, yearly.attributes["first_period_price"]) == (
        Decimal(84),
        Decimal(12),
        PriceTerm.ONE_YEAR,
        "60",
    )
    assert crawler.price_reads[VPS_URL].status == PriceSourceStatus.FETCHED
