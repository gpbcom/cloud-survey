from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.cloudru.crawler import CloudRuCrawler
from models.cloud.enums import CloudProvider, PriceSourceStatus, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
COMPUTE = "/tariffs/evolution/evolution-compute"
DRAAS = "/tariffs/vmware/services/draas-v"


async def read(crawler: CloudRuCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> CloudRuCrawler:
    crawler = CloudRuCrawler()
    crawler.use_prices(CloudProvider.CLOUD_RU, {}, 2.0)
    return crawler


@pytest.fixture
async def documents(crawler: CloudRuCrawler, price_page: PricePage) -> List[Request]:
    [request] = [request async for request in crawler._price_requests()]
    results = await read(crawler, price_page(request.url, "cloudru-tariffs-index.html", {}))
    return [result for result in results if isinstance(result, Request)]


async def document(
    crawler: CloudRuCrawler, documents: List[Request], price_page: PricePage, path: str, fixture: str
) -> Dict[str, ServicePrice]:
    request = next(request for request in documents if request.url.endswith(path))
    return prices(await read(crawler, price_page(request.url, fixture, request.meta)))


def test_the_navigation_lists_the_tariff_documents_with_their_service(
    crawler: CloudRuCrawler, documents: List[Request]
) -> None:
    compute = next(request for request in documents if request.url.endswith(COMPUTE))

    assert len(documents) == 109
    assert not any(request.url.endswith("/index") or "/archive" in request.url for request in documents)
    assert compute.meta[crawler.SERVICE_META] == "Evolution Compute"


async def test_an_instance_is_priced_by_the_hour_without_vat(
    crawler: CloudRuCrawler, documents: List[Request], price_page: PricePage
) -> None:
    found = await document(crawler, documents, price_page, COMPUTE, "cloudru-tariffs-evolution-compute.html")
    instance = found[f"{COMPUTE}/Виртуальная машина 12vCPU/24GB RAM/шт./час"]

    assert (instance.price, instance.unit, instance.vcpu, instance.memory_gib) == (
        Decimal("19.47"),
        PriceUnit.HOUR,
        12,
        Decimal(24),
    )
    assert (instance.attributes["vat"], instance.attributes["price_with_vat"]) == ("excluded", "23.7534")
    assert (instance.currency, instance.family, instance.effective_from) == ("RUB", "evolution", date(2026, 10, 14))


async def test_a_resource_is_priced_per_unit_and_period(
    crawler: CloudRuCrawler, documents: List[Request], price_page: PricePage
) -> None:
    found = await document(crawler, documents, price_page, DRAAS, "cloudru-tariffs-draas-v.html")
    memory = found[f"{DRAAS}/Виртуальная память, резерв ресурсов/ГБ/месяц"]

    assert (memory.price, memory.unit, memory.service) == (Decimal(93), PriceUnit.GIB_MONTH, "Резервный ЦОД (DRAAS) V")
    assert len(found) == 6


async def test_each_document_is_a_source(
    crawler: CloudRuCrawler, documents: List[Request], price_page: PricePage
) -> None:
    found = await document(crawler, documents, price_page, DRAAS, "cloudru-tariffs-draas-v.html")
    source = crawler.price_reads[f"https://cloud.ru/documents{DRAAS}"]

    assert (source.status, source.rows) == (PriceSourceStatus.FETCHED, len(found))


def test_a_long_instance_name_gives_way_to_its_flavor_code(crawler: CloudRuCrawler) -> None:
    name = (
        "Виртуальная машина (ECS) Linux тип GPU Computing-accelerated (P2s) NVIDIA V100 32 vCPU 256ГБ RAM "
        "(p2s.8xlarge.8.linux)"
    )
    row = {"Наименование": name, "Единица тарификации": "шт.", "Период тарификации": "час", "Цена, без НДС": "10"}

    price = crawler._row_price(row, "GPU", f"https://cloud.ru/documents{COMPUTE}", None)

    assert price is not None
    assert (price.instance_type, price.vcpu, price.memory_gib) == ("p2s.8xlarge.8.linux", 32, Decimal(256))
