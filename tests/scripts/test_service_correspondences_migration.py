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
TABLES = ["concept_members", "correspondence_checks", "service_concepts"]
INDEXES = ["ix_concept_members_product_id", "ix_service_concepts_node_name"]


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


def tables(url: str) -> List[str]:
    names = ", ".join(f"'{table}'" for table in TABLES)
    return rows(url, f"SELECT table_name FROM information_schema.tables WHERE table_name IN ({names}) ORDER BY 1")


def indexes(url: str) -> List[str]:
    names = ", ".join(f"'{index}'" for index in INDEXES)
    return rows(url, f"SELECT indexname FROM pg_indexes WHERE indexname IN ({names}) ORDER BY 1")


def test_the_correspondence_tables_are_created_and_dropped(scratch_url: str) -> None:
    migrator = DatabaseMigrator(StorageSettings(url=scratch_url))

    migrator.upgrade()
    assert tables(scratch_url) == TABLES
    assert indexes(scratch_url) == INDEXES
    rows(scratch_url, "INSERT INTO service_concepts (name) VALUES ('Managed Kubernetes')")
    with pytest.raises(asyncpg.UniqueViolationError):
        rows(scratch_url, "INSERT INTO service_concepts (name) VALUES ('managed kubernetes')")

    migrator.downgrade("0006")
    assert tables(scratch_url) == []
    assert indexes(scratch_url) == []

    migrator.upgrade()
    migrator.check()
    assert tables(scratch_url) == TABLES
    assert rows(scratch_url, "SELECT count(*) FROM service_concepts") == ["0"]
