from __future__ import annotations

# Standard Library Imports.
import zlib
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Set, Tuple

# Third Party Imports.
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.storage.enums import DatasetKind


class DatasetLock:
    """The PostgreSQL advisory locks making each dataset written by one crawl at a time.

    Attributes:
        KIND_KEYS (ClassVar[Dict[DatasetKind, int]]): The first lock key of each kind of dataset.
        logger (Logger): The lock logger.

    Notes:
        A lock is identified by two 32-bit keys: the kind of the dataset, and the CRC-32 of its name. A crawl holds
        a session lock (`acquire` / `release`) on its connection: when the crawl process dies, the server releases it,
        which tells the readers that the crawl is no longer running. The short writes (statistics, reclassification)
        take a transaction lock, released at the end of the transaction.
    """

    KIND_KEYS: ClassVar[Dict[DatasetKind, int]] = {
        DatasetKind.CATALOGUE: 1,
        DatasetKind.MARKETPLACE: 2,
        DatasetKind.STATISTICS: 3,
    }

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the lock.

        Args:
            logger (Optional[Logger]): The lock logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("Dataset locks ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _keys(self, kind: DatasetKind, dataset: str) -> Tuple[int, int]:
        """Get the two keys of the lock of a dataset, as the signed integers PostgreSQL takes.

        Args:
            kind (DatasetKind): What the dataset holds.
            dataset (str): The cloud provider, or the statistics source.

        Returns:
            Tuple[int, int]: The key of the kind,
                then the signed CRC-32 of the dataset name.
        """
        checksum = zlib.crc32(dataset.encode("utf-8"))
        return self.KIND_KEYS[kind], checksum - (1 << 32) if checksum >= (1 << 31) else checksum

    ############################
    # Publicly Exposed Methods #
    ############################

    async def acquire(self, connection: AsyncConnection, kind: DatasetKind, dataset: str) -> bool:
        """Take the session lock of a dataset, without waiting.

        Args:
            connection (AsyncConnection): The connection holding the
                lock until `release` (or its end).
            kind (DatasetKind): What the dataset holds.
            dataset (str): The cloud provider, or the statistics source.

        Returns:
            bool: Whether the lock was taken, `False` when another session holds it.
        """
        first, second = self._keys(kind, dataset)
        result = await connection.execute(
            text("SELECT pg_try_advisory_lock(:first, :second)"),
            {"first": first, "second": second},
        )
        taken = bool(result.scalar())
        self.logger.debug("Lock of the %s %s %s.", dataset, kind.value, "taken" if taken else "held by another crawl")
        return taken

    async def release(self, connection: AsyncConnection, kind: DatasetKind, dataset: str) -> None:
        """Release the session lock of a dataset.

        Args:
            connection (AsyncConnection): The connection holding the lock.
            kind (DatasetKind): What the dataset holds.
            dataset (str): The cloud provider, or the statistics source.
        """
        first, second = self._keys(kind, dataset)
        await connection.execute(text("SELECT pg_advisory_unlock(:first, :second)"), {"first": first, "second": second})
        self.logger.debug("Lock of the %s %s released.", dataset, kind.value)

    async def acquire_for_transaction(self, connection: AsyncConnection, kind: DatasetKind, dataset: str) -> bool:
        """Take the lock of a dataset until the end of the current transaction, without waiting.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            kind (DatasetKind): What the dataset holds.
            dataset (str): The cloud provider, or the statistics source.

        Returns:
            bool: Whether the lock was taken,
                `False` when another session holds it.
        """
        first, second = self._keys(kind, dataset)
        result = await connection.execute(
            text("SELECT pg_try_advisory_xact_lock(:first, :second)"), {"first": first, "second": second}
        )
        taken = bool(result.scalar())
        self.logger.debug(
            "Transaction lock of the %s %s %s.",
            dataset,
            kind.value,
            "taken" if taken else "held by another crawl",
        )
        return taken

    async def held(self, connection: AsyncConnection) -> Set[Tuple[int, int]]:
        """Read the dataset locks held by every session of the server.

        Args:
            connection (AsyncConnection): A connection.

        Returns:
            Set[Tuple[int, int]]: The keys of the held locks,
                as `is_held` compares them.
        """
        self.logger.debug("Reading the dataset locks of the server.")
        result = await connection.execute(
            text(
                "SELECT classid::bigint, objid::bigint FROM pg_locks "
                "WHERE locktype = 'advisory' AND objsubid = 2 AND granted"
            )
        )
        return {(int(first), int(second)) for first, second in result.all()}

    def is_held(self, held: Set[Tuple[int, int]], kind: DatasetKind, dataset: str) -> bool:
        """Tell whether the lock of a dataset is among the held locks.

        Args:
            held (Set[Tuple[int, int]]): The held locks (see `held`).
            kind (DatasetKind): What the dataset holds.
            dataset (str): The cloud provider, or the statistics source.

        Returns:
            bool: Whether a session holds the lock of the dataset.
        """
        first, second = self._keys(kind, dataset)
        return (first, second % (1 << 32)) in held
