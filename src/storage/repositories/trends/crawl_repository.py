from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence, Tuple

# Third Party Imports.
from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.storage.crawl_summary import CrawlSummary
from models.storage.enums import CrawlStatus, DatasetKind
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.tables.base import Base
from storage.tables.datasets.crawl_row import CrawlRow


class CrawlRepository:
    """Create, read, update, delete and list the crawls, and read what each completed crawl added and deleted.

    Attributes:
        STATUSES (ClassVar[Tuple[CrawlStatus, ...]]): The outcomes of the crawls read.
        database (Database): The open database.
        table (Table): The `crawls` table.
        logger (Logger): The repository logger.

    Notes:
        - The imports of the former file storage are not read: they would count every item as added at once.
        - The first crawl of a dataset adds nothing: its items are the starting point.
        - A crawl records itself while it writes its dataset (the crawl recorder): `create`, `update` and `delete`
          serve the imports and the maintenance. A crawl referred to by stored items or reports cannot be deleted.
    """

    STATUSES: ClassVar[Tuple[CrawlStatus, ...]] = (CrawlStatus.SUCCEEDED, CrawlStatus.PARTIAL)

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.database = database
        self.table = Base.metadata.tables[CrawlRow.__tablename__]
        self.logger.debug("Repository of the crawl history ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _size(self, row: RowMapping) -> int:
        """Get the number of items listed after a crawl.

        Args:
            row (RowMapping): The crawl row.

        Returns:
            int: The items found by a complete crawl (the others were deleted), the items listed before plus the new
                ones for a partial crawl (nothing was deleted).
        """
        found = int(row["found"])
        if row["status"] == CrawlStatus.SUCCEEDED:
            return found
        return max(int(row["listed_before"]) + int(row["added"]) - int(row["deleted"]), found)

    def _summary(self, row: RowMapping) -> CrawlSummary:
        """Read a stored crawl.

        Args:
            row (RowMapping): The crawl row.

        Returns:
            CrawlSummary: The crawl, with the number of items listed after it.
        """
        return CrawlSummary(
            crawl_id=int(row["id"]),
            kind=DatasetKind(row["kind"]),
            dataset=row["dataset"],
            status=CrawlStatus(row["status"]),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            found=int(row["found"]),
            added=int(row["added"]),
            updated=int(row["updated"]),
            deleted=int(row["deleted"]),
            size=self._size(row),
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    async def read(self, crawl_id: int) -> Optional[CrawlSummary]:
        """Read one crawl, whatever its status.

        Args:
            crawl_id (int): The identifier of the crawl.

        Returns:
            Optional[CrawlSummary]: The crawl, `None` when there is none.

        Raises:
            StorageReadError: If the crawl cannot be read.
        """
        try:
            async with self.database.connect() as connection:
                row = (
                    (await connection.execute(select(self.table).where(self.table.c.id == crawl_id))).mappings().first()
                )
        except SQLAlchemyError as e:
            self.logger.error("The crawl %d cannot be read: %s", crawl_id, e)
            raise StorageReadError("crawls", str(e)) from e
        if row is None:
            self.logger.debug("No crawl %d.", crawl_id)
            return None
        return self._summary(row)

    async def create(self, crawl: CrawlSummary, listed_before: int = 0) -> CrawlSummary:
        """Insert one crawl.

        Args:
            crawl (CrawlSummary): The crawl (its identifier is ignored: the database gives a new one).
            listed_before (int): The items listed before the crawl.

        Returns:
            CrawlSummary: The crawl, as stored.

        Raises:
            StorageWriteError: If the crawl cannot be written.
        """
        statement = (
            insert(self.table)
            .values(
                kind=crawl.kind.value,
                dataset=crawl.dataset,
                status=crawl.status.value,
                started_at=crawl.started_at,
                finished_at=crawl.finished_at,
                listed_before=listed_before,
                found=crawl.found,
                added=crawl.added,
                updated=crawl.updated,
                deleted=crawl.deleted,
            )
            .returning(self.table.c.id)
        )
        try:
            async with self.database.connect() as connection, connection.begin():
                crawl_id = int((await connection.execute(statement)).scalar_one())
        except SQLAlchemyError as e:
            self.logger.error("The %s %s crawl cannot be created: %s", crawl.dataset, crawl.kind.value, e)
            raise StorageWriteError("crawls", str(e)) from e
        self.logger.info("Crawl %d of the %s %s created.", crawl_id, crawl.dataset, crawl.kind.value)
        return await self.read(crawl_id) or crawl.model_copy(update={"crawl_id": crawl_id})

    async def update(self, crawl: CrawlSummary) -> bool:
        """Replace the outcome and counts of one crawl (that of the same identifier).

        Args:
            crawl (CrawlSummary): The crawl.

        Returns:
            bool: Whether the crawl existed (none is created otherwise).

        Raises:
            StorageWriteError: If the crawl cannot be written.
        """
        statement = (
            update(self.table)
            .where(self.table.c.id == crawl.crawl_id)
            .values(
                status=crawl.status.value,
                started_at=crawl.started_at,
                finished_at=crawl.finished_at,
                found=crawl.found,
                added=crawl.added,
                updated=crawl.updated,
                deleted=crawl.deleted,
            )
        )
        try:
            async with self.database.connect() as connection, connection.begin():
                result = await connection.execute(statement)
        except SQLAlchemyError as e:
            self.logger.error("The crawl %d cannot be updated: %s", crawl.crawl_id, e)
            raise StorageWriteError("crawls", str(e)) from e
        found = bool(result.rowcount)
        if found:
            self.logger.info("Crawl %d updated.", crawl.crawl_id)
        else:
            self.logger.warning("No crawl %d: nothing updated.", crawl.crawl_id)
        return found

    async def delete(self, crawl_id: int) -> bool:
        """Delete one crawl.

        Args:
            crawl_id (int): The identifier of the crawl.

        Returns:
            bool: Whether a crawl was deleted.

        Raises:
            StorageWriteError: If the crawl is still referred to (by items, reports or a dataset), or cannot be
                deleted.
        """
        try:
            async with self.database.connect() as connection, connection.begin():
                result = await connection.execute(delete(self.table).where(self.table.c.id == crawl_id))
        except IntegrityError as e:
            self.logger.error("The crawl %d is still referred to: not deleted.", crawl_id)
            raise StorageWriteError("crawls", f"the crawl {crawl_id} is still referred to") from e
        except SQLAlchemyError as e:
            self.logger.error("The crawl %d cannot be deleted: %s", crawl_id, e)
            raise StorageWriteError("crawls", str(e)) from e
        found = bool(result.rowcount)
        if found:
            self.logger.info("Crawl %d deleted.", crawl_id)
        else:
            self.logger.debug("No crawl %d: nothing deleted.", crawl_id)
        return found

    async def list(
        self,
        kinds: Optional[Sequence[DatasetKind]] = None,
        datasets: Optional[Sequence[str]] = None,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> List[CrawlSummary]:
        """List the crawls, whatever their status, in the order they were recorded.

        Args:
            kinds (Optional[Sequence[DatasetKind]]): Only these kinds of dataset, every one when `None` or empty.
            datasets (Optional[Sequence[str]]): Only these datasets, every one when `None` or empty.
            offset (int): The crawls skipped.
            limit (Optional[int]): The most crawls returned, every one when `None`.

        Returns:
            List[CrawlSummary]: The crawls.

        Raises:
            StorageReadError: If the crawls cannot be read.
        """
        table = self.table
        statement = select(table).order_by(table.c.id).offset(offset).limit(limit)
        if kinds:
            statement = statement.where(table.c.kind.in_([kind.value for kind in kinds]))
        if datasets:
            statement = statement.where(table.c.dataset.in_(list(datasets)))
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The crawls cannot be listed: %s", e)
            raise StorageReadError("crawls", str(e)) from e
        crawls = [self._summary(row) for row in rows]
        self.logger.debug("%d crawls listed.", len(crawls))
        return crawls

    async def history(self, kind: DatasetKind, providers: Sequence[CloudProvider] = ()) -> List[CrawlSummary]:
        """Read the completed crawls of a kind of dataset.

        Args:
            kind (DatasetKind): What was crawled: `CATALOGUE` or `MARKETPLACE`.
            providers (Sequence[CloudProvider]): The crawled providers, every one when empty.

        Returns:
            List[CrawlSummary]: The crawls, in start order, with the number of items listed after each.

        Raises:
            StorageReadError: If the crawls cannot be read.
        """
        columns = self.table.c
        statement = (
            select(self.table)
            .where(columns.kind == kind.value, columns.status.in_([status.value for status in self.STATUSES]))
            .order_by(columns.started_at, columns.id)
        )
        if providers:
            statement = statement.where(columns.dataset.in_([provider.value for provider in providers]))
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The %s crawl history cannot be read: %s", kind.value, e)
            raise StorageReadError(f"{kind.value} crawl history", str(e)) from e
        crawls = [self._summary(row) for row in rows]
        self.logger.debug("%d completed %s crawls read.", len(crawls), kind.value)
        return crawls
