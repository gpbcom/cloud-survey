from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

import pytest

from models.cloud.enums import MarketPlayer, MarketRegion
from models.stats.market_report import MarketReport
from models.stats.market_statistics import MarketStatistics
from models.storage.enums import CrawlStatus
from storage.storage import Storage

pytestmark = pytest.mark.db

T0 = datetime(2026, 1, 1, tzinfo=UTC)


async def test_the_statistics_of_a_source_are_replaced_as_a_whole(
    storage: Storage, make_report: Callable[..., MarketReport]
) -> None:
    first = MarketStatistics(
        source="Synergy Research Group",
        crawled_at=T0,
        reports=[
            make_report("2026Q1", [(MarketPlayer.AMAZON, 30.0)]),
            make_report("2026Q2", [(MarketPlayer.AMAZON, 29.0)]),
        ],
    )
    second = MarketStatistics(
        source="Synergy Research Group",
        crawled_at=T0,
        reports=[
            make_report("2026Q2", [(MarketPlayer.AMAZON, 28.0)]),
            make_report("2026Q3", [(MarketPlayer.AMAZON, 27.0)], region=MarketRegion.EUROPE),
        ],
    )

    assert await storage.statistics.read("synergy") is None
    created = await storage.statistics.replace("synergy", first)
    replaced = await storage.statistics.replace("synergy", second)
    loaded = await storage.statistics.read("synergy")

    assert (created.status, created.added, created.deleted) == (CrawlStatus.SUCCEEDED, 2, 0)
    assert (replaced.added, replaced.updated, replaced.deleted) == (1, 1, 1)
    assert loaded is not None
    assert loaded.source == "Synergy Research Group"
    assert loaded.reports == second.reports
