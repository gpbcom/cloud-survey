from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.stackit.crawler import STACKITCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceKind, PriceSourceStatus, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.stored.price_source import PriceSource

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
VERSION = "2026-10-29T07:33:51.816533Z"


async def read(crawler: STACKITCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


def crawler_knowing(sources: Dict[str, PriceSource]) -> STACKITCrawler:
    crawler = STACKITCrawler()
    crawler.use_prices(CloudProvider.STACKIT, sources, 2.0)
    return crawler


@pytest.fixture
def crawler() -> STACKITCrawler:
    return crawler_knowing({})


@pytest.fixture
async def price_list(crawler: STACKITCrawler, price_page: PricePage) -> Dict[str, ServicePrice]:
    return prices(await read(crawler, price_page(crawler.PRICES_URL, "stackit-skus.json", {})))


async def test_every_sku_is_priced_and_the_list_recorded_with_its_version(
    crawler: STACKITCrawler, price_list: Dict[str, ServicePrice]
) -> None:
    source = crawler.price_reads[crawler.PRICES_URL]

    assert len(price_list) == 10
    assert (source.status, source.rows, source.version) == (PriceSourceStatus.FETCHED, 10, VERSION)


async def test_a_machine_has_its_flavor_and_hardware(price_list: Dict[str, ServicePrice]) -> None:
    machine = price_list["ST-0008701"]

    assert (machine.instance_type, machine.vcpu, machine.memory_gib, machine.region) == (
        "c1.1",
        Decimal(1),
        Decimal(2),
        "eu01",
    )
    assert (machine.unit, machine.price, machine.currency) == (PriceUnit.HOUR, Decimal("0.01826770833"), "EUR")
    assert (machine.family, machine.source_kind) == ("Compute Engine", PriceSourceKind.API)
    assert "cfUniqueIds" not in machine.attributes


@pytest.mark.parametrize(
    ("sku", "unit", "factor"),
    [
        ("ST-0039201", PriceUnit.GIB_HOUR, Decimal(1)),
        ("ST-0172901", PriceUnit.TOKEN, Decimal(1_000_000)),
        ("ST-0171701", PriceUnit.GIB_HOUR, Decimal(24)),
        ("ST-0171390", PriceUnit.GIB, Decimal(1) / Decimal(1024)),
        ("ST-0199290", PriceUnit.UNIT, Decimal(1)),
    ],
)
async def test_the_units_are_normalized(
    price_list: Dict[str, ServicePrice], sku: str, unit: PriceUnit, factor: Decimal
) -> None:
    assert (price_list[sku].unit, price_list[sku].unit_factor) == (unit, factor)


async def test_a_band_price_has_its_band_as_tier(price_list: Dict[str, ServicePrice]) -> None:
    assert (price_list["ST-0190701"].tier_start, price_list["ST-0190701"].tier_end) == (Decimal(1), Decimal(8))
    assert (price_list["ST-0190901"].tier_start, price_list["ST-0190901"].tier_end) == (Decimal(128), None)


async def test_a_deprecated_sku_is_kept_and_flagged(price_list: Dict[str, ServicePrice]) -> None:
    assert price_list["ST-0110001"].attributes["deprecated"] == "Yes"


async def test_a_zero_price_is_free(price_list: Dict[str, ServicePrice]) -> None:
    assert (price_list["ST-0101401"].price, price_list["ST-0101401"].model) == (Decimal(0), PriceModel.FREE)


async def test_an_unchanged_list_is_not_read_again(price_page: PricePage) -> None:
    known = PriceSource(
        provider=CloudProvider.STACKIT,
        source_key=STACKITCrawler.PRICES_URL,
        version=VERSION,
        rows=10,
        status=PriceSourceStatus.FETCHED,
    )
    crawler = crawler_knowing({STACKITCrawler.PRICES_URL: known})

    assert await read(crawler, price_page(crawler.PRICES_URL, "stackit-skus.json", {})) == []
    assert crawler.price_reads[crawler.PRICES_URL].status is PriceSourceStatus.UNCHANGED


def test_an_unknown_unit_is_kept_as_other(crawler: STACKITCrawler) -> None:
    assert crawler._sku_unit("per fortnight") == (PriceUnit.OTHER, Decimal(1))
