from __future__ import annotations

import pytest
from sqlalchemy import text

from models.configuration.storage.storage_settings import StorageSettings
from storage.engine.database import Database
from storage.exception import StorageConnectionError, StorageSchemaError
from storage.storage import Storage
from storage.tables.schema import StorageSchema


async def test_an_unreachable_database_is_reported_without_its_password() -> None:
    database = Database(StorageSettings(url="postgresql+asyncpg://user:secret@127.0.0.1:9/nowhere"))

    with pytest.raises(StorageConnectionError) as error:
        await database.open()

    assert "secret" not in str(error.value)
    assert not database.is_open


async def test_a_database_used_before_being_opened_is_reported() -> None:
    database = Database(StorageSettings())

    with pytest.raises(StorageConnectionError, match="not open"):
        database.connect()


@pytest.mark.db
async def test_a_database_at_another_schema_revision_is_refused(
    storage: Storage, storage_settings: StorageSettings
) -> None:
    async with storage.database.connect() as connection:
        await connection.execute(text("UPDATE alembic_version SET version_num = '0000'"))
        await connection.commit()
    database = Database(storage_settings)
    try:
        with pytest.raises(StorageSchemaError, match=f"0000 instead of {StorageSchema.REVISION}"):
            await database.open()
        await database.open(check_schema=False)
        await database.open()
        assert database.is_open
    finally:
        await database.close()
        async with storage.database.connect() as connection:
            await connection.execute(text(f"UPDATE alembic_version SET version_num = '{StorageSchema.REVISION}'"))
            await connection.commit()


@pytest.mark.db
async def test_a_storage_can_be_opened_again_after_closing(storage_settings: StorageSettings) -> None:
    storage = Storage(storage_settings)
    for _ in range(2):
        async with storage:
            assert storage.database.is_open
        assert not storage.database.is_open
    await storage.database.close()
