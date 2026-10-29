from __future__ import annotations

# Standard Library Imports.
import json
from functools import partial
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional

# Third Party Imports.
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

# First Party Imports.
from models.configuration.storage.storage_settings import StorageSettings
from storage.engine.settings_reader import StorageSettingsReader
from storage.exception import StorageConnectionError, StorageSchemaError
from storage.tables.schema import StorageSchema


class Database:
    """The asynchronous connection pool of the PostgreSQL database of the crawled data.

    Attributes:
        POOL_RECYCLE (ClassVar[int]): After how many seconds a pooled connection is replaced.
        PAGE_SIZE (ClassVar[int]): The number of rows per `INSERT` of the batched writes.
        SERVER_SETTINGS (ClassVar[Dict[str, str]]): The session settings of every connection (the JIT compilation
            slows the short queries of the crawls down).
        settings (StorageSettings): The storage settings.
        url (str): The database URL without its password, for the logs.
        logger (Logger): The database logger.
        engine_or_none (Optional[AsyncEngine]): The engine, `None` until `open` (and after `close`).

    Notes:
        - The asyncpg connections belong to the event loop which opened them: a database is opened and closed in the
          same event loop, each event loop (the GUI one, a crawl one) opening its own.
        - The JSON columns are written with the decimal numbers as text (the quantities of the usage profiles, the
          costs of the quotes), which their models read back as decimals.
    """

    POOL_RECYCLE: ClassVar[int] = 1800
    PAGE_SIZE: ClassVar[int] = 1000
    SERVER_SETTINGS: ClassVar[Dict[str, str]] = {"application_name": "poc-crawler", "jit": "off"}

    def __init__(self, settings: StorageSettings, logger: Optional[Logger] = None) -> None:
        """Initialize the database, without connecting yet.

        Args:
            settings (StorageSettings): The storage settings.
            logger (Optional[Logger]): The database logger.
        """
        self.settings = settings
        self.logger = logger if logger else getLogger(__name__)
        self.url = StorageSettingsReader(self.logger).safe_url(settings.url)
        self.engine_or_none: Optional[AsyncEngine] = None
        self.logger.debug("Database %s configured.", self.url)

    ############################
    # Internal Helpers Methods #
    ############################

    async def _schema_revision(self, connection: AsyncConnection) -> Optional[str]:
        """Read the migration revision of the database schema.

        Args:
            connection (AsyncConnection): A connection.

        Returns:
            Optional[str]: The revision, `None` when the database has no schema yet.
        """
        self.logger.debug("Reading the schema revision of %s.", self.url)
        exists = await connection.scalar(text("SELECT to_regclass('alembic_version') IS NOT NULL"))
        if not exists:
            return None
        revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        return str(revision) if revision is not None else None

    ############################
    # Publicly Exposed Methods #
    ############################

    @property
    def is_open(self) -> bool:
        """Tell whether the database is open.

        Returns:
            bool: Whether `open` was called and not `close`.
        """
        return self.engine_or_none is not None

    @property
    def engine(self) -> AsyncEngine:
        """Get the engine of the open database.

        Returns:
            AsyncEngine: The engine.

        Raises:
            StorageConnectionError: If the database is not open.
        """
        if self.engine_or_none is None:
            self.logger.error("The database %s is used before being opened.", self.url)
            raise StorageConnectionError(self.url, "the storage is not open")
        return self.engine_or_none

    async def open(self, check_schema: bool = True) -> None:
        """Create the connection pool and check the database: reachable, with the schema the code expects.

        Args:
            check_schema (bool): Whether the schema revision is checked (not before the migrations).

        Raises:
            StorageConnectionError: If the database cannot be reached.
            StorageSchemaError: If the schema is missing or at another revision (the database is then closed).
        """
        if self.engine_or_none is not None:
            self.logger.debug("The database %s is already open.", self.url)
            return
        self.logger.debug("Opening the database %s.", self.url)
        engine = create_async_engine(
            self.settings.url,
            pool_size=self.settings.pool_size,
            max_overflow=self.settings.max_overflow,
            pool_pre_ping=True,
            pool_recycle=self.POOL_RECYCLE,
            insertmanyvalues_page_size=self.PAGE_SIZE,
            echo=self.settings.echo,
            json_serializer=partial(json.dumps, default=str),
            connect_args={
                "server_settings": dict(self.SERVER_SETTINGS),
                "command_timeout": self.settings.command_timeout_s,
            },
        )
        try:
            async with engine.connect() as connection:
                revision = await self._schema_revision(connection)
        except (OSError, SQLAlchemyError) as e:
            await engine.dispose()
            self.logger.error("The database %s cannot be reached: %s", self.url, e)
            raise StorageConnectionError(self.url, str(e)) from e
        if check_schema and revision != StorageSchema.REVISION:
            await engine.dispose()
            self.logger.error(
                "The database %s schema is at revision %s instead of %s.", self.url, revision, StorageSchema.REVISION
            )
            raise StorageSchemaError(revision or "none", StorageSchema.REVISION)
        self.engine_or_none = engine
        self.logger.info("Database %s open (schema %s).", self.url, revision or "none")

    async def close(self) -> None:
        """Close every connection of the pool. The database can be opened again afterwards."""
        if self.engine_or_none is None:
            return
        engine, self.engine_or_none = self.engine_or_none, None
        await engine.dispose()
        self.logger.info("Database %s closed.", self.url)

    def connect(self) -> AsyncConnection:
        """Get a connection of the pool, to use as `async with database.connect() as connection`.

        Returns:
            AsyncConnection: The connection, returned to the pool at the end of the `async with` block.

        Raises:
            StorageConnectionError: If the database is not open.
        """
        self.logger.debug("Connection to %s requested.", self.url)
        return self.engine.connect()
