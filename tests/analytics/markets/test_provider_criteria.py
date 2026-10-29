from __future__ import annotations

import math
from datetime import date
from typing import List, Optional

import pytest

from analytics.markets.criteria.context_criteria import ContextCriteria
from analytics.markets.criteria.home_criteria import HomeCriteria
from analytics.markets.criteria.usage_criteria import UsageCriteria
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource, ProviderMetric
from models.history.catalog.company import Company
from models.markets.enums import Device, Granularity, ShareMetric, ShareSource, WeightIndicator
from models.markets.facts.weight_observation import WeightObservation
from models.markets.markets_catalog import MarketsCatalog
from models.markets.values.fx_rate import FxRate
from models.markets.values.market_share_value import MarketShareValue

YANDEX = Company(key="yandex", label="Yandex", color="#fc3f1d", provider=CloudProvider.YANDEX_CLOUD, country="RU")
GOOGLE = Company(key="google", label="Google", color="#34a853", provider=CloudProvider.GCP, country="US")
SAMSUNG = Company(key="samsung", label="Samsung", color="#1428a0", country="KR")


def share(
    area: str,
    label: str,
    company: Optional[str],
    value: float,
    period: date,
    granularity: Granularity = Granularity.MONTH,
    source: ShareSource = ShareSource.STATCOUNTER,
    segment: str = "search",
) -> MarketShareValue:
    return MarketShareValue(
        segment=segment,
        area=area,
        period=period,
        granularity=granularity,
        metric=ShareMetric.USAGE,
        device=Device.ALL,
        source=source,
        label=label,
        company=company,
        value=value,
        source_url=f"https://example.org/{area}/{period.isoformat()}",
    )


class TestUsageCriteria:
    def test_months_become_the_quarter_mean_and_labels_are_summed(self) -> None:
        world = [
            share("ww", "Google", "google", 90.0, date(2026, 1, 1)),
            share("ww", "Google", "google", 91.0, date(2026, 2, 1)),
            share("ww", "Google", "google", 92.0, date(2026, 3, 1)),
            share("ww", "YANDEX", "yandex", 1.0, date(2026, 1, 1)),
            share("ww", "Yandex RU", "yandex", 0.5, date(2026, 1, 1)),
        ]
        home = [share("RU", "YANDEX", "yandex", 70.0, date(2026, 4, 1))]

        values = UsageCriteria().measure("search", ShareSource.STATCOUNTER, {"ww": world, "RU": home}, [GOOGLE, YANDEX])

        found = {(value.provider, value.metric, value.period): value.value for value in values}
        assert found[(CloudProvider.GCP, ProviderMetric.USAGE_SEARCH, "2026Q1")] == pytest.approx(91.0)
        assert found[(CloudProvider.YANDEX_CLOUD, ProviderMetric.USAGE_SEARCH, "2026Q1")] == pytest.approx(1.5)
        assert found[(CloudProvider.YANDEX_CLOUD, ProviderMetric.USAGE_SEARCH_HOME, "2026Q2")] == pytest.approx(70.0)
        assert (CloudProvider.GCP, ProviderMetric.USAGE_SEARCH_HOME, "2026Q1") not in found, "no US shares given"
        assert {value.source for value in values} == {MetricSource.STATCOUNTER}

    def test_quarters_are_kept_years_left_out_and_companies_without_provider_skipped(self) -> None:
        tablets = [
            share("ww", "Samsung", "samsung", 20.0, date(2025, 7, 1), Granularity.QUARTER, ShareSource.IDC, "tablets"),
            share("ww", "Google", "google", 3.0, date(2025, 7, 1), Granularity.QUARTER, ShareSource.IDC, "tablets"),
            share("ww", "Google", "google", 2.0, date(2025, 1, 1), Granularity.YEAR, ShareSource.IDC, "tablets"),
        ]

        values = UsageCriteria().measure("tablets", ShareSource.IDC, {"ww": tablets}, [GOOGLE, SAMSUNG])

        assert [(value.provider, value.metric, value.period, value.value) for value in values] == [
            (CloudProvider.GCP, ProviderMetric.SHIPMENTS_TABLETS, "2025Q3", 3.0)
        ]
        assert values[0].source is MetricSource.IDC

    def test_the_areas_are_the_world_then_the_home_countries(self) -> None:
        assert UsageCriteria().areas([YANDEX, GOOGLE, SAMSUNG]) == ["ww", "RU", "US"]

    def test_a_segment_without_criterion_gives_nothing(self) -> None:
        assert UsageCriteria().measure("foundry", ShareSource.TRENDFORCE, {}, [GOOGLE]) == []


class TestContextCriteria:
    def test_the_concentration_is_copied_to_every_provider(self) -> None:
        dram = [
            share("ww", "Samsung", "samsung", 40.0, date(2026, 4, 1), Granularity.QUARTER, ShareSource.TRENDFORCE),
            share("ww", "SK hynix", "sk-hynix", 30.0, date(2026, 4, 1), Granularity.QUARTER, ShareSource.TRENDFORCE),
            share("ww", "Elpida", None, 10.0, date(2026, 4, 1), Granularity.QUARTER, ShareSource.TRENDFORCE),
            share("ww", "Samsung", "samsung", 38.0, date(2026, 1, 1), Granularity.YEAR, ShareSource.TRENDFORCE),
        ]

        values = ContextCriteria().measure("dram", dram, [CloudProvider.AWS, CloudProvider.GCP])

        assert {(value.provider, value.period) for value in values} == {
            (CloudProvider.AWS, "2026Q2"),
            (CloudProvider.GCP, "2026Q2"),
        }
        assert all(value.value == pytest.approx(0.16 + 0.09 + 0.01) for value in values)
        assert {value.metric for value in values} == {ProviderMetric.CONTEXT_DRAM_HHI}
        assert {value.source for value in values} == {MetricSource.TRENDFORCE}


class TestHomeCriteria:
    def rates(self) -> List[FxRate]:
        return [
            FxRate(currency="RUB", day=date(2026, 1, 15), usd_per_unit=1 / 80.0),
            FxRate(currency="RUB", day=date(2026, 4, 15), usd_per_unit=1 / 100.0),
            FxRate(currency="RUB", day=date(2026, 5, 15), usd_per_unit=1 / 100.0),
        ]

    def test_the_home_currency_change_is_a_log_change_and_zero_for_the_dollar(
        self, markets_catalog: MarketsCatalog
    ) -> None:
        values = HomeCriteria().currency_changes(markets_catalog, [YANDEX, GOOGLE, SAMSUNG], self.rates())

        found = {(value.provider, value.period): value.value for value in values}
        assert found == {
            (CloudProvider.YANDEX_CLOUD, "2026Q2"): pytest.approx(math.log(100.0 / 80.0)),
            (CloudProvider.GCP, "2026Q2"): 0.0,
        }
        assert {value.metric for value in values} == {ProviderMetric.HOME_FX_CHANGE}

    def test_the_internet_users_fill_the_four_quarters_of_their_year(self) -> None:
        weights = [
            WeightObservation(
                indicator=WeightIndicator.INTERNET_USERS, country="RU", year=2024, value=90.0, source_url="u"
            ),
            WeightObservation(
                indicator=WeightIndicator.POPULATION, country="RU", year=2024, value=144_000_000, source_url="u"
            ),
            WeightObservation(
                indicator=WeightIndicator.INTERNET_USERS, country="US", year=2024, value=92.0, source_url="u"
            ),
        ]

        values = HomeCriteria().internet_users([YANDEX, GOOGLE], weights)

        assert [value.period for value in values] == ["2024Q1", "2024Q2", "2024Q3", "2024Q4"]
        assert all(value.provider is CloudProvider.YANDEX_CLOUD for value in values), "the US has no population"
        assert values[0].value == pytest.approx(129.6)
        assert values[0].source is MetricSource.WORLD_BANK
