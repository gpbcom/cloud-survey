from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.tencent.crawler import TencentCloudCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]


async def read(crawler: TencentCloudCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> TencentCloudCrawler:
    crawler = TencentCloudCrawler()
    crawler.use_prices(CloudProvider.TENCENT, {}, 2.0)
    return crawler


@pytest.fixture
async def calls(crawler: TencentCloudCrawler, price_page: PricePage) -> List[Request]:
    [regions] = [request async for request in crawler._price_requests()]
    results = await read(crawler, price_page(regions.url, "tencent-regions.html", regions.meta))
    return [request for request in results if isinstance(request, Request)]


def call(calls: List[Request], crawler: TencentCloudCrawler, region: str, charge: str) -> Request:
    return next(
        request
        for request in calls
        if request.meta[crawler.REGION_META] == region and request.meta[crawler.CHARGE_META] == charge
    )


async def test_each_region_is_called_for_both_charge_types(crawler: TencentCloudCrawler, calls: List[Request]) -> None:
    regions = {request.meta[crawler.REGION_META] for request in calls}
    shanghai = call(calls, crawler, "ap-shanghai", "PREPAID")

    assert len(calls) == 2 * len(regions) == 26
    assert "ap-catalog" not in regions
    assert shanghai._session_kwargs["method"] == "POST"
    assert shanghai._session_kwargs["json"]["region"] == "ap-shanghai"
    assert shanghai._session_kwargs["json"]["data"]["Filters"] == [
        {"Name": "instance-charge-type", "Values": ["PREPAID"]}
    ]
    assert shanghai._session_kwargs["headers"]["Origin"] == "https://buy.cloud.tencent.com"


async def test_a_stepped_hourly_price_expands_into_its_usage_tiers(
    crawler: TencentCloudCrawler, calls: List[Request], price_page: PricePage
) -> None:
    request = call(calls, crawler, "ap-shanghai", "POSTPAID_BY_HOUR")
    found = prices(await read(crawler, price_page(request.url, "tencent-cvm-postpaid.json", request.meta)))
    steps = [found[f"ap-shanghai-2/S4.MEDIUM2/POSTPAID_BY_HOUR/{index}"] for index in range(3)]

    assert [(step.price, step.tier_start, step.tier_end) for step in steps] == [
        (Decimal("0.31"), Decimal(0), Decimal(96)),
        (Decimal("0.15"), Decimal(96), Decimal(360)),
        (Decimal("0.1"), Decimal(360), None),
    ]
    assert (steps[0].unit, steps[0].model, steps[0].currency, steps[0].region) == (
        PriceUnit.HOUR,
        PriceModel.ON_DEMAND,
        "CNY",
        "ap-shanghai",
    )
    assert (steps[0].vcpu, steps[0].memory_gib) == (2, Decimal(2))


async def test_a_flat_hourly_price_is_one_row_and_sold_out_types_state_it(
    crawler: TencentCloudCrawler, calls: List[Request], price_page: PricePage
) -> None:
    request = call(calls, crawler, "ap-shanghai", "POSTPAID_BY_HOUR")
    found = prices(await read(crawler, price_page(request.url, "tencent-cvm-postpaid.json", request.meta)))
    flat = found["ap-shanghai-8/MA9m.MEDIUM16/POSTPAID_BY_HOUR"]
    sold_out = next(price for price in found.values() if price.instance_type == "MA9m.48XLARGE1152")

    assert (flat.price, flat.tier_end, flat.family) == (Decimal("0.81"), None, "MA9m")
    assert sold_out.attributes["Status"] == "SOLD_OUT"
    assert any("Gpu" in price.attributes for price in found.values())


async def test_prepaid_prices_are_monthly_then_for_years_paid_at_once(
    crawler: TencentCloudCrawler, calls: List[Request], price_page: PricePage
) -> None:
    request = call(calls, crawler, "ap-guangzhou", "PREPAID")
    found = prices(await read(crawler, price_page(request.url, "tencent-cvm-prepaid.json", request.meta)))
    key = "ap-guangzhou-5/MA9m.MEDIUM16/PREPAID"

    assert [(found[f"{key}/{months}"].price, found[f"{key}/{months}"].term) for months in (1, 12, 72)] == [
        (Decimal("399.2"), PriceTerm.MONTH),
        (Decimal("3976.03"), PriceTerm.ONE_YEAR),
        (Decimal("14371.2"), PriceTerm.SIX_YEARS),
    ]
    assert (found[f"{key}/36"].unit, found[f"{key}/36"].unit_factor) == (PriceUnit.MONTH, Decimal(36))
    assert found[f"{key}/60"].model == PriceModel.COMMITMENT


async def test_the_api_is_recorded_once_every_call_is_answered(
    crawler: TencentCloudCrawler, calls: List[Request], price_page: PricePage
) -> None:
    total = 0
    for request in calls:
        fixture = (
            "tencent-cvm-prepaid.json"
            if request.meta[crawler.CHARGE_META] == "PREPAID"
            else "tencent-cvm-postpaid.json"
        )
        total += len(prices(await read(crawler, price_page(request.url, fixture, request.meta))))
        assert (crawler.PRICES_URL in crawler.price_reads) == (crawler.price_pending == 0)
    source = crawler.price_reads[crawler.PRICES_URL]

    assert (source.status, source.rows) == (PriceSourceStatus.FETCHED, total)


async def test_an_error_answer_fails_the_source(
    crawler: TencentCloudCrawler, calls: List[Request], price_page: PricePage
) -> None:
    crawler.price_pending = 1
    request = calls[0]

    assert prices(await read(crawler, price_page(request.url, "tencent-regions.html", request.meta))) == {}
    assert crawler.PRICES_URL not in crawler.price_reads
    assert request.url in crawler.price_failures


async def test_a_region_where_cvm_is_not_sold_has_no_price_and_does_not_fail(
    crawler: TencentCloudCrawler, calls: List[Request], price_page: PricePage
) -> None:
    request = calls[0]

    assert prices(await read(crawler, price_page(request.url, "tencent-cvm-unsupported.json", request.meta))) == {}
    assert crawler.price_failures == set()


async def test_the_documentation_of_each_catalogue_product_leads_to_its_price_pages(price_page: PricePage) -> None:
    crawler = TencentCloudCrawler()
    products = {"Cloud Block Storage": "https://www.tencentcloud.com/products/cbs", "Untold": None}
    crawler.use_prices(CloudProvider.TENCENT, {}, 2.0, products)

    [documentation] = list(crawler._doc_requests(price_page(crawler.REGIONS_URL, "tencent-doc-362.html", {})))
    pages = list(crawler._price_doc_pages(price_page(documentation.url, "tencent-doc-362.html", documentation.meta)))

    assert documentation.url == "https://cloud.tencent.com/document/product/362"
    assert "https://cloud.tencent.com/document/product/362/2413" in [page.url for page in pages]
    assert all(page.meta[crawler.PRODUCT_PAGE_META] == "Cloud Block Storage" for page in pages)


async def test_a_price_matrix_in_yuan_is_read_by_region_and_type(
    crawler: TencentCloudCrawler, price_page: PricePage
) -> None:
    url = "https://cloud.tencent.com/document/product/362/2413"
    meta: Dict[str, JsonValue] = {crawler.PRODUCT_PAGE_META: "Cloud Block Storage"}
    found = list(prices(await read(crawler, price_page(url, "tencent-doc-362-price.html", meta))).values())
    guangzhou = [
        price
        for price in found
        if str(price.attributes["row"]).startswith("华南地区")
        and "广州" in str(price.attributes["row"])
        and price.family == "包年包月价格"
    ]

    assert len(found) > 100
    assert guangzhou[0].attributes["column"] == "云硬盘类型 高性能云硬盘"
    assert (guangzhou[0].price, guangzhou[0].currency, guangzhou[0].unit) == (
        Decimal("0.35"),
        "CNY",
        PriceUnit.GIB_MONTH,
    )
