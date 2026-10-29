from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.vkcloud.crawler import VKCloudCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]


@pytest.fixture
def crawler() -> VKCloudCrawler:
    crawler = VKCloudCrawler()
    crawler.use_prices(CloudProvider.VK_CLOUD, {}, 2.0)
    return crawler


@pytest.fixture
async def found(crawler: VKCloudCrawler, price_page: PricePage) -> Dict[str, ServicePrice]:
    [request] = [request async for request in crawler._price_requests()]
    results: List[Union[PriceItem, Request]] = [
        result async for result in crawler._parse_prices(price_page(request.url, "vkcloud-pricelist.html", {}))
    ]
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


def test_a_resource_is_priced_per_30_days_with_its_price_per_minute(found: Dict[str, ServicePrice]) -> None:
    cpu = found["Виртуальные серверы//CPU, Intel Cascade Lake/1 шт."]
    ram = found["Виртуальные серверы//RAM/1 Гб"]

    assert (cpu.price, cpu.unit, cpu.currency, cpu.model) == (
        Decimal(820),
        PriceUnit.UNIT_MONTH,
        "RUB",
        PriceModel.ON_DEMAND,
    )
    assert (cpu.attributes["per_minute"], cpu.attributes["vat"]) == ("0.018972", "included")
    assert (ram.price, ram.unit) == (Decimal(223), PriceUnit.GIB_MONTH)


def test_an_instance_flavor_is_a_monthly_instance_and_a_discount_keeps_its_former_price(
    found: Dict[str, ServicePrice],
) -> None:
    gpu = found["Виртуальные серверы (GPU)//GPU1-16-48-V100-1 (16 CPU, 48 RAM, 16 VRAM)/1 шт"]

    assert (gpu.instance_type, gpu.vcpu, gpu.memory_gib, gpu.unit) == (
        "GPU1-16-48-V100-1",
        16,
        Decimal(48),
        PriceUnit.MONTH,
    )
    assert (gpu.price, gpu.attributes["list_price"]) == (Decimal(87433), "174867")


def test_a_usage_and_a_daily_price_are_normalized(found: Dict[str, ServicePrice]) -> None:
    traffic = found["CDN//Общий трафик/1 ГБ"]
    seat = next(price for key, price in found.items() if key.endswith(":Бухгалтерия 8/1 пользователь"))

    assert (traffic.price, traffic.unit, traffic.unit_factor) == (Decimal("0.66"), PriceUnit.GIB, Decimal(1))
    assert (seat.price, seat.unit, seat.unit_factor) == (Decimal(64), PriceUnit.UNIT_HOUR, Decimal(24))


def test_a_restarted_header_and_a_price_on_request(found: Dict[str, ServicePrice]) -> None:
    hot = found["VK Object Storage (объектное хранилище S3) - Hotbox/Параметры горячих данных/Хранение данных/1 Гб"]
    port = found["Подключение каналов связи//Аренда порта на коммутаторе/"]

    assert (hot.price, found["VK Object Storage (объектное хранилище S3) - Hotbox//Исходящий трафик/1 Гб"].price) == (
        Decimal("2.28"),
        Decimal("1.31"),
    )
    assert (port.model, port.price, port.reason is not None) == (PriceModel.QUOTE, None, True)


def test_the_price_list_is_one_source(crawler: VKCloudCrawler, found: Dict[str, ServicePrice]) -> None:
    source = crawler.price_reads[crawler.PRICELIST_URL]

    assert (source.status, source.rows, len(found)) == (PriceSourceStatus.FETCHED, len(found), 30)
