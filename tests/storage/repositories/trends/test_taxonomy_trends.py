from __future__ import annotations

from datetime import UTC, datetime
from typing import List

import pytest

from conftest import build_software
from models.cloud.enums import CloudProvider, SoftwareCategory
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.enums import DatasetKind
from models.storage.pages.item_query import ItemQuery
from models.trends.enums import ChartMetric, MatrixCell, SeriesGrouping
from storage.storage import Storage

pytestmark = pytest.mark.db

T0 = datetime(2026, 1, 1, tzinfo=UTC)
DEV = SoftwareCategory.DEVELOPER_TOOL


async def crawl_software(storage: Storage, provider: CloudProvider, items: List[MarketplaceSoftware]) -> None:
    async with storage.marketplaces.writer(provider, T0, 60.0) as writer:
        for one in items:
            await writer.add(one)
        await writer.finish()


async def crawl_products(storage: Storage, provider: CloudProvider, items: List[CloudProduct]) -> None:
    async with storage.catalogues.writer(provider, T0, 60.0) as writer:
        for one in items:
            await writer.add(one)
        await writer.finish()


def product(name: str, *labels: str) -> CloudProduct:
    return CloudProduct(name=name, description="Zz", catalogue_categories=list(labels))


async def test_the_software_is_counted_per_category_and_domain(storage: Storage) -> None:
    await crawl_software(
        storage,
        CloudProvider.CIVO,
        [
            build_software("Pg", ["database"], [DEV]),
            build_software("Crm", ["crm"], [DEV]),
            build_software("Both", ["database", "crm"], [DEV]),
        ],
    )

    categories = await storage.trends.series(
        DatasetKind.MARKETPLACE, ChartMetric.LISTED, ChartMetric.QUARTER, ItemQuery(), SeriesGrouping.CATEGORY
    )
    domains = await storage.trends.series(
        DatasetKind.MARKETPLACE, ChartMetric.LISTED, ChartMetric.QUARTER, ItemQuery(), SeriesGrouping.DOMAIN
    )

    assert {one.key: one.points[-1].y for one in categories} == {"database": 2, "crm": 2}
    assert {one.key: one.points[-1].y for one in domains} == {"databases": 2, "sales-marketing": 2}


async def test_the_products_are_counted_per_domain_in_series_and_matrices(storage: Storage) -> None:
    await crawl_products(storage, CloudProvider.AWS, [product("RDS", "Databases"), product("S3", "Storage")])
    await crawl_products(storage, CloudProvider.OVH, [product("Managed DB", "Databases")])

    series = await storage.trends.series(
        DatasetKind.CATALOGUE, ChartMetric.LISTED, ChartMetric.QUARTER, ItemQuery(), SeriesGrouping.DOMAIN
    )
    matrix = await storage.matrices.cells(
        ItemQuery(),
        SeriesGrouping.PROVIDER,
        SeriesGrouping.DOMAIN,
        MatrixCell.ROW_SHARE,
        kind=DatasetKind.CATALOGUE,
    )

    assert {one.key: one.points[-1].y for one in series} == {"databases": 2, "storage-services": 1}
    assert matrix.cells == {
        CloudProvider.AWS.value: {"databases": 50.0, "storage-services": 50.0},
        CloudProvider.OVH.value: {"databases": 100.0},
    }
