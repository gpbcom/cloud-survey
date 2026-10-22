from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional, Set, Tuple

# Third Party Imports.
from sqlalchemy import Table, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.storage.dataset_stamp import DatasetStamp
from models.storage.enums import DatasetKind
from storage.engine.database import Database
from storage.engine.dataset_lock import DatasetLock
from storage.exception import StorageReadError
from storage.tables.base import Base
from storage.tables.datasets.dataset_row import DatasetRow


class DatasetRepository:
    """Read the state of the stored datasets: cheap enough to be polled by their readers.

    Attributes:
        database (Database): The open database.
        table (Table): The datasets table.
        lock (DatasetLock): The locks of the running crawls.
        logger (Logger): The repository logger.

    Notes:
        A dataset is in progress while its crawl holds its
        lock: a crawl process which died leaves its dataset
        marked in progress, but its lock is released by the server.
    """

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:   # noqa: E501
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.table: Table = Base.metadata.tables[DatasetRow.__tablename__]
        self.logger = logger if logger else getLogger(__name__)
        self.lock = DatasetLock(self.logger)
        self.logger.debug("Dataset repository ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _stamp(self, row: RowMapping, held: Set[Tuple[int, int]]) -> DatasetStamp:   # noqa: E501
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
            in_progress=bool(row["in_progress"]) and self.lock.is_held(held, kind, row["dataset"]),   # noqa: E501
            size=row["size"],
            revision=row["revision"],
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    async def read(self, connection: AsyncConnection, kind: DatasetKind, dataset: str) -> Optional[DatasetStamp]:   # noqa: E501
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
            select(self.table).where(self.table.c.kind == kind.value, self.table.c.dataset == dataset)   # noqa: E501
        )
        row = result.mappings().first()
        if row is None:
            return None
        return self._stamp(row, await self.lock.held(connection))

    async def stamps(self) -> List[DatasetStamp]:
        """Read the state of every stored dataset.

        Returns:
            List[DatasetStamp]: The states, by kind then dataset.

        Raises:
            StorageReadError: If the datasets cannot be read.
        """
        try:
            async with self.database.connect() as connection:
                result = await connection.execute(select(self.table).order_by(self.table.c.kind, self.table.c.dataset))
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
