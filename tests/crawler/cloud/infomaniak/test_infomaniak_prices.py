from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.infomaniak.crawler import InfomaniakCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
QUERIES = ["3538198066", "461866520", "55375645"]


async def read(crawler: InfomaniakCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> InfomaniakCrawler:
    crawler = InfomaniakCrawler()
    crawler.use_prices(CloudProvider.INFOMANIAK, {}, 2.0)
    return crawler


@pytest.fixture
async def queries(crawler: InfomaniakCrawler, price_page: PricePage) -> List[Union[PriceItem, Request]]:
    results = await read(crawler, price_page(crawler.PRICES_URL, "infomaniak-page-data.json", {}))
    for value in QUERIES:
        url = crawler.QUERY_URL.format(hash=value)
        results += await read(crawler, price_page(url, f"infomaniak-sq-{value}.json", {crawler.PRICE_QUERY: value}))
    return results


async def test_the_page_data_requests_its_static_queries(crawler: InfomaniakCrawler, price_page: PricePage) -> None:
    results = await read(crawler, price_page(crawler.PRICES_URL, "infomaniak-page-data.json", {}))

    assert sorted(request.meta[crawler.PRICE_QUERY] for request in results if isinstance(request, Request)) == sorted(
        QUERIES
    )
    assert crawler.PRICES_URL not in crawler.price_reads


async def test_the_prices_are_recorded_once_every_query_is_read(
    crawler: InfomaniakCrawler, queries: List[Union[PriceItem, Request]]
) -> None:
    source = crawler.price_reads[crawler.PRICES_URL]

    assert (source.status, source.rows) == (PriceSourceStatus.FETCHED, len(prices(queries)))
    assert len(prices(queries)) > 200


async def test_a_flavor_is_priced_per_hour_in_euros(queries: List[Union[PriceItem, Request]]) -> None:
    flavor = prices(queries)["instances/a12_ram24_disk20_perf1"]

    assert (flavor.price, flavor.currency, flavor.unit) == (Decimal("0.04565"), "EUR", PriceUnit.HOUR)
    assert (flavor.vcpu, flavor.memory_gib, flavor.storage_gib) == (Decimal(12), Decimal(24), Decimal(20))


@pytest.mark.parametrize(
    ("key", "unit"),
    [
        ("volume_size/CEPH_1_perf2", PriceUnit.GIB_HOUR),
        ("storage_objects_outgoing_bytes/default", PriceUnit.GIB),
        ("ip_floating/default", PriceUnit.UNIT_HOUR),
        ("software_licence/win2k22", PriceUnit.UNIT_HOUR),
    ],
)
async def test_the_resources_have_their_units(
    queries: List[Union[PriceItem, Request]], key: str, unit: PriceUnit
) -> None:
    assert prices(queries)[key].unit is unit


async def test_the_managed_plans_are_priced(queries: List[Union[PriceItem, Request]]) -> None:
    found = prices(queries)

    database = found["Database as a Service/mysql/essential-db-4"]
    assert (database.price, database.vcpu, database.memory_gib, database.family) == (
        Decimal("0.02671"),
        Decimal(1),
        Decimal(4),
        "mysql",
    )
    shared = found["Kubernetes Service//shared"]
    assert (shared.model, shared.price) == (PriceModel.FREE, Decimal(0))
