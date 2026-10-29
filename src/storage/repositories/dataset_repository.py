from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional, Sequence, Set, Tuple

# Third Party Imports.
from sqlalchemy import Table, delete, insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.storage.dataset_stamp import DatasetStamp
from models.storage.enums import DatasetKind
from storage.engine.database import Database
from storage.engine.dataset_lock import DatasetLock
from storage.exception import StorageReadError, StorageWriteError
from storage.tables.base import ITEM_REVISION, Base
from storage.tables.datasets.dataset_row import DatasetRow


class DatasetRepository:
    """Create, read, update, delete and list the state of the stored datasets: cheap enough to be polled.

    Attributes:
        database (Database): The open database.
        table (Table): The datasets table.
        lock (DatasetLock): The locks of the running crawls.
        logger (Logger): The repository logger.

    Notes:
        A dataset is in progress while its crawl holds its
        lock: a crawl process which died leaves its dataset
        marked in progress, but its lock is released by the server.
        A crawl writes the state of its dataset itself (the crawl recorder): `create`, `update` and `delete` serve
        the imports and the maintenance, never set a dataset in progress, and `update` and `create` give it a new
        revision so that its readers reload it.
    """

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.table: Table = Base.metadata.tables[DatasetRow.__tablename__]
        self.logger = logger if logger else getLogger(__name__)
        self.lock = DatasetLock()
        self.logger.debug("Dataset repository ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _stamp(self, row: RowMapping, held: Set[Tuple[int, int]]) -> DatasetStamp:
        """Build the stamp of a dataset row.

        Args:
            row (RowMapping): The dataset row.
            held (Set[Tuple[int, int]]): The locks held by the running crawls.

        Returns:
            DatasetStamp: The state of the dataset.
        """
        kind = DatasetKind(row["kind"])
        return DatasetStamp(
            kind=kind,
            dataset=row["dataset"],
            label=row["label"],
            crawled_at=row["crawled_at"],
            in_progress=bool(row["in_progress"]) and self.lock.is_held(held, kind, row["dataset"]),
            size=row["size"],
            revision=row["revision"],
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    async def update(self, stamp: DatasetStamp) -> bool:
        """Replace the label, crawl time and size of a dataset, giving it a new revision.

        Args:
            stamp (DatasetStamp): The state.

        Returns:
            bool: Whether the dataset was stored (none is created otherwise).

        Raises:
            StorageWriteError: If the dataset cannot be written.
        """
        table = self.table
        statement = (
            update(table)
            .where(table.c.kind == stamp.kind.value, table.c.dataset == stamp.dataset)
            .values(
                label=stamp.label, crawled_at=stamp.crawled_at, size=stamp.size, revision=ITEM_REVISION.next_value()
            )
        )
        try:
            async with self.database.connect() as connection, connection.begin():
                result = await connection.execute(statement)
        except SQLAlchemyError as e:
            self.logger.error("The %s %s cannot be updated: %s", stamp.dataset, stamp.kind.value, e)
            raise StorageWriteError("datasets", str(e)) from e
        found = bool(result.rowcount)
        if found:
            self.logger.info("Dataset %s %s updated.", stamp.dataset, stamp.kind.value)
        else:
            self.logger.warning("No %s %s stored: nothing updated.", stamp.dataset, stamp.kind.value)
        return found

    async def delete(self, kind: DatasetKind, dataset: str) -> bool:
        """Delete the state of a dataset (its items are left to their repository).

        Args:
            kind (DatasetKind): What the dataset holds.
            dataset (str): The cloud provider, or the statistics source.

        Returns:
            bool: Whether the dataset was stored.

        Raises:
            StorageWriteError: If the dataset cannot be deleted (e.g. its items still refer to it).
        """
        table = self.table
        try:
            async with self.database.connect() as connection, connection.begin():
                result = await connection.execute(
                    delete(table).where(table.c.kind == kind.value, table.c.dataset == dataset)
                )
        except SQLAlchemyError as e:
            self.logger.error("The %s %s cannot be deleted: %s", dataset, kind.value, e)
            raise StorageWriteError("datasets", str(e)) from e
        found = bool(result.rowcount)
        if found:
            self.logger.info("Dataset %s %s deleted.", dataset, kind.value)
        else:
            self.logger.debug("No %s %s stored: nothing deleted.", dataset, kind.value)
        return found

    async def stamp(self, connection: AsyncConnection, kind: DatasetKind, dataset: str) -> Optional[DatasetStamp]:
        """Read the state of a dataset, in the transaction of a connection.

        Args:
            connection (AsyncConnection): A connection.
            kind (DatasetKind): What the dataset holds.
            dataset (str): The cloud provider, or the statistics source.

        Returns:
            Optional[DatasetStamp]: Its state, `None` when it is not stored.
        """
        self.logger.debug("Reading the state of the %s %s.", dataset, kind.value)
        result = await connection.execute(
            select(self.table).where(self.table.c.kind == kind.value, self.table.c.dataset == dataset)
        )
        row = result.mappings().first()
        if row is None:
            return None
        return self._stamp(row, await self.lock.held(connection))

    async def read(self, kind: DatasetKind, dataset: str) -> Optional[DatasetStamp]:
        """Read the state of a dataset.

        Args:
            kind (DatasetKind): What the dataset holds.
            dataset (str): The cloud provider, or the statistics source.

        Returns:
            Optional[DatasetStamp]: Its state, `None` when it is not stored.

        Raises:
            StorageReadError: If the dataset cannot be read.
        """
        try:
            async with self.database.connect() as connection:
                return await self.stamp(connection, kind, dataset)
        except SQLAlchemyError as e:
            self.logger.error("The state of the %s %s cannot be read: %s", dataset, kind.value, e)
            raise StorageReadError("datasets", str(e)) from e

    async def create(self, stamp: DatasetStamp) -> DatasetStamp:
        """Insert the state of a dataset (never in progress).

        Args:
            stamp (DatasetStamp): The state (its revision is drawn from the shared sequence).

        Returns:
            DatasetStamp: The state, as stored.

        Raises:
            StorageWriteError: If the dataset is already stored, or cannot be written.
        """
        row = {
            "kind": stamp.kind.value,
            "dataset": stamp.dataset,
            "label": stamp.label,
            "crawled_at": stamp.crawled_at,
            "size": stamp.size,
        }
        try:
            async with self.database.connect() as connection, connection.begin():
                await connection.execute(insert(self.table).values(row))
        except IntegrityError as e:
            self.logger.error("The %s %s is already stored: not created.", stamp.dataset, stamp.kind.value)
            raise StorageWriteError("datasets", f"{stamp.kind.value} {stamp.dataset} already exists") from e
        except SQLAlchemyError as e:
            self.logger.error("The %s %s cannot be created: %s", stamp.dataset, stamp.kind.value, e)
            raise StorageWriteError("datasets", str(e)) from e
        self.logger.info("Dataset %s %s created.", stamp.dataset, stamp.kind.value)
        return await self.read(stamp.kind, stamp.dataset) or stamp

    async def list(
        self, kinds: Optional[Sequence[DatasetKind]] = None, offset: int = 0, limit: Optional[int] = None
    ) -> List[DatasetStamp]:
        """List the state of the stored datasets.

        Args:
            kinds (Optional[Sequence[DatasetKind]]): Only these kinds, every one when `None` or empty.
            offset (int): The datasets skipped.
            limit (Optional[int]): The most datasets returned, every one when `None`.

        Returns:
            List[DatasetStamp]: The states, by kind then dataset.

        Raises:
            StorageReadError: If the datasets cannot be read.
        """
        table = self.table
        statement = select(table).order_by(table.c.kind, table.c.dataset).offset(offset).limit(limit)
        if kinds:
            statement = statement.where(table.c.kind.in_([kind.value for kind in kinds]))
        try:
            async with self.database.connect() as connection:
                result = await connection.execute(statement)
                rows = result.mappings().all()
                held = await self.lock.held(connection)
        except SQLAlchemyError as e:
            self.logger.error("The stored datasets cannot be read: %s", e)
            raise StorageReadError("datasets", str(e)) from e
        stamps = [self._stamp(row, held) for row in rows]
        self.logger.debug(
            "%d stored datasets, %d in progress.", len(stamps), sum(stamp.in_progress for stamp in stamps)
        )
        return stamps
