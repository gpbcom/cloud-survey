from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional, Sequence, Tuple

# Third Party Imports.
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.curated.enums import CuratedFile
from models.curated.figures.reported_company_record import ReportedCompanyRecord
from storage.engine.database import Database
from storage.repositories.curated.curated_rows import CuratedRows
from storage.repositories.curated.curated_state_repository import CuratedStateRepository
from storage.tables.base import Base
from storage.tables.curated.figures.reported_company_row import ReportedCompanyRow


class ReportedCompanyRepository:
    """Read and write the companies whose figures were researched by hand (currency, fiscal year end, scale).

    Attributes:
        database (Database): The open database.
        table (Table): The `reported_companies` table.
        rows (CuratedRows[ReportedCompanyRecord]): The operations on the table.
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
        self.table: Table = Base.metadata.tables[ReportedCompanyRow.__tablename__]
        self.rows = CuratedRows(
            database,
            self.table,
            ReportedCompanyRecord,
            "researched company",
            {"": CuratedFile.FIGURES},
            ["position"],
            state,
            file_column=None,
            logger=self.logger,
        )
        self.logger.debug("Repository of the researched companies ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: ReportedCompanyRecord) -> ReportedCompanyRecord:
        """Insert one researched company.

        Args:
            value (ReportedCompanyRecord): The researched company.

        Returns:
            ReportedCompanyRecord: The researched company, as stored.

        Raises:
            StorageWriteError: If it exists or cannot be written.
        """
        return await self.rows.create(value)

    async def read(self, company: str) -> Optional[ReportedCompanyRecord]:
        """Read one researched company.

        Args:
            company (str): The company key.

        Returns:
            Optional[ReportedCompanyRecord]: The researched company, `None` when there is none.

        Raises:
            StorageReadError: If it cannot be read.
        """
        return await self.rows.read({"company": company})

    async def update(self, value: ReportedCompanyRecord) -> bool:
        """Replace one researched company (that of the same key).

        Args:
            value (ReportedCompanyRecord): The researched company.

        Returns:
            bool: Whether it existed (none is created otherwise).

        Raises:
            StorageWriteError: If it cannot be written.
        """
        return await self.rows.update(value)

    async def delete(self, company: str) -> bool:
        """Remove one researched company.

        Args:
            company (str): The company key.

        Returns:
            bool: Whether there was one.

        Raises:
            StorageWriteError: If it cannot be removed.
        """
        return await self.rows.delete({"company": company})

    async def list(self) -> List[ReportedCompanyRecord]:
        """List the researched companies, in their order.

        Returns:
            List[ReportedCompanyRecord]: The researched companies.

        Raises:
            StorageReadError: If they cannot be read.
        """
        return await self.rows.list()

    async def upsert(
        self,
        values: Sequence[ReportedCompanyRecord],
        replace_edited: bool = False,
        connection: Optional[AsyncConnection] = None,
    ) -> Tuple[int, int]:
        """Write researched companies, replacing those of the same key, the ones a person changed kept unless asked.

        Args:
            values (Sequence[ReportedCompanyRecord]): The researched companies.
            replace_edited (bool): Whether the ones a person changed are replaced too.
            connection (Optional[AsyncConnection]): A connection in a transaction to write on (a seed).

        Returns:
            Tuple[int, int]: The rows written, then the rows kept because a person changed them.

        Raises:
            StorageWriteError: If they cannot be written.
        """
        return await self.rows.upsert(values, replace_edited, connection)
