from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional

# Third Party Imports.
from sqlalchemy import Table

# First Party Imports.
from models.cloud.prices.profiles.usage_profile import UsageProfile
from storage.engine.database import Database
from storage.mappers.row_store import RowStore
from storage.tables.base import Base
from storage.tables.prices.usage_profile_row import UsageProfileRow


class UsageProfileRepository:
    """Create, read, update, delete and list the workloads whose cost is compared across the providers.

    Attributes:
        database (Database): The open database.
        table (Table): The `usage_profiles` table.
        rows (RowStore[UsageProfile]): The single-row operations.
        logger (Logger): The repository logger.

    Notes:
        Removing a profile removes its cached quotes (a foreign key on cascade).
    """

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.database = database
        self.table: Table = Base.metadata.tables[UsageProfileRow.__tablename__]
        self.rows = RowStore(database, self.table, UsageProfile, "usage profile", self.logger)
        self.logger.debug("Repository of the usage profiles ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: UsageProfile) -> UsageProfile:
        """Insert a usage profile.

        Args:
            value (UsageProfile): The profile.

        Returns:
            UsageProfile: The profile, as stored.

        Raises:
            StorageWriteError: If a profile of that name exists or it cannot be written.
        """
        self.logger.debug("Creating a usage profile.")
        created = await self.rows.create(value)
        self.logger.info("Usage profile created.")
        return created

    async def read(self, name: str) -> Optional[UsageProfile]:
        """Read a usage profile.

        Args:
            name (str): Its name.

        Returns:
            Optional[UsageProfile]: The profile, `None` when there is none.

        Raises:
            StorageReadError: If it cannot be read.
        """
        self.logger.debug("Reading the usage profile %s.", name)
        found = await self.rows.read({"name": name})
        if found is None:
            self.logger.warning("No usage profile %s.", name)
        return found

    async def update(self, value: UsageProfile) -> bool:
        """Replace a usage profile.

        Args:
            value (UsageProfile): The profile.

        Returns:
            bool: Whether it existed.

        Raises:
            StorageWriteError: If it cannot be written.
        """
        self.logger.debug("Updating the usage profile %s.", value.name)
        updated = await self.rows.update(value)
        if updated:
            self.logger.info("Usage profile %s updated.", value.name)
        else:
            self.logger.warning("No usage profile %s to update.", value.name)
        return updated

    async def delete(self, name: str) -> bool:
        """Remove a usage profile and its quotes.

        Args:
            name (str): Its name.

        Returns:
            bool: Whether there was one.

        Raises:
            StorageWriteError: If it cannot be removed.
        """
        self.logger.debug("Deleting the usage profile %s.", name)
        deleted = await self.rows.delete({"name": name})
        if deleted:
            self.logger.info("Usage profile %s deleted.", name)
        else:
            self.logger.warning("No usage profile %s to delete.", name)
        return deleted

    async def list(self, offset: int = 0, limit: Optional[int] = None) -> List[UsageProfile]:
        """List the usage profiles, by name.

        Args:
            offset (int): The rows skipped.
            limit (Optional[int]): The most rows returned, every one when `None`.

        Returns:
            List[UsageProfile]: The profiles.

        Raises:
            StorageReadError: If they cannot be read.
        """
        self.logger.debug("Listing the usage profiles from %d.", offset)
        listed = await self.rows.list(offset=offset, limit=limit)
        self.logger.debug("%d usage profiles listed.", len(listed))
        return listed
