from __future__ import annotations

from datetime import UTC, datetime

import pytest

from models.cloud.enums import CloudProvider, DateCaveat, DateSource
from models.cloud.products.product import CloudProduct
from storage.storage import Storage

pytestmark = pytest.mark.db

T0 = datetime(2026, 1, 1, tzinfo=UTC)
LAUNCH = datetime(2014, 11, 1, tzinfo=UTC)


@pytest.fixture
async def stored(storage: Storage) -> Storage:
    products = [CloudProduct(name=name, description=f"{name} service.") for name in ("Lambda", "S3", "EC2")]
    await storage.catalogues.import_items(CloudProvider.AWS, T0, products)
    return storage


async def test_live_names_are_read_by_identifier(stored: Storage) -> None:
    names = await stored.catalogues.live_names(CloudProvider.AWS)

    assert sorted(names.values()) == ["EC2", "Lambda", "S3"]
    assert await stored.catalogues.live_names(CloudProvider.AZURE) == {}


async def test_launches_are_written_and_counted_once(stored: Storage) -> None:
    ids = {name: item_id for item_id, name in (await stored.catalogues.live_names(CloudProvider.AWS)).items()}
    launches = {
        ids["Lambda"]: (LAUNCH, DateCaveat.CURATED),
        ids["S3"]: (datetime(2006, 1, 1, tzinfo=UTC), DateCaveat.YEAR_ONLY),
    }

    changed = await stored.catalogues.set_launches(CloudProvider.AWS, launches)
    again = await stored.catalogues.set_launches(CloudProvider.AWS, launches)

    assert (changed, again) == (2, 0)
    catalogue = await stored.catalogues.load(CloudProvider.AWS)
    assert catalogue is not None
    dated = {product.name: product for product in catalogue.products}
    assert dated["Lambda"].added_at == LAUNCH
    assert dated["Lambda"].added_caveat is DateCaveat.CURATED
    assert dated["Lambda"].added_from is DateSource.WEBSITE
    assert dated["EC2"].added_caveat is None


async def test_no_launch_writes_nothing(stored: Storage) -> None:
    assert await stored.catalogues.set_launches(CloudProvider.AWS, {}) == 0
