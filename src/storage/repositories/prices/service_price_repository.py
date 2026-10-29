from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Mapping, Optional, Sequence, Set, Tuple

# Third Party Imports.
from sqlalchemy import Table, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.cloud.enums import PriceOrigin
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.stored.stored_price import StoredPrice
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.mappers.row_store import RowStore, RowValue
from storage.repositories.prices.price_records import PriceRecords
from storage.repositories.prices.staged_merge import StagedMerge
from storage.tables.base import Base
from storage.tables.prices.service_price_row import ServicePriceRow
from storage.tables.prices.staging.service_price_stage_row import ServicePriceStageRow


class ServicePriceRepository:
    """Create, read, update, delete and list the prices of the cloud services, and merge the price crawls.

    Attributes:
        ORDER (ClassVar[Tuple[str, ...]]): The columns the prices are listed by.
        database (Database): The open database.
        table (Table): The `service_prices` table.
        stage_table (Table): Its staging table.
        rows (RowStore[StoredPrice]): The single-row operations.
        records (PriceRecords): Writes the prices as copied rows, with their fingerprint.
        merger (StagedMerge): Merges the prices of a crawl.
        logger (Logger): The repository logger.

    Notes:
        - A crawl stages its prices by batches (`stage`), then merges them at its end (`merge`): the changed prices
          get a new row, their former one closed, so that the rows of a `sku_key` are its history.
        - A person changes a price with `revise` (its current row closed, a new one written as changed by a person),
          and removes a crawled one with `close` (kept in the history). `update` and `delete` change or remove a
          row itself, as any repository.
    """

    ORDER: ClassVar[Tuple[str, ...]] = ("provider", "service", "region", "sku_key", "valid_from")

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.database = database
        self.table: Table = Base.metadata.tables[ServicePriceRow.__tablename__]
        self.stage_table: Table = Base.metadata.tables[ServicePriceStageRow.__tablename__]
        self.rows = RowStore(database, self.table, StoredPrice, "service price")
        self.records = PriceRecords()
        self.merger = StagedMerge(
            database, self.table, self.stage_table, "sku_key", PriceRecords.PRICE_COLUMNS, "service price"
        )
        self.logger.debug("Repository of the service prices ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: StoredPrice) -> StoredPrice:
        """Insert a price (typed by a person, or a row restored).

        Args:
            value (StoredPrice): The price, its identifier left empty.

        Returns:
            StoredPrice: The price, as stored (its identifier and validity start filled).

        Raises:
            StorageWriteError: If a current price of the same key exists or the row cannot be written.
        """
        self.logger.debug("Creating a service price.")
        created = await self.rows.create(value)
        self.logger.info("Service price created.")
        return created

    async def read(self, price_id: int) -> Optional[StoredPrice]:
        """Read a price row.

        Args:
            price_id (int): Its identifier.

        Returns:
            Optional[StoredPrice]: The row, `None` when there is none.

        Raises:
            StorageReadError: If it cannot be read.
        """
        self.logger.debug("Reading the service price %d.", price_id)
        found = await self.rows.read({"id": price_id})
        if found is None:
            self.logger.warning("No service price %d.", price_id)
        return found

    async def update(self, value: StoredPrice) -> bool:
        """Replace a price row (that of the same identifier), without keeping the former one.

        Args:
            value (StoredPrice): The row.

        Returns:
            bool: Whether it existed.

        Raises:
            StorageWriteError: If it cannot be written.
        """
        self.logger.debug("Updating the service price %d.", value.id)
        updated = await self.rows.update(value)
        if updated:
            self.logger.info("Service price %d updated.", value.id)
        else:
            self.logger.warning("No service price %d to update.", value.id)
        return updated

    async def delete(self, price_id: int) -> bool:
        """Remove a price row, with no trace in the history (see `close` to end a crawled price).

        Args:
            price_id (int): Its identifier.

        Returns:
            bool: Whether there was one.

        Raises:
            StorageWriteError: If it cannot be removed.
        """
        self.logger.debug("Deleting the service price %d.", price_id)
        deleted = await self.rows.delete({"id": price_id})
        if deleted:
            self.logger.info("Service price %d deleted.", price_id)
        else:
            self.logger.warning("No service price %d to delete.", price_id)
        return deleted

    async def list(
        self,
        filters: Optional[Mapping[str, Sequence[RowValue]]] = None,
        offset: int = 0,
        limit: Optional[int] = 500,
        current: bool = True,
    ) -> List[StoredPrice]:
        """List the prices, by provider, service, region and key, a page at a time.

        Args:
            filters (Optional[Mapping[str, Sequence[RowValue]]]): For each column, the values kept.
            offset (int): The rows skipped.
            limit (Optional[int]): The most rows returned, every one when `None`.
            current (bool): Whether only the current prices are listed (else their history too).

        Returns:
            List[StoredPrice]: The prices.

        Raises:
            StorageReadError: If a filter names an unknown column or the prices cannot be read.
        """
        statement = select(self.table).order_by(*(self.table.c[name] for name in self.ORDER)).offset(offset)
        if current:
            statement = statement.where(self.table.c.valid_to.is_(None))
        for name, values in (filters or {}).items():
            if name not in self.table.columns:
                self.logger.error("The service prices have no column %r to filter on.", name)
                raise StorageReadError("service prices", f"no column {name!r}")
            if values:
                statement = statement.where(self.table.c[name].in_(list(values)))
        if limit is not None:
            statement = statement.limit(limit)
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The service prices cannot be listed: %s", e)
            raise StorageReadError("service prices", str(e)) from e
        prices = [StoredPrice.model_validate(dict(row)) for row in rows]
        self.logger.debug("%d service prices listed from %d.", len(prices), offset)
        return prices

    async def count(self, filters: Optional[Mapping[str, Sequence[RowValue]]] = None, current: bool = True) -> int:
        """Count the prices matching filters (the size of a paged listing).

        Args:
            filters (Optional[Mapping[str, Sequence[RowValue]]]): For each column, the values kept.
            current (bool): Whether only the current prices are counted.

        Returns:
            int: The prices.

        Raises:
            StorageReadError: If a filter names an unknown column or the prices cannot be counted.
        """
        statement = select(func.count()).select_from(self.table)
        if current:
            statement = statement.where(self.table.c.valid_to.is_(None))
        for name, values in (filters or {}).items():
            if name not in self.table.columns:
                self.logger.error("The service prices have no column %r to count on.", name)
                raise StorageReadError("service prices", f"no column {name!r}")
            if values:
                statement = statement.where(self.table.c[name].in_(list(values)))
        try:
            async with self.database.connect() as connection:
                total = (await connection.execute(statement)).scalar_one()
        except SQLAlchemyError as e:
            self.logger.error("The service prices cannot be counted: %s", e)
            raise StorageReadError("service prices", str(e)) from e
        return int(total)

    async def stage(self, run_id: str, prices: Sequence[ServicePrice]) -> int:
        """Copy a batch of prices of a crawl into the staging table.

        Args:
            run_id (str): The crawl.
            prices (Sequence[ServicePrice]): The prices.

        Returns:
            int: The prices staged.

        Raises:
            StorageWriteError: If they cannot be copied.
        """
        if not prices:
            self.logger.debug("No service price to stage for the run %s.", run_id)
        staged = await self.merger.copy(run_id, [self.records.price_record(price) for price in prices])
        self.logger.debug("%d service prices staged for the run %s.", staged, run_id)
        return staged

    async def merge(self, run_id: str, provider: str, sources: Sequence[str]) -> Tuple[int, int]:
        """Merge the staged prices of a crawl into the stored prices.

        Args:
            run_id (str): The crawl.
            provider (str): Its provider.
            sources (Sequence[str]): The sources the crawl read whole (their missing rows are closed).

        Returns:
            Tuple[int, int]: The prices closed, then the prices inserted.

        Raises:
            StorageWriteError: If they cannot be merged.
        """
        self.logger.info(
            "Merging the service prices of the run %s (%s, %d sources read).", run_id, provider, len(sources)
        )
        closed, inserted = await self.merger.merge(run_id, provider, sources)
        if not closed and not inserted:
            self.logger.debug("The service prices of %s are unchanged.", provider)
        return closed, inserted

    async def discard(self, run_id: str) -> int:
        """Remove the staged prices of a failed crawl.

        Args:
            run_id (str): The crawl.

        Returns:
            int: The prices removed.

        Raises:
            StorageWriteError: If they cannot be removed.
        """
        self.logger.warning("Discarding the staged service prices of the run %s.", run_id)
        return await self.merger.discard(run_id)

    async def close(self, price_id: int) -> bool:
        """End a current price: it stays in the history (a crawled price a person removes).

        Args:
            price_id (int): Its identifier.

        Returns:
            bool: Whether a current price was closed.

        Raises:
            StorageWriteError: If it cannot be written.
        """
        statement = (
            update(self.table)
            .where(self.table.c.id == price_id, self.table.c.valid_to.is_(None))
            .values(valid_to=func.now(), edited=True)
        )
        try:
            async with self.database.connect() as connection, connection.begin():
                closed = (await connection.execute(statement)).rowcount > 0
        except SQLAlchemyError as e:
            self.logger.error("The service price %d cannot be closed: %s", price_id, e)
            raise StorageWriteError("service price", str(e)) from e
        if not closed:
            self.logger.warning("No current service price %d to close.", price_id)
        self.logger.info("Service price %d closed by a person.", price_id)
        return closed

    async def revise(self, value: StoredPrice) -> StoredPrice:
        """Change a price by hand, its former row kept in the history.

        Args:
            value (StoredPrice): The changed price (the identifier of its current row, or none for a new one).

        Returns:
            StoredPrice: The new current row, written as changed by a person.

        Raises:
            StorageWriteError: If it cannot be written.
        """
        fact = ServicePrice.model_validate(value.model_dump(include=set(ServicePrice.model_fields)))
        revised = value.model_copy(
            update={
                "id": None,
                "valid_from": None,
                "valid_to": None,
                "origin": PriceOrigin.USER,
                "edited": True,
                "fingerprint": self.records.price_fingerprint(fact),
            }
        )
        close = (
            update(self.table)
            .where(
                self.table.c.provider == value.provider.value,
                self.table.c.sku_key == value.sku_key,
                self.table.c.valid_to.is_(None),
            )
            .values(valid_to=func.now())
        )
        try:
            async with self.database.connect() as connection, connection.begin():
                await connection.execute(close)
        except SQLAlchemyError as e:
            self.logger.error("The service price %s cannot be revised: %s", value.sku_key, e)
            raise StorageWriteError("service price", str(e)) from e
        created = await self.rows.create(revised)
        self.logger.info("Service price %s revised by a person.", value.sku_key)
        return created

    async def history(self, provider: str, sku_key: str) -> List[StoredPrice]:
        """List every row of a priced dimension, the oldest first.

        Args:
            provider (str): The provider.
            sku_key (str): The priced dimension.

        Returns:
            List[StoredPrice]: Its rows.

        Raises:
            StorageReadError: If they cannot be read.
        """
        statement = (
            select(self.table)
            .where(self.table.c.provider == provider, self.table.c.sku_key == sku_key)
            .order_by(self.table.c.valid_from)
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The history of %s %s cannot be read: %s", provider, sku_key, e)
            raise StorageReadError("service prices", str(e)) from e
        return [StoredPrice.model_validate(dict(row)) for row in rows]

    async def coverage(self, provider: str) -> List[Tuple[str, bool, bool]]:
        """Read how the live catalogue products of a provider are covered by its current prices.

        Args:
            provider (str): The provider.

        Returns:
            List[Tuple[str, bool, bool]]: Each live product name, whether it has a price (free included), and
                whether it is stated unpriced (quote, included or not public), by name.

        Raises:
            StorageReadError: If they cannot be read.
        """
        statement = text(
            "SELECT p.name, coalesce(bool_or(sp.price IS NOT NULL), false), "
            "coalesce(bool_or(sp.id IS NOT NULL AND sp.price IS NULL), false) "
            "FROM products AS p LEFT JOIN service_prices AS sp "
            "ON sp.product_id = p.id AND sp.valid_to IS NULL "
            "WHERE p.provider = :provider AND p.deleted_at IS NULL GROUP BY p.id, p.name ORDER BY p.name"
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement, {"provider": provider})).all()
        except SQLAlchemyError as e:
            self.logger.error("The price coverage of %s cannot be read: %s", provider, e)
            raise StorageReadError("service prices", str(e)) from e
        self.logger.debug("Price coverage of %s read: %d live products.", provider, len(rows))
        return [(str(name), bool(priced), bool(unpriced)) for name, priced, unpriced in rows]

    async def crawled_products(self, provider: str, marker: str) -> Set[str]:
        """List the live catalogue products of a provider priced by a crawled price (not by a curated statement).

        Args:
            provider (str): The provider.
            marker (str): The text the source of a curated statement holds (its rows are left out).

        Returns:
            Set[str]: The names of the products having a current price with an amount read by a crawl.

        Raises:
            StorageReadError: If they cannot be read.
        """
        statement = text(
            "SELECT DISTINCT p.name FROM products AS p JOIN service_prices AS sp ON sp.product_id = p.id "
            "WHERE p.provider = :provider AND p.deleted_at IS NULL AND sp.valid_to IS NULL "
            "AND sp.price IS NOT NULL AND strpos(sp.source_url, :marker) = 0"
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement, {"provider": provider, "marker": marker})).all()
        except SQLAlchemyError as e:
            self.logger.error("The crawled products of %s cannot be read: %s", provider, e)
            raise StorageReadError("service prices", str(e)) from e
        if not rows:
            self.logger.warning("No %s product has a crawled price.", provider)
        self.logger.debug("%d %s products have a crawled price.", len(rows), provider)
        return {str(name) for (name,) in rows}

    async def unlinked_services(self, provider: str) -> List[Tuple[str, str, str]]:
        """List the services of the current prices of a provider not linked to a catalogue product yet.

        Args:
            provider (str): The provider.

        Returns:
            List[Tuple[str, str, str]]: Each service name, source and product detail (the `productName` attribute
                of the providers naming their products within a service, empty otherwise), once.

        Raises:
            StorageReadError: If they cannot be read.
        """
        statement = text(
            "SELECT DISTINCT service, source_url, coalesce(attributes->>'productName', '') FROM service_prices "
            "WHERE provider = :provider AND valid_to IS NULL AND product_id IS NULL"
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement, {"provider": provider})).all()
        except SQLAlchemyError as e:
            self.logger.error("The unlinked prices of %s cannot be read: %s", provider, e)
            raise StorageReadError("service prices", str(e)) from e
        self.logger.debug("%d unlinked %s priced services.", len(rows), provider)
        return [(str(service), str(source), str(detail)) for service, source, detail in rows]

    async def unlink_products(self, provider: str) -> int:
        """Unlink the current prices of a provider from the catalogue products, before linking them all again.

        Args:
            provider (str): The provider.

        Returns:
            int: The prices unlinked.

        Raises:
            StorageWriteError: If they cannot be written.
        """
        statement = text(
            "UPDATE service_prices SET product_id = NULL "
            "WHERE provider = :provider AND valid_to IS NULL AND product_id IS NOT NULL"
        )
        try:
            async with self.database.connect() as connection, connection.begin():
                unlinked = (await connection.execute(statement, {"provider": provider})).rowcount
        except SQLAlchemyError as e:
            self.logger.error("The prices of %s cannot be unlinked: %s", provider, e)
            raise StorageWriteError("service prices", str(e)) from e
        self.logger.info("%d %s prices unlinked from their catalogue product.", unlinked, provider)
        return unlinked

    async def link_rows(self, provider: str, links: Sequence[Tuple[str, int]]) -> int:
        """Link the current unlinked prices of a provider whose row matches a curated expression.

        Args:
            provider (str): The provider.
            links (Sequence[Tuple[str, int]]): Each regular expression (PostgreSQL syntax, case ignored, matched
                against `<service> | <sku_key> | <attributes as JSON>`) and its product, the first matching one
                winning.

        Returns:
            int: The prices linked.

        Raises:
            StorageWriteError: If they cannot be written.
        """
        statement = text(
            "UPDATE service_prices SET product_id = :product WHERE provider = :provider AND valid_to IS NULL "
            "AND product_id IS NULL AND (service || ' | ' || sku_key || ' | ' || attributes::text) ~* :pattern"
        )
        linked = 0
        try:
            async with self.database.connect() as connection, connection.begin():
                for pattern, product in links:
                    parameters = {"provider": provider, "product": product, "pattern": pattern}
                    linked += (await connection.execute(statement, parameters)).rowcount
        except SQLAlchemyError as e:
            self.logger.error("The prices of %s cannot be linked by their row: %s", provider, e)
            raise StorageWriteError("service prices", str(e)) from e
        self.logger.info("%d %s prices linked to their catalogue product by their row.", linked, provider)
        return linked

    async def link_products(self, provider: str, links: Sequence[Tuple[str, str, str, int]]) -> int:
        """Link the current prices of a provider to the catalogue products matched to their service and source.

        Args:
            provider (str): The provider.
            links (Sequence[Tuple[str, str, str, int]]): The service, source, product detail and product of each
                link.

        Returns:
            int: The prices linked.

        Raises:
            StorageWriteError: If they cannot be written.
        """
        if not links:
            self.logger.info("No %s price to link to a catalogue product.", provider)
            return 0
        statement = text(
            "UPDATE service_prices AS sp SET product_id = l.product FROM "
            "unnest(CAST(:services AS text[]), CAST(:sources AS text[]), CAST(:details AS text[]), "
            "CAST(:products AS bigint[])) AS l(service, source, detail, product) "
            "WHERE sp.provider = :provider AND sp.valid_to IS NULL AND sp.product_id IS NULL "
            "AND sp.service = l.service AND sp.source_url = l.source "
            "AND coalesce(sp.attributes->>'productName', '') = l.detail"
        )
        parameters = {
            "provider": provider,
            "services": [link[0] for link in links],
            "sources": [link[1] for link in links],
            "details": [link[2] for link in links],
            "products": [link[3] for link in links],
        }
        try:
            async with self.database.connect() as connection, connection.begin():
                linked = (await connection.execute(statement, parameters)).rowcount
        except SQLAlchemyError as e:
            self.logger.error("The prices of %s cannot be linked to their products: %s", provider, e)
            raise StorageWriteError("service prices", str(e)) from e
        self.logger.info("%d %s prices linked to their catalogue product.", linked, provider)
        return linked
