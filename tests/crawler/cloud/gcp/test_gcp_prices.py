from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.gcp.crawler import GoogleCloudPlatformCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceKind, PriceSourceStatus, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]


async def read(crawler: GoogleCloudPlatformCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> GoogleCloudPlatformCrawler:
    crawler = GoogleCloudPlatformCrawler()
    crawler.use_prices(CloudProvider.GCP, {}, 2.0)
    crawler.price_rows = 0
    return crawler


@pytest.fixture
async def pages(crawler: GoogleCloudPlatformCrawler, price_page: PricePage) -> List[Union[PriceItem, Request]]:
    first = await read(crawler, price_page(crawler.PRICES_URL, "gcp-skus-page-1.json", {}))
    return first + await read(crawler, price_page(crawler.PRICES_URL + "&pageToken=x", "gcp-skus-page-2.json", {}))


async def test_the_next_page_is_requested_with_its_token(
    crawler: GoogleCloudPlatformCrawler, price_page: PricePage
) -> None:
    first = await read(crawler, price_page(crawler.PRICES_URL, "gcp-skus-page-1.json", {}))

    urls = [request.url for request in first if isinstance(request, Request)]
    assert len(urls) == 1
    assert urls[0].startswith(crawler.PRICES_URL + "&pageToken=")
    assert crawler.PRICES_URL not in crawler.price_reads


async def test_the_search_is_recorded_after_its_last_page(
    crawler: GoogleCloudPlatformCrawler, pages: List[Union[PriceItem, Request]]
) -> None:
    source = crawler.price_reads[crawler.PRICES_URL]

    assert (source.status, source.rows) == (PriceSourceStatus.FETCHED, 6)
    assert len(prices(pages)) == 6


async def test_a_tiered_sku_has_one_price_per_tier(pages: List[Union[PriceItem, Request]]) -> None:
    found = prices(pages)

    first, second = found["1017-1BAF-7159/0"], found["1017-1BAF-7159/1"]
    assert (first.price, first.tier_start, first.tier_end, first.unit) == (
        Decimal("2.50"),
        Decimal(0),
        Decimal(2000),
        PriceUnit.MONTH,
    )
    assert (second.price, second.tier_start, second.tier_end) == (Decimal("1.00"), Decimal(2000), None)
    assert (first.service, first.currency, first.source_kind) == (
        "Cloud Key Management Service (KMS)",
        "USD",
        PriceSourceKind.CALCULATOR,
    )


async def test_the_regions_of_a_sku(pages: List[Union[PriceItem, Request]]) -> None:
    found = prices(pages)

    assert found["4496-8C0D-228F/0"].region == "asia-southeast3"
    multi = found["84B1-65B8-1DAD/0"]
    assert multi.region == "multi-region"
    assert multi.attributes["service_regions"] == ["asia-east1", "europe-west1", "us-central1", "us-east1", "us-west1"]
    assert found["6F3B-9E3A-6DD6/0"].region == "global"


async def test_a_free_sku_is_free(pages: List[Union[PriceItem, Request]]) -> None:
    free = prices(pages)["A8F1-B2B0-44BC/0"]

    assert (free.model, free.price, free.unit) == (PriceModel.FREE, Decimal(0), PriceUnit.HOUR)


async def test_a_memory_sku_is_per_gib_hour(pages: List[Union[PriceItem, Request]]) -> None:
    ram = prices(pages)["4496-8C0D-228F/0"]

    assert (ram.unit, ram.unit_factor, ram.price) == (PriceUnit.GIB_HOUR, Decimal(1), Decimal("0.0007342"))
    assert ram.attributes["description"] == "Confidential RAM Time Bangkok"


@pytest.mark.parametrize(
    ("unit", "normalized", "factor"),
    [
        ("tebibyte month", PriceUnit.GIB_MONTH, Decimal(1024)),
        ("count", PriceUnit.REQUEST, Decimal(1)),
        ("day", PriceUnit.HOUR, Decimal(24)),
        ("parsec", PriceUnit.OTHER, Decimal(1)),
    ],
)
def test_the_written_units(
    crawler: GoogleCloudPlatformCrawler, unit: str, normalized: PriceUnit, factor: Decimal
) -> None:
    assert crawler._written_unit(unit) == (normalized, factor)


async def test_a_page_that_is_not_json_is_a_failure(crawler: GoogleCloudPlatformCrawler) -> None:
    broken = Response(
        url=GoogleCloudPlatformCrawler.PRICES_URL,
        content=b"<html>",
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
        meta={},
    )

    assert await read(crawler, broken) == []
    assert crawler.price_failures == {GoogleCloudPlatformCrawler.PRICES_URL}


@pytest.mark.parametrize(
    ("text", "groups"),
    [
        (
            "9.00 USD per 3,600 second, for 30 minute and above, per 1 month per project",
            {"quantity": "3,600", "unit": "second", "start": "30", "start_unit": "minute", "scope": "project"},
        ),
        (
            "0.00 USD (Free) per 1 count, for 0 to 1,000 count, per 1 day per project",
            {"start": "0", "end": "1,000", "end_unit": "count", "period": "day"},
        ),
        ("0.00 USD (Free) per 1 gibibyte month, for 0  to 50 gibibyte month, per 1 month per account", {"end": "50"}),
        ("0.00 USD (Free) per month", {"quantity": None, "unit": "month"}),
    ],
)
def test_the_written_price_grammar(text: str, groups: Dict[str, str]) -> None:
    match = GoogleCloudPlatformCrawler.WRITTEN_PRICE.match(text)

    assert match is not None
    assert {key: match[key] for key in groups} == groups


def test_a_sku_without_price_is_not_public(crawler: GoogleCloudPlatformCrawler) -> None:
    service: Dict[str, JsonValue] = {"category": "Vertex AI", "cloud_service_id": "C7E2-9256-1C43"}
    sku: Dict[str, JsonValue] = {"sku_id": "9C10-8313-F21F", "description": "A SKU", "prices": ["Non existing price"]}

    [price] = list(crawler._sku_prices(service, sku))
    assert (price.model, price.price, price.reason) == (
        PriceModel.NOT_PUBLIC,
        None,
        GoogleCloudPlatformCrawler.NO_PRICE_REASON,
    )
