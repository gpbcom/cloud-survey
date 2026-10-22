from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable, List

import pytest

from conftest import build_software, seed_marketplace
from models.cloud.enums import CloudProvider, DeliveryMethod, SoftwareAudience, SoftwareCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.enums import CrawlStatus, DatasetKind
from models.storage.pages.item_query import ItemQuery
from models.trends.enums import ChartMetric, MatrixCell, SeriesGrouping
from storage.storage import Storage

pytestmark = pytest.mark.db

T0, T1 = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)


def item(name: str, publisher: str, delivery: DeliveryMethod = DeliveryMethod.SAAS) -> MarketplaceSoftware:
    return build_software(name, ["database"], [SoftwareCategory.DEVELOPER_TOOL], delivery, publisher)


async def crawl(storage: Storage, provider: CloudProvider, when: datetime, items: List[MarketplaceSoftware]) -> None:
    async with storage.marketplaces.writer(provider, when, 60.0) as writer:
        for one in items:
            await writer.add(one)
        await writer.finish()


async def test_the_history_reads_the_completed_crawls_in_order(storage: Storage) -> None:
    await crawl(storage, CloudProvider.CIVO, T0, [item("Postgres", "ACME")])
    await crawl(storage, CloudProvider.CIVO, T1, [item("Postgres", "ACME"), item("Redis", "Redis Ltd")])
    await seed_marketplace(storage, CloudProvider.SCALEWAY, [item("Slack", "Slack")])

    history = await storage.crawls.history(DatasetKind.MARKETPLACE)

    assert [(one.dataset, one.status, one.added, one.size) for one in history] == [
        (CloudProvider.CIVO.value, CrawlStatus.SUCCEEDED, 0, 1),
        (CloudProvider.CIVO.value, CrawlStatus.SUCCEEDED, 1, 2),
    ]
    assert await storage.crawls.history(DatasetKind.MARKETPLACE, [CloudProvider.SCALEWAY]) == []


@pytest.fixture
async def marketplaces(storage: Storage, make_software: Callable[..., MarketplaceSoftware]) -> Storage:
    await seed_marketplace(
        storage,
        CloudProvider.CIVO,
        [item("Postgres", "ACME"), item("Grafana", "acme ", DeliveryMethod.KUBERNETES)],
    )
    await seed_marketplace(storage, CloudProvider.SCALEWAY, [item("Redis", "Other Co"), item("Slack", "ACME")])
    return storage


async def test_the_cells_count_the_listed_software(marketplaces: Storage) -> None:
    matrix = await marketplaces.matrices.cells(
        ItemQuery(), SeriesGrouping.PROVIDER, SeriesGrouping.DELIVERY, MatrixCell.LISTED
    )

    assert matrix.rows == [CloudProvider.CIVO.value, CloudProvider.SCALEWAY.value]
    assert matrix.columns == [DeliveryMethod.SAAS.value, DeliveryMethod.KUBERNETES.value]
    assert matrix.cells == {
        CloudProvider.CIVO.value: {"saas": 1, "kubernetes": 1},
        CloudProvider.SCALEWAY.value: {"saas": 2},
    }


async def test_the_row_shares_and_the_publishers(marketplaces: Storage) -> None:
    shares = await marketplaces.matrices.cells(
        ItemQuery(), SeriesGrouping.BLOC, SeriesGrouping.DELIVERY, MatrixCell.ROW_SHARE
    )
    publishers = await marketplaces.matrices.cells(
        ItemQuery(), SeriesGrouping.PROVIDER, SeriesGrouping.AUDIENCE, MatrixCell.PUBLISHERS, limit=1
    )

    assert shares.cells == {"other": {"saas": 50.0, "kubernetes": 50.0}, "eu": {"saas": 100.0}}
    assert publishers.rows == [CloudProvider.SCALEWAY.value]
    assert publishers.total_rows == 2
    assert publishers.cells == {CloudProvider.SCALEWAY.value: {SoftwareAudience.DEVELOPER_TOOL.value: 2}}


async def test_the_cells_without_limit_keep_every_row(marketplaces: Storage) -> None:
    matrix = await marketplaces.matrices.cells(
        ItemQuery(), SeriesGrouping.PROVIDER, SeriesGrouping.AUDIENCE, MatrixCell.PUBLISHERS, limit=None
    )

    assert matrix.rows == [CloudProvider.SCALEWAY.value, CloudProvider.CIVO.value]
    assert matrix.total_rows == 2


async def test_the_publisher_overlap_compares_each_pair_of_marketplaces(marketplaces: Storage) -> None:
    shared = await marketplaces.matrices.publisher_overlap(ItemQuery(), jaccard=False)
    overlap = await marketplaces.matrices.publisher_overlap(ItemQuery(), jaccard=True)

    civo, scaleway = CloudProvider.CIVO.value, CloudProvider.SCALEWAY.value
    assert shared.rows == [scaleway, civo]
    assert shared.cells == {scaleway: {scaleway: 2, civo: 1}, civo: {scaleway: 1, civo: 1}}
    assert overlap.cells[civo] == {scaleway: 50.0, civo: 100.0}


async def audiences(storage: Storage) -> Storage:
    developer, end_user = SoftwareCategory.DEVELOPER_TOOL, SoftwareCategory.END_USER_SOFTWARE
    civo = [
        build_software("Postgres", ["database"], [developer]),
        build_software("Slack", ["collaboration"], [end_user]),
        build_software("Odoo", ["erp"], [developer, end_user]),
        build_software("GitLab", ["devops"], [developer, end_user]),
    ]
    await seed_marketplace(storage, CloudProvider.CIVO, civo)
    await seed_marketplace(storage, CloudProvider.SCALEWAY, [build_software("Redis", ["database"], [developer])])
    return storage


async def test_the_audience_counts_the_software_meant_for_both_apart(storage: Storage) -> None:
    await audiences(storage)

    shares = await storage.matrices.cells(
        ItemQuery(), SeriesGrouping.PROVIDER, SeriesGrouping.AUDIENCE, MatrixCell.ROW_SHARE
    )

    assert shares.cells == {
        CloudProvider.CIVO.value: {
            SoftwareAudience.BOTH.value: 50.0,
            SoftwareAudience.DEVELOPER_TOOL.value: 25.0,
            SoftwareAudience.END_USER_SOFTWARE.value: 25.0,
        },
        CloudProvider.SCALEWAY.value: {SoftwareAudience.DEVELOPER_TOOL.value: 100.0},
    }


async def test_the_audience_series_and_facets(storage: Storage) -> None:
    await audiences(storage)

    series = await storage.trends.series(
        DatasetKind.MARKETPLACE, ChartMetric.LISTED, ChartMetric.QUARTER, ItemQuery(), SeriesGrouping.AUDIENCE
    )
    faceted = await storage.trends.series(
        DatasetKind.MARKETPLACE,
        ChartMetric.LISTED,
        ChartMetric.QUARTER,
        ItemQuery(),
        SeriesGrouping.AUDIENCE,
        SeriesGrouping.PROVIDER,
    )
    products = await storage.trends.series(
        DatasetKind.CATALOGUE, ChartMetric.LISTED, ChartMetric.QUARTER, ItemQuery(), SeriesGrouping.AUDIENCE
    )

    latest = {one.key: one.points[-1].y for one in series}
    assert latest == {
        SoftwareAudience.BOTH.value: 2,
        SoftwareAudience.DEVELOPER_TOOL.value: 2,
        SoftwareAudience.END_USER_SOFTWARE.value: 1,
    }
    assert {(one.facet, one.key) for one in faceted} >= {
        (CloudProvider.CIVO.value, SoftwareAudience.BOTH.value),
        (CloudProvider.SCALEWAY.value, SoftwareAudience.DEVELOPER_TOOL.value),
    }
    assert products == [], "the products have no audience"
