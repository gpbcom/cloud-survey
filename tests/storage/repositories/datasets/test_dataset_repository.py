from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

import pytest
from sqlalchemy import text

from models.cloud.enums import CloudProvider, SoftwareCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.enums import DatasetKind
from storage.exception import StorageReadError
from storage.storage import Storage

pytestmark = pytest.mark.db

T0 = datetime(2026, 1, 1, tzinfo=UTC)


async def test_a_dataset_is_in_progress_while_its_crawl_holds_its_lock(
    storage: Storage, make_software: Callable[..., MarketplaceSoftware]
) -> None:
    assert await storage.datasets.stamps() == []
    async with storage.marketplaces.writer(CloudProvider.CIVO, T0, 0.0) as writer:
        await writer.add(make_software("Postgres", ["database"], [SoftwareCategory.DEVELOPER_TOOL]))
        (running,) = await storage.datasets.stamps()
        await writer._release()
        (orphan,) = await storage.datasets.stamps()

    assert (running.kind, running.dataset, running.in_progress, running.size) == (
        DatasetKind.MARKETPLACE,
        "civo",
        True,
        1,
    )
    assert not orphan.in_progress, "a crawl process which died no longer holds the lock"


async def test_unreadable_datasets_are_reported(storage: Storage) -> None:
    async with storage.database.connect() as connection:
        await connection.execute(text("ALTER TABLE datasets RENAME TO datasets_moved"))
        await connection.commit()
    try:
        with pytest.raises(StorageReadError, match="datasets"):
            await storage.datasets.stamps()
    finally:
        async with storage.database.connect() as connection:
            await connection.execute(text("ALTER TABLE datasets_moved RENAME TO datasets"))
            await connection.commit()
