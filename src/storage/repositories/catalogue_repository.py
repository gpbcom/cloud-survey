from __future__ import annotations

# Standard Library Imports.
from logging import Logger
from typing import Optional

# Third Party Imports.
# First Party Imports.
from models.cloud.enums import CloudProvider
from models.cloud.products.catalogue import CloudCatalogue
from models.cloud.products.product import CloudProduct
from models.storage.enums import DatasetKind
from storage.engine.database import Database
from storage.mappers.item_mapper import ItemMapper
from storage.repositories.item_repository import ItemRepository
from storage.repositories.taxonomy.item_categorizer import ItemCategorizer
from storage.tables.base import Base
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

