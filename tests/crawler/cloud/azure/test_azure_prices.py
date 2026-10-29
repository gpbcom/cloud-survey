from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.azure.crawler import AzureCrawler
from crawler.cloud.base import PriceItem
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
NEXT = "https://prices.azure.com:443/api/retail/prices?api-version=2023-01-01-preview&$skip=1000"
VM = "DZH318Z0D1L7/00WP/003dea30-2b48-58f3-9adf-f7cbb5159f08/Consumption//0.0"
SOURCE = AzureCrawler.PRICES_URL + "&%24filter=serviceFamily+eq+%27Compute%27+and+priceType+eq+%27Consumption%27"
META: Dict[str, JsonValue] = {AzureCrawler.PRICE_SOURCE: SOURCE}


async def read(crawler: AzureCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> AzureCrawler:
    crawler = AzureCrawler()
    crawler.use_prices(CloudProvider.AZURE, {}, 2.0)
    crawler.price_rows = {}
    return crawler


@pytest.fixture
async def pages(crawler: AzureCrawler, price_page: PricePage) -> List[Union[PriceItem, Request]]:
    first = await read(crawler, price_page(SOURCE, "azure-prices-page-1.json", META))
    return first + await read(crawler, price_page(NEXT, "azure-prices-page-2.json", META))


async def test_the_pages_are_followed_and_the_api_recorded_after_the_last(
    crawler: AzureCrawler, price_page: PricePage
) -> None:
    first = await read(crawler, price_page(SOURCE, "azure-prices-page-1.json", META))

    requests = [request for request in first if isinstance(request, Request)]
    assert [(request.url, request.meta[crawler.PRICE_SOURCE]) for request in requests] == [(NEXT, SOURCE)]
    assert SOURCE not in crawler.price_reads
    found = prices(first + await read(crawler, price_page(NEXT, "azure-prices-page-2.json", META)))
    source = crawler.price_reads[SOURCE]
    assert (source.status, source.rows) == (PriceSourceStatus.FETCHED, 14)
    assert {price.source_url for price in found.values()} == {SOURCE}


async def test_the_api_is_read_as_listings_of_fewer_than_a_million_items(crawler: AzureCrawler) -> None:
    requests = [request async for request in crawler._price_requests()]

    assert requests[0].url == SOURCE
    assert [request.meta[crawler.PRICE_SOURCE] for request in requests] == [request.url for request in requests]
    assert len(requests) == 3


async def test_a_virtual_machine_has_its_savings_plans(pages: List[Union[PriceItem, Request]]) -> None:
    found = prices(pages)
    machine = found[VM]

    assert (machine.service, machine.family, machine.region, machine.os) == (
        "Virtual Machines",
        "Compute",
        "westeurope",
        "linux",
    )
    assert (machine.price, machine.unit, machine.model, machine.currency) == (
        Decimal("2.432"),
        PriceUnit.HOUR,
        PriceModel.ON_DEMAND,
        "USD",
    )
    assert machine.instance_type == "Standard_E32_v4"
    plans = {price.term: price.model for key, price in found.items() if key.startswith(f"{VM}/savings-plan/")}
    assert plans == {PriceTerm.ONE_YEAR: PriceModel.SAVINGS_PLAN, PriceTerm.THREE_YEARS: PriceModel.SAVINGS_PLAN}


async def test_a_reservation_is_priced_per_year_of_its_term(pages: List[Union[PriceItem, Request]]) -> None:
    found = prices(pages)
    three = found["DZH318Z0D1L7/01RJ/003dea30-2b48-58f3-9adf-f7cbb5159f08/Reservation/3 Years/0.0"]

    assert (three.model, three.term, three.unit, three.unit_factor, three.price) == (
        PriceModel.RESERVED,
        PriceTerm.THREE_YEARS,
        PriceUnit.YEAR,
        Decimal(3),
        Decimal(24287),
    )
    assert three.unit_raw == "3 Years"


async def test_a_windows_machine_has_its_os(pages: List[Union[PriceItem, Request]]) -> None:
    assert {price.os for price in prices(pages).values() if price.service == "Virtual Machines"} == {
        "linux",
        "windows",
    }


async def test_the_tiers_start_at_their_minimum(pages: List[Union[PriceItem, Request]]) -> None:
    tiers = sorted(
        (price.tier_start, price.price) for price in prices(pages).values() if price.sku_key.startswith("DZH318Z0BPH7/")
    )

    assert tiers == [
        (Decimal(0), Decimal("0.045")),
        (Decimal(51200), Decimal("0.0432")),
        (Decimal(512000), Decimal("0.0414")),
    ]


@pytest.mark.parametrize(
    ("measure", "unit", "factor"),
    [
        ("10K", PriceUnit.REQUEST, Decimal(10_000)),
        ("1", PriceUnit.UNIT, Decimal(1)),
        ("1/Day", PriceUnit.UNIT_HOUR, Decimal(24)),
        ("1 GB/Month", PriceUnit.GIB_MONTH, Decimal(1)),
        ("100 Seconds", PriceUnit.SECOND, Decimal(100)),
        ("1 MB", PriceUnit.GIB, Decimal(1) / Decimal(1024)),
        ("1 Parsec", PriceUnit.OTHER, Decimal(1)),
    ],
)
def test_the_units_of_measure(crawler: AzureCrawler, measure: str, unit: PriceUnit, factor: Decimal) -> None:
    assert crawler._measure_unit(measure) == (unit, factor)


async def test_a_dev_test_price_is_kept_apart(pages: List[Union[PriceItem, Request]]) -> None:
    dev = [price for price in prices(pages).values() if "/DevTestConsumption/" in price.sku_key]

    assert [(price.attributes["type"], price.unit_factor) for price in dev] == [("DevTestConsumption", Decimal(1))]
