from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from models.cloud.enums import CloudProvider, SoftwareCategory
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.enums import CrawlStatus
from models.storage.pages.item_query import ItemQuery
from storage.exception import StorageReadError
from storage.storage import Storage

pytestmark = pytest.mark.db

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def product(description: str) -> CloudProduct:
    return CloudProduct(name="Compute", description=description, url="https://ovh.example/compute")


async def crawl(storage: Storage, days: int, description: str) -> None:
    async with storage.catalogues.writer(CloudProvider.OVH, T0 + timedelta(days=days), 60.0) as writer:
        await writer.add(product(description))
        await writer.finish()


async def test_the_versions_are_read_newest_first_with_their_crawl(storage: Storage) -> None:
    await crawl(storage, 0, "VMs")
    await crawl(storage, 1, "VMs")
    await crawl(storage, 2, "Virtual machines")
    (stored,) = (await storage.catalogues.list(ItemQuery())).items

    versions = await storage.catalogues.versions(stored.id)

    assert [version.recorded_at for version in versions] == [T0 + timedelta(days=2), T0]
    assert [version.content["description"] for version in versions] == ["Virtual machines", "VMs"]
    assert {version.crawl_status for version in versions} == {CrawlStatus.SUCCEEDED.value}
    assert versions[0].crawl_id > versions[1].crawl_id
    assert "added_at" not in versions[0].content


async def test_an_import_writes_a_version_and_a_missing_item_has_none(storage: Storage) -> None:
    software = MarketplaceSoftware(
        name="Redis", description="Cache", publisher="Redis Labs", categories=[SoftwareCategory.DEVELOPER_TOOL]
    )
    await storage.marketplaces.import_items(CloudProvider.CIVO, T0, [software])
    (stored,) = (await storage.marketplaces.list(ItemQuery())).items

    (version,) = await storage.marketplaces.versions(stored.id)

    assert (version.recorded_at, version.crawl_status) == (T0, CrawlStatus.IMPORTED.value)
    assert version.content["name"] == "Redis"
    assert await storage.marketplaces.versions(stored.id + 1000) == []
    assert await storage.catalogues.versions(stored.id) == []


async def test_a_read_failure_is_a_storage_read_error(storage: Storage) -> None:
    with (
        patch.object(storage.catalogues.database, "connect", side_effect=SQLAlchemyError("down")),
        pytest.raises(StorageReadError),
    ):
        await storage.catalogues.versions(1)
