from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.seeweb.crawler import SeewebCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
GPU_URL = "https://www.seeweb.it/en/products/cloud-server-gpu"


async def read(crawler: SeewebCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


@pytest.fixture
def crawler() -> SeewebCrawler:
    crawler = SeewebCrawler()
    crawler.use_prices(CloudProvider.SEEWEB, {}, 2.0)
    return crawler


@pytest.fixture
async def found(crawler: SeewebCrawler, price_page: PricePage) -> Dict[str, ServicePrice]:
    meta: Dict[str, JsonValue] = {crawler.SERVICE_META: "Cloud Server GPU", crawler.FAMILY_META: "Compute"}
    results = await read(crawler, price_page(GPU_URL, "seeweb-cloud-server-gpu.html", meta))
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


async def test_the_menu_product_pages_are_requested(crawler: SeewebCrawler, price_page: PricePage) -> None:
    [home] = [request async for request in crawler._price_requests()]
    pages = [
        request
        for request in await read(crawler, price_page(home.url, "../crawler/seeweb_home.html", home.meta))
        if isinstance(request, Request)
    ]

    assert len(pages) == 10
    assert all(page.meta[crawler.SERVICE_META] for page in pages)


def test_a_plan_card_is_priced_by_the_hour_with_its_specification(found: Dict[str, ServicePrice]) -> None:
    plan = found["en/products/cloud-server-gpu/gpu8/hourly"]

    assert (plan.instance_type, plan.price, plan.unit, plan.model, plan.currency) == (
        "AMD MI300X",
        Decimal("2.35"),
        PriceUnit.HOUR,
        PriceModel.ON_DEMAND,
        "EUR",
    )
    assert (plan.vcpu, plan.memory_gib, plan.attributes["gpuRam"]) == (32, Decimal(256), "192")


def test_reserved_prices_are_hourly_commitments(found: Dict[str, ServicePrice]) -> None:
    reserved = [found[f"en/products/cloud-server-gpu/gpu8/hourly_{months}mnths"] for months in (3, 6, 12)]

    assert [(price.price, price.model, price.term) for price in reserved] == [
        (Decimal("2.23"), PriceModel.COMMITMENT, PriceTerm.THREE_MONTHS),
        (Decimal("2.12"), PriceModel.COMMITMENT, PriceTerm.SIX_MONTHS),
        (Decimal("2.00"), PriceModel.COMMITMENT, PriceTerm.ONE_YEAR),
    ]


def test_each_page_is_a_source(crawler: SeewebCrawler, found: Dict[str, ServicePrice]) -> None:
    source = crawler.price_reads[GPU_URL]

    assert (source.status, source.rows, len(found)) == (PriceSourceStatus.FETCHED, 44, 44)


async def test_a_card_priced_outside_the_main_price_block(crawler: SeewebCrawler, price_page: PricePage) -> None:
    url = "https://www.seeweb.it/en/products/cloud-server-shared-cpu"
    meta: Dict[str, JsonValue] = {crawler.SERVICE_META: "Cloud Server Shared CPU", crawler.FAMILY_META: "Compute"}
    results = await read(crawler, price_page(url, "seeweb-cloud-server-shared-cpu.html", meta))
    found = {item["model"].sku_key: item["model"] for item in results if isinstance(item, dict)}
    plan = found["en/products/cloud-server-shared-cpu/ecs1/hourly"]

    assert (plan.instance_type, plan.price, plan.vcpu, plan.memory_gib) == ("1G", Decimal("0.019"), 1, Decimal(1))
    assert found["en/products/cloud-server-shared-cpu/ecs1/hourly_12mnths"].price == Decimal("0.015")
    assert "en/products/cloud-server-shared-cpu/ecs2w/hourly" in found
