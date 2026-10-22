from __future__ import annotations

# Standard Library Imports.
from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import Optional

# Third Party Imports.
from sqlalchemy import Table, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.storage.crawl_summary import CrawlSummary
from models.storage.enums import CrawlStatus, DatasetKind
from storage.tables.base import ITEM_REVISION, Base
from storage.tables.datasets.crawl_row import CrawlRow
from storage.tables.datasets.dataset_row import DatasetRow


class CrawlRecorder:
    """Record the crawls of the datasets, and the state of the datasets their readers watch.

    Attributes:
        crawls (Table): The crawls table.
        datasets (Table): The datasets table.
        logger (Logger): The recorder logger.

    Notes:
        Every method runs in the transaction of the given connection:
        a crawl and its items are written together.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the recorder.

        Args:
            logger (Optional[Logger]): The recorder logger.
        """
        self.crawls: Table = Base.metadata.tables[CrawlRow.__tablename__]
        self.datasets: Table = Base.metadata.tables[DatasetRow.__tablename__]
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("Crawl recorder ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start(
        self,
        connection: AsyncConnection,
        kind: DatasetKind,
        dataset: str,
        started_at: datetime,
        status: CrawlStatus = CrawlStatus.RUNNING,
        label: Optional[str] = None,
    ) -> int:
        """Record the start of a crawl, and mark the dataset as being written.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            kind (DatasetKind): What is crawled.
            dataset (str): The cloud provider, or the statistics source.
            started_at (datetime): When the crawl started: the date of its additions, updates and deletions.
            status (CrawlStatus): The status of the new crawl (`imported` for an import).
            label (Optional[str]): A readable name of the dataset source, kept when `None`.

        Returns:
            int: The identifier of the crawl.
        """
        abandoned = await connection.execute(
            update(self.crawls)
            .where(
                self.crawls.c.kind == kind.value,
                self.crawls.c.dataset == dataset,
                self.crawls.c.status == CrawlStatus.RUNNING.value,
            )
            .values(status=CrawlStatus.ABANDONED.value, finished_at=datetime.now(UTC))
        )
        if abandoned.rowcount:
            self.logger.warning(
                "%d %s %s crawls stopped without finishing: they are marked abandoned.",
                abandoned.rowcount,
                dataset,
                kind.value,
            )
        inserted = await connection.execute(
            insert(self.crawls)
            .values(kind=kind.value, dataset=dataset, status=status.value, started_at=started_at)
            .returning(self.crawls.c.id)
        )
        crawl_id = int(inserted.scalar_one())
        values = {
            "crawled_at": started_at,
            "in_progress": status is CrawlStatus.RUNNING,
            "current_crawl_id": crawl_id if status is CrawlStatus.RUNNING else None,
            "revision": ITEM_REVISION.next_value(),
        }
        if label is not None:
            values["label"] = label
        statement = upsert(self.datasets).values(kind=kind.value, dataset=dataset, **values)
        await connection.execute(
            statement.on_conflict_do_update(index_elements=[self.datasets.c.kind, self.datasets.c.dataset], set_=values)
        )
        self.logger.debug("Crawl %d of the %s %s started at %s.", crawl_id, dataset, kind.value, started_at)
        return int(crawl_id)

    async def progress(self, connection: AsyncConnection, kind: DatasetKind, dataset: str, size: int) -> None:
        """Record that the dataset was written: its readers read it again.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            kind (DatasetKind): What the dataset holds.
            dataset (str): The cloud provider, or the statistics source.
            size (int): The number of items still listed by the website.
        """
        self.logger.debug("The %s %s was written: %d items listed.", dataset, kind.value, size)
        await connection.execute(
            update(self.datasets)
            .where(self.datasets.c.kind == kind.value, self.datasets.c.dataset == dataset)
            .values(size=size, revision=ITEM_REVISION.next_value())
        )

    async def touch(self, connection: AsyncConnection, kind: DatasetKind, dataset: str, size: int) -> None:
        """Record a change of a dataset made by hand, storing the dataset when it is new.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            kind (DatasetKind): What the dataset holds.
            dataset (str): The cloud provider, or the statistics source.
            size (int): The number of items still listed by the website.
        """
        self.logger.debug("The %s %s was changed by hand: %d items listed.", dataset, kind.value, size)
        statement = upsert(self.datasets).values(
            kind=kind.value, dataset=dataset, crawled_at=datetime.now(UTC), size=size
        )
        await connection.execute(
            statement.on_conflict_do_update(
                index_elements=[self.datasets.c.kind, self.datasets.c.dataset],
                set_={"size": size, "revision": ITEM_REVISION.next_value()},
            )
        )

    async def finish(self, connection: AsyncConnection, summary: CrawlSummary, listed_before: int, error: str) -> None:
        """Record the end of a crawl, and mark the dataset as no longer being written.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            summary (CrawlSummary): What the crawl wrote.
            listed_before (int): The number of items listed before the crawl.
            error (str): Why the crawl failed, empty when it did not.
        """
        self.logger.debug("Recording the end of the crawl %d.", summary.crawl_id)
        await connection.execute(
            update(self.crawls)
            .where(self.crawls.c.id == summary.crawl_id)
            .values(
                status=summary.status.value,
                finished_at=summary.finished_at,
                listed_before=listed_before,
                found=summary.found,
                added=summary.added,
                updated=summary.updated,
                deleted=summary.deleted,
                error=error or None,
            )
        )
        values = {
            "in_progress": False,
            "current_crawl_id": None,
            "size": summary.size,
            "revision": ITEM_REVISION.next_value(),
        }
        if summary.status in (CrawlStatus.SUCCEEDED, CrawlStatus.PARTIAL, CrawlStatus.IMPORTED):
            values["last_crawl_id"] = summary.crawl_id
        await connection.execute(
            update(self.datasets)
            .where(self.datasets.c.kind == summary.kind.value, self.datasets.c.dataset == summary.dataset)
            .values(**values)
        )
        log = (
            self.logger.info if summary.status in (CrawlStatus.SUCCEEDED, CrawlStatus.IMPORTED) else self.logger.warning
        )
        log(
            "Crawl %d of the %s %s %s: %d found, %d added, %d updated, %d deleted, %d listed.",
            summary.crawl_id,
            summary.dataset,
            summary.kind.value,
            summary.status.value,
            summary.found,
            summary.added,
            summary.updated,
            summary.deleted,
            summary.size,
        )

    async def exists(self, connection: AsyncConnection, kind: DatasetKind, dataset: str) -> bool:
        """Tell whether a dataset is stored.

        Args:
            connection (AsyncConnection): A connection.
            kind (DatasetKind): What the dataset holds.
            dataset (str): The cloud provider, or the statistics source.

        Returns:
            bool: Whether the dataset has a row.
        """
        self.logger.debug("Checking whether the %s %s is stored.", dataset, kind.value)
        count = await connection.scalar(
            select(func.count())
            .select_from(self.datasets)
            .where(self.datasets.c.kind == kind.value, self.datasets.c.dataset == dataset)
        )
        return bool(count)
