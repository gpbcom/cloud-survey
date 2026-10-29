from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from models.cloud.enums import CloudProvider
from models.companies.enums import (
    CompanyIndicator,
    FinancialGranularity,
    FinancialMetric,
    FinancialSource,
    IndicatorUnit,
)
from models.companies.values.financial_value import FinancialValue
from models.companies.values.indicator_value import IndicatorValue
from models.drivers.enums import MetricSource, ProviderMetric
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from models.markets.enums import Device, Granularity, MarketFeed, ShareMetric, ShareSource
from models.markets.facts.price_point import PricePoint
from models.markets.values.fx_rate import FxRate
from models.markets.values.market_share_value import MarketShareValue
from models.storage.crawl_summary import CrawlSummary
from models.storage.dataset_stamp import DatasetStamp
from models.storage.enums import CrawlStatus, DatasetKind
from models.storage.usage.llm_call import LlmCall
from storage.exception import StorageReadError, StorageWriteError
from storage.storage import Storage

pytestmark = pytest.mark.db

YEAR = FinancialGranularity.YEAR
T0 = datetime(2026, 10, 26, 8, 0, tzinfo=UTC)


def line(value: float = 100.0) -> FinancialValue:
    return FinancialValue(
        company="dec",
        metric=FinancialMetric.REVENUE,
        period_end=date(1997, 6, 28),
        granularity=YEAR,
        source=FinancialSource.REPORTED,
        value=value,
        currency="USD",
        concept="reported:annual-report",
        source_url="https://example.com/ar-1997.pdf",
    )


class TestRowStore:
    async def test_a_line_is_created_read_updated_listed_and_deleted(self, storage: Storage) -> None:
        key = ("dec", FinancialMetric.REVENUE, date(1997, 6, 28), YEAR, FinancialSource.REPORTED)

        created = await storage.financials.create(line())
        updated = await storage.financials.update(line(130.0))
        read = await storage.financials.read(*key)
        listed = await storage.financials.list(["dec"], offset=0, limit=10)
        deleted = await storage.financials.delete(*key)

        assert created == line()
        assert updated is True
        assert read is not None
        assert read.value == 130.0
        assert [item.value for item in listed] == [130.0]
        assert deleted is True
        assert await storage.financials.read(*key) is None
        assert await storage.financials.delete(*key) is False
        assert await storage.financials.update(line()) is False

    async def test_a_duplicate_is_refused(self, storage: Storage) -> None:
        await storage.financials.create(line())

        with pytest.raises(StorageWriteError):
            await storage.financials.create(line())

    async def test_a_malformed_key_or_filter_is_refused(self, storage: Storage) -> None:
        with pytest.raises(StorageReadError):
            await storage.financials.rows.read({"company": "dec"})
        with pytest.raises(StorageReadError):
            await storage.financials.rows.list({"no_such_column": ["x"]})

    async def test_the_list_is_paged_in_key_order(self, storage: Storage) -> None:
        for year in (1995, 1996, 1997):
            await storage.financials.create(line().model_copy(update={"period_end": date(year, 6, 30)}))

        page = await storage.financials.rows.list({"company": ["dec"]}, offset=1, limit=1)

        assert [item.period_end.year for item in page] == [1996]


class TestSingleTableRepositories:
    async def test_an_indicator_point(self, storage: Storage) -> None:
        point = IndicatorValue(
            company="dec",
            indicator=CompanyIndicator.REVENUE,
            period_end=date(1997, 6, 28),
            granularity=YEAR,
            value=13.0,
            unit=IndicatorUnit.CURRENCY,
            currency="USD",
            inputs="revenue",
        )
        key = ("dec", CompanyIndicator.REVENUE, date(1997, 6, 28), YEAR)

        await storage.indicators.create(point)
        assert await storage.indicators.update(point.model_copy(update={"value": 14.0})) is True
        read = await storage.indicators.read(*key)

        assert read is not None
        assert read.value == 14.0
        assert await storage.indicators.delete(*key) is True
        assert await storage.indicators.read(*key) is None

    async def test_an_exchange_rate(self, storage: Storage) -> None:
        rate = FxRate(currency="EUR", day=date(2026, 1, 2), usd_per_unit=1.1)

        await storage.fx.create(rate)
        assert await storage.fx.update(rate.model_copy(update={"usd_per_unit": 1.2})) is True
        read = await storage.fx.read("EUR", date(2026, 1, 2))

        assert read is not None
        assert read.usd_per_unit == 1.2
        assert [item.currency for item in await storage.fx.list(["EUR"], limit=1)] == ["EUR"]
        assert await storage.fx.delete("EUR", date(2026, 1, 2)) is True

    async def test_a_stock_price_keyed_by_its_source(self, storage: Storage) -> None:
        price = PricePoint(listing="NYSE:IBM", day=date(2026, 1, 2), close=150.0, currency="USD", source_url="u")

        await storage.stocks.create(price, MarketFeed.GOOGLE_FINANCE)
        assert await storage.stocks.update(price.model_copy(update={"close": 151.0}), MarketFeed.GOOGLE_FINANCE)
        read = await storage.stocks.read("NYSE:IBM", date(2026, 1, 2), MarketFeed.GOOGLE_FINANCE)

        assert read is not None
        assert read.close == 151.0
        assert await storage.stocks.delete("NYSE:IBM", date(2026, 1, 2), MarketFeed.GOOGLE_FINANCE) is True
        assert await storage.stocks.list(["NYSE:IBM"]) == []

    async def test_a_market_share(self, storage: Storage) -> None:
        share = MarketShareValue(
            segment="search",
            area="ww",
            period=date(2026, 9, 1),
            metric=ShareMetric.USAGE,
            source=ShareSource.STATCOUNTER,
            label="Google",
            value=90.0,
        )
        key = ("search", "ww", date(2026, 9, 1), Granularity.MONTH, Device.ALL, ShareMetric.USAGE)

        await storage.shares.create(share)
        assert await storage.shares.update(share.model_copy(update={"value": 89.0})) is True
        read = await storage.shares.read(*key, ShareSource.STATCOUNTER, "Google")

        assert read is not None
        assert read.value == 89.0
        assert await storage.shares.delete(*key, ShareSource.STATCOUNTER, "Google") is True

    async def test_a_provider_metric(self, storage: Storage) -> None:
        measure = ProviderMetricValue(
            provider=CloudProvider.AWS, period="2026Q1", metric=ProviderMetric.PRODUCTS, value=250.0
        )
        key = (CloudProvider.AWS, "2026Q1", ProviderMetric.PRODUCTS, MetricSource.DERIVED)

        await storage.metrics.create(measure)
        assert await storage.metrics.update(measure.model_copy(update={"value": 260.0})) is True
        read = await storage.metrics.read(*key)

        assert read is not None
        assert read.value == 260.0
        assert await storage.metrics.delete(*key) is True

    async def test_a_language_model_call_gets_its_identifier(self, storage: Storage) -> None:
        call = LlmCall(task="classify-items", provider="anthropic", model="claude-x", cost=Decimal("0.0125"))

        created = await storage.llm_usage.create(call)
        assert created.id is not None
        assert created.called_at is not None
        assert await storage.llm_usage.update(created.model_copy(update={"output_tokens": 42})) is True
        read = await storage.llm_usage.read(created.id)

        assert read is not None
        assert read.output_tokens == 42
        assert read.cost == Decimal("0.0125")
        assert [item.id for item in await storage.llm_usage.list(["classify-items"])] == [created.id]
        assert await storage.llm_usage.delete(created.id) is True
        with pytest.raises(StorageWriteError):
            await storage.llm_usage.update(call)

    async def test_a_dataset_and_a_crawl(self, storage: Storage) -> None:
        stamp = DatasetStamp(kind=DatasetKind.CATALOGUE, dataset="ovh", crawled_at=T0, size=3)

        created = await storage.datasets.create(stamp)
        assert await storage.datasets.update(stamp.model_copy(update={"size": 5})) is True
        read = await storage.datasets.read(DatasetKind.CATALOGUE, "ovh")
        crawl = await storage.crawls.create(
            CrawlSummary(
                crawl_id=1,
                kind=DatasetKind.CATALOGUE,
                dataset="ovh",
                status=CrawlStatus.SUCCEEDED,
                started_at=T0,
                found=5,
            )
        )
        assert await storage.crawls.update(crawl.model_copy(update={"added": 2})) is True

        assert read is not None
        assert read.size == 5
        assert read.revision > created.revision
        assert [item.dataset for item in await storage.datasets.list([DatasetKind.CATALOGUE])] == ["ovh"]
        stored = await storage.crawls.read(crawl.crawl_id)
        assert stored is not None
        assert stored.added == 2
        assert [item.crawl_id for item in await storage.crawls.list([DatasetKind.CATALOGUE], ["ovh"])] == [
            crawl.crawl_id
        ]
        assert await storage.crawls.delete(crawl.crawl_id) is True
        assert await storage.datasets.delete(DatasetKind.CATALOGUE, "ovh") is True
        assert await storage.datasets.read(DatasetKind.CATALOGUE, "ovh") is None
        await storage.datasets.create(stamp)
        with pytest.raises(StorageWriteError):
            await storage.datasets.create(stamp)
