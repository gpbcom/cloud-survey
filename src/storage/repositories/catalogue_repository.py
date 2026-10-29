from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger
from typing import Dict, Optional, Tuple

# Third Party Imports.
from sqlalchemy import bindparam, select, update
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.cloud.enums import CloudProvider, DateCaveat, DateSource
from models.cloud.products.catalogue import CloudCatalogue
from models.cloud.products.product import CloudProduct
from models.storage.enums import DatasetKind
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.mappers.item_mapper import ItemMapper
from storage.repositories.item_repository import ItemRepository
from storage.repositories.taxonomy.item_categorizer import ItemCategorizer
from storage.tables.base import ITEM_REVISION, Base
from storage.tables.items.product_row import ProductRow
from storage.tables.items.product_version_row import ProductVersionRow


class CatalogueRepository(ItemRepository[CloudProduct]):
    """Read and write the product catalogues of the cloud providers."""

    def __init__(
        self, database: Database, logger: Optional[Logger] = None, categorizer: Optional[ItemCategorizer] = None
    ) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
            categorizer (Optional[ItemCategorizer]): The categorizer shared by the repositories of a storage.
        """
        tables = Base.metadata.tables
        mapper = ItemMapper[CloudProduct](
            CloudProduct,
            tables[ProductRow.__tablename__],
            tables[ProductVersionRow.__tablename__],
        )
        super().__init__(database, mapper, DatasetKind.CATALOGUE, logger, categorizer)
        self.logger.debug("Catalogue repository ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def load(self, provider: CloudProvider) -> Optional[CloudCatalogue]:
        """Read the catalogue of a cloud provider, its deleted products included.

        Args:
            provider (CloudProvider): The cloud provider.

        Returns:
            Optional[CloudCatalogue]: The catalogue,
                `None` when it was never crawled.

        Raises:
            StorageReadError: If the catalogue cannot be read.
        """
        self.logger.debug("Loading the %s catalogue.", provider.value)
        read = await self.items(provider)
        if read is None:
            return None
        stamp, products = read
        return CloudCatalogue(
            provider=provider,
            crawled_at=stamp.crawled_at,
            products=products,
            in_progress=stamp.in_progress,
        )

    async def live_names(self, provider: CloudProvider) -> Dict[int, str]:
        """Read the name of each product a provider still lists.

        Args:
            provider (CloudProvider): The cloud provider.

        Returns:
            Dict[int, str]: The name of each live product, by identifier.

        Raises:
            StorageReadError: If the products cannot be read.
        """
        table = self.mapper.table
        statement = select(table.c.id, table.c.name).where(
            table.c.provider == provider.value, table.c.deleted_at.is_(None)
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The %s product names cannot be read: %s", provider.value, e)
            raise StorageReadError(f"{provider.value} product names", str(e)) from e
        self.logger.debug("%d live %s products read.", len(rows), provider.value)
        return {int(item_id): str(name) for item_id, name in rows}

    async def live_pages(self, provider: CloudProvider) -> Dict[int, Tuple[str, Optional[str]]]:
        """Read the name and page of each product a provider still lists.

        Args:
            provider (CloudProvider): The cloud provider.

        Returns:
            Dict[int, Tuple[str, Optional[str]]]: The name and page URL of each live product, by identifier.

        Raises:
            StorageReadError: If the products cannot be read.
        """
        table = self.mapper.table
        statement = select(table.c.id, table.c.name, table.c.url).where(
            table.c.provider == provider.value, table.c.deleted_at.is_(None)
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The %s product pages cannot be read: %s", provider.value, e)
            raise StorageReadError(f"{provider.value} product pages", str(e)) from e
        self.logger.debug("%d live %s product pages read.", len(rows), provider.value)
        return {int(item_id): (str(name), str(url) if url else None) for item_id, name, url in rows}

    async def set_launches(self, provider: CloudProvider, launches: Dict[int, Tuple[datetime, DateCaveat]]) -> int:
        """Write the launch of stored products as their added date, without crawling.

        Args:
            provider (CloudProvider): The cloud provider of the products.
            launches (Dict[int, Tuple[datetime, DateCaveat]]): The launch and its caveat of each product, by
                identifier.

        Returns:
            int: The number of products whose added date changed, 0 when the catalogue is being crawled (logged).

        Raises:
            StorageWriteError: If the launches cannot be written.

        Notes:
            The launch is a website date (`DateSource.WEBSITE`):
            it is read from the provider's announcements. Only
            the products of the provider whose added date,
            caveat or source differs are written (and counted), and
            the catalogue is touched only when one is.
        """
        table = self.mapper.table
        if not launches:
            self.logger.debug("No %s launch to write.", provider.value)
            return 0
        query = select(table.c.id, table.c.added_at, table.c.added_caveat, table.c.added_from).where(
            table.c.provider == provider.value, table.c.id.in_(sorted(launches))
        )
        statement = (
            update(table)
            .where(table.c.id == bindparam("row_id"), table.c.provider == provider.value)
            .values(
                added_at=bindparam("launched"),
                added_from=DateSource.WEBSITE.value,
                added_caveat=bindparam("caveat"),
                revision=ITEM_REVISION.next_value(),
            )
        )
        try:
            async with self.database.connect() as connection, connection.begin():
                if not await self.lock.acquire_for_transaction(connection, self.kind, provider.value):
                    self.logger.warning(
                        "The %s catalogue is being crawled: its launches are not written.", provider.value
                    )
                    return 0
                stored = (await connection.execute(query)).all()
                rows = [
                    {"row_id": item_id, "launched": launches[item_id][0], "caveat": launches[item_id][1].value}
                    for item_id, added_at, added_caveat, added_from in stored
                    if (added_at, added_caveat, added_from)
                    != (launches[item_id][0], launches[item_id][1].value, DateSource.WEBSITE.value)
                ]
                if rows:
                    await connection.execute(statement, rows)
                    await self._touch(connection, [provider.value])
        except SQLAlchemyError as e:
            self.logger.error("The launches of %d %s products cannot be written: %s", len(launches), provider.value, e)
            raise StorageWriteError(f"{provider.value} launches", str(e)) from e
        self.logger.info("%d %s products dated by their launch.", len(rows), provider.value)
        return len(rows)
