from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

import pytest
from sqlalchemy import text

from models.cloud.enums import CloudProvider, DeliveryMethod, SoftwareCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.pages.item_query import ItemQuery
from storage.storage import Storage

pytestmark = pytest.mark.db

T0 = datetime(2026, 1, 1, tzinfo=UTC)


async def seed(storage: Storage, make_software: Callable[..., MarketplaceSoftware]) -> None:
    async with storage.marketplaces.writer(CloudProvider.CIVO, T0, 60.0) as writer:
        await writer.add(make_software("Postgres", ["database"], [SoftwareCategory.DEVELOPER_TOOL]))
        await writer.add(
            make_software(
                "Grafana",
                ["monitoring", "database"],
                [SoftwareCategory.DEVELOPER_TOOL, SoftwareCategory.END_USER_SOFTWARE],
                DeliveryMethod.KUBERNETES,
            )
        )
        await writer.finish()
    async with storage.marketplaces.writer(CloudProvider.SCALEWAY, T0, 60.0) as writer:
        await writer.add(make_software("Slack", ["collaboration"], [SoftwareCategory.END_USER_SOFTWARE]))
        await writer.finish()


async def test_the_facets_count_the_matching_software(
    storage: Storage, make_software: Callable[..., MarketplaceSoftware]
) -> None:
    await seed(storage, make_software)

    facets = await storage.marketplaces.facets(ItemQuery())
    civo = await storage.marketplaces.facets(ItemQuery(providers=[CloudProvider.CIVO]))

    assert facets.total == 3
    assert facets.by_provider == {CloudProvider.CIVO: 2, CloudProvider.SCALEWAY: 1}
    assert facets.by_category == {SoftwareCategory.DEVELOPER_TOOL: 2, SoftwareCategory.END_USER_SOFTWARE: 2}
    assert facets.by_domain == {"databases": 1, "management-observability": 1, "collaboration-productivity": 1}
    assert facets.by_domain_and_category["management-observability"] == {
        SoftwareCategory.DEVELOPER_TOOL: 1,
        SoftwareCategory.END_USER_SOFTWARE: 1,
    }
    assert facets.by_domain_and_category["databases"] == {SoftwareCategory.DEVELOPER_TOOL: 1}
    assert facets.by_publisher == {}
    assert facets.by_delivery == {DeliveryMethod.SAAS: 2, DeliveryMethod.KUBERNETES: 1}
    assert (civo.total, civo.by_provider) == (2, {CloudProvider.CIVO: 2})


async def test_the_stored_software_is_classified_again(
    storage: Storage, make_software: Callable[..., MarketplaceSoftware]
) -> None:
    await seed(storage, make_software)
    async with storage.database.connect() as connection:
        await connection.execute(
            text("UPDATE software SET service_categories = '{}', service_domains = '{}' WHERE name = 'Postgres'")
        )
        await connection.commit()
    stamp = {stamp.dataset: stamp for stamp in await storage.datasets.stamps()}["civo"]

    changed = await storage.marketplaces.reclassify(CloudProvider.CIVO)
    again = await storage.marketplaces.reclassify(CloudProvider.CIVO)

    assert changed is not None
    assert changed >= 1
    assert again == 0
    marketplace = await storage.marketplaces.load(CloudProvider.CIVO)
    assert marketplace is not None
    postgres = next(item for item in marketplace.software if item.name == "Postgres")
    assert postgres.service_categories != []
    assert postgres.service_domains != []
    assert {stamp.dataset: stamp for stamp in await storage.datasets.stamps()}["civo"].revision > stamp.revision


async def test_a_marketplace_not_stored_or_being_crawled_is_not_classified_again(
    storage: Storage, make_software: Callable[..., MarketplaceSoftware]
) -> None:
    await seed(storage, make_software)

    assert await storage.marketplaces.reclassify(CloudProvider.OVH) is None
    async with storage.marketplaces.writer(CloudProvider.CIVO, T0, 60.0):
        assert await storage.marketplaces.reclassify(CloudProvider.CIVO) is None
