from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Optional, Union

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.enums import DatasetKind
from models.storage.pages.item_query import ItemQuery
from models.storage.pages.page import Page
from models.storage.pages.stored_item import StoredItem
from storage.exception import StorageReadError, StorageWriteError
from storage.repositories.catalogue_repository import CatalogueRepository
from storage.repositories.marketplace_repository import MarketplaceRepository

type TrendItem = Union[CloudProduct, MarketplaceSoftware]
type StoredTrendItem = Union[StoredItem[CloudProduct], StoredItem[MarketplaceSoftware]]
type TrendPage = Union[Page[CloudProduct], Page[MarketplaceSoftware]]


class StoredItems:
    """Create, read, update, delete and list the items the trends and matrices count, by kind of dataset.

    Attributes:
        catalogues (CatalogueRepository): The catalogue products.
        marketplaces (MarketplaceRepository): The marketplace software.
        logger (Logger): The logger.

    Notes:
        The trends and matrices own no table: they count
        the stored items, so their CRUDL operations are those of
        the items repository of each kind (a statistics
        dataset holds no item and is refused).
    """

    def __init__(
        self,
        catalogues: CatalogueRepository,
        marketplaces: MarketplaceRepository,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the items.

        Args:
            catalogues (CatalogueRepository): The catalogue products.
            marketplaces (MarketplaceRepository): The marketplace software.
            logger (Optional[Logger]): The logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.catalogues = catalogues
        self.marketplaces = marketplaces
        self.logger.debug("Stored items of the trends ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, kind: DatasetKind, provider: CloudProvider, item: TrendItem) -> StoredTrendItem:
        """Store an item by hand.

        Args:
            kind (DatasetKind): The kind of dataset: `CATALOGUE` for a product, `MARKETPLACE` for a software.
            provider (CloudProvider): The cloud provider of the item.
            item (TrendItem): The item.

        Returns:
            StoredTrendItem: The stored item, with its identifier.

        Raises:
            StorageWriteError: If the kind holds no such item, or the item cannot be written.
        """
        self.logger.debug("Creating a %s item of %s.", kind.value, provider.value)
        match kind:
            case DatasetKind.CATALOGUE if isinstance(item, CloudProduct):
                return await self.catalogues.create(provider, item)
            case DatasetKind.MARKETPLACE if isinstance(item, MarketplaceSoftware):
                return await self.marketplaces.create(provider, item)
            case _:
                self.logger.error("A %s dataset holds no %s: refused.", kind.value, type(item).__name__)
                raise StorageWriteError(f"{kind.value} items", f"a {kind.value} dataset holds no {type(item).__name__}")

    async def read(self, kind: DatasetKind, item_id: int) -> Optional[StoredTrendItem]:
        """Read a stored item.

        Args:
            kind (DatasetKind): The kind of dataset.
            item_id (int): The item identifier.

        Returns:
            Optional[StoredTrendItem]: The item, `None` when it does not exist (or the kind holds no item).

        Raises:
            StorageReadError: If the item cannot be read.
        """
        match kind:
            case DatasetKind.CATALOGUE:
                return await self.catalogues.read(item_id)
            case DatasetKind.MARKETPLACE:
                return await self.marketplaces.read(item_id)
            case _:
                self.logger.warning("A %s dataset holds no item: nothing read.", kind.value)
                return None

    async def update(self, kind: DatasetKind, item_id: int, item: TrendItem) -> Optional[StoredTrendItem]:
        """Replace a stored item by hand.

        Args:
            kind (DatasetKind): The kind of dataset.
            item_id (int): The item identifier.
            item (TrendItem): The new item.

        Returns:
            Optional[StoredTrendItem]: The updated item, `None` when it does not exist.

        Raises:
            StorageWriteError: If the kind holds no such item, or the item cannot be written.
        """
        self.logger.debug("Updating the %s item %d.", kind.value, item_id)
        match kind:
            case DatasetKind.CATALOGUE if isinstance(item, CloudProduct):
                return await self.catalogues.update(item_id, item)
            case DatasetKind.MARKETPLACE if isinstance(item, MarketplaceSoftware):
                return await self.marketplaces.update(item_id, item)
            case _:
                self.logger.error("A %s dataset holds no %s: refused.", kind.value, type(item).__name__)
                raise StorageWriteError(f"{kind.value} items", f"a {kind.value} dataset holds no {type(item).__name__}")

    async def delete(self, kind: DatasetKind, item_id: int) -> bool:
        """Delete a stored item by hand.

        Args:
            kind (DatasetKind): The kind of dataset.
            item_id (int): The item identifier.

        Returns:
            bool: Whether the item existed.

        Raises:
            StorageWriteError: If the kind holds no item, or the item cannot be deleted.
        """
        self.logger.debug("Deleting the %s item %d.", kind.value, item_id)
        match kind:
            case DatasetKind.CATALOGUE:
                return await self.catalogues.delete(item_id)
            case DatasetKind.MARKETPLACE:
                return await self.marketplaces.delete(item_id)
            case _:
                self.logger.error("A %s dataset holds no item: nothing deleted.", kind.value)
                raise StorageWriteError(f"{kind.value} items", "the dataset holds no item")

    async def list(self, kind: DatasetKind, query: ItemQuery) -> TrendPage:
        """List a page of the stored items.

        Args:
            kind (DatasetKind): The kind of dataset.
            query (ItemQuery): The filters, order and bounds of the page.

        Returns:
            TrendPage: The items of the page, with the number of items matching the query.

        Raises:
            StorageReadError: If the kind holds no item, or the items cannot be read.
        """
        match kind:
            case DatasetKind.CATALOGUE:
                return await self.catalogues.list(query)
            case DatasetKind.MARKETPLACE:
                return await self.marketplaces.list(query)
            case _:
                self.logger.error("A %s dataset holds no item: nothing listed.", kind.value)
                raise StorageReadError(f"{kind.value} items", "the dataset holds no item")
