from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.selectel.crawler import SelectelCrawler
from models.cloud.enums import CloudProvider, PriceSourceStatus, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]


async def read(crawler: SelectelCrawler, response: Response) -> Dict[str, ServicePrice]:
    results: List[Union[PriceItem, Request]] = [result async for result in crawler._parse_prices(response)]
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> SelectelCrawler:
    crawler = SelectelCrawler()
    crawler.use_prices(CloudProvider.SELECTEL, {}, 2.0)
    return crawler


async def family(crawler: SelectelCrawler, price_page: PricePage, name: str) -> Dict[str, ServicePrice]:
    url = crawler.PRICES_URL.format(family=name)
    return await read(crawler, price_page(url, f"selectel-prices-{name}.json", {crawler.PRICE_FAMILY: name}))


async def test_every_source_is_requested(crawler: SelectelCrawler) -> None:
    urls = [request.url async for request in crawler._price_requests()]

    assert len(urls) == 10
    assert urls[-2:] == [crawler.SERVERS_URL, crawler.BILLING_URL]


async def test_a_cloud_price_is_in_rubles_per_hour(crawler: SelectelCrawler, price_page: PricePage) -> None:
    found = await family(crawler, price_page, "vpc")

    cores = found["vpc/ru-2c/compute_cores_standard_amd_preemptible"]
    assert (cores.price, cores.currency, cores.unit, cores.service) == (
        Decimal("0.2517768"),
        "RUB",
        PriceUnit.VCPU_HOUR,
        "Cloud Servers",
    )
    ram = found["vpc/ru-2c/compute_ram_standard_amd_preemptible"]
    assert (ram.unit, ram.unit_factor) == (PriceUnit.GIB_HOUR, Decimal(1) / Decimal(1024))
    assert found["vpc/uz-1b/volume_gigabytes_universal"].unit is PriceUnit.GIB_HOUR
    assert found["vpc/ru-1c/compute_vds_1_1_10"].unit is PriceUnit.UNIT_HOUR
    assert crawler.price_reads[crawler.PRICES_URL.format(family="vpc")].status is PriceSourceStatus.FETCHED


async def test_a_traffic_is_per_gib_transferred(crawler: SelectelCrawler, price_page: PricePage) -> None:
    found = await family(crawler, price_page, "craas")

    assert found["craas/ru-9/craas_registry_traffic_tx"].unit is PriceUnit.GIB
    assert found["craas/ru-9/craas_registry_storage"].unit is PriceUnit.GIB_HOUR


async def test_a_dedicated_server_is_priced_per_location(crawler: SelectelCrawler, price_page: PricePage) -> None:
    meta: Dict[str, JsonValue] = {crawler.PRICE_FAMILY: crawler.SERVERS_KEY}
    found = await read(crawler, price_page(crawler.SERVERS_URL, "selectel-servers.json", meta))

    key = "servers/00835804-bbfa-531d-94c2-bac286fa24ed/07ff5ae1-7e8b-4c85-af2c-219798aa0d46"
    monthly, daily = found[f"{key}/month"], found[f"{key}/day"]
    assert (monthly.price, monthly.unit, monthly.instance_type) == (Decimal(20900), PriceUnit.MONTH, "AEL10-SSD")
    assert (monthly.vcpu, monthly.memory_gib, monthly.storage_gib) == (Decimal(4), Decimal(16), Decimal(480))
    assert (daily.price, daily.unit, daily.unit_factor) == (Decimal(1170), PriceUnit.HOUR, Decimal(24))


async def test_a_billing_item_is_monthly_or_once(crawler: SelectelCrawler, price_page: PricePage) -> None:
    meta: Dict[str, JsonValue] = {crawler.PRICE_FAMILY: crawler.BILLING_KEY}
    found = await read(crawler, price_page(crawler.BILLING_URL, "selectel-billing.json", meta))

    colocation, sms = found["billing/1"], found["billing/184"]
    assert (colocation.price, colocation.unit, colocation.service) == (
        Decimal(7390),
        PriceUnit.MONTH,
        "1U server colocation",
    )
    assert (sms.price, sms.unit) == (Decimal("31.9"), PriceUnit.ONE_TIME)
