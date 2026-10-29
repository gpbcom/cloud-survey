from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence

# Third Party Imports.
from sqlalchemy import Table, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.cloud.prices.stored.price_source import PriceSource
from storage.engine.database import Database
from storage.exception import StorageWriteError
from storage.mappers.row_store import RowStore
from storage.tables.base import Base
from storage.tables.prices.price_source_row import PriceSourceRow


class PriceSourceRepository:
    """Create, read, update, delete and list the price sources as last read (the incremental price crawls).

    Attributes:
        database (Database): The open database.
        table (Table): The `price_sources` table.
        rows (RowStore[PriceSource]): The single-row operations.
        logger (Logger): The repository logger.
    """

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.database = database
        self.table: Table = Base.metadata.tables[PriceSourceRow.__tablename__]
        self.rows = RowStore(database, self.table, PriceSource, "price source", self.logger)
        self.logger.debug("Repository of the price sources ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: PriceSource) -> PriceSource:
        """Insert a price source.

        Args:
            value (PriceSource): The source.

        Returns:
            PriceSource: The source, as stored.

        Raises:
            StorageWriteError: If it exists or cannot be written.
        """
        self.logger.debug("Creating a price source.")
        created = await self.rows.create(value)
        self.logger.info("Price source created.")
        return created

    async def read(self, provider: str, source_key: str) -> Optional[PriceSource]:
        """Read a price source.

        Args:
            provider (str): The provider.
            source_key (str): The source.

        Returns:
            Optional[PriceSource]: The source, `None` when it was never read.

        Raises:
            StorageReadError: If it cannot be read.
        """
        self.logger.debug("Reading the price source %s %s.", provider, source_key)
        found = await self.rows.read({"provider": provider, "source_key": source_key})
        if found is None:
            self.logger.info("The price source %s %s was never read: it is read whole.", provider, source_key)
        return found

    async def update(self, value: PriceSource) -> bool:
        """Replace a price source.

        Args:
            value (PriceSource): The source.

        Returns:
            bool: Whether it existed.

        Raises:
            StorageWriteError: If it cannot be written.
        """
        self.logger.debug("Updating the price source %s %s.", value.provider.value, value.source_key)
        updated = await self.rows.update(value)
        if updated:
            self.logger.info("Price source %s %s updated.", value.provider.value, value.source_key)
        else:
            self.logger.warning("No price source %s %s to update.", value.provider.value, value.source_key)
        return updated

    async def delete(self, provider: str, source_key: str) -> bool:
        """Remove a price source (its next crawl reads it whole again).

        Args:
            provider (str): The provider.
            source_key (str): The source.

        Returns:
            bool: Whether there was one.

        Raises:
            StorageWriteError: If it cannot be removed.
        """
        self.logger.debug("Deleting the price source %s %s.", provider, source_key)
        deleted = await self.rows.delete({"provider": provider, "source_key": source_key})
        if deleted:
            self.logger.info("Price source %s %s deleted.", provider, source_key)
        else:
            self.logger.warning("No price source %s %s to delete.", provider, source_key)
        return deleted

    async def list(
        self, providers: Optional[Sequence[str]] = None, offset: int = 0, limit: Optional[int] = None
    ) -> List[PriceSource]:
        """List the price sources.

        Args:
            providers (Optional[Sequence[str]]): Only these providers, every one when `None` or empty.
            offset (int): The rows skipped.
            limit (Optional[int]): The most rows returned, every one when `None`.

        Returns:
            List[PriceSource]: The sources.

        Raises:
            StorageReadError: If they cannot be read.
        """
        self.logger.debug("Listing the price sources from %d.", offset)
        listed = await self.rows.list({"provider": list(providers or [])}, offset=offset, limit=limit)
        self.logger.debug("%d price sources listed.", len(listed))
        return listed

    async def versions(self, provider: str) -> Dict[str, PriceSource]:
        """Read the sources of a provider as last read, to skip those unchanged.

        Args:
            provider (str): The provider.

        Returns:
            Dict[str, PriceSource]: Each source, by its key.

        Raises:
            StorageReadError: If they cannot be read.
        """
        return {source.source_key: source for source in await self.list([provider])}

    async def upsert(self, sources: Sequence[PriceSource]) -> int:
        """Write the sources a crawl read, replacing their former state.

        Args:
            sources (Sequence[PriceSource]): The sources.

        Returns:
            int: The sources written.

        Raises:
            StorageWriteError: If they cannot be written.
        """
        if not sources:
            return 0
        rows = [
            {**source.model_dump(mode="json", exclude={"fetched_at"}), "provider": source.provider.value}
            for source in sources
        ]
        statement = insert(self.table).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=[self.table.c.provider, self.table.c.source_key],
            set_={
                "version": statement.excluded.version,
                "etag": statement.excluded.etag,
                "last_modified": statement.excluded.last_modified,
                "rows": statement.excluded.rows,
                "status": statement.excluded.status,
                "fetched_at": func.now(),
            },
        )
        try:
            async with self.database.connect() as connection, connection.begin():
                await connection.execute(statement)
        except SQLAlchemyError as e:
            self.logger.error("%d price sources cannot be written: %s", len(rows), e)
            raise StorageWriteError("price sources", str(e)) from e
        self.logger.info("%d price sources written.", len(rows))
        return len(rows)
