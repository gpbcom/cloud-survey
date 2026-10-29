from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.combell.crawler import CombellCrawler
from models.cloud.enums import CloudProvider, PriceSourceStatus, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
HOSTING_URL = "https://www.combell.com/en/hosting/web-hosting"


async def read(crawler: CombellCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> CombellCrawler:
    crawler = CombellCrawler()
    crawler.use_prices(CloudProvider.COMBELL, {}, 2.0)
    return crawler


@pytest.fixture
async def openstack(crawler: CombellCrawler, price_page: PricePage) -> Dict[str, ServicePrice]:
    meta: Dict[str, JsonValue] = {crawler.SERVICE_META: ""}
    return prices(await read(crawler, price_page(crawler.OPENSTACK_PRICES_URL, "combell-openstack-pricing.html", meta)))


async def test_the_menu_product_pages_are_requested_with_their_service(
    crawler: CombellCrawler, price_page: PricePage
) -> None:
    [_, home] = [request async for request in crawler._price_requests()]
    pages = [
        request
        for request in await read(crawler, price_page(home.url, "../crawler/combell_home.html", home.meta))
        if isinstance(request, Request)
    ]
    hosting = next(page for page in pages if page.url == HOSTING_URL)

    assert len(pages) == 10
    assert (hosting.meta[crawler.SERVICE_META], hosting.meta[crawler.FAMILY_META]) == ("Web hosting", "Hosting")


def test_an_instance_is_priced_per_month_with_its_specification(openstack: Dict[str, ServicePrice]) -> None:
    instance = openstack["openstack/Servers / instances/Standard 1 GB"]

    assert (instance.price, instance.unit, instance.currency) == (Decimal("4.91"), PriceUnit.MONTH, "EUR")
    assert (instance.vcpu, instance.memory_gib, instance.storage_gib) == (1, Decimal(1), Decimal(25))


def test_a_storage_volume_is_priced_per_gb_and_month(openstack: Dict[str, ServicePrice]) -> None:
    volume = next(price for key, price in openstack.items() if key.endswith("NVMe (Ceph)/50 GB NVMe"))

    assert (volume.price, volume.unit, volume.unit_factor, volume.storage_gib) == (
        Decimal("6.00"),
        PriceUnit.GIB_MONTH,
        Decimal(50),
        Decimal(50),
    )


async def test_a_package_keeps_its_regular_price_and_its_discount(
    crawler: CombellCrawler, price_page: PricePage
) -> None:
    meta: Dict[str, JsonValue] = {crawler.SERVICE_META: "Web hosting", crawler.FAMILY_META: "Hosting"}
    found = prices(await read(crawler, price_page(HOSTING_URL, "combell-web-hosting.html", meta)))
    business = found["en/hosting/web-hosting/Business"]

    assert (business.price, business.unit, business.service, business.family) == (
        Decimal("19.49"),
        PriceUnit.MONTH,
        "Web hosting",
        "Hosting",
    )
    assert (business.attributes["discounted_price"], len(found)) == ("5.99", 3)
    assert crawler.price_reads[HOSTING_URL].status == PriceSourceStatus.FETCHED
