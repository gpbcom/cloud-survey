from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Mapping, Optional, Sequence, Tuple

# Third Party Imports.
from sqlalchemy import Table, func, select, update
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.cloud.enums import PriceOrigin
from models.cloud.prices.facts.free_tier import FreeTier
from models.cloud.prices.stored.stored_free_tier import StoredFreeTier
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.mappers.row_store import RowStore, RowValue
from storage.repositories.prices.price_records import PriceRecords
from storage.repositories.prices.staged_merge import StagedMerge
from storage.tables.base import Base
from storage.tables.prices.free_tier_row import FreeTierRow
from storage.tables.prices.staging.free_tier_stage_row import FreeTierStageRow


class FreeTierRepository:
    """Create, read, update, delete and list the free offers of the cloud providers, and merge the price crawls.

    Attributes:
        ORDER (ClassVar[Tuple[str, ...]]): The columns the offers are listed by.
        database (Database): The open database.
        table (Table): The `free_tiers` table.
        stage_table (Table): Its staging table.
        rows (RowStore[StoredFreeTier]): The single-row operations.
        records (PriceRecords): Writes the offers as copied rows, with their fingerprint.
        merger (StagedMerge): Merges the offers of a crawl.
        logger (Logger): The repository logger.

    Notes:
        As the prices: a crawl stages then merges its offers, keeping their history, and a person changes an offer
        with `revise` or ends one with `close`, neither of which a crawl undoes.
    """

    ORDER: ClassVar[Tuple[str, ...]] = ("provider", "service", "free_key", "valid_from")

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.database = database
        self.table: Table = Base.metadata.tables[FreeTierRow.__tablename__]
        self.stage_table: Table = Base.metadata.tables[FreeTierStageRow.__tablename__]
        self.rows = RowStore(database, self.table, StoredFreeTier, "free tier", self.logger)
        self.records = PriceRecords(self.logger)
        self.merger = StagedMerge(
            database, self.table, self.stage_table, "free_key", PriceRecords.FREE_COLUMNS, "free tier", self.logger
        )
        self.logger.debug("Repository of the free tiers ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: StoredFreeTier) -> StoredFreeTier:
        """Insert a free offer.

        Args:
            value (StoredFreeTier): The offer, its identifier left empty.

        Returns:
            StoredFreeTier: The offer, as stored.

        Raises:
            StorageWriteError: If a current offer of the same key exists or the row cannot be written.
        """
        self.logger.debug("Creating a free tier.")
        created = await self.rows.create(value)
        self.logger.info("Free tier created.")
        return created

    async def read(self, tier_id: int) -> Optional[StoredFreeTier]:
        """Read a free offer row.

        Args:
            tier_id (int): Its identifier.

        Returns:
            Optional[StoredFreeTier]: The row, `None` when there is none.

        Raises:
            StorageReadError: If it cannot be read.
        """
        self.logger.debug("Reading the free tier %d.", tier_id)
        found = await self.rows.read({"id": tier_id})
        if found is None:
            self.logger.warning("No free tier %d.", tier_id)
        return found

    async def update(self, value: StoredFreeTier) -> bool:
        """Replace a free offer row, without keeping the former one.

        Args:
            value (StoredFreeTier): The row.

        Returns:
            bool: Whether it existed.

        Raises:
            StorageWriteError: If it cannot be written.
        """
        self.logger.debug("Updating the free tier %d.", value.id)
        updated = await self.rows.update(value)
        if updated:
            self.logger.info("Free tier %d updated.", value.id)
        else:
            self.logger.warning("No free tier %d to update.", value.id)
        return updated

    async def delete(self, tier_id: int) -> bool:
        """Remove a free offer row, with no trace in the history (see `close`).

        Args:
            tier_id (int): Its identifier.

        Returns:
            bool: Whether there was one.

        Raises:
            StorageWriteError: If it cannot be removed.
        """
        self.logger.debug("Deleting the free tier %d.", tier_id)
        deleted = await self.rows.delete({"id": tier_id})
        if deleted:
            self.logger.info("Free tier %d deleted.", tier_id)
        else:
            self.logger.warning("No free tier %d to delete.", tier_id)
        return deleted

    async def list(
        self,
        filters: Optional[Mapping[str, Sequence[RowValue]]] = None,
        offset: int = 0,
        limit: Optional[int] = 500,
        current: bool = True,
    ) -> List[StoredFreeTier]:
        """List the free offers, by provider and service, a page at a time.

        Args:
            filters (Optional[Mapping[str, Sequence[RowValue]]]): For each column, the values kept.
            offset (int): The rows skipped.
            limit (Optional[int]): The most rows returned, every one when `None`.
            current (bool): Whether only the current offers are listed (else their history too).

        Returns:
            List[StoredFreeTier]: The offers.

        Raises:
            StorageReadError: If a filter names an unknown column or the offers cannot be read.
        """
        statement = select(self.table).order_by(*(self.table.c[name] for name in self.ORDER)).offset(offset)
        if current:
            statement = statement.where(self.table.c.valid_to.is_(None))
        for name, values in (filters or {}).items():
            if name not in self.table.columns:
                self.logger.error("The free tiers have no column %r to filter on.", name)
                raise StorageReadError("free tiers", f"no column {name!r}")
            if values:
                statement = statement.where(self.table.c[name].in_(list(values)))
        if limit is not None:
            statement = statement.limit(limit)
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The free tiers cannot be listed: %s", e)
            raise StorageReadError("free tiers", str(e)) from e
        tiers = [StoredFreeTier.model_validate(dict(row)) for row in rows]
        self.logger.debug("%d free tiers listed from %d.", len(tiers), offset)
        return tiers

    async def stage(self, run_id: str, tiers: Sequence[FreeTier]) -> int:
        """Copy a batch of free offers of a crawl into the staging table.

        Args:
            run_id (str): The crawl.
            tiers (Sequence[FreeTier]): The offers.

        Returns:
            int: The offers staged.

        Raises:
            StorageWriteError: If they cannot be copied.
        """
        if not tiers:
            self.logger.debug("No free tier to stage for the run %s.", run_id)
        staged = await self.merger.copy(run_id, [self.records.free_record(tier) for tier in tiers])
        self.logger.debug("%d free tiers staged for the run %s.", staged, run_id)
        return staged

    async def merge(self, run_id: str, provider: str, sources: Sequence[str]) -> Tuple[int, int]:
        """Merge the staged free offers of a crawl into the stored offers.

        Args:
            run_id (str): The crawl.
            provider (str): Its provider.
            sources (Sequence[str]): The sources the crawl read whole (their missing rows are closed).

        Returns:
            Tuple[int, int]: The offers closed, then the offers inserted.

        Raises:
            StorageWriteError: If they cannot be merged.
        """
        self.logger.info("Merging the free tiers of the run %s (%s, %d sources read).", run_id, provider, len(sources))
        closed, inserted = await self.merger.merge(run_id, provider, sources)
        if not closed and not inserted:
            self.logger.debug("The free tiers of %s are unchanged.", provider)
        return closed, inserted

    async def discard(self, run_id: str) -> int:
        """Remove the staged free offers of a failed crawl.

        Args:
            run_id (str): The crawl.

        Returns:
            int: The offers removed.

        Raises:
            StorageWriteError: If they cannot be removed.
        """
        self.logger.warning("Discarding the staged free tiers of the run %s.", run_id)
        return await self.merger.discard(run_id)

    async def close(self, tier_id: int) -> bool:
        """End a current free offer: it stays in the history.

        Args:
            tier_id (int): Its identifier.

        Returns:
            bool: Whether a current offer was closed.

        Raises:
            StorageWriteError: If it cannot be written.
        """
        statement = (
            update(self.table)
            .where(self.table.c.id == tier_id, self.table.c.valid_to.is_(None))
            .values(valid_to=func.now(), edited=True)
        )
        try:
            async with self.database.connect() as connection, connection.begin():
                closed = (await connection.execute(statement)).rowcount > 0
        except SQLAlchemyError as e:
            self.logger.error("The free tier %d cannot be closed: %s", tier_id, e)
            raise StorageWriteError("free tier", str(e)) from e
        if not closed:
            self.logger.warning("No current free tier %d to close.", tier_id)
        self.logger.info("Free tier %d closed by a person.", tier_id)
        return closed

    async def revise(self, value: StoredFreeTier) -> StoredFreeTier:
        """Change a free offer by hand, its former row kept in the history.

        Args:
            value (StoredFreeTier): The changed offer.

        Returns:
            StoredFreeTier: The new current row, written as changed by a person.

        Raises:
            StorageWriteError: If it cannot be written.
        """
        fact = FreeTier.model_validate(value.model_dump(include=set(FreeTier.model_fields)))
        revised = value.model_copy(
            update={
                "id": None,
                "valid_from": None,
                "valid_to": None,
                "origin": PriceOrigin.USER,
                "edited": True,
                "fingerprint": self.records.free_fingerprint(fact),
            }
        )
        close = (
            update(self.table)
            .where(
                self.table.c.provider == value.provider.value,
                self.table.c.free_key == value.free_key,
                self.table.c.valid_to.is_(None),
            )
            .values(valid_to=func.now())
        )
        try:
            async with self.database.connect() as connection, connection.begin():
                await connection.execute(close)
        except SQLAlchemyError as e:
            self.logger.error("The free tier %s cannot be revised: %s", value.free_key, e)
            raise StorageWriteError("free tier", str(e)) from e
        created = await self.rows.create(revised)
        self.logger.info("Free tier %s revised by a person.", value.free_key)
        return created
