from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional, Sequence, Tuple

# Third Party Imports.
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.curated.enums import CuratedFile
from models.curated.figures.reported_year_record import ReportedYearRecord
from storage.engine.database import Database
from storage.repositories.curated.curated_rows import CuratedRows
from storage.repositories.curated.curated_state_repository import CuratedStateRepository
from storage.tables.base import Base
from storage.tables.curated.figures.reported_year_row import ReportedYearRow


class ReportedYearRepository:
    """Read and write the fiscal years researched by hand.

    Attributes:
        database (Database): The open database.
        table (Table): The `reported_years` table.
        rows (CuratedRows[ReportedYearRecord]): The operations on the table.
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
        self.table: Table = Base.metadata.tables[ReportedYearRow.__tablename__]
        self.rows = CuratedRows(
            database,
            self.table,
            ReportedYearRecord,
            "researched year",
            {"": CuratedFile.FIGURES},
            ["company", "position"],
            state,
            file_column=None,
            logger=self.logger,
        )
        self.logger.debug("Repository of the researched years ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: ReportedYearRecord) -> ReportedYearRecord:
        """Insert one researched year.

        Args:
            value (ReportedYearRecord): The researched year.

        Returns:
            ReportedYearRecord: The researched year, as stored.

        Raises:
            StorageWriteError: If it exists or cannot be written.
        """
        return await self.rows.create(value)

    async def read(self, company: str, fiscal_year: int) -> Optional[ReportedYearRecord]:
        """Read one researched year.

        Args:
            company (str): The company key.
            fiscal_year (int): The fiscal year.

        Returns:
            Optional[ReportedYearRecord]: The researched year, `None` when there is none.

        Raises:
            StorageReadError: If it cannot be read.
        """
        return await self.rows.read({"company": company, "fiscal_year": fiscal_year})

    async def update(self, value: ReportedYearRecord) -> bool:
        """Replace one researched year (that of the same key).

        Args:
            value (ReportedYearRecord): The researched year.

        Returns:
            bool: Whether it existed (none is created otherwise).

        Raises:
            StorageWriteError: If it cannot be written.
        """
        return await self.rows.update(value)

    async def delete(self, company: str, fiscal_year: int) -> bool:
        """Remove one researched year.

        Args:
            company (str): The company key.
            fiscal_year (int): The fiscal year.

        Returns:
            bool: Whether there was one.

        Raises:
            StorageWriteError: If it cannot be removed.
        """
        return await self.rows.delete({"company": company, "fiscal_year": fiscal_year})

    async def list(self, companies: Optional[Sequence[str]] = None) -> List[ReportedYearRecord]:
        """List the researched years, in their order.

        Args:
            companies (Optional[Sequence[str]]): Only these companies, every one when `None` or empty.

        Returns:
            List[ReportedYearRecord]: The researched years.

        Raises:
            StorageReadError: If they cannot be read.
        """
        return await self.rows.list({"company": [item for item in companies or []]})

    async def upsert(
        self,
        values: Sequence[ReportedYearRecord],
        replace_edited: bool = False,
        connection: Optional[AsyncConnection] = None,
    ) -> Tuple[int, int]:
        """Write researched years, replacing those of the same key, the ones a person changed kept unless asked.

        Args:
            values (Sequence[ReportedYearRecord]): The researched years.
            replace_edited (bool): Whether the ones a person changed are replaced too.
            connection (Optional[AsyncConnection]): A connection in a transaction to write on (a seed).

        Returns:
            Tuple[int, int]: The rows written, then the rows kept because a person changed them.

        Raises:
            StorageWriteError: If they cannot be written.
        """
        return await self.rows.upsert(values, replace_edited, connection)
