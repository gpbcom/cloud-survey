from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

import pytest

from analytics.pipeline.matrix_loader import MatrixLoader
from analytics.pipeline.trend_loader import TrendLoader
from analytics.series.chart_presets import ChartPresets
from conftest import build_software, seed_catalogue, seed_marketplace
from models.cloud.enums import CloudProvider, DateSource, MarketPlayer, SoftwareCategory
from models.cloud.products.product import CloudProduct
from models.stats.market_report import MarketReport
from models.stats.market_statistics import MarketStatistics
from models.storage.pages.item_query import ItemQuery
from models.trends.chart_axes import ChartAxes
from models.trends.enums import ChartKind, ChartMetric, ChartNote, ChartPreset, ChartScope, SeriesGrouping
from storage.storage import Storage

pytestmark = pytest.mark.db

ADDED = datetime(2025, 5, 2, tzinfo=UTC)
Q2_2025 = 2025 * 12 + 5


@pytest.fixture
async def seeded(storage: Storage, make_report: Callable[..., MarketReport]) -> Storage:
    products = [
        CloudProduct(name=name, description=name, added_at=ADDED, added_from=DateSource.WEBSITE)
        for name in ("EC2", "S3", "Lambda")
    ]
    await seed_catalogue(storage, CloudProvider.AWS, products)
    software = [
        build_software(name, ["database"], [SoftwareCategory.DEVELOPER_TOOL], publisher=name).model_copy(
            update={"added_at": ADDED, "added_from": DateSource.WEBSITE}
        )
        for name in ("Postgres", "Redis")
    ]
    await seed_marketplace(storage, CloudProvider.AWS, software)
    report = make_report("2025Q2", [(MarketPlayer.AMAZON, 30), (MarketPlayer.MICROSOFT, 20)])
    statistics = MarketStatistics(source="synergy", crawled_at=ADDED, reports=[report])
    await storage.statistics.replace("synergy", statistics)
    return storage


async def test_a_bubble_pairs_the_market_share_with_the_stored_items(seeded: Storage) -> None:
    axes = ChartPresets().axes(ChartPreset.SHARE_VS_LISTINGS)

    result = await TrendLoader("synergy").load(seeded, axes, ItemQuery())

    ((bubble),) = result.series
    point = bubble.points[0]
    assert (bubble.key, point.x, point.y, point.size) == (CloudProvider.AWS.value, 30, 2, 3)
    assert result.as_of == Q2_2025
    assert result.notes == [ChartNote.PLAYER_PROVIDERS]


async def test_a_time_chart_counts_the_items_and_reaches_today(seeded: Storage) -> None:
    axes = ChartAxes(
        scope=ChartScope.CATALOGUE, x=ChartMetric.QUARTER, y=ChartMetric.LISTED, series_by=SeriesGrouping.BLOC
    )

    result = await TrendLoader("synergy").load(seeded, axes, ItemQuery())

    (us,) = result.series
    assert us.key == "us"
    assert (us.points[0].x, us.points[0].y) == (Q2_2025, 3)
    assert us.points[-1].x > Q2_2025
    assert us.points[-1].y == 3


async def test_a_crawl_date_chart_without_crawls_is_empty(seeded: Storage) -> None:
    axes = ChartAxes(scope=ChartScope.MARKETPLACE, x=ChartMetric.CRAWL_DATE, y=ChartMetric.ADDED)

    result = await TrendLoader("synergy").load(seeded, axes, ItemQuery())

    assert result.series == []
    assert ChartNote.CRAWL_HISTORY in result.notes


async def test_the_matrix_loader_shares_the_rows(seeded: Storage) -> None:
    axes = ChartPresets().axes(ChartPreset.DELIVERY_MIX)

    matrix = await MatrixLoader().load(seeded, axes, ItemQuery())
    empty = await MatrixLoader().load(
        seeded, ChartAxes(scope=ChartScope.MARKETPLACE, chart=ChartKind.LINE), ItemQuery()
    )

    assert matrix.cells == {"us": {"saas": 100.0}}
    assert empty.rows == []
