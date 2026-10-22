from __future__ import annotations

# Standard Library Imports.
import time
from datetime import UTC, datetime
from logging import Logger, getLogger
from types import TracebackType
from typing import ClassVar, Dict, Iterable, List, Optional, Set, Tuple, Type

# Third Party Imports.
from pydantic import JsonValue
from sqlalchemy import BigInteger, LargeBinary, any_, bindparam, delete, func, insert, or_, select, text, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from catalogue.history.item_history import ItemHistory
from models.cloud.categorized_item import CategorizedItem
from models.cloud.item_state import ItemState
from models.storage.crawl_summary import CrawlSummary
from models.storage.enums import CrawlStatus, DatasetKind
from models.taxonomy.labels.resolved_label import ResolvedLabel
from storage.engine.database import Database
from storage.engine.dataset_lock import DatasetLock
from storage.exception import StorageLockError, StorageWriteError
from storage.mappers.item_mapper import ItemMapper, RowValue
from storage.repositories.taxonomy.item_categorizer import ItemCategorizer
from storage.tables.base import ITEM_REVISION
from storage.writer.claim_state import ClaimState
from storage.writer.crawl_recorder import CrawlRecorder


class ItemWriter[T: CategorizedItem]:
    """Write the items of a running crawl (products or software) to the storage, dated from the stored ones.

    Attributes:
        DELETE_BATCH (ClassVar[int]): The number of items marked deleted per statement.
        database (Database): The open database.
        mapper (ItemMapper[T]): The converter of the items to rows.
        categorizer (ItemCategorizer): The categorizer of the items in the unified taxonomy.
        kind (DatasetKind): What is crawled.
        provider (str): The crawled cloud provider.
        crawled_at (datetime): When the crawl started: the date of its additions, updates and deletions.
        batch_size (int): The number of items written per batch.
        flush_interval (float): How often, in seconds, the items crawled so far are written.
        label (str): What is written, for the logs (e.g. `aws marketplace`).
        history (ItemHistory[T]): The dating rules of the items.
        claims (Dict[str, int]): The stored item found for each crawled item, by first match key.
        states (Dict[int, ClaimState]): What the crawl knows of each stored item it found, by identifier.
        undo_claims (Dict[str, Optional[int]]): The claims replaced by the pending write, restored when it fails.
        undo_states (Dict[int, Optional[ClaimState]]): The states replaced by the pending write, restored when it fails.
        recorder (CrawlRecorder): The recorder of the crawl.
        lock (DatasetLock): The lock making the crawl the only writer of the dataset.
        logger (Logger): The writer logger.
        buffer (Dict[str, T]): The items crawled since the last write, by first match key.
        connection (Optional[AsyncConnection]): The connection of the crawl, holding the lock.
        crawl_id (int): The identifier of the crawl, 0 before `start`.
        baseline (bool): Whether the dataset was stored before the crawl (else the new items keep an unknown date).
        listed_before (int): The number of items listed before the crawl.
        flushed_at (float): When the items were last written (monotonic clock).
        summary (Optional[CrawlSummary]): What the crawl wrote, once it is over.
        seen (Set[int]): The source labels the crawl sighted.
        revision (Optional[int]): The taxonomy revision of the first write of the crawl.

    Notes:
        The crawl holds a connection, with the lock of the dataset, from `start` to `finish` (or `abort`). Every
        `batch_size` items, or every `flush_interval` seconds, the crawled items are written in one transaction:
        - The stored items having one of their match keys are read, and matched as `ItemHistory` does: a crawled
          item takes, for each of its match keys in order, the first stored item having the key (the lowest
          identifier), unless the crawl already gave it to another item. A crawled item streamed again (e.g. found in
          another category) gets the stored item it got the first time, dated against the item before the crawl.
        - The items are dated (`ItemHistory.date`): the new ones are inserted, the changed ones updated, the
          unchanged ones left untouched (a crawl of an unchanged marketplace writes nothing but its counters).
        - A version is written for the new items and those whose content changed.
        - Before each write, the source labels of the batch are resolved (the new ones stored with their rule links)
          in a short transaction of their own, then each item is categorized (see `ItemCategorizer`): a change of
          categorization updates the item without a version. When the taxonomy changed during the crawl, the items of
          the provider are categorized again once it is over.
        The claims of a write are pending until it is committed: a failed write is rolled back and retried.
        The per-item steps (`_match`, `_claim`, `_version`) run for each crawled item: they do not log, the batches
        do.
        Once the crawl is over, the stored items it did not find are marked deleted, unless it looks partial.
    """

    DELETE_BATCH: ClassVar[int] = 10_000

    def __init__(
        self,
        database: Database,
        mapper: ItemMapper[T],
        kind: DatasetKind,
        provider: str,
        crawled_at: datetime,
        flush_interval: float,
        categorizer: ItemCategorizer,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the writer of a crawl.

        Args:
            database (Database): The open database.
            mapper (ItemMapper[T]): The converter of the items to rows.
            kind (DatasetKind): What is crawled.
            provider (str): The crawled cloud provider.
            crawled_at (datetime): When the crawl started, timezone-aware.
            flush_interval (float): How often, in seconds, the items crawled so far are written.
            categorizer (ItemCategorizer): The categorizer of the items in the unified taxonomy.
            logger (Optional[Logger]): The writer logger.
        """
        self.database = database
        self.mapper = mapper
        self.categorizer = categorizer
        self.kind = kind
        self.provider = provider
        self.crawled_at = crawled_at
        self.batch_size = database.settings.batch_size
        self.flush_interval = flush_interval
        self.label = f"{provider} {kind.value}"
        self.logger = logger if logger else getLogger(__name__)
        self.history = ItemHistory[T](self.label, self.logger)
        self.claims: Dict[str, int] = {}
        self.states: Dict[int, ClaimState] = {}
        self.undo_claims: Dict[str, Optional[int]] = {}
        self.undo_states: Dict[int, Optional[ClaimState]] = {}
        self.recorder = CrawlRecorder(self.logger)
        self.lock = DatasetLock(self.logger)
        self.buffer: Dict[str, T] = {}
        self.connection: Optional[AsyncConnection] = None
        self.crawl_id = 0
        self.baseline = False
        self.listed_before = 0
        self.flushed_at = time.monotonic()
        self.summary: Optional[CrawlSummary] = None
        self.seen: Set[int] = set()
        self.revision: Optional[int] = None
        self.logger.debug(
            "Writer of the %s crawl started at %s ready (batches of %d, every %.1f s).",
            self.label,
            crawled_at,
            self.batch_size,
            flush_interval,
        )

    async def __aenter__(self) -> ItemWriter[T]:
        """Start the crawl.

        Returns:
            ItemWriter[T]: The started writer.
        """
        self.logger.debug("Starting the %s crawl.", self.label)
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Record the failure of the crawl when it did not finish, and release its connection.

        Args:
            exc_type (Optional[Type[BaseException]]): The type of the error stopping the crawl, if any.
            exc (Optional[BaseException]): The error stopping the crawl, if any.
            traceback (Optional[TracebackType]): Its traceback.
        """
        if exc is not None:
            self.logger.warning("The %s crawl stops on an error: %s", self.label, exc)
        else:
            self.logger.debug("Leaving the %s crawl.", self.label)
        if self.summary is None and self.connection is not None:
            await self.abort(CrawlStatus.FAILED, str(exc) if exc else "the crawl did not finish")

    ############################
    # Internal Helpers Methods #
    ############################

    def _match(self, hashes: Iterable[bytes], index: Dict[bytes, int]) -> Optional[int]:
        """Find the stored item of a crawled item, among the stored items the crawl did not find yet.

        Args:
            hashes (Iterable[bytes]): The hashes of the match keys of the crawled item, the most reliable first.
            index (Dict[bytes, int]): The lowest identifier of the items stored before the crawl, by key hash.

        Returns:
            Optional[int]: The identifier of its stored item, `None` when it is new.
        """
        for key_hash in hashes:
            row_id = index.get(key_hash)
            if row_id is not None and row_id not in self.states:
                return row_id
        return None

    def _claim(self, key: str, row_id: int, state: ClaimState) -> None:
        """Record the stored item of a crawled item, pending until the write is committed.

        Args:
            key (str): The first match key of the crawled item.
            row_id (int): The identifier of its stored item.
            state (ClaimState): What the crawl knows of the stored item.
        """
        if key not in self.undo_claims:
            self.undo_claims[key] = self.claims.get(key)
        if row_id not in self.undo_states:
            self.undo_states[row_id] = self.states.get(row_id)
        self.claims[key] = row_id
        self.states[row_id] = state

    def _commit_claims(self) -> None:
        """Keep the claims of the write: it was committed."""
        self.logger.debug("%d claims of the %s crawl kept.", len(self.undo_claims), self.label)
        self.undo_claims.clear()
        self.undo_states.clear()

    def _rollback_claims(self) -> None:
        """Forget the claims of the write: it failed."""
        self.logger.warning("%d claims of the %s crawl rolled back.", len(self.undo_claims), self.label)
        for key, row_id in self.undo_claims.items():
            if row_id is None:
                self.claims.pop(key, None)
            else:
                self.claims[key] = row_id
        for row_id, state in self.undo_states.items():
            if state is None:
                self.states.pop(row_id, None)
            else:
                self.states[row_id] = state
        self._commit_claims()

    def _counts(self) -> Tuple[int, int]:
        """Count the items added and updated by the crawl.

        Returns:
            Tuple[int, int]: The number of new items, then of updated ones.
        """
        self.logger.debug("Counting the items added and updated by the %s crawl.", self.label)
        added = sum(1 for state in self.states.values() if state.new)
        updated = sum(1 for state in self.states.values() if state.updated and not state.new)
        return added, updated

    async def _connect(self) -> AsyncConnection:
        """Get the connection of the crawl, opening a new one (and taking the lock again) when it was lost.

        Returns:
            AsyncConnection: The connection holding the lock of the dataset.

        Raises:
            StorageLockError: If another crawl writes the dataset.
            StorageConnectionError: If the database is not open.
        """
        if self.connection is not None and not self.connection.invalidated and not self.connection.closed:
            return self.connection
        if self.connection is not None:
            self.logger.warning("The connection of the %s crawl was lost: reconnecting.", self.label)
            await self.connection.close()
        connection = await self.database.connect().start()
        if not await self.lock.acquire(connection, self.kind, self.provider):
            await connection.rollback()
            await connection.close()
            self.connection = None
            self.logger.error("The %s is already being written by another crawl.", self.label)
            raise StorageLockError(self.kind.value, self.provider)
        await connection.commit()
        self.connection = connection
        return connection

    async def _release(self) -> None:
        """Release the lock and the connection of the crawl."""
        if self.connection is None:
            return
        connection, self.connection = self.connection, None
        try:
            if not connection.invalidated:
                await self.lock.release(connection, self.kind, self.provider)
                await connection.commit()
        except SQLAlchemyError as e:
            self.logger.warning("The lock of the %s could not be released (the server will): %s", self.label, e)
        finally:
            await connection.close()

    async def _listed(self, connection: AsyncConnection) -> int:
        """Count the stored items still listed by the website.

        Args:
            connection (AsyncConnection): The connection, in a transaction.

        Returns:
            int: The number of items of the provider without a deletion date.
        """
        self.logger.debug("Counting the listed items of the %s.", self.label)
        table = self.mapper.table
        count = await connection.scalar(
            select(func.count())
            .select_from(table)
            .where(table.c.provider == self.provider, table.c.deleted_at.is_(None))
        )
        return int(count or 0)

    async def _candidates(
        self, connection: AsyncConnection, hashes: List[bytes], row_ids: List[int]
    ) -> Tuple[Dict[int, RowMapping], Dict[bytes, int]]:
        """Read the stored items which may be those of the crawled items.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            hashes (List[bytes]): The hashes of the match keys of the crawled items.
            row_ids (List[int]): The stored items found for the crawled items streamed again.

        Returns:
            Tuple[Dict[int, RowMapping], Dict[bytes, int]]: The stored rows by identifier, then the lowest identifier
                of the items stored before the crawl, by key hash.

        Notes:
            The keys are passed as two array parameters (`= ANY(:hashes)`): the statement stays the same whatever the
            batch size, so it is compiled once and planned as index scans.
        """
        self.logger.debug(
            "Reading the stored %s items of %d keys (%d streamed again).", self.label, len(hashes), len(row_ids)
        )
        table = self.mapper.table
        hash_array = bindparam("hashes", hashes, type_=ARRAY(LargeBinary))
        id_array = bindparam("row_ids", row_ids, type_=ARRAY(BigInteger))
        statement = (
            select(table)
            .where(
                table.c.provider == self.provider,
                or_(
                    table.c.match_hash == any_(hash_array),
                    table.c.name_hash == any_(hash_array),
                    table.c.id == any_(id_array),
                ),
            )
            .order_by(table.c.id)
        )
        rows: Dict[int, RowMapping] = {}
        index: Dict[bytes, int] = {}
        for row in (await connection.execute(statement)).mappings():
            row_id = int(row["id"])
            rows[row_id] = row
            if row["first_crawl_id"] != self.crawl_id:
                index.setdefault(bytes(row["match_hash"]), row_id)
                index.setdefault(bytes(row["name_hash"]), row_id)
        return rows, index

    def _version(self, row_id: int, item: T, fingerprint: bytes) -> Dict[str, RowValue]:
        """Build the version of an item found by the crawl.

        Args:
            row_id (int): The item identifier.
            item (T): The dated item.
            fingerprint (bytes): The hash of its content fields.

        Returns:
            Dict[str, RowValue]: The values of the version row.
        """
        content: JsonValue = self.mapper.content(item)
        return {
            "item_id": row_id,
            "crawl_id": self.crawl_id,
            "recorded_at": self.crawled_at,
            "fingerprint": fingerprint,
            "content": content,
        }

    async def _insert(
        self, connection: AsyncConnection, items: List[Tuple[str, T]], labels: Dict[str, ResolvedLabel]
    ) -> List[Tuple[str, int, T]]:
        """Insert the new items.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            items (List[Tuple[str, T]]): The dated new items, with their first match key.
            labels (Dict[str, ResolvedLabel]): The resolved source labels of the batch.

        Returns:
            List[Tuple[str, int, T]]: The items with their first match key and their new identifier.
        """
        self.logger.debug("Inserting %d new %s items.", len(items), self.label)
        if not items:
            return []
        table = self.mapper.table
        rows = [
            {
                **self.mapper.to_row(item, self.provider),
                **self.categorizer.columns(item, labels, None, item.fingerprint_hash()),
                "first_crawl_id": self.crawl_id,
            }
            for _, item in items
        ]
        result = await connection.execute(insert(table).returning(table.c.id, sort_by_parameter_order=True), rows)
        row_ids = [int(row_id) for row_id in result.scalars().all()]
        return [(key, row_id, item) for (key, item), row_id in zip(items, row_ids, strict=True)]

    async def _update(self, connection: AsyncConnection, items: List[Tuple[int, Dict[str, RowValue]]]) -> None:
        """Update the stored items which changed (content, classification or dates).

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            items (List[Tuple[int, Dict[str, RowValue]]]): The new values of the items, with their identifier.
        """
        self.logger.debug("Updating %d changed %s items.", len(items), self.label)
        if not items:
            return
        table = self.mapper.table
        rows = [{**{f"new_{name}": value for name, value in values.items()}, "row_id": i} for i, values in items]
        names = [name.removeprefix("new_") for name in rows[0] if name != "row_id"]
        statement = (
            update(table)
            .where(table.c.id == bindparam("row_id"))
            .values({**{name: bindparam(f"new_{name}") for name in names}, "revision": ITEM_REVISION.next_value()})
        )
        await connection.execute(statement, rows)

    async def _write_versions(
        self, connection: AsyncConnection, versions: List[Dict[str, RowValue]], reverted: List[int]
    ) -> None:
        """Write the versions found by the crawl, and remove those of the items it found back unchanged.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            versions (List[Dict[str, RowValue]]): The new versions.
            reverted (List[int]): The items streamed again with the content they had before the crawl.
        """
        self.logger.debug("Writing %d %s versions, removing %d.", len(versions), self.label, len(reverted))
        table = self.mapper.versions
        if versions:
            statement = upsert(table)
            await connection.execute(
                statement.on_conflict_do_update(
                    index_elements=[table.c.item_id, table.c.crawl_id],
                    set_={"fingerprint": statement.excluded.fingerprint, "content": statement.excluded.content},
                ),
                versions,
            )
        if reverted:
            await connection.execute(
                delete(table).where(
                    table.c.crawl_id == self.crawl_id,
                    table.c.item_id == any_(bindparam("reverted", reverted, type_=ARRAY(BigInteger))),
                )
            )

    async def _write(self, connection: AsyncConnection, items: List[T], labels: Dict[str, ResolvedLabel]) -> None:
        """Write a batch of crawled items, in the current transaction (see the class notes).

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            items (List[T]): The crawled items, distinct.
            labels (Dict[str, ResolvedLabel]): The resolved source labels of the batch.
        """
        keyed = [(item.match_keys()[0], self.mapper.key_hashes(item), item) for item in items]
        hashes = sorted({key_hash for _, item_hashes, _ in keyed for key_hash in item_hashes})
        streamed = [row_id for key, _, _ in keyed if (row_id := self.claims.get(key)) is not None]
        rows, index = await self._candidates(connection, hashes, streamed)
        new: List[Tuple[str, T]] = []
        changed: List[Tuple[int, Dict[str, RowValue]]] = []
        versions: List[Dict[str, RowValue]] = []
        reverted: List[int] = []
        for key, item_hashes, item in keyed:
            row_id = self.claims.get(key)
            if row_id is None:
                row_id = self._match(item_hashes, index)
            stored = rows.get(row_id) if row_id is not None else None
            if row_id is None or stored is None:
                new.append((key, self.history.date(item, None, self.crawled_at, self.baseline)))
                continue
            state = self.states.get(row_id)
            is_new = state is not None and state.new
            prior: Optional[ItemState] = None
            if not is_new:
                prior = state.prior if state is not None and state.prior is not None else self.mapper.state_of(stored)
            dated = self.history.date(item, prior, self.crawled_at, self.baseline)
            fingerprint = dated.fingerprint_hash()
            values = self.mapper.to_row(dated, self.provider, fingerprint)
            values.update(self.categorizer.columns(dated, labels, stored, fingerprint))
            versioned = state.versioned if state is not None else False
            is_changed = self.mapper.differs(values, stored)
            if is_changed:
                changed.append((row_id, values))
            if prior is None or fingerprint != prior.fingerprint:
                versions.append(self._version(row_id, dated, fingerprint))
                versioned = True
            elif versioned:
                reverted.append(row_id)
                versioned = False
            written = is_changed or (state is not None and state.prior is not None)
            claim = ClaimState(
                new=is_new,
                prior=prior if written else None,
                updated=prior is not None and dated.updated_at == self.crawled_at,
                versioned=versioned,
            )
            self._claim(key, row_id, claim)
        for key, row_id, dated in await self._insert(connection, new, labels):
            versions.append(self._version(row_id, dated, dated.fingerprint_hash()))
            self._claim(key, row_id, ClaimState(new=True, prior=None, updated=False, versioned=True))
        await self._update(connection, changed)
        await self._write_versions(connection, versions, reverted)
        self.logger.debug(
            "%s: %d items written (%d new, %d changed, %d unchanged).",
            self.label,
            len(items),
            len(new),
            len(changed),
            len(items) - len(new) - len(changed),
        )

    async def _flush(self) -> None:
        """Write the buffered items in one transaction, and tell the readers.

        Raises:
            SQLAlchemyError: If the items cannot be written (the buffer and the claims are left as before).
            StorageLockError: If the connection was lost and another crawl took the lock meanwhile.
        """
        self.logger.debug("Writing the %d buffered %s items.", len(self.buffer), self.label)
        self.flushed_at = time.monotonic()
        if not self.buffer:
            return
        connection = await self._connect()
        items = list(self.buffer.values())
        try:
            async with connection.begin():
                labels = await self.categorizer.prepare(connection, items, self.kind, self.provider, self.seen)
            if self.revision is None:
                self.revision = self.categorizer.revision
            async with connection.begin():
                await connection.execute(text("SET LOCAL synchronous_commit = off"))
                await self._write(connection, items, labels)
                await self.recorder.progress(connection, self.kind, self.provider, await self._listed(connection))
        except SQLAlchemyError:
            self._rollback_claims()
            self.categorizer.invalidate()
            raise
        self._commit_claims()
        self.buffer.clear()

    async def _delete_missing(self, connection: AsyncConnection) -> int:
        """Mark deleted the stored items listed before the crawl which it did not find.

        Args:
            connection (AsyncConnection): The connection, in a transaction.

        Returns:
            int: The number of items marked deleted.
        """
        table = self.mapper.table
        listed = await connection.execute(
            select(table.c.id).where(table.c.provider == self.provider, table.c.deleted_at.is_(None))
        )
        found = set(self.states)
        missing = sorted(set(listed.scalars().all()) - found)
        for start in range(0, len(missing), self.DELETE_BATCH):
            await connection.execute(
                update(table)
                .where(
                    table.c.id
                    == any_(bindparam("missing", missing[start : start + self.DELETE_BATCH], type_=ARRAY(BigInteger)))
                )
                .values(deleted_at=self.crawled_at, revision=ITEM_REVISION.next_value())
            )
        self.logger.info("%d %s items missing from the crawl are marked deleted.", len(missing), self.label)
        return len(missing)

    async def _close(self, status: CrawlStatus, error: str, deleting: bool) -> CrawlSummary:
        """Record the end of the crawl, optionally marking the missing items deleted, and release the lock.

        Args:
            status (CrawlStatus): The outcome of the crawl.
            error (str): Why the crawl failed, empty when it did not.
            deleting (bool): Whether the stored items the crawl did not find are marked deleted.

        Returns:
            CrawlSummary: What the crawl wrote.
        """
        self.logger.debug("Closing the %s crawl as %s (deleting: %s).", self.label, status.value, deleting)
        connection = await self._connect()
        async with connection.begin():
            deleted = await self._delete_missing(connection) if deleting else 0
            added, updated = self._counts()
            summary = CrawlSummary(
                crawl_id=self.crawl_id,
                kind=self.kind,
                dataset=self.provider,
                status=status,
                started_at=self.crawled_at,
                finished_at=datetime.now(UTC),
                found=len(self.claims),
                added=added if self.baseline else 0,
                updated=updated,
                deleted=deleted,
                size=await self._listed(connection),
            )
            await self.recorder.finish(connection, summary, self.listed_before, error)
        self.summary = summary
        await self._release()
        return summary

    async def _recategorize(self) -> None:
        """Categorize the items of the provider again when the taxonomy changed during the crawl.

        Raises:
            SQLAlchemyError: If the items cannot be categorized again.
        """
        if self.revision is None:
            return
        connection = await self._connect()
        try:
            async with connection.begin():
                current, _ = await self.categorizer.taxonomy.revision(connection)
                if current == self.revision:
                    return
                self.logger.info(
                    "The taxonomy changed during the %s crawl: its items are categorized again.", self.label
                )
                await self.categorizer.recompute(connection, self.mapper, self.kind, self.provider)
        except SQLAlchemyError:
            self.categorizer.invalidate()
            raise

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start(self) -> None:
        """Start the crawl: take the lock of the dataset and record the crawl.

        Raises:
            StorageLockError: If another crawl writes the dataset.
            StorageWriteError: If the crawl cannot be recorded.
        """
        connection = await self._connect()
        try:
            async with connection.begin():
                table = self.mapper.table
                self.baseline = bool(
                    await connection.scalar(select(table.c.id).where(table.c.provider == self.provider).limit(1))
                )
                self.listed_before = await self._listed(connection)
                self.crawl_id = await self.recorder.start(connection, self.kind, self.provider, self.crawled_at)
        except SQLAlchemyError as e:
            await self._release()
            self.logger.error("The %s crawl cannot be recorded: %s", self.label, e)
            raise StorageWriteError(self.label, str(e)) from e
        self.flushed_at = time.monotonic()
        self.logger.info(
            "Writing the %s (crawl %d, %d items listed before).", self.label, self.crawl_id, self.listed_before
        )

    async def add(self, item: T) -> None:
        """Add a crawled item, written with the next batch. An item streamed again replaces its previous version.

        Args:
            item (T): The crawled item, with the website dates if any.

        Notes:
            A failed write of a batch is logged and retried with the next one: the crawl goes on.
        """
        self.buffer[item.match_keys()[0]] = item
        if len(self.buffer) < self.batch_size and time.monotonic() - self.flushed_at < self.flush_interval:
            return
        try:
            await self._flush()
        except (SQLAlchemyError, StorageLockError) as e:
            self.logger.warning(
                "The %d %s items crawled so far could not be written, retried later: %s",
                len(self.buffer),
                self.label,
                e,
            )

    async def abort(self, status: CrawlStatus, reason: str) -> Optional[CrawlSummary]:
        """Stop the crawl without deleting anything: the items written so far are kept.

        Args:
            status (CrawlStatus): The outcome of the crawl (`empty` or `failed`).
            reason (str): Why the crawl stopped.

        Returns:
            Optional[CrawlSummary]: What the crawl wrote, `None` when the stop itself cannot be recorded (logged).
        """
        if self.summary is not None:
            return self.summary
        self.logger.warning("The %s crawl stopped (%s): %s", self.label, status.value, reason)
        self.buffer.clear()
        try:
            return await self._close(status, reason, deleting=False)
        except (SQLAlchemyError, StorageLockError) as e:
            self.logger.error("The end of the %s crawl cannot be recorded: %s", self.label, e)
            await self._release()
            return None

    async def finish(self) -> CrawlSummary:
        """Write the last items, mark deleted the stored items missing from the crawl, and release the lock.

        Returns:
            CrawlSummary: What the crawl wrote, `partial` when it found too few items to delete the missing ones.

        Raises:
            StorageWriteError: If the items cannot be written (the crawl is then recorded as failed when possible).
            StorageLockError: If the connection was lost and another crawl took the lock meanwhile.
        """
        try:
            await self._flush()
            await self._recategorize()
            deleting = self.history.deletes(len(self.claims), self.listed_before, final=True)
            return await self._close(CrawlStatus.SUCCEEDED if deleting else CrawlStatus.PARTIAL, "", deleting)
        except SQLAlchemyError as e:
            await self.abort(CrawlStatus.FAILED, str(e))
            self.logger.error("The %s crawl cannot be written: %s", self.label, e)
            raise StorageWriteError(self.label, str(e)) from e
