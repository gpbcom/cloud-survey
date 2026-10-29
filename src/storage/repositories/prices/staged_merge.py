from __future__ import annotations

# Standard Library Imports.
import zlib
from datetime import date, datetime
from decimal import Decimal
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple, Union

# Third Party Imports.
from sqlalchemy import Table, text
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from storage.engine.database import Database
from storage.exception import StorageWriteError

type StagedValue = Optional[Union[str, int, bool, Decimal, date, datetime]]


class StagedMerge:
    """Merge what a crawl read into a table with history, through an unlogged staging table.

    Attributes:
        LOCK_KIND (ClassVar[int]): The first key of the advisory lock of a merge (7, after the dataset, seed and
            matching locks), the second being the CRC-32 of the provider.
        database (Database): The open database.
        table (Table): The table with history (`valid_from`, `valid_to`, `origin`, `edited`, `fingerprint`).
        stage (Table): Its staging table (`run_id` and the same columns).
        key (str): The column naming a row of a provider, stable from crawl to crawl (`sku_key`, `free_key`).
        columns (List[str]): The columns copied from the staging table into the table.
        label (str): What a row is, in the logs and the errors.
        logger (Logger): The merge logger.

    Notes:
        - A crawl copies its batches into the staging table (`COPY`, no write-ahead log), then merges them at its
          end with three set-based statements in one transaction: the current rows whose fingerprint changed are
          closed (`valid_to`), those of the sources read whole the crawl no longer found too, and the new and
          changed rows are inserted.
          The unchanged rows are not written: a crawl of an unchanged price list costs a copy and two anti-joins.
          A key staged twice in a crawl (e.g. a page read for two products) counts once: its last staged row is
          the one compared and inserted.
        - A row a person wrote or changed (`edited`, origin `user`) is never closed nor replaced by a crawl, and a
          row a person closed (its latest row closed and `edited`) is not opened again by a crawl.
        - Two merges of a provider never run at once (a transaction advisory lock).
    """

    LOCK_KIND: ClassVar[int] = 7

    def __init__(
        self,
        database: Database,
        table: Table,
        stage: Table,
        key: str,
        columns: Sequence[str],
        label: str,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the merge.

        Args:
            database (Database): The open database.
            table (Table): The table with history.
            stage (Table): Its staging table.
            key (str): The column naming a row of a provider.
            columns (Sequence[str]): The columns copied from the staging table.
            label (str): What a row is.
            logger (Optional[Logger]): The merge logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.database = database
        self.table = table
        self.stage = stage
        self.key = key
        self.columns = list(columns)
        self.label = label

    ############################
    # Internal Helpers Methods #
    ############################

    def _lock_key(self, provider: str) -> int:
        """Get the second key of the advisory lock of a provider.

        Args:
            provider (str): The provider.

        Returns:
            int: The CRC-32 of its name, as a signed 32-bit integer.
        """
        key = zlib.crc32(provider.encode("utf-8"))
        signed = key - (1 << 32) if key >= 1 << 31 else key
        self.logger.debug("Merge lock of %s: (%d, %d).", provider, self.LOCK_KIND, signed)
        return signed

    ############################
    # Publicly Exposed Methods #
    ############################

    async def copy(self, run_id: str, records: Sequence[Tuple[StagedValue, ...]]) -> int:
        """Copy a batch of rows of a crawl into the staging table.

        Args:
            run_id (str): The crawl.
            records (Sequence[Tuple[StagedValue, ...]]): The rows, their values in the order of `columns`.

        Returns:
            int: The rows copied.

        Raises:
            StorageWriteError: If the rows cannot be copied.
        """
        if not records:
            self.logger.debug("No %s row to stage for the run %s.", self.label, run_id)
            return 0
        rows = [(run_id, *record) for record in records]
        try:
            async with self.database.connect() as connection:
                raw = await connection.get_raw_connection()
                driver = raw.driver_connection
                if driver is None:
                    self.logger.error("No driver connection to copy the %s rows into.", self.label)
                    raise StorageWriteError(self.label, "the connection has no driver connection")
                await driver.copy_records_to_table(self.stage.name, records=rows, columns=["run_id", *self.columns])
        except (SQLAlchemyError, OSError, ValueError) as e:
            self.logger.error("%d %s rows cannot be staged: %s", len(rows), self.label, e)
            raise StorageWriteError(self.label, str(e)) from e
        self.logger.debug("%d %s rows staged for the run %s.", len(rows), self.label, run_id)
        return len(rows)

    async def merge(self, run_id: str, provider: str, sources: Sequence[str]) -> Tuple[int, int]:
        """Merge the staged rows of a crawl into the table, then remove them.

        Args:
            run_id (str): The crawl.
            provider (str): Its provider.
            sources (Sequence[str]): The sources the crawl read whole: only their rows it missed are closed (the
                rows of a source unchanged since its last read, or not readable, are kept).

        Returns:
            Tuple[int, int]: The rows closed, then the rows inserted.

        Raises:
            StorageWriteError: If the rows cannot be merged.
        """
        table, stage, key = self.table.name, self.stage.name, self.key
        names = ", ".join(self.columns)
        staged = ", ".join(f"s.{name}" for name in self.columns)
        parameters: Dict[str, Union[str, List[str]]] = {"run": run_id, "provider": provider, "sources": list(sources)}
        close_changed = text(
            f"UPDATE {table} AS t SET valid_to = now() FROM (SELECT DISTINCT ON ({key}) {key}, fingerprint "
            f"FROM {stage} WHERE run_id = :run ORDER BY {key}, id DESC) AS s "
            f"WHERE t.provider = :provider AND t.valid_to IS NULL AND NOT t.edited "
            f"AND t.{key} = s.{key} AND t.fingerprint <> s.fingerprint"
        )
        close_missing = text(
            f"UPDATE {table} AS t SET valid_to = now() "
            f"WHERE t.provider = :provider AND t.valid_to IS NULL AND NOT t.edited AND t.origin = 'crawler' "
            f"AND t.source_url = ANY(:sources) "
            f"AND NOT EXISTS (SELECT 1 FROM {stage} AS s WHERE s.run_id = :run AND s.{key} = t.{key})"
        )
        insert = text(
            f"INSERT INTO {table} ({names}) SELECT DISTINCT ON (s.{key}) {staged} FROM {stage} AS s "
            f"WHERE s.run_id = :run AND s.provider = :provider AND NOT EXISTS "
            f"(SELECT 1 FROM {table} AS t WHERE t.provider = :provider AND t.valid_to IS NULL AND t.{key} = s.{key}) "
            f"AND NOT EXISTS (SELECT 1 FROM {table} AS t WHERE t.provider = :provider AND t.{key} = s.{key} "
            f"AND t.edited AND t.valid_to IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {table} AS later "
            f"WHERE later.provider = t.provider AND later.{key} = t.{key} AND later.valid_from > t.valid_from)) "
            f"ORDER BY s.{key}, s.id DESC"
        )
        try:
            async with self.database.connect() as connection, connection.begin():
                await connection.execute(
                    text("SELECT pg_advisory_xact_lock(:kind, :key)"),
                    {"kind": self.LOCK_KIND, "key": self._lock_key(provider)},
                )
                closed = (await connection.execute(close_changed, parameters)).rowcount
                if sources:
                    closed += (await connection.execute(close_missing, parameters)).rowcount
                inserted = (await connection.execute(insert, parameters)).rowcount
                await connection.execute(text(f"DELETE FROM {stage} WHERE run_id = :run"), {"run": run_id})
        except SQLAlchemyError as e:
            self.logger.error("The %s rows of %s cannot be merged: %s", self.label, provider, e)
            raise StorageWriteError(self.label, str(e)) from e
        if not sources:
            self.logger.info(
                "The %s crawl of %s read no source whole: no row it missed is closed.", self.label, provider
            )
        self.logger.info("%s %s merged: %d rows closed, %d inserted.", provider, self.label, closed, inserted)
        return closed, inserted

    async def discard(self, run_id: str) -> int:
        """Remove the staged rows of a crawl without merging them (a failed crawl).

        Args:
            run_id (str): The crawl.

        Returns:
            int: The rows removed.

        Raises:
            StorageWriteError: If the rows cannot be removed.
        """
        try:
            async with self.database.connect() as connection, connection.begin():
                removed = (
                    await connection.execute(
                        text(f"DELETE FROM {self.stage.name} WHERE run_id = :run"), {"run": run_id}
                    )
                ).rowcount
        except SQLAlchemyError as e:
            self.logger.error("The staged %s rows of %s cannot be removed: %s", self.label, run_id, e)
            raise StorageWriteError(self.label, str(e)) from e
        self.logger.info("%d staged %s rows of %s discarded.", removed, self.label, run_id)
        return removed

    def names(self) -> List[str]:
        """Get the columns copied, in order.

        Returns:
            List[str]: The column names.
        """
        self.logger.debug("The %s merge copies %d columns.", self.label, len(self.columns))
        return list(self.columns)
