from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Dict, List

import pytest
from pydantic import JsonValue

from analytics.markets.markets_collector import MarketsCollector
from conftest import build_report
from models.cloud.enums import CloudProvider, MarketPlayer
from models.drivers.enums import MetricSource, ProviderMetric
from models.history.chronology import Chronology
from models.markets.enums import Device, Granularity, MarketFeed, ShareMetric, ShareSource
from models.markets.facts.price_point import PricePoint
from models.markets.markets_catalog import MarketsCatalog
from models.markets.values.fx_rate import FxRate
from models.markets.values.market_share_value import MarketShareValue
from models.stats.market_statistics import MarketStatistics
from storage.storage import Storage

pytestmark = pytest.mark.db


def share(label: str, value: float, area: str = "US", company: str = "google") -> MarketShareValue:
    return MarketShareValue(
        segment="search",
        area=area,
        period=date(2026, 9, 1),
        metric=ShareMetric.USAGE,
        device=Device.ALL,
        source=ShareSource.STATCOUNTER,
        label=label,
        company=company,
        value=value,
        source_url="https://gs.statcounter.com/",
    )


def statcounter(area: str, label: str, value: float) -> Dict[str, JsonValue]:
    return {
        "stat": "search_engine",
        "area": area,
        "device": "all",
        "month": "2026-09-01",
        "label": label,
        "value": value,
        "source_url": "u",
    }


def weight(indicator: str, country: str, value: float) -> Dict[str, JsonValue]:
    return {"indicator": indicator, "country": country, "year": 2024, "value": value, "source_url": "u"}


class TestRepositories:
    async def test_shares_are_upserted_and_read_by_segment_area_and_device(self, storage: Storage) -> None:
        await storage.shares.upsert(
            [share("Google", 85.0), share("bing", 9.0, company="microsoft"), share("Google", 90.0, "GB")]
        )
        await storage.shares.upsert([share("Google", 86.0)])

        read = await storage.shares.list("search", "US", Device.ALL)
        microsoft = await storage.shares.list("search", "US", Device.ALL, companies=["microsoft"])

        assert [(value.label, value.value) for value in read] == [("Google", 86.0), ("bing", 9.0)]
        assert [value.label for value in microsoft] == ["bing"]
        assert await storage.shares.list("search", "US", Device.MOBILE) == []
        assert await storage.shares.areas_with_data("search") == {"US": 2, "GB": 1}

    async def test_replacing_periods_drops_the_labels_of_an_older_release(self, storage: Storage) -> None:
        await storage.shares.upsert(
            [share("Google", 85.0), share("bing", 9.0, company="microsoft"), share("Google", 90.0, "GB")]
        )

        await storage.shares.replace_periods([share("Google", 86.0), share("DuckDuckGo", 2.0, company="duckduckgo")])

        assert [(value.label, value.value) for value in await storage.shares.list("search", "US", Device.ALL)] == [
            ("DuckDuckGo", 2.0),
            ("Google", 86.0),
        ]
        assert len(await storage.shares.list("search", "GB", Device.ALL)) == 1

    async def test_the_coverage_reads_months_and_quarters_apart(self, storage: Storage) -> None:
        quarterly = {
            "granularity": Granularity.QUARTER,
            "source": ShareSource.IDC,
            "segment": "pcs",
            "period": date(2026, 7, 1),
        }
        await storage.shares.upsert(
            [
                share("Google", 85.0),
                share("Lenovo", 24.4, company="lenovo").model_copy(update=quarterly),
                share("Lenovo", 23.7, company="lenovo").model_copy(update={**quarterly, "period": date(2026, 4, 1)}),
            ]
        )

        assert await storage.shares.months() == {("search", "US", "all"): [date(2026, 9, 1)]}
        quarters = await storage.shares.quarters()
        assert {key: sorted(periods) for key, periods in quarters.items()} == {
            ("pcs", "US", "idc"): [date(2026, 4, 1), date(2026, 7, 1)]
        }

    async def test_prices_and_rates_round_trip(self, storage: Storage) -> None:
        points = [
            PricePoint(
                listing="NYSE:IBM", day=date(1986, 10, 24), close=28.98, volume=7700300, currency="USD", source_url="u"
            ),
            PricePoint(listing="NYSE:IBM", day=date(2026, 10, 16), close=250.0, currency="USD", source_url="u"),
            PricePoint(listing="TPE:2330", day=date(2026, 10, 16), close=2385.0, currency="TWD", source_url="u"),
        ]

        assert await storage.stocks.upsert(points) == 3
        assert await storage.fx.upsert([FxRate(currency="TWD", day=date(2026, 10, 16), usd_per_unit=1 / 32.4)]) == 1

        ibm = await storage.stocks.list(["NYSE:IBM"], start=date(2000, 1, 1))
        assert [(point.day, point.close) for point in ibm] == [(date(2026, 10, 16), 250.0)]
        assert (await storage.stocks.spans())["NYSE:IBM"] == (date(1986, 10, 24), date(2026, 10, 16), 2)
        assert [rate.currency for rate in await storage.fx.list(["TWD"])] == ["TWD"]


class TestMarketsCollector:
    async def test_a_crawl_is_measured_written_and_estimated(
        self, storage: Storage, markets_catalog: MarketsCatalog, markets_chronology: Chronology
    ) -> None:
        collector = MarketsCollector(markets_catalog, markets_chronology, storage)
        weights: List[Dict[str, JsonValue]] = [
            weight("IT.NET.USER.ZS", "DE", 90.0),
            weight("SP.POP.TOTL", "DE", 80.0),
            weight("IT.NET.USER.ZS", "FR", 90.0),
            weight("SP.POP.TOTL", "FR", 60.0),
        ]

        await collector.write(MarketFeed.WORLD_BANK, weights)
        written = await collector.write(
            MarketFeed.STATCOUNTER,
            [statcounter("DE", "Google", 90.0), statcounter("FR", "Google", 80.0), statcounter("DE", "YANDEX", 1.0)],
        )
        await collector.finish([MarketFeed.STATCOUNTER, MarketFeed.WORLD_BANK])

        union = {value.label: value for value in await storage.shares.list("search", "eu27", Device.ALL)}
        assert written == 3
        assert union["Google"].value == pytest.approx((80 * 90 + 60 * 80) / 140)
        assert union["Google"].estimate
        assert union["YANDEX"].company == "yandex"

    async def test_synergy_reports_and_stock_measures_are_derived(
        self, storage: Storage, markets_catalog: MarketsCatalog, markets_chronology: Chronology
    ) -> None:
        report = build_report("2026Q2", [(MarketPlayer.AMAZON, 28.0), (MarketPlayer.OTHERS, 72.0)])
        await storage.statistics.replace(
            "synergy", MarketStatistics(source="Synergy Research Group", crawled_at=datetime.now(UTC), reports=[report])
        )
        collector = MarketsCollector(markets_catalog, markets_chronology, storage)
        prices: List[Dict[str, JsonValue]] = [
            {"listing": "NASDAQ:AMZN", "day": day, "close": close, "currency": "USD", "source_url": "u"}
            for day, close in (("2026-03-27", 200.0), ("2026-06-26", 220.0))
        ]

        await collector.write(MarketFeed.GOOGLE_FINANCE, prices)
        await collector.finish([MarketFeed.GOOGLE_FINANCE])

        cloud = await storage.shares.list("cloud", "ww", Device.ALL, source=ShareSource.SYNERGY)
        measures = await storage.metrics.list([ProviderMetric.STOCK_VALUE], [CloudProvider.AWS])
        assert {(value.label, value.period) for value in cloud} == {
            ("amazon", date(2026, 4, 1)),
            ("Others", date(2026, 4, 1)),
        }
        assert [(value.period, value.value, value.source) for value in measures] == [
            ("2026Q1", 200.0, MetricSource.GOOGLE_FINANCE),
            ("2026Q2", 220.0, MetricSource.GOOGLE_FINANCE),
        ]

    async def test_the_new_sources_become_criteria_of_the_providers(
        self, storage: Storage, markets_catalog: MarketsCatalog, markets_chronology: Chronology
    ) -> None:
        collector = MarketsCollector(markets_catalog, markets_chronology, storage)
        dram = share("Samsung", 40.0, area="ww", company="samsung").model_copy(
            update={
                "segment": "dram",
                "source": ShareSource.TRENDFORCE,
                "granularity": Granularity.QUARTER,
                "period": date(2026, 4, 1),
                "metric": ShareMetric.REVENUE,
            }
        )
        await storage.shares.upsert([dram])
        await storage.fx.upsert(
            [
                FxRate(currency="RUB", day=date(2026, 5, 4), usd_per_unit=1 / 80.0),
                FxRate(currency="RUB", day=date(2026, 8, 3), usd_per_unit=1 / 100.0),
            ]
        )
        await collector.write(
            MarketFeed.WORLD_BANK, [weight("IT.NET.USER.ZS", "RU", 90.0), weight("SP.POP.TOTL", "RU", 144e6)]
        )
        await collector.write(
            MarketFeed.STATCOUNTER, [statcounter("ww", "Google", 90.0), statcounter("RU", "YANDEX", 70.0)]
        )

        await collector.finish([MarketFeed.STATCOUNTER, MarketFeed.WORLD_BANK])

        measures = {
            (value.provider, value.metric, value.period): value
            for value in await storage.metrics.list(providers=[CloudProvider.GCP, CloudProvider.YANDEX_CLOUD])
        }
        assert measures[(CloudProvider.GCP, ProviderMetric.USAGE_SEARCH, "2026Q3")].value == pytest.approx(90.0)
        assert measures[(CloudProvider.YANDEX_CLOUD, ProviderMetric.USAGE_SEARCH_HOME, "2026Q3")].value == 70.0
        assert measures[(CloudProvider.GCP, ProviderMetric.CONTEXT_DRAM_HHI, "2026Q2")].value == pytest.approx(0.16)
        assert measures[(CloudProvider.YANDEX_CLOUD, ProviderMetric.HOME_FX_CHANGE, "2026Q3")].value > 0
        assert measures[(CloudProvider.YANDEX_CLOUD, ProviderMetric.HOME_INTERNET_USERS, "2024Q1")].value == (
            pytest.approx(129.6)
        )
        assert CloudProvider.GCP in await storage.metrics.providers()
