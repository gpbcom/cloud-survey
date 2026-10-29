from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.yandex.crawler import YandexCloudCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]


async def read(crawler: YandexCloudCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> YandexCloudCrawler:
    crawler = YandexCloudCrawler()
    crawler.use_prices(CloudProvider.YANDEX_CLOUD, {}, 2.0)
    crawler.price_rows = 0
    return crawler


@pytest.fixture
async def pages(crawler: YandexCloudCrawler, price_page: PricePage) -> List[Union[PriceItem, Request]]:
    first = await read(crawler, price_page(crawler.PRICES_URL, "yandex-price-list-page-1.json", {}))
    return first + await read(
        crawler, price_page(crawler.PRICES_URL + "&pageToken=x", "yandex-price-list-page-2.json", {})
    )


def test_the_prices_are_read_by_a_session_naming_the_crawler(crawler: YandexCloudCrawler) -> None:
    assert crawler._session_manager.session_ids == ["yandex-prices"]
    assert crawler.PRICE_HEADERS == {"User-Agent": crawler.USER_AGENT}


async def test_the_next_page_carries_its_token(crawler: YandexCloudCrawler, price_page: PricePage) -> None:
    first = await read(crawler, price_page(crawler.PRICES_URL, "yandex-price-list-page-1.json", {}))

    [request] = [result for result in first if isinstance(result, Request)]
    assert request.url.startswith(crawler.PRICES_URL + "&pageToken=%7B%22pageToken%22")


async def test_the_list_is_recorded_after_its_last_page(
    crawler: YandexCloudCrawler, pages: List[Union[PriceItem, Request]]
) -> None:
    source = crawler.price_reads[crawler.PRICES_URL]

    assert (source.status, source.rows) == (PriceSourceStatus.FETCHED, 8)
    assert len(prices(pages)) == 8


async def test_a_rate_without_end_ends_at_the_next_one(pages: List[Union[PriceItem, Request]]) -> None:
    found = prices(pages)

    tiers = [found[f"cns.notification_events.mts_marketing_event/{index}"] for index in range(3)]
    assert [(tier.tier_start, tier.tier_end, tier.price) for tier in tiers] == [
        (Decimal(0), Decimal(400000), Decimal("5.43")),
        (Decimal(400000), Decimal(4000000), Decimal("5.32")),
        (Decimal(4000000), None, Decimal("5.27")),
    ]
    assert tiers[0].unit is PriceUnit.REQUEST


async def test_a_free_first_tier_is_free(pages: List[Union[PriceItem, Request]]) -> None:
    found = prices(pages)

    free, paid = found["api-gateway.requests.v1/0"], found["api-gateway.requests.v1/1"]
    assert (free.model, free.tier_end, free.unit, free.unit_factor) == (
        PriceModel.FREE,
        Decimal("0.1"),
        PriceUnit.REQUEST,
        Decimal(1_000_000),
    )
    assert (paid.price, paid.currency, paid.attributes["vat"]) == (Decimal("142.3"), "RUB", "included")


@pytest.mark.parametrize(
    ("unit", "normalized", "factor"),
    [
        ("core*hour", PriceUnit.VCPU_HOUR, Decimal(1)),
        ("gbyte*month", PriceUnit.GIB_MONTH, Decimal(1)),
        ("gpu*hour", PriceUnit.UNIT_HOUR, Decimal(1)),
        ("10k*request", PriceUnit.REQUEST, Decimal(10_000)),
        ("server*month", PriceUnit.MONTH, Decimal(1)),
        ("1k*token", PriceUnit.TOKEN, Decimal(1000)),
        ("unit*day", PriceUnit.UNIT_HOUR, Decimal(24)),
        ("15sec", PriceUnit.SECOND, Decimal(15)),
        ("parsec", PriceUnit.OTHER, Decimal(1)),
    ],
)
def test_the_pricing_units(crawler: YandexCloudCrawler, unit: str, normalized: PriceUnit, factor: Decimal) -> None:
    assert crawler._pricing_unit(unit) == (normalized, factor)
