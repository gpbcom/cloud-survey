from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional, Sequence, Tuple

# Third Party Imports.
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncConnection

from models.curated.companies.company_profile import CompanyProfile

# First Party Imports.
from models.curated.enums import CuratedFile
from storage.engine.database import Database
from storage.repositories.curated.curated_rows import CuratedRows
from storage.repositories.curated.curated_state_repository import CuratedStateRepository
from storage.tables.base import Base
from storage.tables.curated.companies.company_profile_row import CompanyProfileRow


class CompanyProfileRepository:
    """Read and write the companies crawled: their catalogue entry, without their identifiers.

    Attributes:
        database (Database): The open database.
        table (Table): The `company_profiles` table.
        rows (CuratedRows[CompanyProfile]): The operations on the table.
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
        self.table: Table = Base.metadata.tables[CompanyProfileRow.__tablename__]
        self.rows = CuratedRows(
            database,
            self.table,
            CompanyProfile,
            "company profile",
            {"": CuratedFile.COMPANIES},
            ["position"],
            state,
            file_column=None,
            logger=self.logger,
        )
        self.logger.debug("Repository of the company profiles ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: CompanyProfile) -> CompanyProfile:
        """Insert one company profile.

        Args:
            value (CompanyProfile): The company profile.

        Returns:
            CompanyProfile: The company profile, as stored.

        Raises:
            StorageWriteError: If it exists or cannot be written.
        """
        return await self.rows.create(value)

    async def read(self, company: str) -> Optional[CompanyProfile]:
        """Read one company profile.

        Args:
            company (str): The company key.

        Returns:
            Optional[CompanyProfile]: The company profile, `None` when there is none.

        Raises:
            StorageReadError: If it cannot be read.
        """
        return await self.rows.read({"company": company})

    async def update(self, value: CompanyProfile) -> bool:
        """Replace one company profile (that of the same key).

        Args:
            value (CompanyProfile): The company profile.

        Returns:
            bool: Whether it existed (none is created otherwise).

        Raises:
            StorageWriteError: If it cannot be written.
        """
        return await self.rows.update(value)

    async def delete(self, company: str) -> bool:
        """Remove one company profile.

        Args:
            company (str): The company key.

        Returns:
            bool: Whether there was one.

        Raises:
            StorageWriteError: If it cannot be removed.
        """
        return await self.rows.delete({"company": company})

    async def list(self) -> List[CompanyProfile]:
        """List the company profiles, in their order.

        Returns:
            List[CompanyProfile]: The company profiles.

        Raises:
            StorageReadError: If they cannot be read.
        """
        return await self.rows.list()

    async def upsert(
        self,
        values: Sequence[CompanyProfile],
        replace_edited: bool = False,
        connection: Optional[AsyncConnection] = None,
    ) -> Tuple[int, int]:
        """Write company profiles, replacing those of the same key, the ones a person changed kept unless asked.

        Args:
            values (Sequence[CompanyProfile]): The company profiles.
            replace_edited (bool): Whether the ones a person changed are replaced too.
            connection (Optional[AsyncConnection]): A connection in a transaction to write on (a seed).

        Returns:
            Tuple[int, int]: The rows written, then the rows kept because a person changed them.

        Raises:
            StorageWriteError: If they cannot be written.
        """
        return await self.rows.upsert(values, replace_edited, connection)
