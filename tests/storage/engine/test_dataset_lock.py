from __future__ import annotations

import zlib

import pytest

from models.storage.enums import DatasetKind
from storage.engine.dataset_lock import DatasetLock
from storage.storage import Storage


@pytest.mark.parametrize("dataset", ["civo", "amazon-web-services", "microsoft-azure", "synergy"])
def test_the_lock_keys_are_signed_32_bit_integers(dataset: str) -> None:
    first, second = DatasetLock()._keys(DatasetKind.MARKETPLACE, dataset)

    assert first == 2
    assert -(1 << 31) <= second < (1 << 31)
    assert second % (1 << 32) == zlib.crc32(dataset.encode())


@pytest.mark.db
async def test_a_lock_is_held_by_one_session_at_a_time(storage: Storage) -> None:
    lock = DatasetLock()
    async with storage.database.connect() as first, storage.database.connect() as second:
        assert await lock.acquire(first, DatasetKind.CATALOGUE, "civo")
        assert not await lock.acquire(second, DatasetKind.CATALOGUE, "civo")
        assert lock.is_held(await lock.held(second), DatasetKind.CATALOGUE, "civo")
        await lock.release(first, DatasetKind.CATALOGUE, "civo")
        assert not lock.is_held(await lock.held(second), DatasetKind.CATALOGUE, "civo")
        await second.commit()
        async with second.begin():
            assert await lock.acquire_for_transaction(second, DatasetKind.CATALOGUE, "civo")
            assert not await lock.acquire_for_transaction(first, DatasetKind.CATALOGUE, "civo")
