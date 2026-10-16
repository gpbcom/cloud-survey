from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable, Dict, List, Tuple

import pytest
from pydantic import JsonValue, ValidationError

from models.cloud.enums import CloudProvider, MarketPlayer, MarketRegion, MarketSegment
from models.stats.exception import InvalidShareBandError, SharesOverflowError
from models.stats.market_report import MarketReport
from models.stats.market_share import MarketShare
from models.stats.market_statistics import MarketStatistics
from models.stats.provider_mention import ProviderMention

MakeReport = Callable[..., MarketReport]


@pytest.mark.parametrize(
    ("player", "provider"),
    [
        (MarketPlayer.AMAZON, CloudProvider.AWS),
        (MarketPlayer.MICROSOFT, CloudProvider.AZURE),
        (MarketPlayer.GOOGLE, CloudProvider.GCP),
        (MarketPlayer.DEUTSCHE_TELEKOM, CloudProvider.TCLOUD),
        (MarketPlayer.SAP, None),
        (MarketPlayer.OTHERS, None),
    ],
)
def test_player_providers(player: MarketPlayer, provider: CloudProvider) -> None:
    assert player.provider is provider


def test_enum_values() -> None:
    assert MarketRegion("europe") is MarketRegion.EUROPE
    assert MarketSegment("cloud-infrastructure-services") is MarketSegment.CLOUD_INFRASTRUCTURE


class TestMarketShare:
    def test_band(self) -> None:
        share = MarketShare(player=MarketPlayer.AMAZON, share_pct=33, share_low_pct=32, share_high_pct=34)

        assert (share.share_low_pct, share.share_high_pct, share.computed, share.part_of) == (32, 34, False, None)

    def test_inverted_band_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="inverted"):
            MarketShare(player=MarketPlayer.AMAZON, share_pct=33, share_low_pct=34, share_high_pct=32)

    @pytest.mark.parametrize("pct", [-1, 101])
    def test_share_range(self, pct: float) -> None:
        with pytest.raises(ValidationError):
            MarketShare(player=MarketPlayer.AMAZON, share_pct=pct)

    def test_errors_carry_their_values(self) -> None:
        band, overflow = InvalidShareBandError(34, 32), SharesOverflowError(120)

        assert (band.low, band.high, overflow.total) == (34, 32, 120)


class TestMarketReport:
    def test_others_is_computed_from_the_top_level_shares(self, make_report: MakeReport) -> None:
        report = make_report(
            "2024",
            [(MarketPlayer.BIG_THREE, 70), (MarketPlayer.EUROPEAN_PROVIDERS, 15)],
            region=MarketRegion.EUROPE,
        )
        report.shares.append(MarketShare(player=MarketPlayer.SAP, share_pct=2, part_of=MarketPlayer.EUROPEAN_PROVIDERS))

        others = report.others()

        assert others == MarketShare(player=MarketPlayer.OTHERS, share_pct=15, computed=True)
        assert report.share_of(MarketPlayer.OTHERS) == others
        assert report.share_of(MarketPlayer.SAP) is report.shares[2]
        assert report.share_of(MarketPlayer.GOOGLE) is None

    def test_others_of_approximate_shares_is_approximate(self, make_report: MakeReport) -> None:
        report = make_report("2023Q2", [(MarketPlayer.MICROSOFT, 22), (MarketPlayer.GOOGLE, 11)])
        report.shares.append(MarketShare(player=MarketPlayer.AMAZON, share_pct=33, share_low_pct=32, share_high_pct=34))

        others = report.others()

        assert others is not None
        assert (others.share_pct, others.approximate) == (34, True)

    @pytest.mark.parametrize(
        "top_shares", [[], [(MarketPlayer.AMAZON, 33)], [(MarketPlayer.AMAZON, 32), (MarketPlayer.MICROSOFT, 21)]]
    )
    def test_no_others_without_the_leaders(
        self, make_report: MakeReport, top_shares: List[Tuple[MarketPlayer, float]]
    ) -> None:
        assert make_report("2021Q4", top_shares).others() is None

    @pytest.mark.parametrize(
        ("period", "key"), [("2026Q2", (2026, 6)), ("2025H1", (2025, 6)), ("2025H2", (2025, 12)), ("2024", (2024, 12))]
    )
    def test_sort_key(self, make_report: MakeReport, period: str, key: Tuple[int, int]) -> None:
        assert make_report(period, []).sort_key() == key

    @pytest.mark.parametrize(
        "fields",
        [
            {"period": "2026Q5"},
            {"period": "Q2 2026"},
            {"currency": "GBP"},
            {"market_size_bn": 0},
            {"source_url": "/articles/x"},
            {"title": ""},
            {"shares": "amazon"},
            {"shares": [{"player": "amazon", "share_pct": 60}, {"player": "microsoft", "share_pct": 50}]},
        ],
    )
    def test_invalid_reports(self, make_report: MakeReport, fields: Dict[str, JsonValue]) -> None:
        with pytest.raises(ValidationError):
            make_report("2026Q2", [], **fields)

    def test_overflow_message(self, make_report: MakeReport) -> None:
        with pytest.raises(ValidationError, match="sum to 110"):
            make_report("2026Q2", [(MarketPlayer.AMAZON, 60), (MarketPlayer.MICROSOFT, 50)])

    def test_shares_part_of_an_aggregate_do_not_overflow(self, make_report: MakeReport) -> None:
        shares: JsonValue = [
            {"player": "big-three", "share_pct": 63},
            {"player": "amazon", "share_pct": 29, "part_of": "big-three"},
            {"player": "microsoft", "share_pct": 20, "part_of": "big-three"},
            {"player": "google", "share_pct": 14, "part_of": "big-three"},
            {"player": "neoclouds", "share_pct": 5},
        ]

        report = make_report("2025Q3", [], shares=shares)

        others = report.others()
        assert others is not None
        assert others.share_pct == 32

    def test_models_are_accepted_as_shares(self, make_report: MakeReport) -> None:
        report = make_report("2026Q2", [(MarketPlayer.AMAZON, 28)])

        rebuilt = MarketReport.model_validate({**report.model_dump(), "shares": report.shares})

        assert rebuilt == report

    def test_mentions(self) -> None:
        assert ProviderMention(name="Alibaba", rank=4).rank == 4
        with pytest.raises(ValidationError):
            ProviderMention(name="Alibaba", rank=0)


def test_statistics_round_trip(make_report: MakeReport) -> None:
    statistics = MarketStatistics(
        source="Synergy Research Group",
        crawled_at=datetime(2026, 10, 16, tzinfo=UTC),
        reports=[make_report("2026Q2", [(MarketPlayer.AMAZON, 28)])],
    )

    assert MarketStatistics.model_validate_json(statistics.model_dump_json()) == statistics
    assert statistics.size == 1
