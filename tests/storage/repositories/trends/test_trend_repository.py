from __future__ import annotations

from datetime import UTC, datetime
from typing import Dict, List, Optional

import pytest

from conftest import build_software, seed_catalogue, seed_marketplace
from models.cloud.enums import CloudProvider, DateSource, DeliveryMethod, SoftwareCategory
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.enums import DatasetKind
from models.storage.pages.item_query import ItemQuery
from models.trends.enums import ChartMetric, SeriesGrouping
from models.trends.metric_series import MetricSeries
from storage.storage import Storage

pytestmark = pytest.mark.db

Q1_2024, Q2_2024, Q1_2025, Q2_2025, Q3_2025 = 24290.0, 24293.0, 24302.0, 24305.0, 24308.0
Q4_2026 = 24323.0  # The quarter of the import crawl (`CRAWLED_AT`), dating the undated items.


def product(name: str, added: Optional[datetime], deleted: Optional[datetime] = None) -> CloudProduct:
    source = DateSource.WEBSITE if added else None
    return CloudProduct(name=name, description=name, added_at=added, added_from=source, deleted_at=deleted)


def software(
    name: str, publisher: str, labels: List[str], delivery: DeliveryMethod, added: datetime
) -> MarketplaceSoftware:
    built = build_software(name, labels, [SoftwareCategory.DEVELOPER_TOOL], delivery, publisher)
    return built.model_copy(update={"added_at": added, "added_from": DateSource.WEBSITE})


def values(series: List[MetricSeries]) -> Dict[str, Dict[float, float]]:
    return {one.key: {point.x: point.y for point in one.points} for one in series}


@pytest.fixture
async def catalogues(storage: Storage) -> Storage:
    await seed_catalogue(
        storage,
        CloudProvider.AWS,
        [
            product("EC2", datetime(2024, 2, 10, tzinfo=UTC)),
            product("S3", datetime(2024, 5, 1, tzinfo=UTC)),
            product("SimpleDB", datetime(2024, 5, 20, tzinfo=UTC), datetime(2025, 1, 15, tzinfo=UTC)),
        ],
    )
    await seed_catalogue(storage, CloudProvider.SCALEWAY, [product("Kapsule", None)])
    return storage


@pytest.fixture
async def marketplaces(storage: Storage) -> Storage:
    await seed_marketplace(
        storage,
        CloudProvider.CIVO,
        [
            software("Postgres", "ACME", ["database"], DeliveryMethod.SAAS, datetime(2025, 1, 5, tzinfo=UTC)),
            software(
                "Grafana",
                "acme ",
                ["monitoring", "database"],
                DeliveryMethod.KUBERNETES,
                datetime(2025, 4, 2, tzinfo=UTC),
            ),
        ],
    )
    await seed_marketplace(
        storage,
        CloudProvider.SCALEWAY,
        [
            software("Redis", "Other Co", ["database"], DeliveryMethod.SAAS, datetime(2025, 4, 10, tzinfo=UTC)),
            software("Slack", "ACME", ["collaboration"], DeliveryMethod.SAAS, datetime(2025, 7, 1, tzinfo=UTC)),
        ],
    )
    return storage


async def test_the_additions_are_counted_per_quarter_and_provider(catalogues: Storage) -> None:
    series = await catalogues.trends.series(
        DatasetKind.CATALOGUE, ChartMetric.ADDED, ChartMetric.QUARTER, ItemQuery(), SeriesGrouping.PROVIDER
    )

    assert values(series) == {
        CloudProvider.AWS.value: {Q1_2024: 1, Q2_2024: 2},
        CloudProvider.SCALEWAY.value: {Q4_2026: 1},
    }


async def test_the_deletions_are_counted_when_they_happened(catalogues: Storage) -> None:
    series = await catalogues.trends.series(
        DatasetKind.CATALOGUE, ChartMetric.DELETED, ChartMetric.QUARTER, ItemQuery(), SeriesGrouping.PROVIDER
    )

    assert values(series) == {CloudProvider.AWS.value: {Q1_2025: 1}}


async def test_the_listed_items_are_a_running_total_of_the_additions_minus_the_deletions(catalogues: Storage) -> None:
    series = await catalogues.trends.series(
        DatasetKind.CATALOGUE, ChartMetric.LISTED, ChartMetric.QUARTER, ItemQuery(), SeriesGrouping.BLOC
    )

    assert values(series) == {"us": {Q1_2024: 1, Q2_2024: 3, Q1_2025: 2}, "eu": {Q4_2026: 1}}


async def test_the_years_bucket_the_items_and_the_filters_apply(catalogues: Storage) -> None:
    query = ItemQuery(providers=[CloudProvider.AWS], search="S3")

    series = await catalogues.trends.series(
        DatasetKind.CATALOGUE, ChartMetric.ADDED, ChartMetric.YEAR, query, SeriesGrouping.PROVIDER
    )

    assert values(series) == {CloudProvider.AWS.value: {2024 * 12 + 11: 1}}


async def test_the_undated_share_counts_the_items_dated_by_their_first_crawl(catalogues: Storage) -> None:
    assert await catalogues.trends.undated_share(DatasetKind.CATALOGUE, ItemQuery()) == 0.25
    assert await catalogues.trends.undated_share(DatasetKind.MARKETPLACE, ItemQuery()) == 0.0


async def test_the_software_is_counted_per_domain(marketplaces: Storage) -> None:
    series = await marketplaces.trends.series(
        DatasetKind.MARKETPLACE, ChartMetric.ADDED, ChartMetric.QUARTER, ItemQuery(), SeriesGrouping.DOMAIN
    )

    assert values(series) == {
        "databases": {Q1_2025: 1, Q2_2025: 1},
        "management-observability": {Q2_2025: 1},
        "collaboration-productivity": {Q3_2025: 1},
    }


async def test_the_publishers_count_from_their_first_listing(marketplaces: Storage) -> None:
    series = await marketplaces.trends.series(
        DatasetKind.MARKETPLACE, ChartMetric.PUBLISHERS, ChartMetric.QUARTER, ItemQuery(), SeriesGrouping.PROVIDER
    )

    assert values(series) == {
        CloudProvider.CIVO.value: {Q1_2025: 1},
        CloudProvider.SCALEWAY.value: {Q2_2025: 1, Q3_2025: 2},
    }


@pytest.mark.parametrize(
    ("kind", "metric", "grouping"),
    [
        (DatasetKind.CATALOGUE, ChartMetric.PUBLISHERS, SeriesGrouping.PROVIDER),
        (DatasetKind.CATALOGUE, ChartMetric.ADDED, SeriesGrouping.DELIVERY),
        (DatasetKind.MARKETPLACE, ChartMetric.SHARE, SeriesGrouping.PROVIDER),
        (DatasetKind.STATISTICS, ChartMetric.ADDED, SeriesGrouping.PROVIDER),
    ],
)
async def test_the_unsupported_trends_are_empty(
    storage: Storage, kind: DatasetKind, metric: ChartMetric, grouping: SeriesGrouping
) -> None:
    assert await storage.trends.series(kind, metric, ChartMetric.QUARTER, ItemQuery(), grouping) == []


def faceted(series: List[MetricSeries]) -> Dict[str, Dict[str, Dict[float, float]]]:
    found: Dict[str, Dict[str, Dict[float, float]]] = {}
    for one in series:
        assert one.facet is not None
        found.setdefault(one.facet, {})[one.key] = {point.x: point.y for point in one.points}
    return found


async def test_the_listed_categories_are_counted_per_provider_facet(marketplaces: Storage) -> None:
    series = await marketplaces.trends.series(
        DatasetKind.MARKETPLACE,
        ChartMetric.LISTED,
        ChartMetric.QUARTER,
        ItemQuery(),
        SeriesGrouping.CATEGORY,
        SeriesGrouping.PROVIDER,
    )

    assert faceted(series) == {
        CloudProvider.CIVO.value: {
            "relational-database": {Q1_2025: 1},
            "monitoring": {Q2_2025: 1},
        },
        CloudProvider.SCALEWAY.value: {
            "in-memory-cache": {Q2_2025: 1},
            "collaboration": {Q3_2025: 1},
        },
    }


async def test_the_added_items_and_publishers_are_counted_per_facet(marketplaces: Storage) -> None:
    added = await marketplaces.trends.series(
        DatasetKind.MARKETPLACE,
        ChartMetric.ADDED,
        ChartMetric.YEAR,
        ItemQuery(),
        SeriesGrouping.DELIVERY,
        SeriesGrouping.PROVIDER,
    )
    publishers = await marketplaces.trends.series(
        DatasetKind.MARKETPLACE,
        ChartMetric.PUBLISHERS,
        ChartMetric.YEAR,
        ItemQuery(),
        SeriesGrouping.PROVIDER,
        SeriesGrouping.BLOC,
    )

    year_2025 = 2025 * 12 + 11.0
    assert faceted(added) == {
        CloudProvider.CIVO.value: {
            DeliveryMethod.SAAS.value: {year_2025: 1},
            DeliveryMethod.KUBERNETES.value: {year_2025: 1},
        },
        CloudProvider.SCALEWAY.value: {DeliveryMethod.SAAS.value: {year_2025: 2}},
    }
    assert {one.facet for one in publishers} == {"eu", "other"}


async def test_a_facet_like_the_series_or_unknown_for_products_is_not_counted(
    marketplaces: Storage, catalogues: Storage
) -> None:
    same = await marketplaces.trends.series(
        DatasetKind.MARKETPLACE,
        ChartMetric.LISTED,
        ChartMetric.QUARTER,
        ItemQuery(),
        SeriesGrouping.PROVIDER,
        SeriesGrouping.PROVIDER,
    )
    products = await catalogues.trends.series(
        DatasetKind.CATALOGUE,
        ChartMetric.LISTED,
        ChartMetric.QUARTER,
        ItemQuery(),
        SeriesGrouping.PROVIDER,
        SeriesGrouping.DELIVERY,
    )

    assert same == []
    assert products == []


async def test_the_products_are_counted_per_audience(storage: Storage) -> None:
    added = datetime(2024, 2, 10, tzinfo=UTC)
    developer, end_user = SoftwareCategory.DEVELOPER_TOOL, SoftwareCategory.END_USER_SOFTWARE
    await seed_catalogue(
        storage,
        CloudProvider.AWS,
        [
            product("EC2", added).model_copy(update={"categories": [developer]}),
            product("WorkMail", added).model_copy(update={"categories": [end_user]}),
            product("Connect", added).model_copy(update={"categories": [developer, end_user]}),
            product("Lambda", added).model_copy(update={"categories": [developer]}),
        ],
    )

    series = await storage.trends.series(
        DatasetKind.CATALOGUE, ChartMetric.ADDED, ChartMetric.QUARTER, ItemQuery(), SeriesGrouping.AUDIENCE
    )

    assert values(series) == {
        "developer-tool": {Q1_2024: 2.0},
        "end-user-software": {Q1_2024: 1.0},
        "both": {Q1_2024: 1.0},
    }
