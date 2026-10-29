from __future__ import annotations

import math
from datetime import date
from typing import Dict, List, Tuple

import numpy
import pytest

from analytics.markets.correlation.coverage_checker import CoverageChecker
from analytics.markets.correlation.pair_correlation import PairCorrelation
from analytics.markets.correlation.series_granger import SeriesGranger
from analytics.markets.correlation.share_stock_correlation import ShareStockCorrelation
from analytics.markets.stocks.fx_converter import FxConverter
from analytics.markets.stocks.stock_table import StockTable
from models.markets.correlation.counterpart import Counterpart
from models.markets.enums import CorrelationCounterpart, Device, Granularity, ShareMetric, ShareSource
from models.markets.facts.price_point import PricePoint
from models.markets.values.market_share_value import MarketShareValue

LEAD = 3


def month(index: int) -> date:
    return date(2010 + index // 12, index % 12 + 1, 1)


def planted(months: int, seed: int = 7) -> Tuple[List[MarketShareValue], List[PricePoint]]:
    """Share changes whose effect shows in the stock returns `LEAD` months later."""
    generator = numpy.random.default_rng(seed)
    changes = generator.normal(0.0, 1.0, months)
    noise = generator.normal(0.0, 0.004, months)
    level, close = 50.0, 100.0
    shares: List[MarketShareValue] = []
    prices: List[PricePoint] = []
    for index in range(months):
        level += float(changes[index])
        returns = 0.02 * float(changes[index - LEAD]) if index >= LEAD else 0.0
        close *= math.exp(returns + float(noise[index]))
        shares.append(
            MarketShareValue(
                segment="search",
                area="ww",
                period=month(index),
                metric=ShareMetric.USAGE,
                device=Device.ALL,
                source=ShareSource.STATCOUNTER,
                label="Google",
                company="google",
                value=min(100.0, max(0.0, level)),
            )
        )
        prices.append(
            PricePoint(
                listing="NASDAQ:GOOGL", day=month(index).replace(day=27), close=close, currency="USD", source_url="u"
            )
        )
    return shares, prices


def analysis() -> ShareStockCorrelation:
    return ShareStockCorrelation(StockTable(FxConverter()))


class TestCoverage:
    def test_three_years_of_months_are_enough(self) -> None:
        entry = CoverageChecker().entry("s", [month(index) for index in range(36)])

        assert entry.enough
        assert entry.points == 36
        assert entry.longest_gap == 0

    @pytest.mark.parametrize(
        ("periods", "gap"),
        [
            ([month(index) for index in range(30)], 0),
            ([month(index) for index in range(60) if not 20 <= index < 24], 4),
        ],
    )
    def test_too_few_months_or_a_long_gap_are_not(self, periods: List[date], gap: int) -> None:
        entry = CoverageChecker().entry("s", periods)

        assert not entry.enough
        assert entry.longest_gap == gap

    def test_quarters_need_four_years(self) -> None:
        quarters = [date(2010 + index // 4, 3 * (index % 4) + 1, 1) for index in range(16)]

        assert CoverageChecker().entry("q", quarters, Granularity.QUARTER).enough
        assert not CoverageChecker().entry("q", quarters[:15], Granularity.QUARTER).enough


class TestSeriesGranger:
    def test_a_leading_series_is_detected_one_way(self) -> None:
        generator = numpy.random.default_rng(3)
        x = generator.normal(size=200)
        y = numpy.concatenate([[0.0], 0.8 * x[:-1]]) + generator.normal(scale=0.3, size=200)

        assert (SeriesGranger().p_value(y, x, 2) or 1.0) < 0.001
        assert (SeriesGranger().p_value(x, y, 2) or 0.0) > 0.01

    def test_too_short_series_give_nothing(self) -> None:
        assert SeriesGranger().p_value(numpy.ones(5), numpy.ones(5), 3) is None


class TestShareStockCorrelation:
    def test_a_planted_lead_is_found_at_its_lag(self) -> None:
        shares, prices = planted(120)

        result = analysis().analyse("google", "search", "ww", "all", shares, "NASDAQ:GOOGL", prices)

        assert result.refusal is None
        best = max((lag for lag in result.lags if lag.rho is not None), key=lambda lag: abs(lag.rho or 0.0))
        assert best.lag == LEAD
        assert (best.rho or 0.0) > 0.8
        assert (best.q_value or 1.0) < 0.01
        assert best.low is not None
        assert best.low > 0.5
        assert (result.share_leads_p or 1.0) < 0.001
        assert len(result.lags) == 2 * PairCorrelation.MAX_LAG[Granularity.MONTH] + 1

    def test_too_few_months_are_refused(self) -> None:
        shares, prices = planted(24)

        result = analysis().analyse("google", "search", "ww", "all", shares, "NASDAQ:GOOGL", prices)

        assert result.lags == []
        assert "24 months" in (result.refusal or "")

    def test_a_company_without_listing_is_refused(self) -> None:
        shares, _ = planted(60)

        result = analysis().analyse("mozilla", "browsers", "ww", "all", shares, None, [])

        assert "no listing" in (result.refusal or "")

    def test_quarterly_shares_are_correlated_with_quarter_end_closes(self) -> None:
        generator = numpy.random.default_rng(11)
        changes = generator.normal(0.0, 1.0, 40)
        level, close = 30.0, 100.0
        shares: List[MarketShareValue] = []
        prices: List[PricePoint] = []
        for index in range(40):
            quarter = date(2015 + index // 4, 3 * (index % 4) + 1, 1)
            level += float(changes[index])
            close *= math.exp(0.03 * float(changes[index - 1]) if index else 0.0)
            shares.append(
                MarketShareValue(
                    segment="foundry",
                    area="ww",
                    period=quarter,
                    granularity="quarter",
                    metric=ShareMetric.REVENUE,
                    source=ShareSource.TRENDFORCE,
                    label="TSMC",
                    company="tsmc",
                    value=level,
                )
            )
            for month in range(3):
                day = date(quarter.year, quarter.month + month, 25)
                prices.append(PricePoint(listing="TPE:2330", day=day, close=close, currency="USD", source_url="u"))

        result = analysis().analyse("tsmc", "foundry", "ww", "all", shares, "TPE:2330", prices)

        assert result.refusal is None
        assert result.granularity is Granularity.QUARTER
        assert len(result.lags) == 2 * PairCorrelation.MAX_LAG[Granularity.QUARTER] + 1
        best = max((lag for lag in result.lags if lag.rho is not None), key=lambda lag: abs(lag.rho or 0.0))
        assert best.lag == 1
        assert (best.rho or 0.0) > 0.9


class TestPairCorrelation:
    def test_months_become_quarter_means_or_quarter_ends(self) -> None:
        months = {date(2026, month, 1): float(month) for month in range(1, 7)}

        assert PairCorrelation().to_quarters(months, period_end=False) == {date(2026, 1, 1): 2.0, date(2026, 4, 1): 5.0}
        assert PairCorrelation().to_quarters(months, period_end=True) == {date(2026, 1, 1): 3.0, date(2026, 4, 1): 6.0}

    def test_a_monthly_share_leading_a_quarterly_context_is_found_after_alignment(self) -> None:
        generator = numpy.random.default_rng(3)
        quarters = [date(2005 + index // 4, index % 4 * 3 + 1, 1) for index in range(80)]
        changes = generator.normal(0.0, 1.0, len(quarters))
        level = 30.0
        context: Dict[date, float] = {}
        values: List[MarketShareValue] = []
        hhi = 0.3
        for index, quarter in enumerate(quarters):
            level += float(changes[index])
            for month in range(3):
                day = date(quarter.year, quarter.month + month, 1)
                values.append(
                    MarketShareValue(
                        segment="search",
                        area="ww",
                        period=day,
                        metric=ShareMetric.USAGE,
                        device=Device.ALL,
                        source=ShareSource.STATCOUNTER,
                        label="Samsung",
                        company="samsung",
                        value=level,
                    )
                )
            hhi += 0.02 * float(changes[index - 1]) if index else 0.0
            context[quarter] = hhi + 0.002 * float(generator.normal())
        counterpart = Counterpart(kind=CorrelationCounterpart.CONTEXT, label="DRAM concentration", segment="dram")

        result = analysis().compare("samsung", "search", "ww", "all", values, counterpart, context, Granularity.QUARTER)

        best = max((lag for lag in result.lags if lag.rho is not None), key=lambda lag: abs(lag.rho or 0.0))
        assert result.granularity is Granularity.QUARTER
        assert result.counterpart is CorrelationCounterpart.CONTEXT
        assert result.counterpart_label == "DRAM concentration"
        assert best.lag == 1
        assert best.rho is not None
        assert best.rho > 0.8
        assert len(result.lags) == 2 * PairCorrelation.MAX_LAG[Granularity.QUARTER] + 1
