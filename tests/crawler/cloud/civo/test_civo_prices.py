from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.civo.crawler import CivoCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceKind, PriceSourceStatus, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
L40S = "nvidia-l40s-48gb/Small 1 x NVIDIA L40S - 48GB | 96 GB | 12 | 200GB NVMe | FREE"


@pytest.fixture
def crawler() -> CivoCrawler:
    crawler = CivoCrawler()
    crawler.use_prices(CloudProvider.CIVO, {}, 2.0)
    return crawler


@pytest.fixture
async def found(crawler: CivoCrawler, price_page: PricePage) -> Dict[str, ServicePrice]:
    response = price_page(crawler.PRICING_URL, "civo-pricing.html", {})
    results: List[Union[PriceItem, Request]] = [result async for result in crawler._parse_prices(response)]
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


async def test_the_page_is_recorded(crawler: CivoCrawler, found: Dict[str, ServicePrice]) -> None:
    source = crawler.price_reads[crawler.PRICING_URL]

    assert (source.status, source.rows) == (PriceSourceStatus.FETCHED, len(found))
    assert {price.source_kind for price in found.values()} == {PriceSourceKind.PAGE}


async def test_a_gpu_has_on_demand_and_commitment_prices(found: Dict[str, ServicePrice]) -> None:
    on_demand, yearly = found[f"{L40S}/hourly/on-demand"], found[f"{L40S}/hourly/12"]

    assert (on_demand.price, on_demand.unit, on_demand.model, on_demand.currency) == (
        Decimal("1.29"),
        PriceUnit.HOUR,
        PriceModel.ON_DEMAND,
        "USD",
    )
    assert (yearly.price, yearly.model, yearly.term) == (Decimal("1.09"), PriceModel.COMMITMENT, PriceTerm.ONE_YEAR)
    assert (on_demand.vcpu, on_demand.memory_gib, on_demand.storage_gib, on_demand.service) == (
        Decimal(12),
        Decimal(96),
        Decimal(200),
        "Nvidia Gpus",
    )
    assert found[f"{L40S}/monthly/on-demand"].price == Decimal("941.70")


async def test_a_storage_is_priced_per_gib(found: Dict[str, ServicePrice]) -> None:
    volume = next(price for price in found.values() if price.family == "volumes" and price.unit is PriceUnit.GIB_MONTH)

    assert (volume.price, volume.instance_type) == (Decimal("0.11"), None)


async def test_the_traffic_is_free(found: Dict[str, ServicePrice]) -> None:
    traffic = [price for price in found.values() if price.family == "data-transfer"]

    assert {(price.model, price.unit) for price in traffic} == {(PriceModel.FREE, PriceUnit.GIB)}
    assert len(traffic) == 2


async def test_an_unpriced_commitment_is_skipped(found: Dict[str, ServicePrice]) -> None:
    b200 = [key for key in found if key.startswith("nvidia-b200/")]

    assert not [key for key in b200 if key.endswith("/hourly/on-demand")]
    assert any(key.endswith("/hourly/24") for key in b200)
