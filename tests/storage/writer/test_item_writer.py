from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from catalogue.history.item_history import ItemHistory
from models.cloud.enums import CloudProvider, DateSource
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.enums import CrawlStatus
from storage.exception import StorageLockError, StorageWriteError
from storage.storage import Storage

pytestmark = pytest.mark.db

PROVIDER = CloudProvider.CIVO
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def software(
    name: str,
    description: str = "d",
    url: Optional[str] = None,
    labels: Tuple[str, ...] = ("A",),
    added_at: Optional[datetime] = None,
) -> MarketplaceSoftware:
    return MarketplaceSoftware(
        name=name,
        description=description,
        url=url,
        publisher="ACME",
        categories=["developer-tool"],
        marketplace_categories=list(labels),
        added_at=added_at,
    )


async def crawl(storage: Storage, day: int, items: List[MarketplaceSoftware], interval: float = 0.0):
    async with storage.marketplaces.writer(PROVIDER, T0 + timedelta(days=day), interval) as writer:
        for item in items:
            await writer.add(item)
        return await writer.finish()


def dates(
    items: List[MarketplaceSoftware],
) -> List[Tuple[str, Optional[str], Optional[datetime], Optional[datetime], Optional[datetime]]]:
    return sorted((item.name, item.url, item.added_at, item.updated_at, item.deleted_at) for item in items)


async def stored(storage: Storage) -> List[MarketplaceSoftware]:
    marketplace = await storage.marketplaces.load(PROVIDER)
    assert marketplace is not None
    return marketplace.software


async def versions(storage: Storage) -> List[Tuple[int, int]]:
    async with storage.database.connect() as connection:
        result = await connection.execute(text("SELECT item_id, crawl_id FROM software_versions ORDER BY 1, 2"))
        return [(int(item), int(crawl)) for item, crawl in result.all()]


async def test_the_writer_dates_the_crawls_as_the_item_history(storage: Storage) -> None:
    crawls = [
        [
            software("a", url="https://x/a"),
            software("b"),
            software("c"),
            software("a", url="https://x/a", labels=("A", "B")),
        ],
        [software("a", url="https://x/a", labels=("A", "B")), software("b", description="changed"), software("d")],
        [software("a", url="https://x/a2"), software("b", description="changed")],
        [software("a", url="https://x/a2"), software("b", description="changed"), software("c"), software("d")],
    ]
    previous: Optional[List[MarketplaceSoftware]] = None
    for day, items in enumerate(crawls):
        await crawl(storage, day, items)
        distinct = list({item.identity(): item for item in items}.values())
        previous = ItemHistory[MarketplaceSoftware]("reference").merge(previous, distinct, T0 + timedelta(days=day))
        assert dates(await stored(storage)) == dates(previous)


async def test_the_first_crawl_keeps_the_added_dates_unknown_and_writes_a_version_each(storage: Storage) -> None:
    summary = await crawl(storage, 0, [software("a"), software("b", added_at=T0 - timedelta(days=9))])

    assert (summary.status, summary.found, summary.added, summary.updated, summary.deleted, summary.size) == (
        CrawlStatus.SUCCEEDED,
        2,
        0,
        0,
        0,
        2,
    )
    by_name = {item.name: item for item in await stored(storage)}
    assert by_name["a"].added_at is None
    assert (by_name["b"].added_at, by_name["b"].added_from) == (T0 - timedelta(days=9), DateSource.WEBSITE)
    assert await versions(storage) == [(1, 1), (2, 1)]


async def test_an_unchanged_crawl_writes_nothing_but_its_counters(storage: Storage) -> None:
    items = [software(name) for name in "abcdefg"]
    await crawl(storage, 0, items)
    async with storage.database.connect() as connection:
        before = (await connection.execute(text("SELECT id, revision FROM software ORDER BY id"))).all()

    summary = await crawl(storage, 1, items)

    async with storage.database.connect() as connection:
        after = (await connection.execute(text("SELECT id, revision FROM software ORDER BY id"))).all()
    assert after == before
    assert (summary.added, summary.updated, summary.deleted) == (0, 0, 0)
    assert len(await versions(storage)) == len(items)


async def test_a_changed_item_is_updated_and_versioned_once(storage: Storage) -> None:
    await crawl(storage, 0, [software("a"), software("b")])

    summary = await crawl(storage, 1, [software("a", description="new"), software("b")])

    assert summary.updated == 1
    updated = {item.name: item for item in await stored(storage)}["a"]
    assert (updated.updated_at, updated.updated_from, updated.description) == (
        T0 + timedelta(days=1),
        DateSource.CRAWL,
        "new",
    )
    assert await versions(storage) == [(1, 1), (1, 2), (2, 1)]


async def test_an_item_streamed_again_is_dated_against_the_previous_crawl(storage: Storage) -> None:
    await crawl(storage, 0, [software("a", url="https://x/a")])

    summary = await crawl(
        storage,
        1,
        [
            software("a", url="https://x/a", labels=("B",)),
            software("filler 1"),
            software("filler 2"),
            software("a", url="https://x/a", labels=("A",)),
        ],
    )

    item = {item.name: item for item in await stored(storage)}["a"]
    assert item.marketplace_categories == ["A"]
    assert item.updated_at is None, "streamed back to its previous content: not an update"
    assert summary.updated == 0
    assert (1, 2) not in await versions(storage), "the version of the intermediate content is removed"


async def test_an_item_whose_page_moved_is_recognized_by_its_name(storage: Storage) -> None:
    await crawl(storage, 0, [software("a", url="https://x/a"), software("b")])

    await crawl(storage, 1, [software("a", url="https://x/moved"), software("b")])

    rows = await stored(storage)
    assert len(rows) == 2
    assert {item.name: item.url for item in rows}["a"] == "https://x/moved"


async def test_the_missing_items_are_deleted_and_listed_again_when_found_back(storage: Storage) -> None:
    await crawl(storage, 0, [software("a"), software("b"), software("c")])

    deleting = await crawl(storage, 1, [software("a"), software("b")])
    found_back = await crawl(storage, 2, [software("a"), software("b"), software("c")])

    assert (deleting.deleted, deleting.size) == (1, 2)
    item = {item.name: item for item in await stored(storage)}["c"]
    assert item.deleted_at is None
    assert item.updated_at == T0 + timedelta(days=2), "listed again after its deletion: an update"
    assert (found_back.updated, found_back.size) == (1, 3)


async def test_a_partial_crawl_deletes_nothing(storage: Storage) -> None:
    await crawl(storage, 0, [software(name) for name in "abcd"])

    summary = await crawl(storage, 1, [software("a")])

    assert (summary.status, summary.deleted, summary.size) == (CrawlStatus.PARTIAL, 0, 4)


async def test_an_aborted_crawl_keeps_what_it_wrote_and_deletes_nothing(storage: Storage) -> None:
    await crawl(storage, 0, [software("a"), software("b")])

    async with storage.marketplaces.writer(PROVIDER, T0 + timedelta(days=1), 0.0) as writer:
        await writer.add(software("c"))
        summary = await writer.abort(CrawlStatus.EMPTY, "stopped")

    assert summary is not None
    assert (summary.status, summary.deleted) == (CrawlStatus.EMPTY, 0)
    assert sorted(item.name for item in await stored(storage) if not item.is_deleted) == ["a", "b", "c"]


async def test_a_crawl_failing_inside_the_writer_is_recorded_as_failed(storage: Storage) -> None:
    writer = storage.marketplaces.writer(PROVIDER, T0, 0.0)
    await writer.__aenter__()
    await writer.add(software("a"))

    await writer.__aexit__(RuntimeError, RuntimeError("boom"), None)

    async with storage.database.connect() as connection:
        status, error = (await connection.execute(text("SELECT status, error FROM crawls"))).one()
    assert (status, error) == ("failed", "boom")


async def test_a_crawl_left_running_is_abandoned_by_the_next_one(storage: Storage) -> None:
    writer = storage.marketplaces.writer(PROVIDER, T0, 0.0)
    await writer.start()
    await writer._release()

    await crawl(storage, 1, [software("a")])

    async with storage.database.connect() as connection:
        statuses = (await connection.execute(text("SELECT status FROM crawls ORDER BY id"))).scalars().all()
    assert statuses == ["abandoned", "succeeded"]


async def test_two_crawls_of_a_provider_cannot_run_at_the_same_time(storage: Storage) -> None:
    async with storage.marketplaces.writer(PROVIDER, T0, 0.0):
        with pytest.raises(StorageLockError, match="already being written"):
            async with storage.marketplaces.writer(PROVIDER, T0, 0.0):
                pass


async def test_a_failing_batch_is_rolled_back_and_retried_with_the_next_one(
    storage: Storage, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = storage.marketplaces.writer(PROVIDER, T0, 0.0)
    original = writer._write
    calls: Dict[str, int] = {"count": 0}

    async def failing_once(connection, items, labels):
        calls["count"] += 1
        await original(connection, items, labels)
        if calls["count"] == 1:
            raise OperationalError("INSERT", {}, Exception("connection reset"))

    async with writer:
        monkeypatch.setattr(writer, "_write", failing_once)
        await writer.add(software("a"))
        assert list(writer.buffer), "kept for the next batch"
        assert not writer.claims, "rolled back"
        await writer.add(software("b"))
        summary = await writer.finish()

    assert (summary.status, summary.found) == (CrawlStatus.SUCCEEDED, 2)
    assert sorted(item.name for item in await stored(storage)) == ["a", "b"]


async def test_a_failing_last_batch_fails_the_crawl(storage: Storage, monkeypatch: pytest.MonkeyPatch) -> None:
    writer = storage.marketplaces.writer(PROVIDER, T0, 60.0)

    async def failing(connection, items, labels):
        raise OperationalError("INSERT", {}, Exception("disk full"))

    async with writer:
        await writer.add(software("a"))
        monkeypatch.setattr(writer, "_write", failing)
        with pytest.raises(StorageWriteError, match="disk full"):
            await writer.finish()

    assert writer.summary is not None
    assert writer.summary.status is CrawlStatus.FAILED


async def test_the_writer_reconnects_when_its_connection_is_lost(storage: Storage) -> None:
    async with storage.marketplaces.writer(PROVIDER, T0, 0.0) as writer:
        assert writer.connection is not None
        await writer.connection.invalidate()
        await writer.add(software("a"))
        summary = await writer.finish()

    assert summary.found == 1
    async with storage.database.connect() as connection:
        assert (await connection.execute(select(text("count(*)")).select_from(text("software")))).scalar() == 1
