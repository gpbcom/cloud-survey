from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.aruba.crawler import ArubaCloudCrawler
from crawler.cloud.base import PriceItem
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]


async def read(crawler: ArubaCloudCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> List[ServicePrice]:
    return [item["model"] for item in results if isinstance(item, dict) and isinstance(item["model"], ServicePrice)]


@pytest.fixture
def crawler() -> ArubaCloudCrawler:
    crawler = ArubaCloudCrawler()
    crawler.use_prices(CloudProvider.ARUBA, {}, 2.0)
    return crawler


@pytest.fixture
async def pages(crawler: ArubaCloudCrawler, price_page: PricePage) -> List[Request]:
    [request] = [request async for request in crawler._price_requests()]
    return [
        result
        for result in await read(crawler, price_page(request.url, "aruba-pricing.html", {}))
        if isinstance(result, Request)
    ]


async def page(
    crawler: ArubaCloudCrawler, pages: List[Request], price_page: PricePage, path: str, fixture: str
) -> List[ServicePrice]:
    request = next(request for request in pages if request.url.endswith(path))
    return prices(await read(crawler, price_page(request.url, fixture, request.meta)))


def test_the_pricing_cards_link_the_product_pricing_pages(crawler: ArubaCloudCrawler, pages: List[Request]) -> None:
    services = {request.url.rsplit("/", 1)[-1]: request.meta[crawler.SERVICE_META] for request in pages}

    assert len(pages) == 32
    assert services["openstack-cloud-server"] == "OpenStack Cloud Server"
    assert services["server-bare-metal"] == "Dedicated Servers"


async def test_a_server_is_priced_by_the_hour_month_and_year(
    crawler: ArubaCloudCrawler, pages: List[Request], price_page: PricePage
) -> None:
    found = await page(crawler, pages, price_page, "openstack-cloud-server", "aruba-openstack-cloud-server.html")
    server = [price for price in found if price.instance_type == "PRO O1A2"]

    assert [(price.price, price.unit, price.unit_factor, price.model, price.term) for price in server] == [
        (Decimal("0.019"), PriceUnit.HOUR, Decimal(1), PriceModel.ON_DEMAND, PriceTerm.NONE),
        (Decimal("13.20"), PriceUnit.MONTH, Decimal(1), PriceModel.ON_DEMAND, PriceTerm.NONE),
        (Decimal("154.00"), PriceUnit.MONTH, Decimal(12), PriceModel.COMMITMENT, PriceTerm.ONE_YEAR),
    ]
    assert (server[0].vcpu, server[0].memory_gib, server[0].storage_gib, server[0].currency) == (
        1,
        Decimal(2),
        Decimal(20),
        "EUR",
    )
    assert server[0].attributes["vat"] == "excluded"


async def test_tokens_are_priced_per_million_by_side(
    crawler: ArubaCloudCrawler, pages: List[Request], price_page: PricePage
) -> None:
    found = await page(crawler, pages, price_page, "ai-models", "aruba-ai-models.html")
    llama = [price for price in found if "Llama-3.1-8B-Instruct" in price.sku_key]

    assert [(price.price, price.unit, price.unit_factor, price.attributes["side"]) for price in llama] == [
        (Decimal("0.0164"), PriceUnit.TOKEN, Decimal(1_000_000), "input"),
        (Decimal("0.0409"), PriceUnit.TOKEN, Decimal(1_000_000), "output"),
    ]


async def test_a_yearly_fee_alone_and_a_free_price(
    crawler: ArubaCloudCrawler, pages: List[Request], price_page: PricePage
) -> None:
    found = await page(crawler, pages, price_page, "domains-and-DNS", "aruba-domains.html")
    com = [price for price in found if "/.com/" in price.sku_key]

    assert [(price.price, price.unit, price.model) for price in com] == [
        (Decimal(0), PriceUnit.UNIT, PriceModel.FREE),
        (Decimal("14.99"), PriceUnit.YEAR, PriceModel.ON_DEMAND),
        (Decimal("14.99"), PriceUnit.YEAR, PriceModel.ON_DEMAND),
    ]


async def test_a_price_of_a_storage_size_is_per_gb_and_each_page_is_a_source(
    crawler: ArubaCloudCrawler, pages: List[Request], price_page: PricePage
) -> None:
    found = await page(crawler, pages, price_page, "cloud-object-storage", "aruba-object-storage.html")
    pay_per_use = found[0]
    source = crawler.price_reads["https://www.arubacloud.com/pricing/public-cloud/cloud-object-storage"]

    assert (pay_per_use.price, pay_per_use.unit, pay_per_use.unit_factor) == (
        Decimal("0.00028"),
        PriceUnit.GIB_HOUR,
        Decimal(10),
    )
    assert found[1].storage_gib == Decimal(4096)
    assert (source.status, source.rows) == (PriceSourceStatus.FETCHED, len(found))


async def test_a_price_written_amount_first_takes_its_period_from_its_column(
    crawler: ArubaCloudCrawler, pages: List[Request], price_page: PricePage
) -> None:
    found = await page(crawler, pages, price_page, "server-quickstart", "aruba-quickstart.html")
    server = next(price for price in found if "QB - 1230" in price.sku_key)

    assert (server.price, server.unit, server.model) == (Decimal("19.99"), PriceUnit.MONTH, PriceModel.ON_DEMAND)
    assert server.attributes["status"] == "sold out"
    assert len(found) == 12


async def test_the_product_pages_are_read_for_their_price_tables(price_page: PricePage) -> None:
    crawler = ArubaCloudCrawler()
    url = "https://www.arubacloud.com/container/container-registry"
    crawler.use_prices(CloudProvider.ARUBA, {}, 2.0, {"Container Registry": url, "Untold": None})
    requests = [request async for request in crawler.start_requests()]
    [page_request] = [request for request in requests if crawler.PRODUCT_PAGE_META in request.meta]

    found = prices(await read(crawler, price_page(page_request.url, "aruba-product-registry.html", page_request.meta)))
    small = [price for price in found if price.attributes["row"].startswith("Small")]

    assert page_request.url == url
    assert [(price.price, price.unit, price.currency, price.service) for price in small] == [
        (Decimal("0.01233"), PriceUnit.HOUR, "EUR", "Container Registry"),
        (Decimal("9.00"), PriceUnit.MONTH, "EUR", "Container Registry"),
    ]
    assert crawler.price_reads[url].rows == len(found)
