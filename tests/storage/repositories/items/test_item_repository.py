from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import List

import pytest

from models.cloud.enums import CloudProvider, DeliveryMethod, SoftwareCategory
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.enums import CrawlStatus, ItemField, ItemSort
from models.storage.pages.item_query import ItemQuery
from storage.exception import StorageLockError, StorageWriteError
from storage.storage import Storage

pytestmark = pytest.mark.db

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def listing(
    name: str,
    publisher: str = "ACME",
    description: str = "A tool",
    categories: List[SoftwareCategory] = [SoftwareCategory.DEVELOPER_TOOL],  # noqa: B006
    delivery: DeliveryMethod = DeliveryMethod.SAAS,
    path: List[str] = ["Data", "Databases"],  # noqa: B006
) -> MarketplaceSoftware:
    return MarketplaceSoftware(
        name=name,
        description=description,
        publisher=publisher,
        url=f"https://market.example/{name.casefold().replace(' ', '-')}",
        delivery=delivery,
        categories=categories,
        marketplace_categories=path,
        marketplace_category_paths=[{"path": path, "id": path[-1].casefold()}],
    )


async def seed(storage: Storage) -> None:
    async with storage.marketplaces.writer(CloudProvider.CIVO, T0, 60.0) as writer:
        await writer.add(listing("Postgres"))
        await writer.add(listing("Redis", publisher="Redis Labs"))
        await writer.add(
            listing(
                "Slack",
                publisher="Salesforce",
                description="Team chat",
                categories=[SoftwareCategory.END_USER_SOFTWARE],
                delivery=DeliveryMethod.OTHER,
                path=["Productivity"],
            )
        )
        await writer.finish()
    async with storage.marketplaces.writer(CloudProvider.SCALEWAY, T0 + timedelta(days=1), 60.0) as writer:
        await writer.add(listing("MySQL", publisher="Oracle"))
        await writer.finish()


async def names(storage: Storage, query: ItemQuery) -> List[str]:
    return [stored.item.name for stored in (await storage.marketplaces.list(query)).items]


async def test_pages_are_filtered_ordered_and_counted_by_the_server(storage: Storage) -> None:
    await seed(storage)

    first = await storage.marketplaces.list(ItemQuery(sort=ItemSort.NAME, limit=2))
    second = await storage.marketplaces.list(ItemQuery(sort=ItemSort.NAME, limit=2, offset=2))

    assert [stored.item.name for stored in first.items] == ["MySQL", "Postgres"]
    assert [stored.item.name for stored in second.items] == ["Redis", "Slack"]
    assert (first.total, first.has_more, second.has_more) == (4, True, False)
    assert first.items[0].provider is CloudProvider.SCALEWAY


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (ItemQuery(providers=[CloudProvider.SCALEWAY]), ["MySQL"]),
        (ItemQuery(search="redis"), ["Redis"]),
        (ItemQuery(search="SALES"), ["Slack"]),
        (ItemQuery(search="team chat"), []),
        (ItemQuery(search="team chat", search_description=True), ["Slack"]),
        (ItemQuery(search="100%_"), []),
        (ItemQuery(categories=[SoftwareCategory.END_USER_SOFTWARE]), ["Slack"]),
        (ItemQuery(deliveries=[DeliveryMethod.OTHER]), ["Slack"]),
        (ItemQuery(service_categories=["databases"]), ["MySQL", "Postgres", "Redis"]),
        (ItemQuery(service_categories=["collaboration-productivity"]), ["Slack"]),
        (ItemQuery(service_categories=["in-memory-cache", "collaboration"]), ["Redis", "Slack"]),
        (ItemQuery(sort=ItemSort.PUBLISHER), ["Postgres", "MySQL", "Redis", "Slack"]),
        (ItemQuery(sort=ItemSort.NAME, descending=True), ["Slack", "Redis", "Postgres", "MySQL"]),
        (ItemQuery(sort=ItemSort.PROVIDER), ["Postgres", "Redis", "Slack", "MySQL"]),
        (ItemQuery(sort=ItemSort.ADDED_AT), ["Postgres", "Redis", "Slack", "MySQL"]),
    ],
)
async def test_the_pages_filters_and_orders(storage: Storage, query: ItemQuery, expected: List[str]) -> None:
    await seed(storage)

    found = await names(storage, query)

    assert found == expected if query.sort is not ItemSort.ID else sorted(found) == sorted(expected)


async def test_the_deleted_items_are_read_on_request_only(storage: Storage) -> None:
    await seed(storage)
    async with storage.marketplaces.writer(CloudProvider.CIVO, T0 + timedelta(days=2), 60.0) as writer:
        await writer.add(listing("Postgres"))
        await writer.add(listing("Redis", publisher="Redis Labs"))
        await writer.finish()

    listed = await names(storage, ItemQuery(providers=[CloudProvider.CIVO]))
    every = await names(storage, ItemQuery(providers=[CloudProvider.CIVO], include_deleted=True))

    assert sorted(listed) == ["Postgres", "Redis"]
    assert sorted(every) == ["Postgres", "Redis", "Slack"]
    assert await storage.marketplaces.count(ItemQuery(include_deleted=True)) == 4


async def test_items_are_created_read_updated_and_deleted_by_hand(storage: Storage) -> None:
    await seed(storage)

    created = await storage.marketplaces.create(CloudProvider.OVH, listing("Grafana"))
    read = await storage.marketplaces.read(created.id)
    updated = await storage.marketplaces.update(created.id, listing("Grafana", publisher="Grafana Labs"))
    reread = await storage.marketplaces.read(created.id)
    deleted = await storage.marketplaces.delete(created.id)

    assert read is not None
    assert (read.provider, read.item.name) == (CloudProvider.OVH, "Grafana")
    assert updated is not None
    assert updated.revision > created.revision
    assert reread is not None
    assert reread.item.publisher == "Grafana Labs"
    assert deleted
    assert await storage.marketplaces.read(created.id) is None
    stamps = {(stamp.kind.value, stamp.dataset): stamp for stamp in await storage.datasets.stamps()}
    assert stamps[("marketplace", "ovh-cloud")].size == 0


async def test_the_changes_by_hand_of_a_missing_item_report_it(storage: Storage) -> None:
    assert await storage.marketplaces.update(404, listing("Nothing")) is None
    assert not await storage.marketplaces.delete(404)


async def test_a_provider_being_crawled_cannot_be_changed_by_hand(storage: Storage) -> None:
    await seed(storage)
    item = (await storage.marketplaces.list(ItemQuery(limit=1))).items[0]

    async with storage.marketplaces.writer(item.provider, T0, 60.0):
        with pytest.raises(StorageLockError):
            await storage.marketplaces.create(item.provider, listing("Late"))
        with pytest.raises(StorageLockError):
            await storage.marketplaces.update(item.id, item.item)
        with pytest.raises(StorageLockError):
            await storage.marketplaces.delete(item.id)


async def test_the_changes_since_a_revision_are_the_written_items(storage: Storage) -> None:
    await seed(storage)
    every = await storage.marketplaces.changes(CloudProvider.CIVO, 0)
    assert every is not None
    assert len(every.items) == 3

    async with storage.marketplaces.writer(CloudProvider.CIVO, T0 + timedelta(days=1), 60.0) as writer:
        await writer.add(listing("Postgres", description="Changed"))
        await writer.add(listing("Redis", publisher="Redis Labs"))
        await writer.add(
            listing(
                "Slack",
                publisher="Salesforce",
                description="Team chat",
                path=["Productivity"],
                categories=[SoftwareCategory.END_USER_SOFTWARE],
                delivery=DeliveryMethod.OTHER,
            )
        )
        await writer.finish()
    changed = await storage.marketplaces.changes(CloudProvider.CIVO, every.revision)

    assert changed is not None
    assert [item.name for item in changed.items.values()] == ["Postgres"]
    assert changed.revision > every.revision
    assert await storage.marketplaces.changes(CloudProvider.OVH, 0) is None


async def test_a_catalogue_is_loaded_as_a_document(storage: Storage) -> None:
    assert await storage.catalogues.load(CloudProvider.OVH) is None
    async with storage.catalogues.writer(CloudProvider.OVH, T0, 60.0) as writer:
        await writer.add(CloudProduct(name="Compute", description="VMs", url="https://ovh.example/compute"))
        await writer.finish()

    catalogue = await storage.catalogues.load(CloudProvider.OVH)

    assert catalogue is not None
    assert (catalogue.crawled_at, catalogue.in_progress, [product.name for product in catalogue.products]) == (
        T0,
        False,
        ["Compute"],
    )
    assert [stored.item.name for stored in (await storage.catalogues.list(ItemQuery(search="comp"))).items] == [
        "Compute"
    ]


async def test_an_import_stores_the_items_as_they_are_once(storage: Storage) -> None:
    items = [listing("Postgres").model_copy(update={"added_at": T0, "deleted_at": T0 + timedelta(days=3)})]

    summary = await storage.marketplaces.import_items(CloudProvider.CIVO, T0, items)
    kept = await storage.marketplaces.import_items(CloudProvider.CIVO, T0, [listing("Other")])
    replaced = await storage.marketplaces.import_items(CloudProvider.CIVO, T0, [listing("Other")], replace=True)

    assert summary is not None
    assert (summary.status, summary.found, summary.size) == (CrawlStatus.IMPORTED, 1, 0)
    assert kept is None
    assert replaced is not None
    marketplace = await storage.marketplaces.load(CloudProvider.CIVO)
    assert marketplace is not None
    assert [item.name for item in marketplace.software] == ["Other"]


async def test_the_selected_rows_are_resolved_to_identifiers(storage: Storage) -> None:
    await seed(storage)
    query = ItemQuery(sort=ItemSort.NAME)

    item_ids = await storage.marketplaces.item_ids(query, 1, 2)
    page = await storage.marketplaces.list(query)

    assert item_ids == [stored.id for stored in page.items[1:3]]
    assert await storage.marketplaces.item_ids(query, 10, 5) == []


async def test_several_items_are_read_changed_and_deleted_at_once(storage: Storage) -> None:
    await seed(storage)
    every = (await storage.marketplaces.list(ItemQuery(sort=ItemSort.NAME))).items
    chosen = [stored.id for stored in every[:3]]

    read = await storage.marketplaces.read_many([*chosen, 9999])
    changed = await storage.marketplaces.update_many(
        chosen, {ItemField.PUBLISHER: "Bulk Vendor", ItemField.DELIVERY: DeliveryMethod.KUBERNETES.value}
    )
    after = await storage.marketplaces.read_many(chosen)
    removed = await storage.marketplaces.delete_many([*chosen[:2], 9999])

    assert [stored.id for stored in read] == sorted(chosen)
    assert changed == 3
    assert {stored.item.publisher for stored in after} == {"Bulk Vendor"}
    assert {stored.item.delivery for stored in after} == {DeliveryMethod.KUBERNETES}
    assert all(stored.item.added_at == before.item.added_at for stored, before in zip(after, read, strict=False))
    assert removed == 2
    assert await storage.marketplaces.count(ItemQuery(include_deleted=True)) == 2
    stamps = {stamp.dataset: stamp for stamp in await storage.datasets.stamps()}
    assert stamps["civo"].size + stamps["scaleway"].size == 2


async def test_bulk_changes_are_validated(storage: Storage) -> None:
    await seed(storage)
    item_ids = await storage.marketplaces.item_ids(ItemQuery(), 0, 4)

    with pytest.raises(StorageWriteError, match="invalid change"):
        await storage.marketplaces.update_many(item_ids, {ItemField.NAME: " "})
    with pytest.raises(StorageWriteError, match="no field publisher"):
        await storage.catalogues.update_many([1], {ItemField.PUBLISHER: "x"})
    assert await storage.marketplaces.update_many([], {ItemField.NAME: "x"}) == 0
    assert await storage.marketplaces.update_many(item_ids, {}) == 0
    assert await storage.marketplaces.delete_many([]) == 0
    assert {stored.item.name for stored in await storage.marketplaces.read_many(item_ids)} != {" "}


async def test_bulk_changes_are_refused_while_a_provider_is_crawled(storage: Storage) -> None:
    await seed(storage)
    item_ids = await storage.marketplaces.item_ids(ItemQuery(providers=[CloudProvider.CIVO]), 0, 10)

    async with storage.marketplaces.writer(CloudProvider.CIVO, T0, 60.0):
        with pytest.raises(StorageLockError):
            await storage.marketplaces.update_many(item_ids, {ItemField.PUBLISHER: "x"})
        with pytest.raises(StorageLockError):
            await storage.marketplaces.delete_many(item_ids)


async def test_matching_items_are_streamed_by_batches_in_order(
    storage: Storage, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed(storage)
    monkeypatch.setattr(type(storage.marketplaces), "STREAM_SIZE", 2)

    batches = [batch async for batch in storage.marketplaces.stream(ItemQuery(sort=ItemSort.NAME, limit=1))]

    assert [len(batch) for batch in batches] == [2, 2]
    assert [stored.item.name for batch in batches for stored in batch] == ["MySQL", "Postgres", "Redis", "Slack"]
    filtered = storage.marketplaces.stream(ItemQuery(providers=[CloudProvider.SCALEWAY]))
    assert [stored.item.name for batch in [batch async for batch in filtered] for stored in batch] == ["MySQL"]


async def test_the_items_matching_a_query_are_deleted_by_the_server(storage: Storage) -> None:
    await seed(storage)
    before = {stamp.dataset: stamp.revision for stamp in await storage.datasets.stamps()}

    removed = await storage.marketplaces.delete_matching(ItemQuery(deliveries=[DeliveryMethod.SAAS]))

    assert removed == 3
    remaining = await storage.marketplaces.list(ItemQuery(sort=ItemSort.NAME))
    assert [stored.item.name for stored in remaining.items] == ["Slack"]
    after = {stamp.dataset: stamp for stamp in await storage.datasets.stamps()}
    assert after[CloudProvider.CIVO.value].revision > before[CloudProvider.CIVO.value]
    assert after[CloudProvider.SCALEWAY.value].size == 0
    assert await storage.marketplaces.delete_matching(ItemQuery(search="nothing like this")) == 0


async def test_deleting_matching_items_is_refused_while_a_provider_is_crawled(storage: Storage) -> None:
    await seed(storage)

    async with storage.marketplaces.writer(CloudProvider.SCALEWAY, T0 + timedelta(days=2), 60.0):
        with pytest.raises(StorageLockError):
            await storage.marketplaces.delete_matching(ItemQuery())

    assert await storage.marketplaces.count(ItemQuery()) == 4


async def test_restricted_providers_without_any_provider_match_no_item(storage: Storage) -> None:
    await seed(storage)

    assert await storage.marketplaces.count(ItemQuery(restrict_providers=True)) == 0
    assert await storage.marketplaces.count(ItemQuery()) == 4
    restricted = ItemQuery(providers=[CloudProvider.SCALEWAY], restrict_providers=True)
    assert await storage.marketplaces.count(restricted) == 1
    assert (await storage.marketplaces.facets(ItemQuery(restrict_providers=True))).total == 0
