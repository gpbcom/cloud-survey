from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger, getLogger
from typing import AsyncIterator, ClassVar, Dict, List, Optional, Sequence, Set, Tuple, cast

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from sqlalchemy import BigInteger, Select, String, any_, bindparam, column, delete, func, insert, select, true, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.cloud.categorized_item import CategorizedItem
from models.cloud.enums import CloudProvider
from models.storage.crawl_summary import CrawlSummary
from models.storage.dataset_changes import DatasetChanges
from models.storage.dataset_stamp import DatasetStamp
from models.storage.enums import CrawlStatus, DatasetKind, ItemField
from models.storage.pages.item_query import ItemQuery
from models.storage.pages.page import Page
from models.storage.pages.stored_item import StoredItem
from models.storage.versions.item_version import ItemVersion
from models.taxonomy.enums import CategorySource, LabelStatus
from models.taxonomy.facets.unclassified_count import UnclassifiedCount
from models.taxonomy.labels.label_count import LabelCount
from storage.engine.database import Database
from storage.engine.dataset_lock import DatasetLock
from storage.exception import StorageLockError, StorageReadError, StorageWriteError
from storage.mappers.item_mapper import ItemMapper, RowValue
from storage.mappers.item_query_builder import ItemQueryBuilder
from storage.repositories.dataset_repository import DatasetRepository
from storage.repositories.taxonomy.item_categorizer import ItemCategorizer
from storage.tables.base import ITEM_REVISION, Base
from storage.tables.datasets.crawl_row import CrawlRow
from storage.tables.taxonomy.source_label_row import SourceLabelRow
from storage.writer.crawl_recorder import CrawlRecorder
from storage.writer.item_writer import ItemWriter


class ItemRepository[T: CategorizedItem]:
    """Read and write the stored items of a kind (catalogue products or marketplace software).

    Attributes:
        STREAM_SIZE (ClassVar[int]): The number of rows read from the server at a time.
        LABEL_LIMIT (ClassVar[int]): The largest number of source labels counted for the picker, the most frequent
            first.
        database (Database): The open database.
        mapper (ItemMapper[T]): The converter of the items to rows.
        builder (ItemQueryBuilder): The translator of the page queries into SQL.
        kind (DatasetKind): What the items are.
        datasets (DatasetRepository): The state of the datasets.
        lock (DatasetLock): The lock keeping the writes by hand and the imports away from a running crawl.
        recorder (CrawlRecorder): The recorder of the imports and of the changes made by hand.
        categorizer (ItemCategorizer): The categorizer of the items in the unified taxonomy.
        logger (Logger): The repository logger.

    Notes:
        - The crawls write through `writer` (dated from the stored items).
        - The items are read by page (`list`, filtered, ordered and counted by the server), one at a time (`read`),
          or every item of a provider (`items`, `changes`, streamed from the server).
        - `create`, `update` and `delete` change the items by hand, `update_many` and `delete_many` several items at
          once (in one transaction, the selected rows resolved with `item_ids`), `delete_matching` every item matching
          a query (removed by the server). They are refused while a provider of the items is crawled, and write no
          version (the versions are the history of the crawls).
        - `stream` reads every item matching a query by batches (an export).
        - Every write categorizes the items in the unified taxonomy (see `ItemCategorizer`). A change of their
          categories by hand pins them (`categories_source` = `user`). `recategorize` categorizes stored items again.
    """

    STREAM_SIZE: ClassVar[int] = 2000
    LABEL_LIMIT: ClassVar[int] = 1000

    def __init__(
        self,
        database: Database,
        mapper: ItemMapper[T],
        kind: DatasetKind,
        logger: Optional[Logger] = None,
        categorizer: Optional[ItemCategorizer] = None,
    ) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            mapper (ItemMapper[T]): The converter of the items to rows.
            kind (DatasetKind): What the items are.
            logger (Optional[Logger]): The repository logger.
            categorizer (Optional[ItemCategorizer]): The categorizer shared by the repositories of a storage, a new
                one when not given.
        """
        self.database = database
        self.mapper = mapper
        self.builder = ItemQueryBuilder(mapper.table)
        self.kind = kind
        self.logger = logger if logger else getLogger(__name__)
        self.datasets = DatasetRepository(database)
        self.lock = DatasetLock()
        self.recorder = CrawlRecorder()
        self.categorizer = categorizer if categorizer else ItemCategorizer(database)
        self.logger.debug("Repository of the %s items ready.", kind.value)

    ############################
    # Internal Helpers Methods #
    ############################

    def _label(self, provider: CloudProvider) -> str:
        """Name the items of a provider, for the logs and errors.

        Args:
            provider (CloudProvider): The cloud provider.

        Returns:
            str: e.g. `aws marketplace`.
        """
        return f"{provider.value} {self.kind.value}"

    def _stored(self, row: RowMapping) -> StoredItem[T]:
        """Build a stored item from its row.

        Args:
            row (RowMapping): The row, with the item columns.
                `provider` and `revision`.

        Returns:
            StoredItem[T]: The item with its storage identity.
        """
        return StoredItem[T](
            id=int(row["id"]),
            provider=CloudProvider(row["provider"]),
            revision=int(row["revision"]),
            item=self.mapper.to_model(row),
        )

    def _selection(self) -> Select[Tuple[RowValue, ...]]:
        """Get the selection of the items with their storage identity.

        Returns:
            Select[Tuple[RowValue, ...]]: The item columns, `provider`, `revision` and `categories_fingerprint`.
        """
        table = self.mapper.table
        columns = [*self.mapper.columns(), table.c.provider, table.c.revision, table.c.categories_fingerprint]
        return cast(Select[Tuple[RowValue, ...]], select(*columns))

    async def _listed(self, connection: AsyncConnection, provider: str) -> int:
        """Count the items of a provider still listed by the website.

        Args:
            connection (AsyncConnection): A connection.
            provider (str): The cloud provider.

        Returns:
            int: The number of items without a deletion date.
        """
        self.logger.debug("Counting the listed %s items of %s.", self.kind.value, provider)
        table = self.mapper.table
        count = await connection.scalar(
            select(func.count()).select_from(table).where(table.c.provider == provider, table.c.deleted_at.is_(None))
        )
        return int(count or 0)

    async def _lock(self, connection: AsyncConnection, provider: str) -> None:
        """Take the lock of the items of a provider until the end of the transaction.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            provider (str): The cloud provider.

        Raises:
            StorageLockError: If the provider is being crawled.
        """
        if not await self.lock.acquire_for_transaction(connection, self.kind, provider):
            self.logger.error("The %s %s is being crawled: it cannot be changed.", provider, self.kind.value)
            raise StorageLockError(self.kind.value, provider)

    async def _provider_of(self, connection: AsyncConnection, item_id: int) -> Optional[str]:
        """Find the cloud provider of a stored item.

        Args:
            connection (AsyncConnection): A connection.
            item_id (int): The item identifier.

        Returns:
            Optional[str]: Its cloud provider,
                `None` when the item does not exist.
        """
        self.logger.debug("Finding the provider of the %s item %d.", self.kind.value, item_id)
        table = self.mapper.table
        provider = await connection.scalar(select(table.c.provider).where(table.c.id == item_id))
        return str(provider) if provider is not None else None

    async def _lock_items(self, connection: AsyncConnection, item_ids: Sequence[int]) -> List[str]:
        """Take the locks of the providers of some items until the end of the transaction.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            item_ids (Sequence[int]): The item identifiers.

        Returns:
            List[str]: The cloud providers of the items, sorted.

        Raises:
            StorageLockError: If one of the providers is being crawled.
        """
        table = self.mapper.table
        result = await connection.execute(
            select(table.c.provider)
            .where(table.c.id == any_(bindparam("item_ids", list(item_ids), type_=ARRAY(BigInteger))))
            .distinct()
        )
        providers = sorted(str(provider) for provider in result.scalars().all())
        self.logger.debug("Locking %d providers for %d %s items.", len(providers), len(item_ids), self.kind.value)
        for provider in providers:
            await self._lock(connection, provider)
        return providers

    async def _touch(self, connection: AsyncConnection, providers: Sequence[str]) -> None:
        """Record that the items of some providers were changed by hand: their readers read them again.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            providers (Sequence[str]): The cloud providers.
        """
        self.logger.debug("Recording the changes by hand of %d %s datasets.", len(providers), self.kind.value)
        for provider in providers:
            await self.recorder.touch(connection, self.kind, provider, await self._listed(connection, provider))

    def _changed(self, row: RowMapping, changes: Dict[ItemField, JsonValue]) -> T:
        """Apply changes made by hand to a stored item.

        Args:
            row (RowMapping): The stored row.
            changes (Dict[ItemField, JsonValue]): The new value of each changed field.

        Returns:
            T: The changed item, validated (its dates are kept).

        Raises:
            StorageWriteError: If a changed value is invalid.
        """
        item = self.mapper.to_model(row)
        values: Dict[str, JsonValue] = {field.value: value for field, value in changes.items()}
        if ItemField.SERVICE_CATEGORIES in changes:
            values["categories_source"] = CategorySource.USER.value
        try:
            changed = self.mapper.model.model_validate({**item.model_dump(mode="json"), **values})
        except ValidationError as e:
            self.logger.error("Invalid change of the %s item %d: %s", self.kind.value, row["id"], e.errors()[0]["msg"])
            raise StorageWriteError(
                f"{self.kind.value} item {row['id']}", f"invalid change ({e.errors()[0]['msg']})"
            ) from e
        self.logger.debug("%s item %d changed by hand: %s.", self.kind.value, row["id"], ", ".join(changes))
        return changed

    async def _read(
        self, provider: CloudProvider, after: Optional[int]
    ) -> Optional[Tuple[DatasetStamp, Dict[int, T], int]]:
        """Read the items of a provider, streaming them from the server.

        Args:
            provider (CloudProvider): The cloud provider.
            after (Optional[int]): Only the items written after this revision, every item when `None`.

        Returns:
            Optional[Tuple[DatasetStamp, Dict[int, T], int]]: The state of the dataset,
                the items by identifier (in
                the order they were found first),
                then the highest revision read.
                `None` when it is not stored.

        Raises:
            StorageReadError: If the items cannot be read.
        """
        table = self.mapper.table
        statement = self._selection().where(table.c.provider == provider.value)
        if after is not None:
            statement = statement.where(table.c.revision > after)
        items: Dict[int, T] = {}
        revision = after or 0
        try:
            async with self.database.connect() as connection:
                stamp = await self.datasets.stamp(connection, self.kind, provider.value)
                if stamp is None:
                    return None
                result = await connection.stream(
                    statement.order_by(table.c.id).execution_options(yield_per=self.STREAM_SIZE)
                )
                async for partition in result.mappings().partitions():
                    for row in partition:
                        items[int(row["id"])] = self.mapper.to_model(row)
                        revision = max(revision, int(row["revision"]))
        except SQLAlchemyError as e:
            self.logger.error("The %s cannot be read: %s", self._label(provider), e)
            raise StorageReadError(self._label(provider), str(e)) from e
        return stamp, items, max(revision, stamp.revision)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def list(self, query: ItemQuery) -> Page[T]:
        """Read a page of items: filtered, ordered, and counted by the server.

        Args:
            query (ItemQuery): The filters, order and bounds of the page.

        Returns:
            Page[T]: The items of the page, with the number
                of matching items when `query.with_total`.

        Raises:
            StorageReadError: If the items cannot be read.
        """
        table = self.mapper.table
        conditions = self.builder.filters(query)
        statement = (
            self._selection()
            .where(*conditions)
            .order_by(*self.builder.order(query))
            .offset(query.offset)
            .limit(query.limit)
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
                total: Optional[int] = None
                if query.with_total:
                    count = await connection.scalar(select(func.count()).select_from(table).where(*conditions))
                    total = int(count or 0)
        except SQLAlchemyError as e:
            self.logger.error("A page of %s items cannot be read: %s", self.kind.value, e)
            raise StorageReadError(f"{self.kind.value} items", str(e)) from e
        page = Page[T](items=[self._stored(row) for row in rows], offset=query.offset, limit=query.limit, total=total)
        self.logger.debug(
            "Page of %d %s items read at %d (%s matching).",
            len(page.items),
            self.kind.value,
            query.offset,
            total,
        )
        return page

    async def read(self, item_id: int) -> Optional[StoredItem[T]]:
        """Read a stored item.

        Args:
            item_id (int): The item identifier.

        Returns:
            Optional[StoredItem[T]]: The item, `None` when it does not exist.

        Raises:
            StorageReadError: If the item cannot be read.
        """
        try:
            async with self.database.connect() as connection:
                row = (
                    (await connection.execute(self._selection().where(self.mapper.table.c.id == item_id)))
                    .mappings()
                    .first()
                )
        except SQLAlchemyError as e:
            self.logger.error("The %s item %d cannot be read: %s", self.kind.value, item_id, e)
            raise StorageReadError(f"{self.kind.value} item {item_id}", str(e)) from e
        if row is None:
            self.logger.debug("No %s item %d.", self.kind.value, item_id)
            return None
        return self._stored(row)

    async def versions(self, item_id: int) -> List[ItemVersion]:
        """Read the stored versions of an item, with the status of the crawls which found them.

        Args:
            item_id (int): The item identifier.

        Returns:
            List[ItemVersion]: The versions, the newest first, empty when the item has none (or does not exist).

        Raises:
            StorageReadError: If the versions cannot be read.

        Notes:
            - The versions are joined to their crawls (a left join: a version keeps its content without its crawl).
            - A version whose row cannot be read as a model is skipped, with a warning.
        """
        versions = self.mapper.versions
        crawls = Base.metadata.tables[CrawlRow.__tablename__]
        statement = (
            select(versions.c.crawl_id, versions.c.recorded_at, versions.c.content, crawls.c.status)
            .select_from(versions.outerjoin(crawls, crawls.c.id == versions.c.crawl_id))
            .where(versions.c.item_id == item_id)
            .order_by(versions.c.recorded_at.desc(), versions.c.crawl_id.desc())
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The versions of the %s item %d cannot be read: %s", self.kind.value, item_id, e)
            raise StorageReadError(f"versions of the {self.kind.value} item {item_id}", str(e)) from e
        read: List[ItemVersion] = []
        for row in rows:
            try:
                read.append(
                    ItemVersion(
                        crawl_id=row["crawl_id"],
                        recorded_at=row["recorded_at"],
                        crawl_status=row["status"],
                        content=row["content"],
                    )
                )
            except ValidationError as e:
                self.logger.warning(
                    "A version of the %s item %d (crawl %s) is skipped: %s",
                    self.kind.value,
                    item_id,
                    row["crawl_id"],
                    e,
                )
        self.logger.debug("%d versions of the %s item %d read.", len(read), self.kind.value, item_id)
        return read

    async def create(self, provider: CloudProvider, item: T) -> StoredItem[T]:
        """Store a new item by hand, with its dates as given.

        Args:
            provider (CloudProvider): The cloud provider of the item.
            item (T): The item.

        Returns:
            StoredItem[T]: The stored item, with its identifier.

        Raises:
            StorageLockError: If the provider is being crawled.
            StorageWriteError: If the item cannot be stored.
        """
        table = self.mapper.table
        label = self._label(provider)
        try:
            async with self.database.connect() as connection, connection.begin():
                await self._lock(connection, provider.value)
                labels = await self.categorizer.prepare(connection, [item], self.kind, provider.value)
                categorized = self.categorizer.columns(item, labels, None, item.fingerprint_hash())
                row = (
                    (
                        await connection.execute(
                            insert(table)
                            .values({**self.mapper.to_row(item, provider.value), **categorized, "first_crawl_id": None})
                            .returning(table.c.id, table.c.revision)
                        )
                    )
                    .mappings()
                    .one()
                )
                await self.recorder.touch(
                    connection,
                    self.kind,
                    provider.value,
                    await self._listed(connection, provider.value),
                )
        except SQLAlchemyError as e:
            self.categorizer.invalidate()
            self.logger.error("The %s item %r cannot be created: %s", label, getattr(item, "name", ""), e)
            raise StorageWriteError(label, str(e)) from e
        stored = StoredItem[T](id=int(row["id"]), provider=provider, revision=int(row["revision"]), item=item)
        self.logger.info("%s item %d created.", label, stored.id)
        return stored

    async def update(self, item_id: int, item: T) -> Optional[StoredItem[T]]:
        """Replace a stored item by hand, with its dates as given: its provider and identifier are kept.

        Args:
            item_id (int): The item identifier.
            item (T): The new item.

        Returns:
            Optional[StoredItem[T]]: The updated item, `None` when it does not exist.

        Raises:
            StorageLockError: If the provider of the item is being crawled.
            StorageWriteError: If the item cannot be updated.
        """
        table = self.mapper.table
        try:
            async with self.database.connect() as connection, connection.begin():
                provider = await self._provider_of(connection, item_id)
                if provider is None:
                    self.logger.warning("No %s item %d to update.", self.kind.value, item_id)
                    return None
                await self._lock(connection, provider)
                stored = (await connection.execute(self._selection().where(table.c.id == item_id))).mappings().one()
                labels = await self.categorizer.prepare(connection, [item], self.kind, None)
                categorized = self.categorizer.columns(item, labels, stored, item.fingerprint_hash())
                revision = await connection.scalar(
                    update(table)
                    .where(table.c.id == item_id)
                    .values(
                        {**self.mapper.to_row(item, provider), **categorized, "revision": ITEM_REVISION.next_value()}
                    )
                    .returning(table.c.revision)
                )
                await self.recorder.touch(connection, self.kind, provider, await self._listed(connection, provider))
        except SQLAlchemyError as e:
            self.categorizer.invalidate()
            self.logger.error("The %s item %d cannot be updated: %s", self.kind.value, item_id, e)
            raise StorageWriteError(f"{self.kind.value} item {item_id}", str(e)) from e
        self.logger.info("%s %s item %d updated.", provider, self.kind.value, item_id)
        return StoredItem[T](id=item_id, provider=CloudProvider(provider), revision=int(revision or 0), item=item)

    async def delete(self, item_id: int) -> bool:
        """Remove a stored item and its versions, by hand.

        Args:
            item_id (int): The item identifier.

        Returns:
            bool: Whether the item existed.

        Raises:
            StorageLockError: If the provider of the item is being crawled.
            StorageWriteError: If the item cannot be removed.

        Notes:
            Its readers see the item disappear at their
            next full read only: the changes (`changes`) report the
            written items, not the removed ones. A crawl marks
            the missing items deleted instead.
        """
        table = self.mapper.table
        try:
            async with self.database.connect() as connection, connection.begin():
                provider = await self._provider_of(connection, item_id)
                if provider is None:
                    self.logger.warning("No %s item %d to delete.", self.kind.value, item_id)
                    return False
                await self._lock(connection, provider)
                await connection.execute(delete(table).where(table.c.id == item_id))
                await self.recorder.touch(connection, self.kind, provider, await self._listed(connection, provider))
        except SQLAlchemyError as e:
            self.logger.error("The %s item %d cannot be deleted: %s", self.kind.value, item_id, e)
            raise StorageWriteError(f"{self.kind.value} item {item_id}", str(e)) from e
        self.logger.info("%s %s item %d deleted.", provider, self.kind.value, item_id)
        return True

    async def item_ids(self, query: ItemQuery, offset: int, count: int) -> List[int]:
        """Get the identifiers of the items at some positions of a page query: the rows selected in a table.

        Args:
            query (ItemQuery): The filters and order of the table (its bounds are ignored).
            offset (int): The position of the first item.
            count (int): The number of items.

        Returns:
            List[int]: The identifiers of the items, in the order of the query.

        Raises:
            StorageReadError: If the items cannot be read.
        """
        table = self.mapper.table
        statement = (
            select(table.c.id)
            .where(*self.builder.filters(query))
            .order_by(*self.builder.order(query))
            .offset(max(offset, 0))
            .limit(max(count, 0))
        )
        try:
            async with self.database.connect() as connection:
                item_ids = [int(item_id) for item_id in (await connection.execute(statement)).scalars().all()]
        except SQLAlchemyError as e:
            self.logger.error("The identifiers of the %s items cannot be read: %s", self.kind.value, e)
            raise StorageReadError(f"{self.kind.value} items", str(e)) from e
        self.logger.debug("%d %s identifiers read from %d.", len(item_ids), self.kind.value, offset)
        return item_ids

    async def read_many(self, item_ids: Sequence[int]) -> List[StoredItem[T]]:
        """Read several stored items.

        Args:
            item_ids (Sequence[int]): The item identifiers.

        Returns:
            List[StoredItem[T]]: The existing items, by identifier.

        Raises:
            StorageReadError: If the items cannot be read.
        """
        table = self.mapper.table
        statement = (
            self._selection()
            .where(table.c.id == any_(bindparam("item_ids", list(item_ids), type_=ARRAY(BigInteger))))
            .order_by(table.c.id)
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("%d %s items cannot be read: %s", len(item_ids), self.kind.value, e)
            raise StorageReadError(f"{self.kind.value} items", str(e)) from e
        if len(rows) < len(set(item_ids)):
            self.logger.warning(
                "%d of the %d %s items asked do not exist.",
                len(set(item_ids)) - len(rows),
                len(item_ids),
                self.kind.value,
            )
        self.logger.info("%d %s items read.", len(rows), self.kind.value)
        return [self._stored(row) for row in rows]

    async def update_many(self, item_ids: Sequence[int], changes: Dict[ItemField, JsonValue]) -> int:
        """Change some fields of several stored items by hand, in one transaction. Their dates are kept.

        Args:
            item_ids (Sequence[int]): The item identifiers.
            changes (Dict[ItemField, JsonValue]): The new value of each changed field (as JSON).

        Returns:
            int: The number of items changed.

        Raises:
            StorageLockError: If a provider of the items is being crawled.
            StorageWriteError: If a field is not one of the items, a value is invalid, or the items cannot be written.
        """
        table = self.mapper.table
        unknown: Set[ItemField] = {field for field in changes if field.value not in self.mapper.fields}
        if unknown:
            names = ", ".join(sorted(field.value for field in unknown))
            self.logger.error("The %s items have no field %s.", self.kind.value, names)
            raise StorageWriteError(f"{self.kind.value} items", f"no field {names}")
        if not item_ids or not changes:
            self.logger.warning("Nothing to change in the %s items.", self.kind.value)
            return 0
        batch = self.database.settings.batch_size
        changed = 0
        try:
            async with self.database.connect() as connection, connection.begin():
                providers = await self._lock_items(connection, item_ids)
                for start in range(0, len(item_ids), batch):
                    chunk = list(item_ids[start : start + batch])
                    rows = (
                        (
                            await connection.execute(
                                self._selection().where(
                                    table.c.id == any_(bindparam("item_ids", chunk, type_=ARRAY(BigInteger)))
                                )
                            )
                        )
                        .mappings()
                        .all()
                    )
                    items = [self._changed(row, changes) for row in rows]
                    labels = await self.categorizer.prepare(connection, items, self.kind, None)
                    values = [
                        {
                            **{
                                f"new_{name}": value
                                for name, value in {
                                    **self.mapper.to_row(item, str(row["provider"])),
                                    **self.categorizer.columns(item, labels, row, item.fingerprint_hash()),
                                }.items()
                            },
                            "row_id": int(row["id"]),
                        }
                        for row, item in zip(rows, items, strict=True)
                    ]
                    if values:
                        written = [name.removeprefix("new_") for name in values[0] if name != "row_id"]
                        await connection.execute(
                            update(table)
                            .where(table.c.id == bindparam("row_id"))
                            .values(
                                {
                                    **{name: bindparam(f"new_{name}") for name in written},
                                    "revision": ITEM_REVISION.next_value(),
                                }
                            ),
                            values,
                        )
                    changed += len(values)
                await self._touch(connection, providers)
        except SQLAlchemyError as e:
            self.categorizer.invalidate()
            self.logger.error("%d %s items cannot be changed: %s", len(item_ids), self.kind.value, e)
            raise StorageWriteError(f"{self.kind.value} items", str(e)) from e
        self.logger.info("%d %s items changed by hand (%s).", changed, self.kind.value, ", ".join(changes))
        return changed

    async def delete_many(self, item_ids: Sequence[int]) -> int:
        """Remove several stored items and their versions by hand, in one transaction.

        Args:
            item_ids (Sequence[int]): The item identifiers.

        Returns:
            int: The number of items removed.

        Raises:
            StorageLockError: If a provider of the items is being crawled.
            StorageWriteError: If the items cannot be removed.
        """
        table = self.mapper.table
        if not item_ids:
            self.logger.warning("No %s item to delete.", self.kind.value)
            return 0
        batch = self.database.settings.batch_size
        removed = 0
        try:
            async with self.database.connect() as connection, connection.begin():
                providers = await self._lock_items(connection, item_ids)
                for start in range(0, len(item_ids), batch):
                    chunk = list(item_ids[start : start + batch])
                    result = await connection.execute(
                        delete(table).where(table.c.id == any_(bindparam("item_ids", chunk, type_=ARRAY(BigInteger))))
                    )
                    removed += result.rowcount
                await self._touch(connection, providers)
        except SQLAlchemyError as e:
            self.logger.error("%d %s items cannot be deleted: %s", len(item_ids), self.kind.value, e)
            raise StorageWriteError(f"{self.kind.value} items", str(e)) from e
        self.logger.info("%d %s items deleted by hand.", removed, self.kind.value)
        return removed

    async def items(self, provider: CloudProvider) -> Optional[Tuple[DatasetStamp, List[T]]]:
        """Read every stored item of a provider, the deleted ones included, streamed from the server.

        Args:
            provider (CloudProvider): The cloud provider.

        Returns:
            Optional[Tuple[DatasetStamp, List[T]]]: The state of the dataset and its items, in the order they were
                found first, `None` when it is not stored.

        Raises:
            StorageReadError: If the items cannot be read.
        """
        read = await self._read(provider, None)
        if read is None:
            self.logger.debug("No %s stored.", self._label(provider))
            return None
        stamp, items, _ = read
        self.logger.info("%d %s items read (%d listed).", len(items), self._label(provider), stamp.size)
        return stamp, list(items.values())

    async def changes(self, provider: CloudProvider, after: int) -> Optional[DatasetChanges[T]]:
        """Read the items of a provider written after a revision, to refresh a copy of them.

        Args:
            provider (CloudProvider): The cloud provider.
            after (int): The revision of the copy, 0 to read every item.

        Returns:
            Optional[DatasetChanges[T]]: The items written after the revision, `None` when it is not stored.

        Raises:
            StorageReadError: If the items cannot be read.
        """
        read = await self._read(provider, after)
        if read is None:
            return None
        stamp, items, revision = read
        self.logger.debug("%d %s items changed since revision %d.", len(items), self._label(provider), after)
        return DatasetChanges[T](stamp=stamp, items=items, revision=revision)

    async def count(self, query: ItemQuery) -> int:
        """Count the items matching the filters of a query.

        Args:
            query (ItemQuery): The query (its order and bounds are ignored).

        Returns:
            int: The number of matching items.

        Raises:
            StorageReadError: If the items cannot be counted.
        """
        table = self.mapper.table
        try:
            async with self.database.connect() as connection:
                count = await connection.scalar(
                    select(func.count()).select_from(table).where(*self.builder.filters(query))
                )
        except SQLAlchemyError as e:
            self.logger.error("The %s items cannot be counted: %s", self.kind.value, e)
            raise StorageReadError(f"{self.kind.value} items", str(e)) from e
        return int(count or 0)

    async def stream(self, query: ItemQuery) -> AsyncIterator[List[StoredItem[T]]]:
        """Read every item matching the filters of a query, in its order, streamed from the server by batches.

        Args:
            query (ItemQuery): The filters and order (its bounds are ignored).

        Yields:
            List[StoredItem[T]]: The next batch of items (`STREAM_SIZE` at most), never all of them at once.

        Raises:
            StorageReadError: If the items cannot be read.
        """
        statement = (
            self._selection()
            .where(*self.builder.filters(query))
            .order_by(*self.builder.order(query))
            .execution_options(yield_per=self.STREAM_SIZE)
        )
        streamed = 0
        self.logger.info("Streaming the matching %s items.", self.kind.value)
        try:
            async with self.database.connect() as connection:
                result = await connection.stream(statement)
                async for partition in result.mappings().partitions():
                    batch = [self._stored(row) for row in partition]
                    streamed += len(batch)
                    self.logger.debug("%d %s items streamed.", streamed, self.kind.value)
                    yield batch
        except SQLAlchemyError as e:
            self.logger.error("The %s items cannot be streamed: %s", self.kind.value, e)
            raise StorageReadError(f"{self.kind.value} items", str(e)) from e
        self.logger.info("%d %s items streamed.", streamed, self.kind.value)

    async def delete_matching(self, query: ItemQuery) -> int:
        """Remove every stored item matching the filters of a query (and their versions) by hand, in one transaction.

        Args:
            query (ItemQuery): The filters (its order and bounds are ignored).

        Returns:
            int: The number of items removed.

        Raises:
            StorageLockError: If a provider of the matching items is being crawled.
            StorageWriteError: If the items cannot be removed.

        Notes:
            The items are removed by the server, without reading them:
            a selection of millions of items costs no
            memory. The providers of the matching items are locked first,
            so that a crawl starting meanwhile waits.
        """
        table = self.mapper.table
        conditions = self.builder.filters(query)
        try:
            async with self.database.connect() as connection, connection.begin():
                result = await connection.execute(select(table.c.provider).where(*conditions).distinct())
                providers = sorted(str(provider) for provider in result.scalars().all())
                if not providers:
                    self.logger.warning("No %s item matches the deletion filters.", self.kind.value)
                    return 0
                self.logger.debug("Locking %d providers to delete matching %s items.", len(providers), self.kind.value)
                for provider in providers:
                    await self._lock(connection, provider)
                removed = (await connection.execute(delete(table).where(*conditions))).rowcount
                await self._touch(connection, providers)
        except SQLAlchemyError as e:
            self.logger.error("The matching %s items cannot be deleted: %s", self.kind.value, e)
            raise StorageWriteError(f"{self.kind.value} items", str(e)) from e
        self.logger.info("%d %s items of %d providers deleted by hand.", removed, self.kind.value, len(providers))
        return removed

    def writer(self, provider: CloudProvider, crawled_at: datetime, flush_interval: float) -> ItemWriter[T]:
        """Get the writer of a crawl of a provider, to use as `async with repository.writer(...) as writer`.

        Args:
            provider (CloudProvider): The crawled cloud provider.
            crawled_at (datetime): When the crawl started, timezone-aware.
            flush_interval (float): How often, in seconds, the items crawled so far are written.

        Returns:
            ItemWriter[T]: The writer, started by `async with`.
        """
        self.logger.debug("Writer of a %s crawl started at %s.", self._label(provider), crawled_at)
        return ItemWriter[T](
            self.database, self.mapper, self.kind, provider.value, crawled_at, flush_interval, self.categorizer
        )

    async def import_items(
        self,
        provider: CloudProvider,
        crawled_at: datetime,
        items: List[T],
        replace: bool = False,
    ) -> Optional[CrawlSummary]:
        """Store items as they are, with their dates: the import of a file of the former file storage.

        Args:
            provider (CloudProvider): The cloud provider.
            crawled_at (datetime): When the items were crawled.
            items (List[T]): The dated items, the deleted ones included.
            replace (bool): Whether the stored items of
                the provider are replaced (else a stored dataset is kept).

        Returns:
            Optional[CrawlSummary]: What was imported, `None` when the dataset
                is already stored and kept (logged).

        Raises:
            StorageLockError: If the dataset is being crawled.
            StorageWriteError: If the items cannot be written.
        """
        label = self._label(provider)
        table = self.mapper.table
        size = sum(1 for item in items if not item.is_deleted)
        try:
            async with self.database.connect() as connection, connection.begin():
                await self._lock(connection, provider.value)
                if await self.recorder.exists(connection, self.kind, provider.value):
                    if not replace:
                        self.logger.warning("The %s is already stored: its file is not imported.", label)
                        return None
                    removed = await connection.execute(delete(table).where(table.c.provider == provider.value))
                    self.logger.warning("The %d stored %s items are replaced.", removed.rowcount, label)
                crawl_id = await self.recorder.start(
                    connection, self.kind, provider.value, crawled_at, status=CrawlStatus.IMPORTED
                )
                batch = self.database.settings.batch_size
                seen: Set[int] = set()
                for start in range(0, len(items), batch):
                    page = items[start : start + batch]
                    labels = await self.categorizer.prepare(connection, page, self.kind, provider.value, seen)
                    rows = [
                        {
                            **self.mapper.to_row(item, provider.value),
                            **self.categorizer.columns(item, labels, None, item.fingerprint_hash()),
                            "first_crawl_id": crawl_id,
                        }
                        for item in page
                    ]
                    result = await connection.execute(
                        insert(table).returning(table.c.id, table.c.fingerprint, sort_by_parameter_order=True), rows
                    )
                    versions = [
                        {
                            "item_id": int(row["id"]),
                            "crawl_id": crawl_id,
                            "recorded_at": crawled_at,
                            "fingerprint": row["fingerprint"],
                            "content": self.mapper.content(item),
                        }
                        for item, row in zip(page, result.mappings().all(), strict=True)
                    ]
                    await connection.execute(insert(self.mapper.versions), versions)
                summary = CrawlSummary(
                    crawl_id=crawl_id,
                    kind=self.kind,
                    dataset=provider.value,
                    status=CrawlStatus.IMPORTED,
                    started_at=crawled_at,
                    finished_at=crawled_at,
                    found=len(items),
                    added=len(items),
                    size=size,
                )
                await self.recorder.finish(connection, summary, 0, "")
        except SQLAlchemyError as e:
            self.categorizer.invalidate()
            self.logger.error("The %s cannot be imported: %s", label, e)
            raise StorageWriteError(label, str(e)) from e
        return summary

    async def recategorize(
        self,
        provider: CloudProvider,
        label_ids: Optional[Sequence[int]] = None,
        node_slugs: Optional[Sequence[str]] = None,
    ) -> Optional[int]:
        """Categorize the stored items of a provider again, from the current taxonomy and label links, without crawling.

        Args:
            provider (CloudProvider): The cloud provider.
            label_ids (Optional[Sequence[int]]): Only the items carrying one of these source labels.
            node_slugs (Optional[Sequence[str]]): Only the items filed under one of these categories or domains.

        Returns:
            Optional[int]: The number of items whose categorization or audiences changed, `None` when the
                dataset is not stored or is being crawled (logged).

        Raises:
            StorageWriteError: If the items cannot be categorized again.
        """
        label = self._label(provider)
        try:
            async with self.database.connect() as connection, connection.begin():
                if not await self.lock.acquire_for_transaction(connection, self.kind, provider.value):
                    self.logger.warning("The %s is being crawled: it is not categorized again.", label)
                    return None
                if not await self.recorder.exists(connection, self.kind, provider.value):
                    self.logger.debug("No %s stored to categorize again.", label)
                    return None
                changed = await self.categorizer.recompute(
                    connection, self.mapper, self.kind, provider.value, label_ids, node_slugs
                )
                if changed:
                    await self.recorder.progress(
                        connection, self.kind, provider.value, await self._listed(connection, provider.value)
                    )
        except SQLAlchemyError as e:
            self.categorizer.invalidate()
            self.logger.error("The %s cannot be categorized again: %s", label, e)
            raise StorageWriteError(label, str(e)) from e
        self.logger.info("%s categorized again: %d items changed.", label, changed)
        return changed

    async def reclassify(self, provider: CloudProvider) -> Optional[int]:
        """Classify the stored items of a provider again with the current rules, taxonomy and label links.

        Args:
            provider (CloudProvider): The cloud provider.

        Returns:
            Optional[int]: The number of items whose categories or audiences changed, `None` when the dataset
                is not stored or is being crawled (logged).

        Raises:
            StorageWriteError: If the items cannot be classified again.
        """
        self.logger.debug("Classifying the %s again.", self._label(provider))
        return await self.recategorize(provider)

    async def category_counts(self, query: ItemQuery) -> Dict[str, int]:
        """Count the matching items filed under each category and domain of the unified taxonomy.

        Args:
            query (ItemQuery): The filters (its own taxonomy filter, order and bounds are ignored).

        Returns:
            Dict[str, int]: The number of matching items of each taxonomy slug (categories and domains), the largest
                first.

        Raises:
            StorageReadError: If the categories cannot be counted.
        """
        table = self.mapper.table
        unfiltered = query.model_copy(update={"service_categories": []})
        count = func.count().label("count")
        slug = func.unnest(func.array_cat(table.c.service_categories, table.c.service_domains))
        nodes = slug.table_valued("slug").render_derived()
        statement = (
            select(column("slug", String), count)
            .select_from(table)
            .join(nodes, true())
            .where(*self.builder.filters(unfiltered))
            .group_by(column("slug", String))
            .order_by(count.desc(), column("slug", String))
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The %s categories cannot be counted: %s", self.kind.value, e)
            raise StorageReadError(f"{self.kind.value} categories", str(e)) from e
        counts = {str(name): int(total) for name, total in rows}
        self.logger.debug("%d %s taxonomy nodes counted.", len(counts), self.kind.value)
        return counts

    async def label_counts(self, query: ItemQuery) -> List[LabelCount]:
        """Count the matching items carrying each source label, its aliases counted with it, for the label picker.

        Args:
            query (ItemQuery): The filters (its own label filter, order and bounds are ignored).

        Returns:
            List[LabelCount]: The most frequent labels (the noise left out), the largest count first.

        Raises:
            StorageReadError: If the labels cannot be counted.
        """
        table = self.mapper.table
        unfiltered = query.model_copy(update={"source_labels": []})
        labels = Base.metadata.tables[SourceLabelRow.__tablename__]
        own = labels.alias("own")
        canonical = labels.alias("canonical")
        carried = func.unnest(table.c.source_label_ids).table_valued("label_id").render_derived()
        group = func.coalesce(canonical.c.name_key, canonical.c.key, own.c.name_key, own.c.key)
        count = func.count(func.distinct(table.c.id)).label("count")
        statement = (
            select(
                func.min(func.coalesce(canonical.c.id, own.c.id)).label("id"),
                func.min(func.coalesce(canonical.c.name_en, own.c.name_en, own.c.text)).label("name"),
                func.min(func.coalesce(canonical.c.text, own.c.text)).label("text"),
                func.min(func.coalesce(canonical.c.language, own.c.language)).label("language"),
                count,
            )
            .select_from(table)
            .join(carried, true())
            .join(own, own.c.id == carried.c.label_id)
            .outerjoin(canonical, canonical.c.id == own.c.canonical_id)
            .where(*self.builder.filters(unfiltered), own.c.status != LabelStatus.NOISE.value)
            .group_by(group)
            .order_by(count.desc(), group)
            .limit(self.LABEL_LIMIT)
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The %s source labels cannot be counted: %s", self.kind.value, e)
            raise StorageReadError(f"{self.kind.value} source labels", str(e)) from e
        counts = [LabelCount.model_validate(dict(row)) for row in rows]
        self.logger.debug("%d %s source labels counted.", len(counts), self.kind.value)
        return counts

    async def unclassified(self) -> List[UnclassifiedCount]:
        """Count the listed items of each provider, and those nothing could categorize (filed under `other`).

        Returns:
            List[UnclassifiedCount]: The counts of each stored provider, the largest share of unclassified items first.

        Raises:
            StorageReadError: If the items cannot be counted.
        """
        table = self.mapper.table
        unclassified = func.count().filter(table.c.service_categories.any_() == "other")
        statement = (
            select(table.c.provider, func.count(), unclassified)
            .where(table.c.deleted_at.is_(None))
            .group_by(table.c.provider)
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The unclassified %s items cannot be counted: %s", self.kind.value, e)
            raise StorageReadError(f"unclassified {self.kind.value} items", str(e)) from e
        counts = [
            UnclassifiedCount(provider=CloudProvider(provider), kind=self.kind, total=total, unclassified=other)
            for provider, total, other in rows
            if provider in {known.value for known in CloudProvider}
        ]
        counts.sort(key=lambda count: (-count.share(), count.provider.value))
        self.logger.debug("Unclassified %s items counted for %d providers.", self.kind.value, len(counts))
        return counts

    async def unclassified_batch(
        self, limit: int, after: int = 0, provider: Optional[CloudProvider] = None
    ) -> List[StoredItem[T]]:
        """Read listed items nothing categorized (filed under `other`), for the language model.

        Args:
            limit (int): The largest number of items read.
            after (int): Only the items of a larger identifier (the next batch).
            provider (Optional[CloudProvider]): Only the items of a provider, every provider when `None`.

        Returns:
            List[StoredItem[T]]: The items, by identifier.

        Raises:
            StorageReadError: If the items cannot be read.
        """
        table = self.mapper.table
        query = ItemQuery(providers=[provider] if provider else [], service_categories=["other"])
        statement = (
            self._selection().where(*self.builder.filters(query), table.c.id > after).order_by(table.c.id).limit(limit)
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The unclassified %s items cannot be read: %s", self.kind.value, e)
            raise StorageReadError(f"unclassified {self.kind.value} items", str(e)) from e
        items = [self._stored(row) for row in rows]
        self.logger.debug("%d unclassified %s items read after %d.", len(items), self.kind.value, after)
        return items

    async def apply_llm_categories(self, categories: Dict[int, Tuple[List[str], List[str]]]) -> int:
        """File unclassified items under the categories the language model gave them.

        Args:
            categories (Dict[int, Tuple[List[str], List[str]]]): The categories and domains of each item.

        Returns:
            int: The number of items changed.

        Raises:
            StorageWriteError: If the categories cannot be written.

        Notes:
            Only the items still filed under `other` (and not set by hand) change. The categories are kept until the
            content of the item changes (`categories_fingerprint`, the content hash they were given for).
        """
        table = self.mapper.table
        rows = [
            {"row_id": item_id, "new_categories": slugs, "new_domains": domains}
            for item_id, (slugs, domains) in sorted(categories.items())
            if slugs
        ]
        if not rows:
            return 0
        statement = (
            update(table)
            .where(
                table.c.id == bindparam("row_id"),
                table.c.service_categories.any_() == "other",
                table.c.categories_source.is_distinct_from(CategorySource.USER.value),
            )
            .values(
                service_categories=bindparam("new_categories"),
                service_domains=bindparam("new_domains"),
                categories_source=CategorySource.LLM.value,
                categories_fingerprint=table.c.fingerprint,
                revision=ITEM_REVISION.next_value(),
            )
        )
        try:
            async with self.database.connect() as connection, connection.begin():
                result = await connection.execute(statement, rows)
                providers = sorted(
                    set(
                        (
                            await connection.execute(
                                select(table.c.provider).where(table.c.id.in_([row["row_id"] for row in rows]))
                            )
                        ).scalars()
                    )
                )
                await self._touch(connection, providers)
        except SQLAlchemyError as e:
            self.categorizer.invalidate()
            self.logger.error(
                "The model categories of %d %s items cannot be written: %s", len(rows), self.kind.value, e
            )
            raise StorageWriteError(f"{self.kind.value} items", str(e)) from e
        changed = int(result.rowcount or 0)
        self.logger.info("%d %s items categorized by the language model.", changed, self.kind.value)
        return changed
