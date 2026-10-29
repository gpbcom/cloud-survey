from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional, Sequence, Tuple

# Third Party Imports.
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncConnection

from models.curated.companies.company_identifier import CompanyIdentifier

# First Party Imports.
from models.curated.enums import CuratedFile, IdentifierKind, IdentifierStatus
from storage.engine.database import Database
from storage.repositories.curated.curated_rows import CuratedRows
from storage.repositories.curated.curated_state_repository import CuratedStateRepository
from storage.tables.base import Base
from storage.tables.curated.companies.company_identifier_row import CompanyIdentifierRow


class CompanyIdentifierRepository:
    """Read and write the identifiers of the companies at their sources (SEC, OpenAlex, Google Patents).

    Attributes:
        database (Database): The open database.
        table (Table): The `company_identifiers` table.
        rows (CuratedRows[CompanyIdentifier]): The operations on the table.
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
        self.table: Table = Base.metadata.tables[CompanyIdentifierRow.__tablename__]
        self.rows = CuratedRows(
            database,
            self.table,
            CompanyIdentifier,
            "company identifier",
            {"": CuratedFile.COMPANIES},
            ["company", "kind", "position"],
            state,
            file_column=None,
            logger=self.logger,
        )
        self.logger.debug("Repository of the company identifiers ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: CompanyIdentifier) -> CompanyIdentifier:
        """Insert one company identifier.

        Args:
            value (CompanyIdentifier): The company identifier.

        Returns:
            CompanyIdentifier: The company identifier, as stored.

        Raises:
            StorageWriteError: If it exists or cannot be written.
        """
        return await self.rows.create(value)

    async def read(self, company: str, kind: IdentifierKind, value: str) -> Optional[CompanyIdentifier]:
        """Read one company identifier.

        Args:
            company (str): The company key.
            kind (IdentifierKind): What it identifies the company at.
            value (str): The identifier.

        Returns:
            Optional[CompanyIdentifier]: The company identifier, `None` when there is none.

        Raises:
            StorageReadError: If it cannot be read.
        """
        return await self.rows.read({"company": company, "kind": kind.value, "value": value})

    async def update(self, value: CompanyIdentifier) -> bool:
        """Replace one company identifier (that of the same key).

        Args:
            value (CompanyIdentifier): The company identifier.

        Returns:
            bool: Whether it existed (none is created otherwise).

        Raises:
            StorageWriteError: If it cannot be written.
        """
        return await self.rows.update(value)

    async def delete(self, company: str, kind: IdentifierKind, value: str) -> bool:
        """Remove one company identifier.

        Args:
            company (str): The company key.
            kind (IdentifierKind): What it identifies the company at.
            value (str): The identifier.

        Returns:
            bool: Whether there was one.

        Raises:
            StorageWriteError: If it cannot be removed.
        """
        return await self.rows.delete({"company": company, "kind": kind.value, "value": value})

    async def list(
        self, companies: Optional[Sequence[str]] = None, statuses: Optional[Sequence[IdentifierStatus]] = None
    ) -> List[CompanyIdentifier]:
        """List the company identifiers, in their order.

        Args:
            companies (Optional[Sequence[str]]): Only these companies, every one when `None` or empty.
            statuses (Optional[Sequence[IdentifierStatus]]): Only these statuses, every one when `None` or empty.

        Returns:
            List[CompanyIdentifier]: The company identifiers.

        Raises:
            StorageReadError: If they cannot be read.
        """
        return await self.rows.list(
            {"company": [item for item in companies or []], "status": [item.value for item in statuses or []]}
        )

    async def upsert(
        self,
        values: Sequence[CompanyIdentifier],
        replace_edited: bool = False,
        connection: Optional[AsyncConnection] = None,
    ) -> Tuple[int, int]:
        """Write company identifiers, replacing those of the same key, the ones a person changed kept unless asked.

        Args:
            values (Sequence[CompanyIdentifier]): The company identifiers.
            replace_edited (bool): Whether the ones a person changed are replaced too.
            connection (Optional[AsyncConnection]): A connection in a transaction to write on (a seed).

        Returns:
            Tuple[int, int]: The rows written, then the rows kept because a person changed them.

        Raises:
            StorageWriteError: If they cannot be written.
        """
        return await self.rows.upsert(values, replace_edited, connection)
