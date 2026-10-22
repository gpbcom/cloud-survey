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
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.tables.base import Base
from storage.tables.metrics.provider_metric_row import ProviderMetricRow


class ProviderMetricRepository:
    """Read and write the measures of the providers per quarter (the criteria and targets of the driver analysis).

    Attributes:
        database (Database): The open database.
        table (Table): The `provider_metrics` table.
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
        self.logger.debug("Repository of the provider metrics ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

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

    async def read(
        self,
        metrics: Optional[Sequence[ProviderMetric]] = None,
        providers: Optional[Sequence[CloudProvider]] = None,
    ) -> List[ProviderMetricValue]:
        """Read measures.

        Args:
            metrics (Optional[Sequence[ProviderMetric]]): Only these metrics, all of them when `None`.
            providers (Optional[Sequence[CloudProvider]]): Only these providers, all of them when `None` or empty.

        Returns:
            List[ProviderMetricValue]: The measures, by provider, quarter, metric and source.

        Raises:
            StorageReadError: If the measures cannot be read.
        """
        table = self.table
        statement = select(table).order_by(table.c.provider, table.c.period, table.c.metric, table.c.source)
        if metrics:
            statement = statement.where(table.c.metric.in_([metric.value for metric in metrics]))
        if providers:
            statement = statement.where(table.c.provider.in_([provider.value for provider in providers]))
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The provider metrics cannot be read: %s", e)
            raise StorageReadError("provider metrics", str(e)) from e
        known = {provider.value for provider in CloudProvider}
        values = [ProviderMetricValue.model_validate(dict(row)) for row in rows if row["provider"] in known]
        self.logger.debug("%d provider metrics read.", len(values))
        return values
