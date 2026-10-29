from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, FrozenSet, List, Optional, Sequence, Tuple

# Third Party Imports.
from sqlalchemy import ColumnElement, Row
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.storage.enums import DatasetKind
from models.storage.pages.item_query import ItemQuery
from models.trends.enums import ChartMetric, SeriesGrouping
from models.trends.metric_point import MetricPoint
from models.trends.metric_series import MetricSeries
from storage.engine.database import Database
from storage.exception import StorageReadError
from storage.mappers.item_query_builder import ItemQueryBuilder
from storage.repositories.trends.stored_items import StoredItems, StoredTrendItem, TrendItem, TrendPage
from storage.repositories.trends.trend_statements import TrendStatements
from storage.tables.base import Base
from storage.tables.datasets.crawl_row import CrawlRow
from storage.tables.items.product_row import ProductRow
from storage.tables.items.software_row import SoftwareRow

TrendRow = Row[str, str, datetime, int]


class TrendRepository:
    """Read the chart trends of the stored items (counts per series key and bucket), and CRUDL the items counted.

    Attributes:
        METRICS (ClassVar[FrozenSet[ChartMetric]]): The metrics counted from the stored items.
        SOFTWARE_ONLY (ClassVar[FrozenSet[SeriesGrouping]]): The groupings known for the marketplace software only
            (the audience is known for the products too, the products being classified).
        GRAIN_MONTHS (ClassVar[Dict[ChartMetric, int]]): The number of months of each calendar bucket.
        database (Database): The open database.
        items (StoredItems): The counted items (the CRUDL operations of the repository).
        statements (Dict[DatasetKind, TrendStatements]): The statement builder of each items table.
        builders (Dict[DatasetKind, ItemQueryBuilder]): The filter builder of each items table.
        logger (Logger): The repository logger.

    Notes:
        - The deleted items are always read: the deletions and the listed items over time count them.
        - The trends own no table: `create`, `read`, `update`, `delete` and `list` are those of the counted items
          (see `StoredItems`).
    """

    METRICS: ClassVar[FrozenSet[ChartMetric]] = frozenset(
        {ChartMetric.ADDED, ChartMetric.DELETED, ChartMetric.LISTED, ChartMetric.PUBLISHERS}
    )
    SOFTWARE_ONLY: ClassVar[FrozenSet[SeriesGrouping]] = frozenset({SeriesGrouping.DELIVERY})
    GRAIN_MONTHS: ClassVar[Dict[ChartMetric, int]] = {
        ChartMetric.YEAR: 12,
        ChartMetric.QUARTER: 3,
        ChartMetric.MONTH: 1,
    }

    def __init__(self, database: Database, items: StoredItems, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            items (StoredItems): The counted items, whose CRUDL operations the repository exposes.
            logger (Optional[Logger]): The repository logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.database = database
        self.items = items
        tables = Base.metadata.tables
        crawls = tables[CrawlRow.__tablename__]
        counted = {
            DatasetKind.CATALOGUE: tables[ProductRow.__tablename__],
            DatasetKind.MARKETPLACE: tables[SoftwareRow.__tablename__],
        }
        self.statements = {kind: TrendStatements(table, crawls) for kind, table in counted.items()}
        self.builders = {kind: ItemQueryBuilder(table) for kind, table in counted.items()}
        self.logger.debug("Repository of the chart trends ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _conditions(self, kind: DatasetKind, query: ItemQuery) -> List[ColumnElement[bool]]:
        """Build the filters of a query, the deleted items included.

        Args:
            kind (DatasetKind): The items read.
            query (ItemQuery): The query.

        Returns:
            List[ColumnElement[bool]]: The conditions the items must meet.
        """
        return self.builders[kind].filters(query.model_copy(update={"include_deleted": True}))

    def _supported(
        self,
        kind: DatasetKind,
        metric: ChartMetric,
        grain: ChartMetric,
        grouping: SeriesGrouping,
        facet: Optional[SeriesGrouping] = None,
    ) -> bool:
        """Tell whether a trend can be counted from the stored items.

        Args:
            kind (DatasetKind): The items read.
            metric (ChartMetric): The counted metric.
            grain (ChartMetric): The calendar bucket.
            grouping (SeriesGrouping): The grouping of the series.
            facet (Optional[SeriesGrouping]): The grouping of the facets, `None` for none.

        Returns:
            bool: Whether the items table, metric, bucket, grouping and facets go together.
        """
        software = kind is DatasetKind.MARKETPLACE
        groupings = [grouping] if facet is None else [grouping, facet]
        return (
            kind in self.statements
            and metric in self.METRICS
            and grain in self.GRAIN_MONTHS
            and facet is not grouping
            and SeriesGrouping.PLAYER not in groupings
            and (software or (not self.SOFTWARE_ONLY.intersection(groupings) and metric is not ChartMetric.PUBLISHERS))
        )

    def _series(self, rows: Sequence[TrendRow], grain: ChartMetric) -> List[MetricSeries]:
        """Build the series of the counted rows.

        Args:
            rows (Sequence[TrendRow]): The facet, key, bucket start and value rows.
            grain (ChartMetric): The calendar bucket.

        Returns:
            List[MetricSeries]: One series per facet and key (no facet for an empty one), its points on the last month
                of their bucket, in time order.
        """
        months = self.GRAIN_MONTHS[grain]
        points: Dict[Tuple[str, str], List[MetricPoint]] = {}
        skipped = 0
        for facet, key, bucket, value in rows:
            if key is None or bucket is None or facet is None:
                skipped += 1
                continue
            x = float(bucket.year * 12 + bucket.month - 1 + months - 1)
            points.setdefault((str(facet), str(key)), []).append(MetricPoint(x=x, y=float(value)))
        if skipped:
            self.logger.debug("%d counted rows without a key or a date left out of the series.", skipped)
        return [
            MetricSeries(key=key, facet=facet or None, points=sorted(found, key=lambda point: point.x))
            for (facet, key), found in points.items()
        ]

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, kind: DatasetKind, provider: CloudProvider, item: TrendItem) -> StoredTrendItem:
        """Store an item counted by the trends by hand (see `StoredItems.create`).

        Args:
            kind (DatasetKind): The kind of dataset: `CATALOGUE` for a product, `MARKETPLACE` for a software.
            provider (CloudProvider): The cloud provider of the item.
            item (TrendItem): The item.

        Returns:
            StoredTrendItem: The stored item, with its identifier.

        Raises:
            StorageWriteError: If the kind holds no such item, or the item cannot be written.
        """
        self.logger.debug("Creating a %s item counted by the trends.", kind.value)
        return await self.items.create(kind, provider, item)

    async def read(self, kind: DatasetKind, item_id: int) -> Optional[StoredTrendItem]:
        """Read an item counted by the trends.

        Args:
            kind (DatasetKind): The kind of dataset.
            item_id (int): The item identifier.

        Returns:
            Optional[StoredTrendItem]: The item, `None` when it does not exist.

        Raises:
            StorageReadError: If the item cannot be read.
        """
        return await self.items.read(kind, item_id)

    async def update(self, kind: DatasetKind, item_id: int, item: TrendItem) -> Optional[StoredTrendItem]:
        """Replace an item counted by the trends by hand.

        Args:
            kind (DatasetKind): The kind of dataset.
            item_id (int): The item identifier.
            item (TrendItem): The new item.

        Returns:
            Optional[StoredTrendItem]: The updated item, `None` when it does not exist.

        Raises:
            StorageWriteError: If the kind holds no such item, or the item cannot be written.
        """
        self.logger.debug("Updating the %s item %d counted by the trends.", kind.value, item_id)
        return await self.items.update(kind, item_id, item)

    async def delete(self, kind: DatasetKind, item_id: int) -> bool:
        """Delete an item counted by the trends by hand.

        Args:
            kind (DatasetKind): The kind of dataset.
            item_id (int): The item identifier.

        Returns:
            bool: Whether the item existed.

        Raises:
            StorageWriteError: If the kind holds no item, or the item cannot be deleted.
        """
        self.logger.debug("Deleting the %s item %d counted by the trends.", kind.value, item_id)
        return await self.items.delete(kind, item_id)

    async def list(self, kind: DatasetKind, query: ItemQuery) -> TrendPage:
        """List a page of the items counted by the trends.

        Args:
            kind (DatasetKind): The kind of dataset.
            query (ItemQuery): The filters, order and bounds of the page.

        Returns:
            TrendPage: The items of the page, with the number of items matching the query.

        Raises:
            StorageReadError: If the kind holds no item, or the items cannot be read.
        """
        return await self.items.list(kind, query)

    async def series(
        self,
        kind: DatasetKind,
        metric: ChartMetric,
        grain: ChartMetric,
        query: ItemQuery,
        grouping: SeriesGrouping,
        facet: Optional[SeriesGrouping] = None,
    ) -> List[MetricSeries]:
        """Count a metric of the stored items per facet, series key and calendar bucket.

        Args:
            kind (DatasetKind): The items read: `CATALOGUE` or `MARKETPLACE`.
            metric (ChartMetric): `ADDED`, `DELETED`, `LISTED` or `PUBLISHERS` (software only).
            grain (ChartMetric): The calendar bucket: `YEAR`, `QUARTER` or `MONTH`.
            query (ItemQuery): The filters of the items (their order and bounds are ignored).
            grouping (SeriesGrouping): `PROVIDER`, `BLOC`, `DELIVERY`, `TYPE` (these two for software only) or
                `AUDIENCE`.
            facet (Optional[SeriesGrouping]): Another of those groupings splitting the series into facets (one small
                chart each, the series tagged with it), `None` for none.

        Returns:
            List[MetricSeries]: One series per facet and key, its points on the last month of their bucket, empty when
                the combination cannot be counted (logged).

        Raises:
            StorageReadError: If the items cannot be counted.
        """
        if not self._supported(kind, metric, grain, grouping, facet):
            self.logger.warning(
                "The %s of the %s cannot be counted by %s and %s.",
                metric.value,
                kind.value,
                grouping.value,
                grain.value,
            )
            return []
        statements = self.statements[kind]
        conditions = self._conditions(kind, query)
        match metric:
            case ChartMetric.LISTED:
                statement = statements.listed(grouping, grain, conditions, facet)
            case ChartMetric.PUBLISHERS:
                statement = statements.publishers(grouping, grain, conditions, facet)
            case _:
                statement = statements.events(
                    grouping, grain, conditions, deleted=metric is ChartMetric.DELETED, facet=facet
                )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The %s trend of the %s cannot be counted: %s", metric.value, kind.value, e)
            raise StorageReadError(f"{kind.value} trends", str(e)) from e
        series = self._series(rows, grain)
        self.logger.debug(
            "%s trend of the %s counted: %d series by %s.", metric.value, kind.value, len(series), grouping.value
        )
        return series

    async def undated_share(self, kind: DatasetKind, query: ItemQuery) -> float:
        """Get the share of the items without a published added date (dated by the crawl which first found them).

        Args:
            kind (DatasetKind): The items read: `CATALOGUE` or `MARKETPLACE`.
            query (ItemQuery): The filters of the items.

        Returns:
            float: The share of undated items, between 0 and 1 (0 without items).

        Raises:
            StorageReadError: If the items cannot be counted.
        """
        if kind not in self.statements:
            self.logger.warning("The %s have no added date.", kind.value)
            return 0.0
        statement = self.statements[kind].undated(self._conditions(kind, query))
        try:
            async with self.database.connect() as connection:
                row = (await connection.execute(statement)).one()
        except SQLAlchemyError as e:
            self.logger.error("The undated %s cannot be counted: %s", kind.value, e)
            raise StorageReadError(f"{kind.value} dates", str(e)) from e
        undated, total = int(row[0] or 0), int(row[1] or 0)
        self.logger.debug("%d of %d %s items have no published added date.", undated, total, kind.value)
        return undated / total if total else 0.0
