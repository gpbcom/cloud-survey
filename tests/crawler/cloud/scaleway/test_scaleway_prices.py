from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.scaleway.crawler import ScalewayCrawler
from models.cloud.enums import CloudProvider, FreeTierKind, PriceModel, PriceSourceKind, PriceSourceStatus, PriceUnit
from models.cloud.prices.facts.free_tier import FreeTier
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
FIRST = ScalewayCrawler.PRICES_URL + "?page_size=1000&page=1"
SECOND = ScalewayCrawler.PRICES_URL + "?page_size=1000&page=2"


async def read(crawler: ScalewayCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> ScalewayCrawler:
    crawler = ScalewayCrawler()
    crawler.use_prices(CloudProvider.SCALEWAY, {}, 2.0)
    return crawler


@pytest.fixture
async def catalog(crawler: ScalewayCrawler, price_page: PricePage) -> List[Union[PriceItem, Request]]:
    first = await read(crawler, price_page(FIRST, "scaleway-catalog-page-1.json", {crawler.PRICE_PAGE: 1}))
    second = await read(crawler, price_page(SECOND, "scaleway-catalog-page-2.json", {crawler.PRICE_PAGE: 2}))
    return first + second


def test_the_price_mode_reads_politely_whatever_robots_txt_says(crawler: ScalewayCrawler) -> None:
    assert crawler.robots_txt_obey is False
    assert crawler.download_delay == 2.0
    assert crawler.concurrent_requests == 1


def test_the_price_mode_reads_over_plain_http_on_any_host(crawler: ScalewayCrawler) -> None:
    request = crawler._price_request(FIRST)

    assert crawler._session_manager.session_ids == ["scaleway-prices"]
    assert request.sid == "scaleway-prices"
    assert crawler.allowed_domains == set()


async def test_the_first_page_requests_the_following_ones(crawler: ScalewayCrawler, price_page: PricePage) -> None:
    results = await read(crawler, price_page(FIRST, "scaleway-catalog-page-1.json", {crawler.PRICE_PAGE: 1}))

    requests = [result for result in results if isinstance(result, Request)]
    assert [request.url for request in requests] == [SECOND]
    assert requests[0].meta[crawler.PRICE_PAGE] == 2
    assert len(prices(results)) == 7
    assert crawler.PRICES_URL not in crawler.price_reads


async def test_the_catalog_is_recorded_once_every_page_is_read(
    crawler: ScalewayCrawler, catalog: List[Union[PriceItem, Request]]
) -> None:
    source = crawler.price_reads[crawler.PRICES_URL]

    assert source.status is PriceSourceStatus.FETCHED
    assert source.rows == 12
    assert crawler.price_count == 12


async def test_an_instance_price_has_its_hardware(catalog: List[Union[PriceItem, Request]]) -> None:
    price = prices(catalog)["/instance/server/basic3_x2c_4g/fr-par-1"]

    assert (price.provider, price.service, price.family) == (CloudProvider.SCALEWAY, "Instance", "Compute")
    assert (price.region, price.instance_type) == ("fr-par-1", "BASIC3-X2C-4G")
    assert (price.vcpu, price.memory_gib) == (Decimal(2), Decimal(4))
    assert (price.price, price.currency, price.unit) == (Decimal("0.039449"), "EUR", PriceUnit.HOUR)
    assert (price.model, price.source_kind, price.source_url) == (
        PriceModel.ON_DEMAND,
        PriceSourceKind.API,
        ScalewayCrawler.PRICES_URL,
    )


async def test_dedicated_servers_count_their_threads(catalog: List[Union[PriceItem, Request]]) -> None:
    found = prices(catalog)

    assert found["/baremetal/em-a115x-ssd/hourly/run_ams1"].vcpu == Decimal(4)
    assert found["/baremetal/em-a115x-ssd/hourly/run_ams1"].attributes["status"] == "end_of_sale"
    dedibox = found["/dedibox/core-10-l/monthly/fr-par/dc/dc2"]
    assert (dedibox.vcpu, dedibox.memory_gib, dedibox.region) == (Decimal(64), Decimal(256), "dc2")
    assert (dedibox.unit, dedibox.price) == (PriceUnit.MONTH, Decimal("449.99"))


@pytest.mark.parametrize(
    ("sku", "unit", "factor", "written"),
    [
        ("/storage/obj/usage-new-gen-bucket-standard/fr-par", PriceUnit.GIB_HOUR, Decimal(1), "gigabyte"),
        ("/storage/obj/bandwidth/to-external/fr-par", PriceUnit.GIB, Decimal(1), "gigabyte"),
        ("/ai/inference_dedicated/deployment/h100-1/fr-par", PriceUnit.MINUTE, Decimal(1), "node"),
        ("/ai/generative_apis/consumption/glm_5_3_input/fr-par", PriceUnit.TOKEN, Decimal(1000), "1000 token"),
        ("/baremetal/em-a115x-ssd/monthly/run_ams1/fees", PriceUnit.ONE_TIME, Decimal(1), "setup"),
        ("/observability/cockpit/retention-custom-log/fr-par", PriceUnit.GIB_HOUR, Decimal(24), "gigabyte_day"),
    ],
)
async def test_the_units_are_normalized(
    catalog: List[Union[PriceItem, Request]], sku: str, unit: PriceUnit, factor: Decimal, written: str
) -> None:
    price = prices(catalog)[sku]

    assert (price.unit, price.unit_factor, price.unit_raw) == (unit, factor, written)


async def test_a_zero_price_is_free(catalog: List[Union[PriceItem, Request]]) -> None:
    price = prices(catalog)["/tools/registry/internal-bandwidth/fr"]

    assert (price.price, price.model) == (Decimal(0), PriceModel.FREE)


async def test_a_product_without_price_is_not_public(catalog: List[Union[PriceItem, Request]]) -> None:
    price = prices(catalog)["/observability/cockpit/rule-metric/fr-par"]

    assert (price.price, price.model, price.unit) == (None, PriceModel.NOT_PUBLIC, PriceUnit.OTHER)
    assert price.reason == ScalewayCrawler.NO_PRICE_REASON


async def test_a_free_offer_is_a_free_tier(catalog: List[Union[PriceItem, Request]]) -> None:
    offers = [item["model"] for item in catalog if isinstance(item, dict) and isinstance(item["model"], FreeTier)]

    assert [(offer.free_key, offer.kind, offer.service) for offer in offers] == [
        ("/ai/generative_apis/consumption/offer", FreeTierKind.ALWAYS_FREE, "Generative APIs")
    ]
    assert [item["fact"] for item in catalog if isinstance(item, dict) and item["model"] in offers] == ["free-tier"]


async def test_a_withdrawn_product_is_skipped(catalog: List[Union[PriceItem, Request]]) -> None:
    assert "/storage/snapshot/unified/fr-par1" not in prices(catalog)


async def test_a_failed_page_leaves_the_catalog_unread(crawler: ScalewayCrawler, price_page: PricePage) -> None:
    await read(crawler, price_page(FIRST, "scaleway-catalog-page-1.json", {crawler.PRICE_PAGE: 1}))
    failed = Response(
        url=SECOND, content=b"", status=503, reason="Unavailable", cookies={}, headers={}, request_headers={}, meta={}
    )

    assert await read(crawler, failed) == []
    assert crawler.price_failures == {SECOND}
    assert crawler.PRICES_URL not in crawler.price_reads


async def test_a_malformed_page_is_a_failure(crawler: ScalewayCrawler) -> None:
    broken = Response(
        url=FIRST, content=b"<html>", status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta={}
    )

    assert await read(crawler, broken) == []
    assert crawler.price_failures == {FIRST}


def test_an_unknown_unit_is_kept_as_other(crawler: ScalewayCrawler) -> None:
    assert crawler._price_unit("/new/thing/fr-par", {"unit": "fortnight", "size": 2}) == (
        PriceUnit.OTHER,
        "2 fortnight",
        Decimal(2),
    )
