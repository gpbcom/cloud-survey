from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.gcore.crawler import GcoreCrawler
from models.cloud.enums import CloudProvider, PriceSourceStatus, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
VM = GcoreCrawler.PRICES_URL.format(kind="vm")
BM = GcoreCrawler.PRICES_URL.format(kind="bm")


async def read(crawler: GcoreCrawler, response: Response) -> Dict[str, ServicePrice]:
    results: List[Union[PriceItem, Request]] = [result async for result in crawler._parse_prices(response)]
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> GcoreCrawler:
    crawler = GcoreCrawler()
    crawler.use_prices(CloudProvider.GCORE, {}, 2.0)
    return crawler


async def test_both_listings_are_requested(crawler: GcoreCrawler) -> None:
    assert [request.url async for request in crawler._price_requests()] == [VM, BM]


async def test_a_flavor_has_an_hourly_and_a_monthly_price(crawler: GcoreCrawler, price_page: PricePage) -> None:
    found = await read(crawler, price_page(VM, "gcore-pricing-vm.json", {crawler.PRICE_KIND: "vm"}))

    hourly = found["vm/Frankfurt-2/standard_g3aw/g3aw-standard-96-512/hour"]
    monthly = found["vm/Frankfurt-2/standard_g3aw/g3aw-standard-96-512/month"]
    assert (hourly.price, hourly.unit, hourly.region, hourly.currency) == (
        Decimal("2.811"),
        PriceUnit.HOUR,
        "Frankfurt-2",
        "EUR",
    )
    assert (monthly.price, monthly.unit) == (Decimal("2052.28"), PriceUnit.MONTH)
    assert (hourly.instance_type, hourly.vcpu, hourly.memory_gib, hourly.service) == (
        "g3aw-standard-96-512",
        Decimal(96),
        Decimal(512),
        "Virtual Machines",
    )
    assert crawler.price_reads[VM].status is PriceSourceStatus.FETCHED


async def test_a_gpu_flavor_keeps_its_gpus(crawler: GcoreCrawler, price_page: PricePage) -> None:
    found = await read(crawler, price_page(VM, "gcore-pricing-vm.json", {crawler.PRICE_KIND: "vm"}))

    gpu = next(price for price in found.values() if price.family == "gpu_g1")
    assert (gpu.service, gpu.attributes["gpu"]) == ("GPU Virtual Machines", "1 GPU")


async def test_a_bare_metal_listing_has_servers_and_traffic(crawler: GcoreCrawler, price_page: PricePage) -> None:
    found = await read(crawler, price_page(BM, "gcore-pricing-bm.json", {crawler.PRICE_KIND: "bm"}))

    server = next(price for price in found.values() if price.family == "bm0")
    assert (server.service, server.vcpu, server.attributes["cpu"]) == ("Bare Metal", None, server.attributes["cpu"])
    assert server.memory_gib is not None
    traffic = found["bm/Paris-2/egress/Egress traffic Bare Metal/GB"]
    assert (traffic.unit, traffic.price, traffic.service) == (PriceUnit.GIB, Decimal("0.0013"), "Egress traffic")
    assert {price.sku_key.split("/")[0] for price in found.values()} == {"bm"}
