from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.aws.crawler import AWSCrawler
from crawler.cloud.base import PriceItem
from crawler.exception import PriceDownloadError
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceStatus, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.stored.price_source import PriceSource

PricePage = Callable[[str, str, Dict[str, JsonValue]], Response]
FIXTURES = Path(__file__).parents[3] / "fixtures" / "prices"
VERSION = "20261028180352"


async def read(crawler: AWSCrawler, response: Response) -> List[Union[PriceItem, Request]]:
    return [result async for result in crawler._parse_prices(response)]


def prices(results: List[Union[PriceItem, Request]]) -> Dict[str, ServicePrice]:
    return {
        item["model"].sku_key: item["model"]
        for item in results
        if isinstance(item, dict) and isinstance(item["model"], ServicePrice)
    }


def crawler_knowing(sources: Dict[str, PriceSource], monkeypatch: pytest.MonkeyPatch) -> AWSCrawler:
    crawler = AWSCrawler()
    crawler.use_prices(CloudProvider.AWS, sources, 2.0)

    async def lines(url: str) -> AsyncGenerator[str]:
        if "/il-central-1/" in url:
            raise PriceDownloadError(crawler.name, url, "HTTP 503")
        for line in (FIXTURES / "aws-ec2-eu-west-3.csv").read_text().splitlines():
            yield line

    monkeypatch.setattr(crawler, "_stream_lines", lines)
    return crawler


@pytest.fixture
def crawler(monkeypatch: pytest.MonkeyPatch) -> AWSCrawler:
    return crawler_knowing({}, monkeypatch)


def region_index(price_page: PricePage) -> Response:
    url = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/region_index.json"
    return price_page(url, "aws-ec2-region-index.json", {AWSCrawler.PRICE_OFFER: "AmazonEC2"})


async def test_the_offer_index_requests_each_region_index_and_each_savings_plan_once(
    crawler: AWSCrawler, price_page: PricePage
) -> None:
    index = price_page(crawler.OFFER_INDEX_URL, "aws-offer-index.json", {crawler.PRICE_OFFER: ""})
    results = await read(crawler, index)

    host = "https://pricing.us-east-1.amazonaws.com"
    assert [
        (request.url, request.meta[crawler.PRICE_OFFER]) for request in results if isinstance(request, Request)
    ] == [
        (f"{host}/offers/v1.0/aws/AmazonEC2/current/region_index.json", "AmazonEC2"),
        (f"{host}/savingsPlan/v1.0/aws/AWSComputeSavingsPlan/current/region_index.json", "AWSComputeSavingsPlan"),
        (f"{host}/offers/v1.0/aws/AmazonS3/current/region_index.json", "AmazonS3"),
    ]


async def test_a_region_file_is_streamed_and_recorded_with_its_version(
    crawler: AWSCrawler, price_page: PricePage
) -> None:
    found = prices(await read(crawler, region_index(price_page)))

    source = crawler.price_reads[crawler.PRICE_FILE_URL.format(offer="AmazonEC2", region="eu-west-3")]
    assert (source.status, source.version, source.rows) == (PriceSourceStatus.FETCHED, VERSION, 3)
    assert len(found) == 3


async def test_a_failed_region_file_fails_alone(crawler: AWSCrawler, price_page: PricePage) -> None:
    await read(crawler, region_index(price_page))

    failed = crawler.PRICE_FILE_URL.format(offer="AmazonEC2", region="il-central-1")
    assert crawler.price_failures == {failed}
    assert failed not in crawler.price_reads


async def test_an_instance_price_has_its_hardware(crawler: AWSCrawler, price_page: PricePage) -> None:
    instance = prices(await read(crawler, region_index(price_page)))["22GYZ2SCWC5N7E5F.JRTCKXETXF.6YS6EN2CT7"]

    assert (instance.instance_type, instance.vcpu, instance.os, instance.region) == (
        "i7ie.3xlarge",
        Decimal(12),
        "Linux",
        "eu-west-3",
    )
    assert (instance.price, instance.unit, instance.model, instance.currency) == (
        Decimal("1.8147"),
        PriceUnit.HOUR,
        PriceModel.ON_DEMAND,
        "USD",
    )
    assert instance.memory_gib == Decimal(96)
    assert instance.service == "Amazon Elastic Compute Cloud"


async def test_a_reservation_accounting_line_is_skipped(crawler: AWSCrawler, price_page: PricePage) -> None:
    assert "224C7AQTVTWEJERF.JRTCKXETXF.6YS6EN2CT7" not in prices(await read(crawler, region_index(price_page)))


async def test_a_reservation_has_its_term_and_its_upfront_fee(crawler: AWSCrawler, price_page: PricePage) -> None:
    found = prices(await read(crawler, region_index(price_page)))

    hourly, upfront = found["228C5H6AR3Z2JAN9.4NA7Y494T4.6YS6EN2CT7"], found["228C5H6AR3Z2JAN9.38NPMPTW36.2TG2D8R56U"]
    assert (hourly.model, hourly.term, hourly.unit) == (PriceModel.RESERVED, PriceTerm.ONE_YEAR, PriceUnit.HOUR)
    assert (upfront.model, upfront.unit, upfront.price) == (PriceModel.RESERVED, PriceUnit.ONE_TIME, Decimal(136988))


async def test_an_unchanged_file_is_not_downloaded(monkeypatch: pytest.MonkeyPatch, price_page: PricePage) -> None:
    source = AWSCrawler.PRICE_FILE_URL.format(offer="AmazonEC2", region="eu-west-3")
    known = PriceSource(
        provider=CloudProvider.AWS, source_key=source, version=VERSION, rows=3, status=PriceSourceStatus.FETCHED
    )
    crawler = crawler_knowing({source: known}, monkeypatch)

    assert prices(await read(crawler, region_index(price_page))) == {}
    assert crawler.price_reads[source].status is PriceSourceStatus.UNCHANGED


@pytest.mark.parametrize(
    ("fixture", "rate", "unit", "factor"),
    [
        ("aws-s3-eu-west-3.csv", "4PMVMK58J94ER67S.JRTCKXETXF.D42MF2PVJS", PriceUnit.GIB_MONTH, Decimal(1)),
        ("aws-bedrock-eu-west-3.csv", "226EKWYF6VFZ9VFF.JRTCKXETXF.6YS6EN2CT7", PriceUnit.TOKEN, Decimal(1000)),
        ("aws-lambda-eu-west-3.csv", "3H5B5V4S3Z8AFPMU.JRTCKXETXF.6YS6EN2CT7", PriceUnit.GIB_SECOND, Decimal(1)),
    ],
)
async def test_the_units_of_other_services(
    monkeypatch: pytest.MonkeyPatch, fixture: str, rate: str, unit: PriceUnit, factor: Decimal
) -> None:
    crawler = AWSCrawler()
    crawler.use_prices(CloudProvider.AWS, {}, 2.0)

    async def lines(url: str) -> AsyncGenerator[str]:
        for line in (FIXTURES / fixture).read_text().splitlines():
            yield line

    monkeypatch.setattr(crawler, "_stream_lines", lines)
    found = {
        price.sku_key: price
        async for price in crawler._file_prices("https://file", "Offer", "eu-west-3", "https://source")
    }
    assert (found[rate].unit, found[rate].unit_factor) == (unit, factor)


async def test_a_volume_tier_has_its_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = AWSCrawler()
    crawler.use_prices(CloudProvider.AWS, {}, 2.0)

    async def lines(url: str) -> AsyncGenerator[str]:
        for line in (FIXTURES / "aws-s3-eu-west-3.csv").read_text().splitlines():
            yield line

    monkeypatch.setattr(crawler, "_stream_lines", lines)
    tiers = sorted(
        [
            (price.tier_start, price.tier_end)
            async for price in crawler._file_prices("https://f", "AmazonS3", "r", "https://source")
        ],
        key=lambda tier: tier[0],
    )
    assert tiers == [(Decimal(0), Decimal(51200)), (Decimal(51200), Decimal(512000)), (Decimal(512000), None)]


async def test_a_savings_plan_keeps_the_linux_shared_rates(
    monkeypatch: pytest.MonkeyPatch, price_page: PricePage
) -> None:
    crawler = AWSCrawler()
    crawler.use_prices(CloudProvider.AWS, {}, 2.0)

    async def lines(url: str) -> AsyncGenerator[str]:
        for line in (FIXTURES / "aws-savings-eu-west-3.csv").read_text().splitlines():
            yield line

    monkeypatch.setattr(crawler, "_stream_lines", lines)
    meta: Dict[str, JsonValue] = {crawler.PRICE_OFFER: "AWSComputeSavingsPlan", crawler.PRICE_SAVINGS: True}
    found = prices(await read(crawler, price_page("https://plans", "aws-savings-region-index.json", meta)))

    assert list(found) == ["9YXW8M33H4UKWPMX.5CY42GXBRZGVE7ER"]
    rate = found["9YXW8M33H4UKWPMX.5CY42GXBRZGVE7ER"]
    assert (rate.model, rate.term, rate.unit, rate.price, rate.instance_type, rate.region) == (
        PriceModel.SAVINGS_PLAN,
        PriceTerm.THREE_YEARS,
        PriceUnit.HOUR,
        Decimal("0.368"),
        "c5d.4xlarge",
        "eu-west-3",
    )
    source = crawler.SAVINGS_FILE_URL.format(offer="AWSComputeSavingsPlan", region="eu-west-3")
    assert (rate.source_url, crawler.price_reads[source].version) == (source, "20261028180249")
