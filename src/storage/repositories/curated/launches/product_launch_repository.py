from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional, Sequence, Tuple

# Third Party Imports.
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.curated.enums import CuratedFile
from models.curated.launches.product_launch import ProductLaunch
from storage.engine.database import Database
from storage.repositories.curated.curated_rows import CuratedRows
from storage.repositories.curated.curated_state_repository import CuratedStateRepository
from storage.tables.base import Base
from storage.tables.curated.launches.product_launch_row import ProductLaunchRow


class ProductLaunchRepository:
    """Read and write the curated launches of the cloud products (their date and source, or why they have none).

    Attributes:
        database (Database): The open database.
        table (Table): The `product_launches` table.
        rows (CuratedRows[ProductLaunch]): The operations on the table.
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
        self.table: Table = Base.metadata.tables[ProductLaunchRow.__tablename__]
        self.rows = CuratedRows(
            database,
            self.table,
            ProductLaunch,
            "product launch",
            {"": CuratedFile.LAUNCHES},
            ["position"],
            state,
            file_column=None,
            logger=self.logger,
        )
        self.logger.debug("Repository of the product launches ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: ProductLaunch) -> ProductLaunch:
        """Insert one product launch.

        Args:
            value (ProductLaunch): The product launch.

        Returns:
            ProductLaunch: The product launch, as stored.

        Raises:
            StorageWriteError: If it exists or cannot be written.
        """
        return await self.rows.create(value)

    async def read(self, crawler: str, name: str) -> Optional[ProductLaunch]:
        """Read one product launch.

        Args:
            crawler (str): The cloud crawler.
            name (str): The product name.

        Returns:
            Optional[ProductLaunch]: The product launch, `None` when there is none.

        Raises:
            StorageReadError: If it cannot be read.
        """
        return await self.rows.read({"crawler": crawler, "name": name})

    async def update(self, value: ProductLaunch) -> bool:
        """Replace one product launch (that of the same key).

        Args:
            value (ProductLaunch): The product launch.

        Returns:
            bool: Whether it existed (none is created otherwise).

        Raises:
            StorageWriteError: If it cannot be written.
        """
        return await self.rows.update(value)

    async def delete(self, crawler: str, name: str) -> bool:
        """Remove one product launch.

        Args:
            crawler (str): The cloud crawler.
            name (str): The product name.

        Returns:
            bool: Whether there was one.

        Raises:
            StorageWriteError: If it cannot be removed.
        """
        return await self.rows.delete({"crawler": crawler, "name": name})

    async def list(self, crawlers: Optional[Sequence[str]] = None) -> List[ProductLaunch]:
        """List the product launches, in their order.

        Args:
            crawlers (Optional[Sequence[str]]): Only these crawlers, every one when `None` or empty.

        Returns:
            List[ProductLaunch]: The product launches.

        Raises:
            StorageReadError: If they cannot be read.
        """
        return await self.rows.list({"crawler": [item for item in crawlers or []]})

    async def upsert(
        self,
        values: Sequence[ProductLaunch],
        replace_edited: bool = False,
        connection: Optional[AsyncConnection] = None,
    ) -> Tuple[int, int]:
        """Write product launches, replacing those of the same key, the ones a person changed kept unless asked.

        Args:
            values (Sequence[ProductLaunch]): The product launches.
            replace_edited (bool): Whether the ones a person changed are replaced too.
            connection (Optional[AsyncConnection]): A connection in a transaction to write on (a seed).

        Returns:
            Tuple[int, int]: The rows written, then the rows kept because a person changed them.

        Raises:
            StorageWriteError: If they cannot be written.
        """
        return await self.rows.upsert(values, replace_edited, connection)
