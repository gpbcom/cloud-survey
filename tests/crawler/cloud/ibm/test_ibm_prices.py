from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.ibm.crawler import IBMCloudCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
PLAN: Dict[str, JsonValue] = {
    IBMCloudCrawler.PRICE_STAGE: "pricing",
    IBMCloudCrawler.SERVICE_META: "Virtual Server for VPC",
    IBMCloudCrawler.SERVICE_NAME_META: "is.instance",
    IBMCloudCrawler.PLAN_META: "plan-bx3d",
    IBMCloudCrawler.PLAN_NAME_META: "bx3d-128x640",
}


async def read(crawler: IBMCloudCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


def missing(url: str, meta: Dict[str, JsonValue]) -> Response:
    return Response(
        url=url, content=b"{}", status=404, reason="Not Found", cookies={}, headers={}, request_headers={}, meta=meta
    )


@pytest.fixture
def crawler() -> IBMCloudCrawler:
    crawler = IBMCloudCrawler()
    crawler.use_prices(CloudProvider.IBM, {}, 2.0)
    crawler.price_pending = 1
    return crawler


async def test_the_services_page_requests_the_next_page_and_the_active_services_plans(
    crawler: IBMCloudCrawler, price_page: PricePage
) -> None:
    meta: Dict[str, JsonValue] = {crawler.PRICE_STAGE: "services", crawler.OFFSET_META: 0}
    results = await read(crawler, price_page(crawler.SERVICES_URL.format(offset=0), "ibm-services.json", meta))

    urls = [result.url for result in results if isinstance(result, Request)]
    assert urls == [
        crawler.SERVICES_URL.format(offset=3),
        crawler.PLANS_URL.format(id="databases-for-elasticsearch", offset=0),
        crawler.PLANS_URL.format(id="20aaec51-7943-4509-a180-5360036fd649", offset=0),
    ]
    assert crawler.price_pending == 3


async def test_a_lite_plan_is_free_and_the_others_have_their_pricing_requested(
    crawler: IBMCloudCrawler, price_page: PricePage
) -> None:
    meta: Dict[str, JsonValue] = {crawler.PRICE_STAGE: "plans", crawler.SERVICE_META: "Object Storage"}
    results = await read(crawler, price_page("https://plans", "ibm-plans.json", meta))

    requests = [result for result in results if isinstance(result, Request)]
    assert [request.meta[crawler.PLAN_NAME_META] for request in requests] == ["cos-one-rate-plan", "standard"]
    lite = next(iter(prices(results).values()))
    assert (lite.model, lite.price, lite.service, lite.unit) == (
        PriceModel.FREE,
        Decimal(0),
        "Object Storage",
        PriceUnit.OTHER,
    )


async def test_a_plan_pricing_has_one_price_per_metric_and_tier(
    crawler: IBMCloudCrawler, price_page: PricePage
) -> None:
    found = prices(await read(crawler, price_page("https://pricing", "ibm-plan-pricing.json", PLAN)))

    first, second, last = (found[f"plan-bx3d@global/part-is.redhatOS/{index}"] for index in range(3))
    assert (first.tier_start, first.tier_end, first.price) == (Decimal(0), Decimal(8), Decimal("0.01717"))
    assert (second.tier_start, second.tier_end) == (Decimal(8), Decimal(127))
    assert (last.tier_start, last.tier_end, last.price) == (Decimal(127), None, Decimal("0.00909"))
    assert (first.unit, first.currency, first.region) == (PriceUnit.VCPU_HOUR, "USD", "global")
    assert (first.instance_type, first.vcpu, first.memory_gib) == ("bx3d-128x640", Decimal(128), Decimal(640))
    assert str(first.effective_from) == "2026-10-01"
    windows = found["plan-bx3d@global/part-is.windowsOS/0"]
    assert (windows.tier_start, windows.tier_end, windows.price) == (Decimal(0), None, Decimal("0.05151"))
    assert found["plan-bx3d@global/part-is.windowsOS-BYOL/0"].model is PriceModel.FREE


async def test_a_plan_priced_by_region_is_read_from_its_deployments(
    crawler: IBMCloudCrawler, price_page: PricePage
) -> None:
    fallback = await read(crawler, missing("https://pricing/plan", PLAN))

    assert [request.url for request in fallback if isinstance(request, Request)] == [
        crawler.DEPLOYMENTS_URL.format(id="plan-bx3d")
    ]
    meta: Dict[str, JsonValue] = {**PLAN, crawler.PRICE_STAGE: "deployments"}
    listing = await read(crawler, price_page("https://deployments", "ibm-deployments.json", meta))
    assert [request.meta[crawler.DEPLOYMENT_META] for request in listing if isinstance(request, Request)] == [
        "databases-for-postgresql-standard:au-syd",
        "databases-for-postgresql-standard:br-sao",
    ]
    regional = prices(await read(crawler, price_page("https://pricing/au-syd", "ibm-deployment-pricing.json", PLAN)))
    assert {price.region for price in regional.values()} == {"au-syd"}
    assert all(key.startswith("plan-bx3d@au-syd/") for key in regional)


async def test_a_region_without_pricing_is_not_public(crawler: IBMCloudCrawler) -> None:
    meta: Dict[str, JsonValue] = {**PLAN, crawler.DEPLOYMENT_META: "plan-bx3d:eu-de"}
    found = prices(await read(crawler, missing("https://pricing/eu-de", meta)))

    assert [(price.sku_key, price.model, price.region) for price in found.values()] == [
        ("plan-bx3d@eu-de/plan", PriceModel.NOT_PUBLIC, "eu-de")
    ]
    assert crawler.price_failures == set()


async def test_a_pricing_without_metric_is_not_public(crawler: IBMCloudCrawler, price_page: PricePage) -> None:
    response = Response(
        url="https://pricing",
        content=b'{"deployment_location": "global", "metrics": null}',
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
        meta=PLAN,
    )

    found = prices(await read(crawler, response))
    assert [(price.model, price.reason) for price in found.values()] == [
        (PriceModel.NOT_PUBLIC, IBMCloudCrawler.NO_PRICING_REASON)
    ]


async def test_the_catalog_is_recorded_once_nothing_is_pending(crawler: IBMCloudCrawler, price_page: PricePage) -> None:
    await read(crawler, price_page("https://pricing", "ibm-plan-pricing.json", PLAN))

    source = crawler.price_reads[crawler.GLOBAL_CATALOG_URL]
    assert (source.status, source.rows) == (PriceSourceStatus.FETCHED, crawler.price_rows)
    assert crawler.price_rows > 0


async def test_a_failure_keeps_the_catalog_unrecorded(crawler: IBMCloudCrawler) -> None:
    crawler.price_pending = 2
    blocked = Response(
        url="https://plans",
        content=b"",
        status=500,
        reason="Error",
        cookies={},
        headers={},
        request_headers={},
        meta={},
    )

    await read(crawler, blocked)
    assert crawler.price_failures == {"https://plans"}
    assert crawler.GLOBAL_CATALOG_URL not in crawler.price_reads


@pytest.mark.parametrize(
    ("charge", "unit"),
    [
        ({"charge_unit": "Gigabyte-Month", "charge_unit_name": "GIGABYTE_MONTHS"}, PriceUnit.GIB_MONTH),
        ({"charge_unit": "Instance-Hour", "charge_unit_name": "INSTANCE_HOURS"}, PriceUnit.HOUR),
        ({"charge_unit": "API Call", "charge_unit_name": "API_CALLS", "charge_unit_quantity": 1000}, PriceUnit.REQUEST),
        ({"charge_unit": "Fortnight", "charge_unit_name": "FORTNIGHTS"}, PriceUnit.OTHER),
    ],
)
def test_the_charge_units(crawler: IBMCloudCrawler, charge: Dict[str, JsonValue], unit: PriceUnit) -> None:
    assert crawler._charge_unit(charge)[0] is unit
