from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.ovh.crawler import OVHcloudCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.stored.price_source import PriceSource

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]


async def read(crawler: OVHcloudCrawler, catalog: str, price_page: PricePage) -> Dict[str, ServicePrice]:
    response = price_page(
        crawler.PRICES_URL.format(catalog=catalog), f"ovhcloud-{catalog}.json", {crawler.PRICE_CATALOG: catalog}
    )
    results: List[Union[PriceItem, Request]] = [result async for result in crawler._parse_prices(response)]
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


def crawler_knowing(sources: Dict[str, PriceSource]) -> OVHcloudCrawler:
    crawler = OVHcloudCrawler()
    crawler.use_prices(CloudProvider.OVH, sources, 2.0)
    return crawler


@pytest.fixture
def crawler() -> OVHcloudCrawler:
    return crawler_knowing({})


@pytest.fixture
async def cloud(crawler: OVHcloudCrawler, price_page: PricePage) -> Dict[str, ServicePrice]:
    return await read(crawler, "cloud", price_page)


def test_every_catalog_is_requested(crawler: OVHcloudCrawler) -> None:
    assert len(crawler.PRICE_CATALOGS) == 10
    assert crawler.PRICES_URL.format(catalog="cloud").endswith("/order/catalog/public/cloud?ovhSubsidiary=FR")


async def test_the_catalog_is_recorded_with_its_version(
    crawler: OVHcloudCrawler, cloud: Dict[str, ServicePrice]
) -> None:
    source = crawler.price_reads[crawler.PRICES_URL.format(catalog="cloud")]

    assert (source.status, source.version, source.rows) == (PriceSourceStatus.FETCHED, "9694", len(cloud))
    assert len(cloud) == 8


async def test_an_instance_has_its_hardware(cloud: Dict[str, ServicePrice]) -> None:
    instance = cloud["cloud/addons/b3-8.consumption/default/consumption/1hour/0/0/1"]

    assert (instance.instance_type, instance.vcpu, instance.memory_gib, instance.storage_gib) == (
        "b3-8",
        Decimal(2),
        Decimal(8),
        Decimal(50),
    )
    assert (instance.price, instance.currency, instance.unit, instance.region) == (
        Decimal("0.0512"),
        "EUR",
        PriceUnit.HOUR,
        "global",
    )
    assert instance.service == "Public Cloud Instance"


async def test_a_zone_group_plan_has_its_region(cloud: Dict[str, ServicePrice]) -> None:
    assert cloud["cloud/addons/b3-8.consumption.3AZ/default/consumption/1hour/0/0/1"].region == "3az"


async def test_a_consumption_tier_keeps_its_quantities(cloud: Dict[str, ServicePrice]) -> None:
    free = cloud["cloud/addons/bandwidth_instance_out.consumption.SGP1/default/consumption/0none/0/0/1"]
    paid = cloud["cloud/addons/bandwidth_instance_out.consumption.SGP1/default/consumption/0none/0/0/1025"]

    assert (free.model, free.tier_start, free.tier_end, free.unit) == (
        PriceModel.FREE,
        Decimal(0),
        Decimal(1024),
        PriceUnit.GIB,
    )
    assert (paid.price, paid.tier_start, paid.tier_end, paid.region) == (
        Decimal("0.01"),
        Decimal(1024),
        None,
        "sgp1",
    )


@pytest.mark.parametrize(
    ("sku", "unit", "price"),
    [
        ("cloud/addons/storage-standard.consumption/default/consumption/0none/0/0/1", PriceUnit.GIB_HOUR, "0.00000972"),
        (
            "cloud/addons/ai-endpoints.llama-3-3-70b-instruct-output_tokens.unit.consumption/default/consumption/0none/0/0/1",
            PriceUnit.TOKEN,
            "0.00000067",
        ),
        (
            "cloud/addons/quantum-notebook.a10-1-gpu.minute.consumption/default/consumption/0none/0/0/1",
            PriceUnit.MINUTE,
            "0.015",
        ),
        ("cloud/plans/credit/default/installation/0none/0/0/1", PriceUnit.ONE_TIME, "0.01"),
    ],
)
async def test_the_units_are_normalized(cloud: Dict[str, ServicePrice], sku: str, unit: PriceUnit, price: str) -> None:
    assert (cloud[sku].unit, cloud[sku].unit_factor, cloud[sku].price) == (unit, Decimal(1), Decimal(price))


async def test_a_commitment_has_its_term(crawler: OVHcloudCrawler, price_page: PricePage) -> None:
    vps = await read(crawler, "vps", price_page)

    yearly = vps["vps/plans/vps-2025-model1.LZ/upfront12/renew/1month/12/1/1"]
    assert (yearly.model, yearly.term, yearly.unit, yearly.price) == (
        PriceModel.COMMITMENT,
        PriceTerm.ONE_YEAR,
        PriceUnit.MONTH,
        Decimal("6.37"),
    )
    assert (yearly.vcpu, yearly.memory_gib) == (Decimal(4), Decimal(8))
    assert vps["vps/plans/vps-2025-model1.LZ/default/installation/0none/0/0/1"].model is PriceModel.FREE


async def test_a_domain_is_priced_by_the_year_and_a_premium_one_is_a_quote(
    crawler: OVHcloudCrawler, price_page: PricePage
) -> None:
    domain = await read(crawler, "domain", price_page)

    renewal = domain["domain/plans/fr/create-default/renew/12month/0/1/1"]
    assert (renewal.unit, renewal.price, renewal.service) == (PriceUnit.YEAR, Decimal("7.79"), "Domain .fr")
    premium = domain["domain/plans/fr/create-premium/dynamic+renew/12month/0/1/1"]
    assert (premium.model, premium.price, premium.reason) == (PriceModel.QUOTE, None, OVHcloudCrawler.QUOTE_REASON)


async def test_an_unchanged_catalog_is_not_read_again(price_page: PricePage) -> None:
    url = OVHcloudCrawler.PRICES_URL.format(catalog="cloud")
    known = PriceSource(
        provider=CloudProvider.OVH, source_key=url, version="9694", rows=8, status=PriceSourceStatus.FETCHED
    )
    crawler = crawler_knowing({url: known})

    assert await read(crawler, "cloud", price_page) == {}
    assert crawler.price_reads[url].status is PriceSourceStatus.UNCHANGED


def test_an_unknown_commercial_unit_falls_back_to_the_interval(crawler: OVHcloudCrawler) -> None:
    pricing: Dict[str, JsonValue] = {"capacities": ["renew"], "interval": 1, "intervalUnit": "month"}

    assert crawler._pricing_unit("parsec*h", pricing) == (PriceUnit.MONTH, Decimal(1), "1 month")
