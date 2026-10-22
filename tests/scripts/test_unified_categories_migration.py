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
TAXONOMY_TABLES = ["label_links", "label_sightings", "llm_usage", "source_labels", "taxonomy_nodes", "taxonomy_state"]


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


def tables(url: str) -> List[str]:
    database = make_url(url).database or ""
    statement = "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
    return asyncio.run(server_rows(url, statement, database))


def item_columns(url: str) -> List[str]:
    database = make_url(url).database or ""
    statement = (
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'software' "
        "AND column_name IN ('service_categories', 'source_label_ids') ORDER BY column_name"
    )
    return asyncio.run(server_rows(url, statement, database))


def test_the_unified_categories_migrate_up_and_down(scratch_url: str) -> None:
    migrator = DatabaseMigrator(StorageSettings(url=scratch_url))

    migrator.upgrade()
    assert set(TAXONOMY_TABLES) <= set(tables(scratch_url))
    assert item_columns(scratch_url) == ["service_categories", "source_label_ids"]
    nodes = asyncio.run(
        server_rows(scratch_url, "SELECT count(*) FROM taxonomy_nodes", make_url(scratch_url).database or "")
    )
    assert int(nodes[0]) >= 200, "an upgrade to the head seeds the taxonomy"

    migrator.downgrade("0004")
    assert not set(TAXONOMY_TABLES) & set(tables(scratch_url))
    assert item_columns(scratch_url) == []

    migrator.upgrade()
    migrator.check()
    assert not migrator.seed(), "the seed of the same files is applied once"
