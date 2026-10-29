from __future__ import annotations

# Standard Library Imports.
from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import List, Optional

# Third Party Imports.
from sqlalchemy import Table
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.curated.enums import CuratedFile
from models.curated.state.curated_state import CuratedState
from storage.engine.database import Database
from storage.exception import StorageWriteError
from storage.mappers.row_store import RowStore
from storage.tables.base import Base
from storage.tables.curated.records.curated_state_row import CuratedStateRow


class CuratedStateRepository:
    """Read and write the state of each file of the curated bundle: its revision and its last seed.

    Attributes:
        database (Database): The open database.
        table (Table): The `curated_state` table.
        rows (RowStore[CuratedState]): The single-row operations on the table.
        logger (Logger): The repository logger.

    Notes:
        The catalogues read from the database are cached by revision: every write of a curated row increments the
        revision of its file (`bump`), so a reader reads again only what changed.
    """

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.logger = logger if logger else getLogger(__name__)
        self.table: Table = Base.metadata.tables[CuratedStateRow.__tablename__]
        self.rows = RowStore(database, self.table, CuratedState, "curated state", self.logger)
        self.logger.debug("Repository of the curated state ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, state: CuratedState) -> CuratedState:
        """Insert the state of a bundle file.

        Args:
            state (CuratedState): The state.

        Returns:
            CuratedState: The state, as stored.

        Raises:
            StorageWriteError: If the state exists or cannot be written.
        """
        self.logger.debug("Creating the curated state of %s.", state.dataset.value)
        return await self.rows.create(state)

    async def read(self, dataset: CuratedFile) -> Optional[CuratedState]:
        """Read the state of a bundle file.

        Args:
            dataset (CuratedFile): The bundle file.

        Returns:
            Optional[CuratedState]: The state, `None` before the first seed or write.

        Raises:
            StorageReadError: If the state cannot be read.
        """
        return await self.rows.read({"dataset": dataset.value})

    async def update(self, state: CuratedState) -> bool:
        """Replace the state of a bundle file.

        Args:
            state (CuratedState): The state.

        Returns:
            bool: Whether there was a state to replace.

        Raises:
            StorageWriteError: If the state cannot be written.
        """
        return await self.rows.update(state)

    async def delete(self, dataset: CuratedFile) -> bool:
        """Forget the state of a bundle file (the next seed applies it again).

        Args:
            dataset (CuratedFile): The bundle file.

        Returns:
            bool: Whether there was a state.

        Raises:
            StorageWriteError: If the state cannot be removed.
        """
        return await self.rows.delete({"dataset": dataset.value})

    async def list(self) -> List[CuratedState]:
        """List the state of every bundle file stored.

        Returns:
            List[CuratedState]: The states, by bundle file.

        Raises:
            StorageReadError: If the states cannot be read.
        """
        return await self.rows.list()

    async def bump(self, dataset: CuratedFile) -> None:
        """Increment the revision of a bundle file (its rows were written).

        Args:
            dataset (CuratedFile): The bundle file.

        Raises:
            StorageWriteError: If the state cannot be written.
        """
        table = self.table
        statement = upsert(table).values(dataset=dataset.value, revision=1)
        statement = statement.on_conflict_do_update(
            index_elements=[table.c.dataset], set_={"revision": table.c.revision + 1}
        )
        try:
            async with self.database.connect() as connection, connection.begin():
                await connection.execute(statement)
        except SQLAlchemyError as e:
            self.logger.error("The revision of the curated %s cannot be incremented: %s", dataset.value, e)
            raise StorageWriteError("curated state", str(e)) from e
        self.logger.debug("Revision of the curated %s incremented.", dataset.value)

    async def seeded(self, dataset: CuratedFile, seed_hash: str, connection: Optional[AsyncConnection] = None) -> None:
        """Record that a bundle file was applied, and increment its revision.

        Args:
            dataset (CuratedFile): The bundle file.
            seed_hash (str): The hash of the file applied.
            connection (Optional[AsyncConnection]): The connection of the seed, in its transaction (a connection of
                the pool otherwise).

        Raises:
            StorageWriteError: If the state cannot be written.
        """
        table = self.table
        now = datetime.now(UTC)
        statement = upsert(table).values(dataset=dataset.value, revision=1, seed_hash=seed_hash, seeded_at=now)
        statement = statement.on_conflict_do_update(
            index_elements=[table.c.dataset],
            set_={"revision": table.c.revision + 1, "seed_hash": seed_hash, "seeded_at": now},
        )
        try:
            if connection is not None:
                await connection.execute(statement)
            else:
                async with self.database.connect() as own, own.begin():
                    await own.execute(statement)
        except SQLAlchemyError as e:
            self.logger.error("The seed of the curated %s cannot be recorded: %s", dataset.value, e)
            raise StorageWriteError("curated state", str(e)) from e
        self.logger.info("Curated %s seeded (hash %s).", dataset.value, seed_hash[:12])
