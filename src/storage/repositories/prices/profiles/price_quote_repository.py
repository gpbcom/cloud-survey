from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional, Sequence

# Third Party Imports.
from sqlalchemy import Table, delete
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.cloud.prices.profiles.price_quote import PriceQuote
from storage.engine.database import Database
from storage.exception import StorageWriteError
from storage.mappers.row_store import RowStore
from storage.tables.base import Base
from storage.tables.prices.price_quote_row import PriceQuoteRow


class PriceQuoteRepository:
    """Create, read, update, delete and list the cached monthly costs of the usage profiles.

    Attributes:
        database (Database): The open database.
        table (Table): The `price_quotes` table.
        rows (RowStore[PriceQuote]): The single-row operations.
        logger (Logger): The repository logger.

    Notes:
        A quote is a cache: a price crawl or an edit of a price or a profile clears the quotes it may change, and
        the explorer computes them again when they are shown.
    """

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.database = database
        self.table: Table = Base.metadata.tables[PriceQuoteRow.__tablename__]
        self.rows = RowStore(database, self.table, PriceQuote, "price quote", self.logger)
        self.logger.debug("Repository of the price quotes ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: PriceQuote) -> PriceQuote:
        """Insert a quote.

        Args:
            value (PriceQuote): The quote.

        Returns:
            PriceQuote: The quote, as stored.

        Raises:
            StorageWriteError: If it exists or cannot be written.
        """
        self.logger.debug("Creating a price quote.")
        created = await self.rows.create(value)
        self.logger.info("Price quote created.")
        return created

    async def read(self, profile: str, provider: str, region: str, options: str) -> Optional[PriceQuote]:
        """Read a quote.

        Args:
            profile (str): The usage profile.
            provider (str): The provider.
            region (str): The region.
            options (str): The options of the costing.

        Returns:
            Optional[PriceQuote]: The quote, `None` when it was not computed.

        Raises:
            StorageReadError: If it cannot be read.
        """
        self.logger.debug("Reading the price quote %s %s %s %s.", profile, provider, region, options)
        found = await self.rows.read({"profile": profile, "provider": provider, "region": region, "options": options})
        if found is None:
            self.logger.warning("No price quote %s %s %s %s.", profile, provider, region, options)
        return found

    async def update(self, value: PriceQuote) -> bool:
        """Replace a quote.

        Args:
            value (PriceQuote): The quote.

        Returns:
            bool: Whether it existed.

        Raises:
            StorageWriteError: If it cannot be written.
        """
        self.logger.debug(
            "Updating the price quote %s %s %s %s.", value.profile, value.provider.value, value.region, value.options
        )
        updated = await self.rows.update(value)
        if updated:
            self.logger.info(
                "Price quote %s %s %s %s updated.", value.profile, value.provider.value, value.region, value.options
            )
        else:
            self.logger.warning(
                "No price quote %s %s %s %s to update.",
                value.profile,
                value.provider.value,
                value.region,
                value.options,
            )
        return updated

    async def delete(self, profile: str, provider: str, region: str, options: str) -> bool:
        """Remove a quote.

        Args:
            profile (str): The usage profile.
            provider (str): The provider.
            region (str): The region.
            options (str): The options of the costing.

        Returns:
            bool: Whether there was one.

        Raises:
            StorageWriteError: If it cannot be removed.
        """
        self.logger.debug("Deleting the price quote %s %s %s %s.", profile, provider, region, options)
        deleted = await self.rows.delete(
            {"profile": profile, "provider": provider, "region": region, "options": options}
        )
        if deleted:
            self.logger.info("Price quote %s %s %s %s deleted.", profile, provider, region, options)
        else:
            self.logger.warning("No price quote %s %s %s %s to delete.", profile, provider, region, options)
        return deleted

    async def list(
        self, profiles: Optional[Sequence[str]] = None, offset: int = 0, limit: Optional[int] = None
    ) -> List[PriceQuote]:
        """List the quotes.

        Args:
            profiles (Optional[Sequence[str]]): Only these profiles, every one when `None` or empty.
            offset (int): The rows skipped.
            limit (Optional[int]): The most rows returned, every one when `None`.

        Returns:
            List[PriceQuote]: The quotes.

        Raises:
            StorageReadError: If they cannot be read.
        """
        self.logger.debug("Listing the price quotes from %d.", offset)
        listed = await self.rows.list({"profile": list(profiles or [])}, offset=offset, limit=limit)
        self.logger.debug("%d price quotes listed.", len(listed))
        return listed

    async def clear(self, profile: Optional[str] = None) -> int:
        """Remove the cached quotes of a profile, or every one (after a price crawl or a price edit).

        Args:
            profile (Optional[str]): The profile, every one when `None`.

        Returns:
            int: The quotes removed.

        Raises:
            StorageWriteError: If they cannot be removed.
        """
        statement = delete(self.table)
        if profile is not None:
            statement = statement.where(self.table.c.profile == profile)
        try:
            async with self.database.connect() as connection, connection.begin():
                removed = (await connection.execute(statement)).rowcount
        except SQLAlchemyError as e:
            self.logger.error("The price quotes cannot be cleared: %s", e)
            raise StorageWriteError("price quotes", str(e)) from e
        self.logger.info("%d price quotes cleared.", removed)
        return removed
