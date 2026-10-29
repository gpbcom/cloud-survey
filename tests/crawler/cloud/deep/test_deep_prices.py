from __future__ import annotations

from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.deep.crawler import DEEPCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceKind, PriceSourceStatus
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]


@pytest.fixture
def crawler() -> DEEPCrawler:
    crawler = DEEPCrawler()
    crawler.use_prices(CloudProvider.DEEP, {}, 2.0, {"Cloud Backup": None, "Private Cloud": "https://www.deep.eu/private"})
    return crawler


async def read(crawler: DEEPCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


async def test_the_catalogue_page_is_the_evidence_of_the_quoted_products(
    crawler: DEEPCrawler, price_page: PricePage
) -> None:
    [request] = [request async for request in crawler._price_requests()]
    results = await read(crawler, price_page(request.url, "../crawler/deep_cloud.html", request.meta))
    quotes = [item["model"] for item in results if isinstance(item, dict) and isinstance(item["model"], ServicePrice)]

    assert request.url == crawler.catalogue_url
    assert [(quote.sku_key, quote.service, quote.model, quote.price) for quote in quotes] == [
        ("unpriced/Cloud Backup", "Cloud Backup", PriceModel.QUOTE, None),
        ("unpriced/Private Cloud", "Private Cloud", PriceModel.QUOTE, None),
    ]
    assert (quotes[0].reason, quotes[0].source_kind) == (crawler.UNPRICED_REASON, PriceSourceKind.PAGE)
    assert crawler.price_reads[crawler.catalogue_url].status == PriceSourceStatus.FETCHED


async def test_without_known_product_nothing_is_stated(price_page: PricePage) -> None:
    crawler = DEEPCrawler()
    crawler.use_prices(CloudProvider.DEEP, {}, 2.0)
    [request] = [request async for request in crawler._price_requests()]

    assert await read(crawler, price_page(request.url, "../crawler/deep_cloud.html", request.meta)) == []
