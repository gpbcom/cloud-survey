from __future__ import annotations

# Standard Library Imports.
import asyncio
from logging import Logger, getLogger
from typing import Optional

# Third Party Imports.
from alembic import context
from alembic.config import Config
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# First Party Imports.
from storage.tables.schema import StorageSchema


class MigrationEnvironment:
    """Run the Alembic migrations of the storage, online with the asyncpg driver or offline as SQL.

    Attributes:
        config (Config): The Alembic configuration, set by `DatabaseMigrator`.
        schema (StorageSchema): The schema the migrations are compared with.
        logger (Logger): The migration logger.
    """

    def __init__(self, config: Config, logger: Optional[Logger] = None) -> None:
        """Initialize the environment.

        Args:
            config (Config): The Alembic configuration.
            logger (Optional[Logger]): The migration logger.
        """
        self.config = config
        self.schema = StorageSchema()
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("Migration environment ready (%d tables).", len(self.schema.metadata.tables))

    ############################
    # Internal Helpers Methods #
    ############################

    def _url(self) -> str:
        """Get the database URL of the configuration.

        Returns:
            str: The SQLAlchemy URL.
        """
        self.logger.debug("Reading the database URL of the migrations.")
        return self.config.get_main_option("sqlalchemy.url") or ""

    def _migrate(self, connection: Connection) -> None:
        """Run the migrations on a connection, in one transaction.

        Args:
            connection (Connection): The synchronous facade of the asyncpg connection.
        """
        self.logger.debug("Running the migrations in one transaction.")
        context.configure(connection=connection, target_metadata=self.schema.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

    async def _migrate_online(self) -> None:
        """Run the migrations on the database, with a dedicated engine."""
        self.logger.info("Migrating the database online.")
        engine = create_async_engine(self._url(), poolclass=pool.NullPool)
        try:
            async with engine.connect() as connection:
                await connection.run_sync(self._migrate)
        finally:
            await engine.dispose()

    ############################
    # Publicly Exposed Methods #
    ############################

    def run(self) -> None:
        """Run the migrations: as SQL printed on the standard output in offline mode, else on the database."""
        if context.is_offline_mode():
            self.logger.debug("Writing the migrations as SQL.")
            context.configure(url=self._url(), target_metadata=self.schema.metadata, literal_binds=True)
            with context.begin_transaction():
                context.run_migrations()
            return
        self.logger.debug("Running the migrations on the database.")
        asyncio.run(self._migrate_online())


MigrationEnvironment(context.config).run()
