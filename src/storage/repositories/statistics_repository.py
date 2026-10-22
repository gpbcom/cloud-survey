from __future__ import annotations

# Standard Library Imports.
from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import Optional

# Third Party Imports.
from sqlalchemy import Boolean, Table, delete, literal_column, select
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.stats.market_statistics import MarketStatistics
from models.storage.crawl_summary import CrawlSummary
from models.storage.enums import CrawlStatus, DatasetKind
from storage.engine.database import Database
from storage.engine.dataset_lock import DatasetLock
from storage.exception import StorageLockError, StorageReadError, StorageWriteError
from storage.mappers.report_mapper import ReportMapper
from storage.repositories.dataset_repository import DatasetRepository
from storage.tables.base import Base
from storage.tables.datasets.market_report_row import MarketReportRow
from storage.writer.crawl_recorder import CrawlRecorder


class StatisticsRepository:
    """Read and write the cloud market statistics of the sources (e.g. Synergy Research Group).

    Attributes:
        database (Database): The open database.
        table (Table): The market reports table.
        mapper (ReportMapper): The converter of the reports to rows.
        datasets (DatasetRepository): The state of the datasets.
        lock (DatasetLock): The lock making a crawl
            the only writer of the statistics of a source.
        recorder (CrawlRecorder): The recorder of the crawls.
        logger (Logger): The repository logger.

    Notes:
        The statistics of a source are replaced as a whole by each crawl:
            a report missing from the crawl is removed.
    """

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.table: Table = Base.metadata.tables[MarketReportRow.__tablename__]
        self.logger = logger if logger else getLogger(__name__)
        self.mapper = ReportMapper(self.table, self.logger)
        self.datasets = DatasetRepository(database, self.logger)
        self.lock = DatasetLock(self.logger)
        self.recorder = CrawlRecorder(self.logger)
        self.logger.debug("Statistics repository ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def replace(
        self,
        name: str,
        statistics: MarketStatistics,
        status: CrawlStatus = CrawlStatus.SUCCEEDED,
    ) -> CrawlSummary:
        """Replace the stored statistics of a source with crawled ones.

        Args:
            name (str): The source name, e.g. `synergy`.
            statistics (MarketStatistics): The crawled statistics.
            status (CrawlStatus): The status of the crawl (`imported` for an import).

        Returns:
            CrawlSummary: What the crawl wrote.

        Raises:
            StorageLockError: If the statistics of the source are being written by another crawl.
            StorageWriteError: If the statistics cannot be written.
        """
        label = f"{name} statistics"
        table = self.table
        try:
            async with self.database.connect() as connection, connection.begin():
                if not await self.lock.acquire_for_transaction(connection, DatasetKind.STATISTICS, name):
                    self.logger.error("The %s are already being written by another crawl.", label)
                    raise StorageLockError(DatasetKind.STATISTICS.value, name)
                crawl_id = await self.recorder.start(
                    connection,
                    DatasetKind.STATISTICS,
                    name,
                    statistics.crawled_at,
                    status=status,
                    label=statistics.source,
                )
                rows = [
                    self.mapper.to_row(report, name, position, crawl_id)
                    for position, report in enumerate(statistics.reports)
                ]
                added = 0
                if rows:
                    statement = upsert(table)
                    keys = [table.c.source, table.c.period, table.c.region, table.c.segment]
                    columns = [column for column in rows[0] if column not in {key.name for key in keys}]
                    result = await connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=keys,
                            set_={column: statement.excluded[column] for column in columns},
                        ).returning(literal_column("xmax = 0", Boolean)),
                        rows,
                    )
                    added = sum(1 for inserted in result.scalars().all() if inserted)
                removed = await connection.execute(
                    delete(table).where(table.c.source == name, table.c.crawl_id != crawl_id)
                )
                summary = CrawlSummary(
                    crawl_id=crawl_id,
                    kind=DatasetKind.STATISTICS,
                    dataset=name,
                    status=status,
                    started_at=statistics.crawled_at,
                    finished_at=datetime.now(UTC),
                    found=len(rows),
                    added=added,
                    updated=len(rows) - added,
                    deleted=removed.rowcount,
                    size=len(rows),
                )
                await self.recorder.finish(connection, summary, len(rows) - added + removed.rowcount, "")
        except SQLAlchemyError as e:
            self.logger.error("The %s cannot be written: %s", label, e)
            raise StorageWriteError(label, str(e)) from e
        return summary

    async def load(self, name: str) -> Optional[MarketStatistics]:
        """Read the statistics of a source.

        Args:
            name (str): The source name, e.g. `synergy`.

        Returns:
            Optional[MarketStatistics]: The statistics, its reports in their crawled order,
                `None` when never crawled.

        Raises:
            StorageReadError: If the statistics cannot be read.
        """
        try:
            async with self.database.connect() as connection:
                stamp = await self.datasets.read(connection, DatasetKind.STATISTICS, name)
                if stamp is None:
                    self.logger.debug("No %s statistics stored.", name)
                    return None
                result = await connection.execute(
                    select(*self.mapper.columns()).where(self.table.c.source == name).order_by(self.table.c.position)
                )
                reports = [self.mapper.to_model(row) for row in result.mappings()]
        except SQLAlchemyError as e:
            self.logger.error("The %s statistics cannot be read: %s", name, e)
            raise StorageReadError(f"{name} statistics", str(e)) from e
        self.logger.info("%d %s market reports read.", len(reports), name)
        return MarketStatistics(source=stamp.label or name, crawled_at=stamp.crawled_at, reports=reports)
