from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.oracle.crawler import OracleCloudCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.stored.price_source import PriceSource

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
VERSION = "2026-10-08T14:38:16.165Z"


async def read(crawler: OracleCloudCrawler, price_page: PricePage) -> Dict[str, ServicePrice]:
    response = price_page(crawler.PRICES_URL, "oracle-products.json", {})
    results: List[Union[PriceItem, Request]] = [result async for result in crawler._parse_prices(response)]
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


def crawler_knowing(sources: Dict[str, PriceSource]) -> OracleCloudCrawler:
    crawler = OracleCloudCrawler()
    crawler.use_prices(CloudProvider.ORACLE, sources, 2.0)
    return crawler


@pytest.fixture
def crawler() -> OracleCloudCrawler:
    return crawler_knowing({})


@pytest.fixture
async def parts(crawler: OracleCloudCrawler, price_page: PricePage) -> Dict[str, ServicePrice]:
    return await read(crawler, price_page)


async def test_every_part_is_priced_in_dollars(crawler: OracleCloudCrawler, parts: Dict[str, ServicePrice]) -> None:
    source = crawler.price_reads[crawler.PRICES_URL]

    assert len(parts) == 8
    assert (source.status, source.version, source.rows) == (PriceSourceStatus.FETCHED, VERSION, 8)
    assert {price.currency for price in parts.values()} == {"USD"}


async def test_a_tiered_part_has_one_price_per_tier(parts: Dict[str, ServicePrice]) -> None:
    free, paid = parts["B88327/0"], parts["B88327/10240"]

    assert (free.model, free.tier_start, free.tier_end, free.unit) == (
        PriceModel.FREE,
        Decimal(0),
        Decimal(10240),
        PriceUnit.GIB,
    )
    assert (paid.price, paid.tier_start, paid.tier_end) == (Decimal("0.0085"), Decimal(10240), None)


@pytest.mark.parametrize(
    ("part", "unit", "factor"),
    [
        ("B109635", PriceUnit.VCPU_HOUR, Decimal(1)),
        ("B108776", PriceUnit.VCPU_HOUR, Decimal(2)),
        ("B111847", PriceUnit.TOKEN, Decimal(1_000_000)),
        ("B109166", PriceUnit.GIB_MONTH, Decimal(1)),
        ("B108077", PriceUnit.REQUEST, Decimal(10_000)),
        ("B110464", PriceUnit.OTHER, Decimal(1)),
    ],
)
async def test_the_metrics_are_normalized(
    parts: Dict[str, ServicePrice], part: str, unit: PriceUnit, factor: Decimal
) -> None:
    assert (parts[part].unit, parts[part].unit_factor) == (unit, factor)


async def test_a_part_keeps_its_name_and_service(parts: Dict[str, ServicePrice]) -> None:
    storage = parts["B109166"]

    assert storage.service == "HeatWave Cluster"
    assert storage.attributes["displayName"] == "MySQL HeatWave - AWS - Storage"
    assert (storage.price, storage.region) == (Decimal("0.03"), "global")


async def test_an_unchanged_list_is_not_read_again(price_page: PricePage) -> None:
    known = PriceSource(
        provider=CloudProvider.ORACLE,
        source_key=OracleCloudCrawler.PRICES_URL,
        version=VERSION,
        rows=8,
        status=PriceSourceStatus.FETCHED,
    )
    crawler = crawler_knowing({OracleCloudCrawler.PRICES_URL: known})

    assert await read(crawler, price_page) == {}
    assert crawler.price_reads[crawler.PRICES_URL].status is PriceSourceStatus.UNCHANGED


@pytest.mark.parametrize(
    ("metric", "unit", "factor"),
    [
        ("1MIL Function Invocations", PriceUnit.REQUEST, Decimal(1_000_000)),
        ("10,000 GB Memory-Seconds", PriceUnit.GIB_SECOND, Decimal(10_000)),
        ("5K Messages Per Hour", PriceUnit.HOUR, Decimal(1)),
        ("NVMe Terabyte Per Hour", PriceUnit.GIB_HOUR, Decimal(1024)),
        ("Resource Possession Per Day", PriceUnit.UNIT_HOUR, Decimal(24)),
        ("A fortnight of something", PriceUnit.OTHER, Decimal(1)),
    ],
)
def test_the_metric_rules(crawler: OracleCloudCrawler, metric: str, unit: PriceUnit, factor: Decimal) -> None:
    assert crawler._metric_unit(metric, "A part") == (unit, factor)
