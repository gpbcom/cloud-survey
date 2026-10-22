from __future__ import annotations

from datetime import UTC, datetime
from typing import List

import pytest

from models.cloud.enums import CloudProvider, SoftwareAudience, SoftwareCategory
from models.cloud.products.product import CloudProduct
from models.storage.pages.item_query import ItemQuery
from storage.storage import Storage

pytestmark = pytest.mark.db

T0 = datetime(2026, 1, 1, tzinfo=UTC)
DEV = SoftwareCategory.DEVELOPER_TOOL
USER = SoftwareCategory.END_USER_SOFTWARE


def product(name: str, categories: List[SoftwareCategory]) -> CloudProduct:
    return CloudProduct(name=name, description=f"{name} service.", categories=categories)


@pytest.fixture
async def stored(storage: Storage) -> Storage:
    await storage.catalogues.import_items(
        CloudProvider.AWS,
        T0,
        [
            product("EC2", [DEV]),
            product("WorkMail", [USER]),
            product("Connect", [DEV, USER]),
            product("Unclassified", []),
        ],
    )
    return storage


@pytest.mark.parametrize(
    ("audiences", "names"),
    [
        ([SoftwareAudience.DEVELOPER_TOOL], ["EC2"]),
        ([SoftwareAudience.END_USER_SOFTWARE], ["WorkMail"]),
        ([SoftwareAudience.BOTH], ["Connect"]),
        ([SoftwareAudience.DEVELOPER_TOOL, SoftwareAudience.BOTH], ["Connect", "EC2"]),
        ([], ["Connect", "EC2", "Unclassified", "WorkMail"]),
    ],
)
async def test_the_products_are_filtered_by_audience(
    stored: Storage, audiences: List[SoftwareAudience], names: List[str]
) -> None:
    page = await stored.catalogues.list(ItemQuery(audiences=audiences))

    assert sorted(item.item.name for item in page.items) == names


async def test_the_categories_are_stored_and_read_back(stored: Storage) -> None:
    page = await stored.catalogues.list(ItemQuery(search="Connect"))

    assert [item.item.categories for item in page.items] == [[DEV, USER]]


async def test_the_stored_products_are_classified_again(stored: Storage) -> None:
    stamp = {stamp.dataset: stamp for stamp in await stored.datasets.stamps()}[CloudProvider.AWS.value]

    changed = await stored.catalogues.reclassify(CloudProvider.AWS)
    again = await stored.catalogues.reclassify(CloudProvider.AWS)

    assert changed is not None
    assert changed >= 1
    assert again == 0
    catalogue = await stored.catalogues.load(CloudProvider.AWS)
    assert catalogue is not None
    assert all(item.categories for item in catalogue.products)
    assert {stamp.dataset: stamp for stamp in await stored.datasets.stamps()}[
        CloudProvider.AWS.value
    ].revision > stamp.revision


async def test_a_catalogue_not_stored_or_being_crawled_is_not_classified_again(stored: Storage) -> None:
    assert await stored.catalogues.reclassify(CloudProvider.OVH) is None
    async with stored.catalogues.writer(CloudProvider.AWS, T0, 60.0):
        assert await stored.catalogues.reclassify(CloudProvider.AWS) is None
