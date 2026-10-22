from __future__ import annotations

from datetime import UTC, datetime
from typing import List

import pytest
from sqlalchemy import text

from models.cloud.enums import CloudProvider
from models.cloud.products.product import CloudProduct
from models.storage.pages.item_query import ItemQuery
from storage.storage import Storage

pytestmark = pytest.mark.db

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def product(name: str, categories: List[str]) -> CloudProduct:
    return CloudProduct(name=name, description=f"{name} service.", catalogue_categories=categories)


@pytest.fixture
async def stored(storage: Storage) -> Storage:
    await storage.catalogues.import_items(
        CloudProvider.AWS,
        T0,
        [product("EC2", ["Compute"]), product("Lambda", ["Compute", "Serverless"]), product("S3", ["Storage"])],
    )
    await storage.catalogues.import_items(
        CloudProvider.OVH, T0, [product("Public Cloud", []), product("Bare", ["Compute"])]
    )
    return storage


async def test_the_categories_are_stored_and_read_back(stored: Storage) -> None:
    page = await stored.catalogues.list(ItemQuery(providers=[CloudProvider.AWS], search="Lambda"))

    assert [item.item.catalogue_categories for item in page.items] == [["Compute", "Serverless"]]


async def test_the_products_are_filtered_by_their_catalogue_category_labels(stored: Storage) -> None:
    async with stored.database.connect() as connection:
        statement = text("SELECT id FROM source_labels WHERE key IN ('serverless', 'storage')")
        labels = list((await connection.execute(statement)).scalars())

    page = await stored.catalogues.list(ItemQuery(source_labels=labels))

    assert len(labels) == 2
    assert sorted(item.item.name for item in page.items) == ["Lambda", "S3"]
