from __future__ import annotations

from datetime import date
from typing import List

import pytest

from analytics.markets.shares.share_mapper import ShareMapper
from analytics.markets.shares.share_table import ShareTable
from analytics.markets.shares.union_estimator import UnionEstimator
from conftest import build_report
from models.cloud.enums import MarketPlayer, MarketSegment
from models.markets.catalog.market_area import MarketArea
from models.markets.enums import AreaKind, Device, Granularity, ShareMetric, ShareSource, WeightIndicator
from models.markets.facts.release_share import ReleaseShare
from models.markets.facts.share_observation import ShareObservation
from models.markets.facts.weight_observation import WeightObservation
from models.markets.markets_catalog import MarketsCatalog
from models.markets.values.market_share_value import MarketShareValue

UNION = MarketArea(key="eu27", label="EU-27", kind=AreaKind.UNION, members=["DE", "FR"])


def share(area: str, label: str, value: float, company: str = "", month: date = date(2024, 1, 1)) -> MarketShareValue:
    return MarketShareValue(
        segment="browsers",
        area=area,
        period=month,
        metric=ShareMetric.USAGE,
        device=Device.ALL,
        source=ShareSource.STATCOUNTER,
        label=label,
        company=company or None,
        value=value,
    )


def weights(year: int, users: List[float]) -> List[WeightObservation]:
    found: List[WeightObservation] = []
    for country, count in zip(("DE", "FR"), users, strict=True):
        found.append(
            WeightObservation(
                indicator=WeightIndicator.INTERNET_USERS, country=country, year=year, value=50.0, source_url="u"
            )
        )
        found.append(
            WeightObservation(
                indicator=WeightIndicator.POPULATION, country=country, year=year, value=count * 2, source_url="u"
            )
        )
    return found


class TestShareMapper:
    def test_statcounter_labels_get_their_segment_and_company(self, markets_catalog: MarketsCatalog) -> None:
        observations = [
            ShareObservation(
                stat="browser", area="FR", device="mobile", month="2024-05", label=label, value=value, source_url="u"
            )
            for label, value in (("Chrome", 60.0), ("Samsung Internet", 5.0), ("Puffin", 0.2))
        ]

        values = ShareMapper(markets_catalog).statcounter(observations)

        assert [value.segment for value in values] == ["browsers"] * 3
        assert [value.company for value in values] == ["google", "samsung", None]
        assert values[0].period == date(2024, 5, 1)
        assert values[0].device is Device.MOBILE

    def test_synergy_reports_give_quarterly_cloud_shares_without_aggregates(
        self, markets_catalog: MarketsCatalog
    ) -> None:
        report = build_report(
            "2026Q2",
            [(MarketPlayer.BIG_THREE, 63.0), (MarketPlayer.OTHERS, 37.0)],
        )
        members = [
            {"player": player.value, "share_pct": pct, "part_of": MarketPlayer.BIG_THREE.value}
            for player, pct in (
                (MarketPlayer.AMAZON, 28.0),
                (MarketPlayer.MICROSOFT, 20.0),
                (MarketPlayer.GOOGLE, 15.0),
            )
        ]
        report = report.model_validate(
            {**report.model_dump(mode="json"), "shares": [*report.model_dump(mode="json")["shares"], *members]}
        )
        half = build_report("2025H1", [(MarketPlayer.AMAZON, 30.0)])

        values = ShareMapper(markets_catalog).synergy([report, half])

        assert sorted(value.label for value in values) == ["Others", "amazon", "google", "microsoft"]
        assert {value.period for value in values} == {date(2026, 4, 1)}
        assert {value.granularity for value in values} == {Granularity.QUARTER}
        assert {value.company for value in values if value.label == "amazon"} == {"amazon"}
        assert {value.area for value in values} == {"ww"}

    def test_synergy_other_players_get_their_chronology_company(self, markets_catalog: MarketsCatalog) -> None:
        players = (
            MarketPlayer.AMAZON,
            MarketPlayer.ALIBABA,
            MarketPlayer.IBM,
            MarketPlayer.ORACLE,
            MarketPlayer.HUAWEI,
            MarketPlayer.TENCENT,
        )
        report = build_report("2019Q4", [(player, 5.0) for player in players])
        public = build_report("2019Q3", [(MarketPlayer.AMAZON, 40.0)], segment=MarketSegment.PUBLIC_IAAS_PAAS)

        values = ShareMapper(markets_catalog).synergy([report, public])

        assert {value.label: value.company for value in values} == {
            "amazon": "amazon",
            "alibaba": "alibaba",
            "ibm": "ibm",
            "oracle": "oracle",
            "huawei": "huawei",
            "tencent": "tencent",
        }
        assert {value.period for value in values} == {date(2019, 10, 1)}, "the public IaaS and PaaS shares are left out"

    def test_a_period_takes_the_shares_of_a_single_release(self, markets_catalog: MarketsCatalog) -> None:
        def release(label: str, value: float, published: date, url: str) -> ReleaseShare:
            return ReleaseShare(
                source="idc",
                segment="pcs",
                area="ww",
                period=date(2025, 4, 1),
                granularity="quarter",
                label=label,
                value=value,
                title="PC Market",
                published=published,
                source_url=url,
            )

        quarter = [
            release("Lenovo", 23.7, date(2025, 7, 9), "q"),
            release("ASUS", 7.0, date(2025, 7, 9), "q"),
            release("Others", 69.3, date(2025, 7, 9), "q"),
        ]
        year_ago = [
            release("Lenovo", 24.0, date(2026, 7, 8), "y"),
            release("Acer", 6.0, date(2026, 7, 8), "y"),
            release("Others", 70.0, date(2026, 7, 8), "y"),
        ]
        partial = [release("Lenovo", 30.0, date(2026, 10, 1), "p")]

        values = ShareMapper(markets_catalog).releases([*quarter, *year_ago, *partial])

        assert {(value.label, value.value) for value in values} == {("Lenovo", 24.0), ("Acer", 6.0), ("Others", 70.0)}
        assert {value.company for value in values} == {"lenovo", "acer", None}
        assert {value.metric for value in values} == {ShareMetric.UNITS}
        assert {value.granularity for value in values} == {Granularity.QUARTER}

    def test_the_manual_shares_of_the_dossier_are_mapped(self, markets_catalog: MarketsCatalog) -> None:
        values = ShareMapper(markets_catalog).manual()

        ibm = {value.period: value for value in values if value.segment == "mainframes" and value.area == "US"}
        assert ibm[date(1961, 1, 1)].value == 52
        assert ibm[date(1961, 1, 1)].granularity is Granularity.YEAR
        assert {value.source for value in values} == {ShareSource.MANUAL}
        assert any(value.granularity is Granularity.QUARTER for value in values)


class TestUnionEstimator:
    def test_members_are_weighted_by_their_internet_users(self) -> None:
        members = [
            share("DE", "Chrome", 60.0, "google"),
            share("FR", "Chrome", 40.0, "google"),
            share("DE", "bing", 10.0, "microsoft"),
        ]

        estimates = {
            value.label: value for value in UnionEstimator().estimate(UNION, members, weights(2024, [80.0, 60.0]))
        }

        assert estimates["Chrome"].value == pytest.approx((80 * 60 + 60 * 40) / 140)
        assert estimates["bing"].value == pytest.approx(80 * 10 / 140), "a label absent from a member counts as zero"
        assert estimates["Chrome"].area == "eu27"
        assert estimates["Chrome"].estimate

    def test_a_missing_year_takes_the_latest_known(self) -> None:
        members = [
            share("DE", "Chrome", 60.0, "google", date(2026, 9, 1)),
            share("FR", "Chrome", 40.0, "google", date(2026, 9, 1)),
        ]

        estimates = UnionEstimator().estimate(UNION, members, weights(2023, [80.0, 60.0]))

        assert estimates[0].value == pytest.approx((80 * 60 + 60 * 40) / 140)

    def test_a_member_without_figures_that_month_does_not_weigh(self) -> None:
        members = [share("DE", "Chrome", 60.0, "google"), share("IT", "Chrome", 90.0, "google")]

        estimates = UnionEstimator().estimate(UNION, members, weights(2024, [80.0, 60.0]))

        assert [value.value for value in estimates] == [pytest.approx(60.0)]


class TestShareTable:
    def test_the_top_companies_by_peak_then_the_others(self) -> None:
        values = [
            share("ww", "Symbian", 40.0, "nokia", date(2009, 1, 1)),
            share("ww", "Symbian", 1.0, "nokia", date(2014, 1, 1)),
            share("ww", "Android", 30.0, "google", date(2009, 1, 1)),
            share("ww", "Chrome OS", 5.0, "google", date(2009, 1, 1)),
            share("ww", "Android", 39.0, "google", date(2014, 1, 1)),
            share("ww", "iOS", 20.0, "apple", date(2014, 1, 1)),
            share("ww", "Linux", 2.0, "", date(2014, 1, 1)),
        ]

        lines = ShareTable().series(values, {"google": "Google", "nokia": "Nokia"}, top=2)

        assert [line.label for line in lines] == ["Nokia", "Google", "Others"]
        assert dict(lines[1].points) == {date(2009, 1, 1): 35.0, date(2014, 1, 1): 39.0}
        assert lines[1].labels == ["Android", "Chrome OS"]
        assert dict(lines[2].points) == {date(2014, 1, 1): 22.0}
        assert lines[2].company is None

    def test_the_window_limits_the_periods(self) -> None:
        values = [
            share("ww", "Chrome", 50.0, "google", date(2010, 1, 1)),
            share("ww", "Chrome", 60.0, "google", date(2020, 1, 1)),
        ]

        lines = ShareTable().series(values, {}, start=date(2015, 1, 1))

        assert lines[0].points == [(date(2020, 1, 1), 60.0)]
        assert lines[0].label == "google"
