from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional, Sequence, Tuple

# Third Party Imports.
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.curated.enums import CuratedFile
from models.curated.figures.reported_event_record import ReportedEventRecord
from storage.engine.database import Database
from storage.repositories.curated.curated_rows import CuratedRows
from storage.repositories.curated.curated_state_repository import CuratedStateRepository
from storage.tables.base import Base
from storage.tables.curated.figures.reported_event_row import ReportedEventRow


class ReportedEventRepository:
    """Read and write the dated figures researched by hand (the private companies' funding rounds and run rates).

    Attributes:
        database (Database): The open database.
        table (Table): The `reported_events` table.
        rows (CuratedRows[ReportedEventRecord]): The operations on the table.
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
        self.table: Table = Base.metadata.tables[ReportedEventRow.__tablename__]
        self.rows = CuratedRows(
            database,
            self.table,
            ReportedEventRecord,
            "researched event",
            {"": CuratedFile.FIGURES},
            ["company", "position"],
            state,
            file_column=None,
            logger=self.logger,
        )
        self.logger.debug("Repository of the researched events ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: ReportedEventRecord) -> ReportedEventRecord:
        """Insert one researched event.

        Args:
            value (ReportedEventRecord): The researched event.

        Returns:
            ReportedEventRecord: The researched event, as stored.

        Raises:
            StorageWriteError: If it exists or cannot be written.
        """
        return await self.rows.create(value)

    async def read(self, company: str, position: int) -> Optional[ReportedEventRecord]:
        """Read one researched event.

        Args:
            company (str): The company key.
            position (int): Its rank among the company's events.

        Returns:
            Optional[ReportedEventRecord]: The researched event, `None` when there is none.

        Raises:
            StorageReadError: If it cannot be read.
        """
        return await self.rows.read({"company": company, "position": position})

    async def update(self, value: ReportedEventRecord) -> bool:
        """Replace one researched event (that of the same key).

        Args:
            value (ReportedEventRecord): The researched event.

        Returns:
            bool: Whether it existed (none is created otherwise).

        Raises:
            StorageWriteError: If it cannot be written.
        """
        return await self.rows.update(value)

    async def delete(self, company: str, position: int) -> bool:
        """Remove one researched event.

        Args:
            company (str): The company key.
            position (int): Its rank among the company's events.

        Returns:
            bool: Whether there was one.

        Raises:
            StorageWriteError: If it cannot be removed.
        """
        return await self.rows.delete({"company": company, "position": position})

    async def list(self, companies: Optional[Sequence[str]] = None) -> List[ReportedEventRecord]:
        """List the researched events, in their order.

        Args:
            companies (Optional[Sequence[str]]): Only these companies, every one when `None` or empty.

        Returns:
            List[ReportedEventRecord]: The researched events.

        Raises:
            StorageReadError: If they cannot be read.
        """
        return await self.rows.list({"company": [item for item in companies or []]})

    async def upsert(
        self,
        values: Sequence[ReportedEventRecord],
        replace_edited: bool = False,
        connection: Optional[AsyncConnection] = None,
    ) -> Tuple[int, int]:
        """Write researched events, replacing those of the same key, the ones a person changed kept unless asked.

        Args:
            values (Sequence[ReportedEventRecord]): The researched events.
            replace_edited (bool): Whether the ones a person changed are replaced too.
            connection (Optional[AsyncConnection]): A connection in a transaction to write on (a seed).

        Returns:
            Tuple[int, int]: The rows written, then the rows kept because a person changed them.

        Raises:
            StorageWriteError: If they cannot be written.
        """
        return await self.rows.upsert(values, replace_edited, connection)
