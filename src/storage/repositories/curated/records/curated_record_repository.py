from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional, Sequence, Tuple

# Third Party Imports.
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.curated.enums import CuratedDataset, CuratedFile
from models.curated.records.curated_record import CuratedRecord
from storage.engine.database import Database
from storage.repositories.curated.curated_rows import CuratedRows
from storage.repositories.curated.curated_state_repository import CuratedStateRepository
from storage.tables.base import Base
from storage.tables.curated.records.curated_record_row import CuratedRecordRow


class CuratedRecordRepository:
    """Read and write the curated records: the sections of the chronology and of the markets catalogue.

    Attributes:
        database (Database): The open database.
        table (Table): The `curated_records` table.
        rows (CuratedRows[CuratedRecord]): The operations on the table.
        logger (Logger): The repository logger.
    """

    def __init__(self, database: Database, state: CuratedStateRepository, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            state (CuratedStateRepository): The revisions of the bundle files, incremented by every write.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.logger = logger if logger else getLogger(__name__)
        self.table: Table = Base.metadata.tables[CuratedRecordRow.__tablename__]
        self.rows = CuratedRows(
            database,
            self.table,
            CuratedRecord,
            "curated record",
            {"chronology-": CuratedFile.CHRONOLOGY, "markets-": CuratedFile.MARKETS, "launch-": CuratedFile.LAUNCHES},
            ["dataset", "position"],
            state,
            file_column="dataset",
            logger=self.logger,
        )
        self.logger.debug("Repository of the curated records ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: CuratedRecord) -> CuratedRecord:
        """Insert one curated record.

        Args:
            value (CuratedRecord): The curated record.

        Returns:
            CuratedRecord: The curated record, as stored.

        Raises:
            StorageWriteError: If it exists or cannot be written.
        """
        return await self.rows.create(value)

    async def read(self, dataset: CuratedDataset, key: str) -> Optional[CuratedRecord]:
        """Read one curated record.

        Args:
            dataset (CuratedDataset): The section.
            key (str): The natural key of the entry.

        Returns:
            Optional[CuratedRecord]: The curated record, `None` when there is none.

        Raises:
            StorageReadError: If it cannot be read.
        """
        return await self.rows.read({"dataset": dataset.value, "key": key})

    async def update(self, value: CuratedRecord) -> bool:
        """Replace one curated record (that of the same key).

        Args:
            value (CuratedRecord): The curated record.

        Returns:
            bool: Whether it existed (none is created otherwise).

        Raises:
            StorageWriteError: If it cannot be written.
        """
        return await self.rows.update(value)

    async def delete(self, dataset: CuratedDataset, key: str) -> bool:
        """Remove one curated record.

        Args:
            dataset (CuratedDataset): The section.
            key (str): The natural key of the entry.

        Returns:
            bool: Whether there was one.

        Raises:
            StorageWriteError: If it cannot be removed.
        """
        return await self.rows.delete({"dataset": dataset.value, "key": key})

    async def list(self, datasets: Optional[Sequence[CuratedDataset]] = None) -> List[CuratedRecord]:
        """List the curated records, in their order.

        Args:
            datasets (Optional[Sequence[CuratedDataset]]): Only these sections, every one when `None` or empty.

        Returns:
            List[CuratedRecord]: The curated records.

        Raises:
            StorageReadError: If they cannot be read.
        """
        return await self.rows.list({"dataset": [item.value for item in datasets or []]})

    async def upsert(
        self,
        values: Sequence[CuratedRecord],
        replace_edited: bool = False,
        connection: Optional[AsyncConnection] = None,
    ) -> Tuple[int, int]:
        """Write curated records, replacing those of the same key, the ones a person changed kept unless asked.

        Args:
            values (Sequence[CuratedRecord]): The curated records.
            replace_edited (bool): Whether the ones a person changed are replaced too.
            connection (Optional[AsyncConnection]): A connection in a transaction to write on (a seed).

        Returns:
            Tuple[int, int]: The rows written, then the rows kept because a person changed them.

        Raises:
            StorageWriteError: If they cannot be written.
        """
        return await self.rows.upsert(values, replace_edited, connection)
