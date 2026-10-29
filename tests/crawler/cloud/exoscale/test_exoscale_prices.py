from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.exoscale.crawler import ExoscaleCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceKind, PriceSourceStatus, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
ENDPOINTS = ["cdn", "dbaas-pg", "dns", "kms", "network", "opencompute", "sos"]


async def read(crawler: ExoscaleCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> ExoscaleCrawler:
    crawler = ExoscaleCrawler()
    crawler.use_prices(CloudProvider.EXOSCALE, {}, 2.0)
    return crawler


@pytest.fixture
async def pricing(crawler: ExoscaleCrawler, price_page: PricePage) -> List[Union[PriceItem, Request]]:
    results = await read(crawler, price_page(crawler.PRICING_URL, "exoscale-pricing.html", {}))
    for endpoint in ENDPOINTS:
        url = crawler.PRICES_API_URL.format(endpoint=endpoint)
        meta: Dict[str, JsonValue] = {crawler.PRICE_ENDPOINT: endpoint}
        results += await read(crawler, price_page(url, f"exoscale-api-{endpoint}.json", meta))
    return results


async def test_the_page_requests_the_endpoints_its_prices_read(crawler: ExoscaleCrawler, price_page: PricePage) -> None:
    results = await read(crawler, price_page(crawler.PRICING_URL, "exoscale-pricing.html", {}))

    requests = [result for result in results if isinstance(result, Request)]
    assert [request.meta[crawler.PRICE_ENDPOINT] for request in requests] == ENDPOINTS
    assert requests[0].url == "https://portal.exoscale.com/api/pricing/cdn"
    assert prices(results) == {}


async def test_the_prices_come_once_every_endpoint_is_read(
    crawler: ExoscaleCrawler, pricing: List[Union[PriceItem, Request]]
) -> None:
    source = crawler.price_reads[crawler.PRICING_URL]

    assert source.status is PriceSourceStatus.FETCHED
    assert source.rows == len(prices(pricing)) == crawler.price_count


async def test_an_instance_has_its_hardware_and_api_price(pricing: List[Union[PriceItem, Request]]) -> None:
    micro = prices(pricing)["opencompute/standard/micro"]

    assert (micro.service, micro.instance_type, micro.region) == ("Standard Instances", "Micro", "global")
    assert (micro.vcpu, micro.memory_gib, micro.storage_gib) == (Decimal(1), Decimal("0.5"), Decimal(10))
    assert (micro.price, micro.currency, micro.unit) == (Decimal("0.00729"), "EUR", PriceUnit.HOUR)
    assert (micro.source_kind, micro.source_url) == (PriceSourceKind.API, ExoscaleCrawler.PRICING_URL)


async def test_a_managed_database_plan_is_priced_by_the_hour(pricing: List[Union[PriceItem, Request]]) -> None:
    plan = prices(pricing)["dbaas-pg/hobbyist-2"]

    assert (plan.service, plan.unit, plan.vcpu, plan.memory_gib) == (
        "Managed PostgreSQL",
        PriceUnit.HOUR,
        Decimal(2),
        Decimal(2),
    )
    assert plan.attributes["Max. Connections"] == "25"


@pytest.mark.parametrize(
    ("sku", "unit", "price"),
    [
        ("sos/storage_volume_tier1", PriceUnit.GIB_HOUR, Decimal("0.0000275")),
        ("sos/storage_traffic", PriceUnit.GIB, Decimal("0.02")),
        ("network/eip_address", PriceUnit.UNIT_HOUR, Decimal("0.01389")),
        ("Network/Private Connect/One-Off Setup Cost", PriceUnit.ONE_TIME, Decimal(2500)),
        ("Network/Private Connect/Direct Port per month", PriceUnit.MONTH, Decimal(500)),
        ("dns/medium", PriceUnit.MONTH, Decimal(5)),
        ("kms/additional_key", PriceUnit.MONTH, Decimal("1.0000008")),
    ],
)
async def test_the_units_come_from_the_header_the_row_or_the_section(
    pricing: List[Union[PriceItem, Request]], sku: str, unit: PriceUnit, price: Decimal
) -> None:
    found = prices(pricing)[sku]

    assert (found.unit, found.price) == (unit, price)


async def test_a_volume_tier_has_its_bounds(pricing: List[Union[PriceItem, Request]]) -> None:
    tier = prices(pricing)["cdn/tier2"]

    assert (tier.unit, tier.tier_start, tier.tier_end) == (PriceUnit.GIB, Decimal(25000), Decimal(100000))


async def test_a_language_model_has_one_price_per_token_kind(pricing: List[Union[PriceItem, Request]]) -> None:
    found = {key: price for key, price in prices(pricing).items() if key.startswith("On-Demand Inference/")}

    model = found["On-Demand Inference/Qwen3.8-27B/Output per 1M tokens"]
    assert (model.unit, model.unit_factor, model.price) == (PriceUnit.TOKEN, Decimal(1_000_000), Decimal("2.40"))
    assert model.source_kind is PriceSourceKind.PAGE
    assert "On-Demand Inference/Qwen3-Embedding-8B/Output per 1M tokens" not in found


async def test_the_written_prices_are_read(pricing: List[Union[PriceItem, Request]]) -> None:
    found = prices(pricing)

    assert found["Network/Traffic INBOUND"].model is PriceModel.FREE
    assert found["Support/Built-In/Included for all customers."].model is PriceModel.INCLUDED
    enterprise = found["Support/Enterprise/For companies running critical workloads."]
    assert (enterprise.model, enterprise.price, enterprise.reason) == (
        PriceModel.NOT_PUBLIC,
        None,
        "5% of usage (min. 1'500)",
    )


async def test_a_missing_endpoint_price_skips_the_row(crawler: ExoscaleCrawler) -> None:
    crawler.price_api = {"opencompute": {"running_micro": "0.00729000"}}

    assert crawler._cell_price("{{ prices.opencompute.standard.tiny[currency] | number:8 }}") is None
    assert crawler._cell_price("{{ prices.opencompute.standard.micro[currency] | number:8 }}") == (
        Decimal("0.00729"),
        PriceModel.ON_DEMAND,
        None,
    )


async def test_a_failed_endpoint_leaves_the_page_unread(crawler: ExoscaleCrawler, price_page: PricePage) -> None:
    results = await read(crawler, price_page(crawler.PRICING_URL, "exoscale-pricing.html", {}))
    failed_url = crawler.PRICES_API_URL.format(endpoint="cdn")
    failed = Response(
        url=failed_url, content=b"", status=502, reason="Bad", cookies={}, headers={}, request_headers={}, meta={}
    )

    results += await read(crawler, failed)
    assert crawler.price_failures == {failed_url}
    assert crawler.PRICING_URL not in crawler.price_reads
    assert prices(results) == {}


async def test_a_page_without_table_is_a_failure(crawler: ExoscaleCrawler) -> None:
    empty = Response(
        url=ExoscaleCrawler.PRICING_URL,
        content=b"<html><body></body></html>",
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
        meta={},
    )

    assert await read(crawler, empty) == []
    assert crawler.price_failures == {ExoscaleCrawler.PRICING_URL}
