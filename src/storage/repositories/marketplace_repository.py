from __future__ import annotations

# Standard Library Imports.
from logging import Logger
from typing import ClassVar, Dict, List, Optional

# Third Party Imports.
from pydantic import JsonValue
from sqlalchemy import ColumnElement, String, column, func, select, true
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.cloud.software.marketplace import CloudMarketplace
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.storage.enums import DatasetKind
from models.storage.pages.item_query import ItemQuery
from models.storage.pages.software_facets import SoftwareFacets
from storage.engine.database import Database
from storage.engine.dataset_lock import DatasetLock
from storage.exception import StorageReadError
from storage.mappers.item_mapper import ItemMapper
from storage.repositories.item_repository import ItemRepository
from storage.repositories.taxonomy.item_categorizer import ItemCategorizer
from storage.tables.base import Base
from storage.tables.items.software_row import SoftwareRow
from storage.tables.items.software_version_row import SoftwareVersionRow
from storage.writer.crawl_recorder import CrawlRecorder


class MarketplaceRepository(ItemRepository[MarketplaceSoftware]):
    """Read and write the software of the marketplaces of the cloud providers.

    Attributes:
        PICKER_LIMIT (ClassVar[int]): The largest number of publishers counted for the picker, the most frequent
            first.
        lock (DatasetLock): The lock keeping a reclassification away from a running crawl.
        recorder (CrawlRecorder): The recorder telling the readers about a reclassification.
    """

    PICKER_LIMIT: ClassVar[int] = 500

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
        mapper = ItemMapper[MarketplaceSoftware](
            MarketplaceSoftware, tables[SoftwareRow.__tablename__], tables[SoftwareVersionRow.__tablename__]
        )
        super().__init__(database, mapper, DatasetKind.MARKETPLACE, logger, categorizer)
        self.lock = DatasetLock(self.logger)
        self.recorder = CrawlRecorder(self.logger)
        self.logger.debug("Marketplace repository ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _pickers(
        self, connection: AsyncConnection, conditions: List[ColumnElement[bool]]
    ) -> Dict[str, JsonValue]:
        """Count the matching software of the most frequent publishers.

        Args:
            connection (AsyncConnection): A connection.
            conditions (List[ColumnElement[bool]]): The filters of the query.

        Returns:
            Dict[str, JsonValue]: The `by_publisher` facet.
        """
        table = self.mapper.table
        count = func.count().label("count")
        publishers = await connection.execute(
            select(table.c.publisher, count)
            .where(*conditions, table.c.publisher.is_not(None))
            .group_by(table.c.publisher)
            .order_by(count.desc())
            .limit(self.PICKER_LIMIT)
        )
        counted: Dict[str, JsonValue] = {value: total for value, total in publishers.all()}
        self.logger.debug("%d publishers counted for the picker.", len(counted))
        return {"by_publisher": counted}

    ############################
    # Publicly Exposed Methods #
    ############################

    async def load(self, provider: CloudProvider) -> Optional[CloudMarketplace]:
        """Read the marketplace of a cloud provider, its deleted software included.

        Args:
            provider (CloudProvider): The cloud provider.

        Returns:
            Optional[CloudMarketplace]: The marketplace, `None` when it was never crawled.

        Raises:
            StorageReadError: If the marketplace cannot be read.
        """
        self.logger.debug("Loading the %s marketplace.", provider.value)
        read = await self.items(provider)
        if read is None:
            return None
        stamp, software = read
        return CloudMarketplace(
            provider=provider, crawled_at=stamp.crawled_at, software=software, in_progress=stamp.in_progress
        )

    async def facets(self, query: ItemQuery, pickers: bool = False) -> SoftwareFacets:
        """Count the software matching the filters of a query, by provider, audience, taxonomy domain and delivery.

        Args:
            query (ItemQuery): The query (its order and bounds are ignored).
            pickers (bool): Whether the most frequent publishers are counted too (for the publisher picker).

        Returns:
            SoftwareFacets: The counts, computed by the server.

        Raises:
            StorageReadError: If the software cannot be counted.
        """
        table = self.mapper.table
        conditions = self.builder.filters(query)
        domain = func.unnest(table.c.service_domains).table_valued("domain").render_derived()
        category = func.unnest(table.c.categories).table_valued("category").render_derived()
        try:
            async with self.database.connect() as connection:
                total = await connection.scalar(select(func.count()).select_from(table).where(*conditions))
                providers = await connection.execute(
                    select(table.c.provider, func.count()).where(*conditions).group_by(table.c.provider)
                )
                deliveries = await connection.execute(
                    select(table.c.delivery, func.count()).where(*conditions).group_by(table.c.delivery)
                )
                categories = await connection.execute(
                    select(column("category", String), func.count())
                    .select_from(table)
                    .join(category, true())
                    .where(*conditions)
                    .group_by(column("category", String))
                )
                domains = await connection.execute(
                    select(column("domain", String), func.count())
                    .select_from(table)
                    .join(domain, true())
                    .where(*conditions)
                    .group_by(column("domain", String))
                )
                pairs = await connection.execute(
                    select(column("domain", String), column("category", String), func.count())
                    .select_from(table)
                    .join(domain, true())
                    .join(category, true())
                    .where(*conditions)
                    .group_by(column("domain", String), column("category", String))
                )
                by_domain_and_category: Dict[str, Dict[str, int]] = {}
                for domain_value, category_value, count in pairs.all():
                    by_domain_and_category.setdefault(domain_value, {})[category_value] = count
                picked = await self._pickers(connection, conditions) if pickers else {}
                facets = SoftwareFacets.model_validate(
                    {
                        **picked,
                        "total": int(total or 0),
                        "by_provider": {value: count for value, count in providers.all()},
                        "by_delivery": {value: count for value, count in deliveries.all()},
                        "by_category": {value: count for value, count in categories.all()},
                        "by_domain": {value: count for value, count in domains.all()},
                        "by_domain_and_category": by_domain_and_category,
                    }
                )
        except SQLAlchemyError as e:
            self.logger.error("The marketplace software cannot be counted: %s", e)
            raise StorageReadError("marketplace software", str(e)) from e
        self.logger.debug("Facets of %d marketplace software counted.", facets.total)
        return facets
