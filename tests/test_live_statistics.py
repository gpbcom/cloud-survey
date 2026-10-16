from __future__ import annotations

from datetime import date, timedelta

import pytest

from crawler.stats.synergy import SynergyResearchCrawler
from models.cloud.enums import MarketPlayer, MarketRegion, MarketSegment
from models.stats.market_report import MarketReport

# Smoke test against the real Synergy Research Group website (plain HTTP): `pytest --live`.
# It detects wording changes of the press releases the offline fixtures cannot see.
pytestmark = pytest.mark.live

TOP_PLAYERS = (MarketPlayer.AMAZON, MarketPlayer.MICROSOFT, MarketPlayer.GOOGLE)


async def test_crawls_the_market_shares() -> None:
    crawler = SynergyResearchCrawler()

    reports = [MarketReport.model_validate(item) async for item in crawler.stream()]

    quarterly = sorted(
        (
            report
            for report in reports
            if report.region is MarketRegion.WORLDWIDE
            and report.segment is MarketSegment.CLOUD_INFRASTRUCTURE
            and "Q" in report.period
        ),
        key=lambda report: report.sort_key(),
    )
    assert len(quarterly) >= 10
    latest = quarterly[-1]
    assert latest.published >= date.today() - timedelta(days=270)
    shares = [latest.share_of(player) for player in TOP_PLAYERS]
    assert all(share is not None for share in shares)
    assert 55 <= sum(share.share_pct for share in shares if share is not None) <= 75
    assert any(report.region is MarketRegion.EUROPE for report in reports)
