from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import List, Optional

import pytest
from sqlalchemy import text

from models.cloud.enums import (
    CloudProvider,
    DateCaveat,
    DateSource,
    SoftwareAudience,
    SoftwareCategory,
)
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.filters.date_filter import DateFilter
from models.storage.pages.item_query import ItemQuery
from storage.storage import Storage

pytestmark = pytest.mark.db

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def listing(
    name: str,
    publisher: str,
    labels: List[str],
    paths: List[List[str]],
    added_at: Optional[datetime] = None,
    caveat: Optional[DateCaveat] = None,
    deleted_at: Optional[datetime] = None,
) -> MarketplaceSoftware:
    return MarketplaceSoftware.model_validate(
        {
            "name": name,
            "description": f"{name} for the {labels[0].casefold()} teams",
            "publisher": publisher,
            "url": f"https://market.example/{publisher.split()[0].casefold()}/{name.casefold()}",
            "categories": [SoftwareCategory.DEVELOPER_TOOL],
            "marketplace_categories": labels,
            "marketplace_category_paths": [{"path": path} for path in paths],
            "added_at": added_at,
            "added_from": DateSource.WEBSITE if added_at else None,
            "added_caveat": caveat,
            "deleted_at": deleted_at,
        }
    )


@pytest.fixture
async def stored(storage: Storage) -> Storage:
    software = [
        listing("Grafana", "Grafana Labs", ["Monitoring"], [["DevOps", "Monitoring"]], added_at=T0),
        listing("Loki", "Grafana Labs", ["Logging"], [["DevOps", "Logging"]], added_at=T0 + timedelta(days=30)),
        listing(
            "Odoo",
            "Odoo SA",
            ["ERP", "CRM"],
            [["Business", "ERP"]],
            added_at=T0 + timedelta(days=60),
            caveat=DateCaveat.YEAR_ONLY,
        ),
        listing("Legacy", "Old Corp", ["CRM"], [["Business", "CRM"]], deleted_at=T0 + timedelta(days=10)),
    ]
    await storage.marketplaces.import_items(CloudProvider.CIVO, T0, software)
    return storage


async def names(storage: Storage, query: ItemQuery) -> List[str]:
    return sorted(stored.item.name for stored in (await storage.marketplaces.list(query)).items)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (ItemQuery(name="LOK"), ["Loki"]),
        (ItemQuery(description="erp teams"), ["Odoo"]),
        (ItemQuery(url="nowhere"), []),
        (ItemQuery(url="/GRAFANA/"), ["Grafana", "Loki"]),
        (ItemQuery(publishers=["Grafana Labs"]), ["Grafana", "Loki"]),
        (ItemQuery(added=DateFilter(after=T0 + timedelta(days=1))), ["Loki", "Odoo"]),
        (ItemQuery(added=DateFilter(before=T0 + timedelta(days=31))), ["Grafana", "Loki"]),
        (ItemQuery(added=DateFilter(sources=[DateSource.WEBSITE])), ["Grafana", "Loki", "Odoo"]),
        (ItemQuery(added=DateFilter(known=False), include_deleted=True), ["Legacy"]),
        (ItemQuery(updated=DateFilter(known=True)), []),
        (ItemQuery(deleted=DateFilter(after=T0)), ["Legacy"]),
        (ItemQuery(deleted=DateFilter(before=T0)), []),
        (ItemQuery(approximate=True), ["Odoo"]),
        (ItemQuery(approximate=False), ["Grafana", "Loki"]),
        (ItemQuery(caveats=[DateCaveat.YEAR_ONLY]), ["Odoo"]),
        (ItemQuery(caveats=[DateCaveat.PAGE_MODIFIED]), []),
    ],
)
async def test_every_field_can_be_filtered(stored: Storage, query: ItemQuery, expected: List[str]) -> None:
    assert await names(stored, query) == expected


async def test_the_pickers_count_the_most_frequent_values(stored: Storage) -> None:
    facets = await stored.marketplaces.facets(ItemQuery(), pickers=True)
    without = await stored.marketplaces.facets(ItemQuery())

    assert facets.by_publisher == {"Grafana Labs": 2, "Odoo SA": 1}
    assert without.by_publisher == {}
    assert facets.model_copy(update={"by_publisher": {}}) == without


async def test_the_pickers_follow_the_filters(stored: Storage) -> None:
    facets = await stored.marketplaces.facets(ItemQuery(publishers=["Odoo SA"]), pickers=True)

    assert facets.by_publisher == {"Odoo SA": 1}
    assert facets.total == 1


async def test_the_source_labels_filter_the_listed_or_deleted_software(stored: Storage) -> None:
    async with stored.database.connect() as connection:
        crm = (await connection.execute(text("SELECT id FROM source_labels WHERE key = 'crm'"))).scalar_one()

    assert await names(stored, ItemQuery(source_labels=[crm])) == ["Odoo"]
    assert await names(stored, ItemQuery(source_labels=[crm], include_deleted=True)) == ["Legacy", "Odoo"]


async def test_the_software_is_filtered_by_audience(storage: Storage) -> None:
    both = listing("Odoo", "Odoo SA", ["ERP"], [["Business"]]).model_copy(
        update={"categories": [SoftwareCategory.DEVELOPER_TOOL, SoftwareCategory.END_USER_SOFTWARE]}
    )
    await storage.marketplaces.import_items(
        CloudProvider.CIVO, T0, [listing("Grafana", "Grafana Labs", ["Monitoring"], [["DevOps"]]), both]
    )

    assert await names(storage, ItemQuery(audiences=[SoftwareAudience.BOTH])) == ["Odoo"]
    assert await names(storage, ItemQuery(audiences=[SoftwareAudience.DEVELOPER_TOOL])) == ["Grafana"]
    assert await names(storage, ItemQuery(audiences=[SoftwareAudience.END_USER_SOFTWARE])) == []
