from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import PriceItem
from crawler.cloud.volcengine.crawler import VolcanoEngineCrawler
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
TEMPLATE = "CLT7310571628986405164"


async def read(crawler: VolcanoEngineCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


@pytest.fixture
def crawler() -> VolcanoEngineCrawler:
    crawler = VolcanoEngineCrawler()
    crawler.use_prices(CloudProvider.VOLCENGINE, {}, 2.0)
    return crawler


@pytest.fixture
async def table(crawler: VolcanoEngineCrawler, price_page: PricePage) -> List[Union[PriceItem, Request]]:
    navigation, _docs = [request async for request in crawler._price_requests()]
    requests = await read(crawler, price_page(navigation.url, "volcengine-navigation.json", navigation.meta))
    ecs = next(
        request
        for request in requests
        if isinstance(request, Request) and request.meta[crawler.TEMPLATE_META] == TEMPLATE
    )
    following = await read(crawler, price_page(ecs.url, "volcengine-template.json", ecs.meta))
    [prices_request] = [request for request in following if isinstance(request, Request)]
    crawler.price_pending = 1
    return await read(crawler, price_page(prices_request.url, "volcengine-table.json", prices_request.meta))


async def test_the_navigation_requests_each_detail_template(
    crawler: VolcanoEngineCrawler, price_page: PricePage
) -> None:
    navigation, _docs = [request async for request in crawler._price_requests()]
    requests = [
        request
        for request in await read(crawler, price_page(navigation.url, "volcengine-navigation.json", navigation.meta))
        if isinstance(request, Request)
    ]

    assert len(requests) == 77
    assert requests[0].url.endswith("Action=ListTemplate&Version=2020-01-01")
    assert requests[0]._session_kwargs["method"] == "POST"
    assert requests[0]._session_kwargs["json"] == {"TemplateCode": requests[0].meta[crawler.TEMPLATE_META]}


async def test_the_navigation_is_recorded_once_every_call_is_answered(
    crawler: VolcanoEngineCrawler, table: List[Union[PriceItem, Request]]
) -> None:
    source = crawler.price_reads[crawler.NAVIGATION_URL]

    assert (source.status, source.rows) == (PriceSourceStatus.FETCHED, len(prices(table)))


async def test_an_instance_is_priced_by_the_hour_and_by_subscription(table: List[Union[PriceItem, Request]]) -> None:
    found = prices(table)

    hourly = found["ecs.c3il_12xlarge_cn-shanghai/ecs.c3il.12xlarge/hourly/1"]
    assert (hourly.price, hourly.unit, hourly.region, hourly.currency, hourly.instance_type) == (
        Decimal("9.6246"),
        PriceUnit.HOUR,
        "cn-shanghai",
        "CNY",
        "ecs.c3il.12xlarge",
    )
    yearly = found["ecs.c3al_12xlarge_ap-southeast-1/ecs.c3al.12xlarge.month/monthly/12"]
    assert (yearly.unit, yearly.unit_factor, yearly.model, yearly.term, yearly.price) == (
        PriceUnit.MONTH,
        Decimal(12),
        PriceModel.COMMITMENT,
        PriceTerm.ONE_YEAR,
        Decimal("38327.63"),
    )


async def test_a_progressive_price_expands_into_tiers(table: List[Union[PriceItem, Request]]) -> None:
    found = prices(table)

    tiers = [found[f"image_RedHat_cn-hongkong/RedHat/hourly/1/{index}"] for index in range(3)]
    assert [(tier.tier_start, tier.tier_end, tier.price) for tier in tiers] == [
        (Decimal(0), Decimal(8), Decimal("0.1041")),
        (Decimal(8), Decimal(127), Decimal("0.0781")),
        (Decimal(127), None, Decimal("0.0694")),
    ]
    assert tiers[0].unit is PriceUnit.VCPU_HOUR


async def test_a_disk_is_priced_per_gib_hour(table: List[Union[PriceItem, Request]]) -> None:
    disk = prices(table)["system-EBS_ESSD_PL0_ap-southeast-1/system-EBS_ESSD_PL0/hourly/1"]

    assert (disk.unit, disk.price) == (PriceUnit.GIB_HOUR, Decimal("0.0008415"))


@pytest.mark.parametrize(
    ("item", "period", "unit", "factor"),
    [
        ({"Unit": "百万Tokens", "BillingByUsage": True}, "hourly", PriceUnit.TOKEN, Decimal(1_000_000)),
        ({"Unit": "万次", "BillingByUsage": True}, "hourly", PriceUnit.REQUEST, Decimal(10_000)),
        ({"Unit": "GB", "BillingByUsage": True}, "hourly", PriceUnit.GIB, Decimal(1)),
        ({"Unit": "MB/s", "BillingByUsage": False}, "hourly", PriceUnit.OTHER, Decimal(1)),
    ],
)
def test_the_charge_units(
    crawler: VolcanoEngineCrawler, item: Dict[str, JsonValue], period: str, unit: PriceUnit, factor: Decimal
) -> None:
    assert crawler._charge_unit(item, period, 1)[:2] == (unit, factor)


async def test_the_documentation_home_requests_the_libraries_of_the_catalogue_products(price_page: PricePage) -> None:
    crawler = VolcanoEngineCrawler()
    products = {
        "火山 方舟": "https://www.volcengine.com/product/ark",
        "容器服务": "https://www.volcengine.com/product/vke",
    }
    crawler.use_prices(CloudProvider.VOLCENGINE, {}, 2.0, products)
    requests = [request async for request in crawler._price_requests()]
    home = requests[-1]

    following = await read(crawler, price_page(home.url, "volcengine-docs-home.html", home.meta))

    assert home.url == crawler.DOCS_HOME_URL
    assert [(request.url, request.meta[crawler.DOCS_PRODUCT_META]) for request in following] == [
        ("https://docs.volcengine.com/docs/ark?lang=zh", "火山 方舟"),
        ("https://docs.volcengine.com/docs/vke?lang=zh", "容器服务"),
    ]


async def test_a_library_requests_its_billing_documents_only(
    crawler: VolcanoEngineCrawler, price_page: PricePage
) -> None:
    meta: Dict[str, JsonValue] = {
        crawler.DOCS_STAGE_META: "library",
        crawler.DOCS_PRODUCT_META: "容器服务",
        crawler.DOCS_LIBRARY_META: "vke",
    }

    following = await read(crawler, price_page(crawler.DOCS_LIBRARY_URL, "volcengine-docs-library.html", meta))

    assert [request.meta[crawler.DOCS_PAGE_META] for request in following if isinstance(request, Request)] == [
        "https://docs.volcengine.com/docs/vke/billing",
        "https://docs.volcengine.com/docs/vke/vci-billing-overview",
        "https://docs.volcengine.com/docs/vke/pay-as-you-go-13",
    ]


async def test_a_billing_document_is_read_for_its_markdown_price_tables(
    crawler: VolcanoEngineCrawler, price_page: PricePage
) -> None:
    page = "https://docs.volcengine.com/docs/vke/pay-as-you-go-13"
    meta: Dict[str, JsonValue] = {
        crawler.DOCS_STAGE_META: "document",
        crawler.DOCS_PRODUCT_META: "容器服务",
        crawler.DOCS_PAGE_META: page,
    }

    found = prices(
        await read(crawler, price_page("https://docs.volcengine.com/api/doc", "volcengine-docs-document.json", meta))
    )

    hourly = next(
        price
        for price in found.values()
        if price.attributes["row"] == "通用算力型 u1" and price.unit is PriceUnit.GIB_HOUR
    )
    assert hourly.price == Decimal("0.021149202")
    assert hourly.currency == "CNY"
    assert hourly.service == "容器服务"
    assert hourly.source_url == page
    assert len(found) == 17
    assert sum(price.unit is PriceUnit.GIB_SECOND for price in found.values()) == 4
    assert page in crawler.price_reads


async def test_a_folder_of_the_documentation_tree_has_no_price_and_is_no_failure(
    crawler: VolcanoEngineCrawler, price_page: PricePage
) -> None:
    meta: Dict[str, JsonValue] = {crawler.DOCS_STAGE_META: "document", crawler.DOCS_PRODUCT_META: "x"}

    found = await read(crawler, price_page("https://docs.volcengine.com/api/doc", "volcengine-docs-folder.json", meta))

    assert found == []
    assert crawler.price_failures == set()
