from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from typing import List

import asyncpg
import pytest
from sqlalchemy.engine import make_url

from models.configuration.storage.storage_settings import StorageSettings
from scripts.migrate_database import DatabaseMigrator

pytestmark = pytest.mark.db

TEST_DATABASE_VARIABLE = "STORAGE_TEST_DATABASE_URL"
INSERT_SOFTWARE = (
    "INSERT INTO software (provider, match_hash, name_hash, name, description, fingerprint, delivery, "
    "marketplace_categories, categories) VALUES ('aws', 'm', 'n', 'Postgres', 'Database.', 'f', 'saas', '{}', '{}')"
)


async def server_rows(url: str, statement: str, database: str = "postgres") -> List[str]:
    server = make_url(url).set(drivername="postgresql", database=database)
    connection = await asyncpg.connect(server.render_as_string(hide_password=False))
    try:
        return [str(row[0]) for row in await connection.fetch(statement)]
    finally:
        await connection.close()


@pytest.fixture
def scratch_url() -> Iterator[str]:
    base = os.getenv(TEST_DATABASE_VARIABLE, "").strip()
    if not base:
        pytest.skip(f"Database test: set {TEST_DATABASE_VARIABLE}.")
    name = f"poc_crawler_migration_{uuid.uuid4().hex[:12]}"
    asyncio.run(server_rows(base, f'CREATE DATABASE "{name}" TEMPLATE template0'))
    try:
        yield make_url(base).set(database=name).render_as_string(hide_password=False)
    finally:
        asyncio.run(server_rows(base, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def rows(url: str, statement: str) -> List[str]:
    return asyncio.run(server_rows(url, statement, make_url(url).database or ""))


def type_columns(url: str) -> List[str]:
    statement = (
        "SELECT table_name || '.' || column_name FROM information_schema.columns "
        "WHERE (table_name = 'software' AND column_name = 'types') "
        "OR (table_name = 'taxonomy_nodes' AND column_name = 'software_type') ORDER BY 1"
    )
    return rows(url, statement)


def type_indexes(url: str) -> List[str]:
    return rows(url, "SELECT indexname FROM pg_indexes WHERE indexname = 'ix_software_types'")


def test_the_software_types_are_dropped_and_restored(scratch_url: str) -> None:
    migrator = DatabaseMigrator(StorageSettings(url=scratch_url))

    migrator.upgrade()
    assert type_columns(scratch_url) == []
    assert type_indexes(scratch_url) == []
    rows(scratch_url, INSERT_SOFTWARE)

    migrator.downgrade("0005")
    assert type_columns(scratch_url) == ["software.types", "taxonomy_nodes.software_type"]
    assert type_indexes(scratch_url) == ["ix_software_types"]
    assert rows(scratch_url, "SELECT array_to_string(types, ',') FROM software") == ["other"]

    migrator.upgrade()
    migrator.check()
    assert type_columns(scratch_url) == []
    assert rows(scratch_url, "SELECT name FROM software") == ["Postgres"]
