from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence, Tuple

# Third Party Imports.
from sqlalchemy import select
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.storage.crawl_summary import CrawlSummary
from models.storage.enums import CrawlStatus, DatasetKind
from storage.engine.database import Database
from storage.exception import StorageReadError
from storage.tables.base import Base
from storage.tables.datasets.crawl_row import CrawlRow


class CrawlRepository:
    """Read the history of the crawls: what each completed crawl added, updated and deleted.

    Attributes:
        STATUSES (ClassVar[Tuple[CrawlStatus, ...]]): The outcomes of the crawls read.
        database (Database): The open database.
        logger (Logger): The repository logger.

    Notes:
        - The imports of the former file storage are not read: they would count every item as added at once.
        - The first crawl of a dataset adds nothing: its items are the starting point.
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

    ############################
    # Publicly Exposed Methods #
    ############################

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
            select(
                columns.id,
                columns.dataset,
                columns.status,
                columns.started_at,
                columns.finished_at,
                columns.listed_before,
                columns.found,
                columns.added,
                columns.updated,
                columns.deleted,
            )
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
        crawls = [
            CrawlSummary(
                crawl_id=int(row["id"]),
                kind=kind,
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
            for row in rows
        ]
        self.logger.debug("%d completed %s crawls read.", len(crawls), kind.value)
        return crawls
