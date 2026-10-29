from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional, Sequence

# Third Party Imports.
from sqlalchemy import Table, delete, func, select
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource, ProviderMetric
from models.drivers.metrics.metric_coverage import MetricCoverage
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.mappers.row_store import RowStore
from storage.tables.base import Base
from storage.tables.metrics.provider_metric_row import ProviderMetricRow


class ProviderMetricRepository:
    """Read and write the measures of the providers per quarter (the criteria and targets of the driver analysis).

    Attributes:
        database (Database): The open database.
        table (Table): The `provider_metrics` table.
        rows (RowStore[ProviderMetricValue]): The single-measure operations on the table.
        logger (Logger): The repository logger.

    Notes:
        A measure is identified by its provider, quarter,
        metric and source: a source never overwrites another
        one, and the derived measures are replaced as a whole at each refresh.
    """

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.logger = logger if logger else getLogger(__name__)
        self.table: Table = Base.metadata.tables[ProviderMetricRow.__tablename__]
        self.rows = RowStore(database, self.table, ProviderMetricValue, "provider metric", self.logger)
        self.logger.debug("Repository of the provider metrics ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: ProviderMetricValue) -> ProviderMetricValue:
        """Insert one measure.

        Args:
            value (ProviderMetricValue): The measure.

        Returns:
            ProviderMetricValue: The measure, as stored.

        Raises:
            StorageWriteError: If a measure has the same key (provider, quarter, metric and source).
        """
        self.logger.debug("Creating a provider metric.")
        return await self.rows.create(value)

    async def read(
        self, provider: CloudProvider, period: str, metric: ProviderMetric, source: MetricSource
    ) -> Optional[ProviderMetricValue]:
        """Read one measure.

        Args:
            provider (CloudProvider): The provider.
            period (str): The quarter, written YYYYQn.
            metric (ProviderMetric): What is measured.
            source (MetricSource): Where it comes from.

        Returns:
            Optional[ProviderMetricValue]: The measure, `None` when there is none.

        Raises:
            StorageReadError: If the measure cannot be read.
        """
        return await self.rows.read(
            {"provider": provider.value, "period": period, "metric": metric.value, "source": source.value}
        )

    async def update(self, value: ProviderMetricValue) -> bool:
        """Replace one measure (that of the same provider, quarter, metric and source).

        Args:
            value (ProviderMetricValue): The measure.

        Returns:
            bool: Whether the measure existed (none is created otherwise).

        Raises:
            StorageWriteError: If the measure cannot be written.
        """
        self.logger.debug("Updating a provider metric.")
        return await self.rows.update(value)

    async def delete(self, provider: CloudProvider, period: str, metric: ProviderMetric, source: MetricSource) -> bool:
        """Delete one measure.

        Args:
            provider (CloudProvider): The provider.
            period (str): The quarter, written YYYYQn.
            metric (ProviderMetric): What is measured.
            source (MetricSource): Where it comes from.

        Returns:
            bool: Whether a measure was deleted.

        Raises:
            StorageWriteError: If the measure cannot be deleted.
        """
        return await self.rows.delete(
            {"provider": provider.value, "period": period, "metric": metric.value, "source": source.value}
        )

    async def upsert(self, values: Sequence[ProviderMetricValue]) -> int:
        """Write measures, replacing those of the same provider, quarter, metric and source.

        Args:
            values (Sequence[ProviderMetricValue]): The measures.

        Returns:
            int: The number of measures written.

        Raises:
            StorageWriteError: If the measures cannot be written.
        """
        rows = [
            {
                "provider": value.provider.value,
                "period": value.period,
                "metric": value.metric.value,
                "source": value.source.value,
                "value": value.value,
                "source_url": value.source_url,
            }
            for value in {(v.provider, v.period, v.metric, v.source): v for v in values}.values()
        ]
        if not rows:
            return 0
        table = self.table
        try:
            async with self.database.connect() as connection, connection.begin():
                for start in range(0, len(rows), 1000):
                    statement = upsert(table).values(rows[start : start + 1000])
                    await connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=[table.c.provider, table.c.period, table.c.metric, table.c.source],
                            set_={
                                "value": statement.excluded.value,
                                "source_url": statement.excluded.source_url,
                                "fetched_at": func.now(),
                            },
                        )
                    )
        except SQLAlchemyError as e:
            self.logger.error("The provider metrics cannot be written: %s", e)
            raise StorageWriteError("provider metrics", str(e)) from e
        self.logger.info("%d provider metrics written.", len(rows))
        return len(rows)

    async def replace_source(self, source: MetricSource, values: Sequence[ProviderMetricValue]) -> int:
        """Replace every measure of a source (e.g. the derived ones, computed again).

        Args:
            source (MetricSource): The source.
            values (Sequence[ProviderMetricValue]): Its new measures (those of another source are left out).

        Returns:
            int: The number of measures written.

        Raises:
            StorageWriteError: If the measures cannot be replaced.
        """
        try:
            async with self.database.connect() as connection, connection.begin():
                await connection.execute(delete(self.table).where(self.table.c.source == source.value))
        except SQLAlchemyError as e:
            self.logger.error("The %s provider metrics cannot be deleted: %s", source.value, e)
            raise StorageWriteError(f"{source.value} provider metrics", str(e)) from e
        kept = [value for value in values if value.source is source]
        written = await self.upsert(kept)
        self.logger.info("%s provider metrics replaced: %d measures.", source.value, written)
        return written

    async def list(
        self,
        metrics: Optional[Sequence[ProviderMetric]] = None,
        providers: Optional[Sequence[CloudProvider]] = None,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> List[ProviderMetricValue]:
        """List measures.

        Args:
            metrics (Optional[Sequence[ProviderMetric]]): Only these metrics, all of them when `None`.
            providers (Optional[Sequence[CloudProvider]]): Only these providers, all of them when `None` or empty.
            offset (int): The measures skipped.
            limit (Optional[int]): The most measures returned, every one when `None`.

        Returns:
            List[ProviderMetricValue]: The measures, by provider, quarter, metric and source.

        Raises:
            StorageReadError: If the measures cannot be read.

        Notes:
            A row of an unknown provider, metric or source (e.g. written by a newer version, or by a metric since
            removed) is skipped, the unknown metrics and sources logged as a warning.
        """
        table = self.table
        statement = select(table).order_by(table.c.provider, table.c.period, table.c.metric, table.c.source)
        if metrics:
            statement = statement.where(table.c.metric.in_([metric.value for metric in metrics]))
        if providers:
            statement = statement.where(table.c.provider.in_([provider.value for provider in providers]))
        statement = statement.offset(offset).limit(limit)
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The provider metrics cannot be read: %s", e)
            raise StorageReadError("provider metrics", str(e)) from e
        known = {provider.value for provider in CloudProvider}
        metrics_known = {metric.value for metric in ProviderMetric}
        sources_known = {source.value for source in MetricSource}
        mentioned = [row for row in rows if row["provider"] in known]
        kept = [row for row in mentioned if row["metric"] in metrics_known and row["source"] in sources_known]
        if len(kept) < len(mentioned):
            unknown = sorted(
                {
                    f"{row['metric']}/{row['source']}"
                    for row in mentioned
                    if row["metric"] not in metrics_known or row["source"] not in sources_known
                }
            )
            self.logger.warning(
                "%d stored provider metrics skipped: unknown metric or source (%s).",
                len(mentioned) - len(kept),
                ", ".join(unknown),
            )
        values = [ProviderMetricValue.model_validate(dict(row)) for row in kept]
        self.logger.debug("%d provider metrics read.", len(values))
        return values

    async def providers(self) -> List[CloudProvider]:
        """List the providers holding at least one measure.

        Returns:
            List[CloudProvider]: The providers, in their order of declaration.

        Raises:
            StorageReadError: If the measures cannot be read.
        """
        statement = select(self.table.c.provider).distinct()
        try:
            async with self.database.connect() as connection:
                stored = {str(row[0]) for row in (await connection.execute(statement)).all()}
        except SQLAlchemyError as e:
            self.logger.error("The providers of the provider metrics cannot be read: %s", e)
            raise StorageReadError("provider metrics", str(e)) from e
        providers = [provider for provider in CloudProvider if provider.value in stored]
        self.logger.debug("%d providers hold provider metrics.", len(providers))
        return providers

    async def coverage(self) -> List[MetricCoverage]:
        """Describe what the stored measures of each criterion cover (the tooltips of the Rise drivers card).

        Returns:
            List[MetricCoverage]: One entry per criterion stored: its providers, first and last quarter, measures
                and sources.

        Raises:
            StorageReadError: If the measures cannot be read.
        """
        table = self.table
        statement = select(
            table.c.metric,
            func.count(table.c.provider.distinct()),
            func.min(table.c.period),
            func.max(table.c.period),
            func.count(),
            func.array_agg(table.c.source.distinct()),
        ).group_by(table.c.metric)
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The coverage of the provider metrics cannot be read: %s", e)
            raise StorageReadError("provider metrics", str(e)) from e
        known = {metric.value for metric in ProviderMetric}
        sources = {source.value for source in MetricSource}
        coverage = [
            MetricCoverage(
                metric=ProviderMetric(metric),
                providers=int(providers),
                first=str(first),
                last=str(last),
                observations=int(observations),
                sources=[MetricSource(source) for source in sorted(stored or []) if source in sources],
            )
            for metric, providers, first, last, observations, stored in rows
            if metric in known
        ]
        self.logger.debug("Coverage of %d provider metrics read.", len(coverage))
        return coverage
