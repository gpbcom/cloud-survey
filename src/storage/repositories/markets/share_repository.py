from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Tuple

# Third Party Imports.
from sqlalchemy import Table, delete, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.markets.enums import Device, Granularity, ShareMetric, ShareSource
from models.markets.values.market_share_value import MarketShareValue
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.tables.base import Base
from storage.tables.markets.market_share_row import MarketShareRow


class MarketShareRepository:
    """Read and write the market shares of the companies, by segment, area, device and period.

    Attributes:
        CHUNK (int): The rows written per statement.
        database (Database): The open database.
        table (Table): The `market_shares` table.
        logger (Logger): The repository logger.

    Notes:
        A share is identified by its segment, area, period, granularity, device, metric, source and label: a crawl
        writes the months it read again (StatCounter revises the last one), the other months are kept.
    """

    CHUNK = 2000

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.logger = logger if logger else getLogger(__name__)
        self.table: Table = Base.metadata.tables[MarketShareRow.__tablename__]
        self.logger.debug("Repository of the market shares ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def upsert(self, values: Sequence[MarketShareValue]) -> int:
        """Write shares, replacing those with the same key.

        Args:
            values (Sequence[MarketShareValue]): The shares.

        Returns:
            int: The number of shares written.

        Raises:
            StorageWriteError: If the shares cannot be written.
        """
        unique: Dict[Tuple[str, str, date, str, str, str, str, str], MarketShareValue] = {
            (
                v.segment,
                v.area,
                v.period,
                v.granularity.value,
                v.device.value,
                v.metric.value,
                v.source.value,
                v.label,
            ): v
            for v in values
        }
        rows = [
            {
                "segment": value.segment,
                "area": value.area,
                "period": value.period,
                "device": value.device.value,
                "metric": value.metric.value,
                "source": value.source.value,
                "label": value.label,
                "granularity": value.granularity.value,
                "company": value.company,
                "value": value.value,
                "estimate": value.estimate,
                "source_url": value.source_url,
            }
            for value in unique.values()
        ]
        if not rows:
            return 0
        table = self.table
        keys = [
            table.c.segment,
            table.c.area,
            table.c.period,
            table.c.granularity,
            table.c.device,
            table.c.metric,
            table.c.source,
        ]
        try:
            async with self.database.connect() as connection, connection.begin():
                for start in range(0, len(rows), self.CHUNK):
                    statement = upsert(table).values(rows[start : start + self.CHUNK])
                    await connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=[*keys, table.c.label],
                            set_={
                                "company": statement.excluded.company,
                                "value": statement.excluded.value,
                                "estimate": statement.excluded.estimate,
                                "source_url": statement.excluded.source_url,
                                "fetched_at": func.now(),
                            },
                        )
                    )
        except SQLAlchemyError as e:
            self.logger.error("The market shares cannot be written: %s", e)
            raise StorageWriteError("market shares", str(e)) from e
        self.logger.info("%d market shares written.", len(rows))
        return len(rows)

    async def replace_periods(self, values: Sequence[MarketShareValue]) -> int:
        """Write shares, replacing every stored share of the periods they cover (a release's table is a whole).

        Args:
            values (Sequence[MarketShareValue]): The shares.

        Returns:
            int: The number of shares written.

        Raises:
            StorageWriteError: If the shares cannot be replaced.

        Notes:
            A period is a segment, an area, a period and its granularity, a device, a metric and a source: the labels
            a previous crawl stored for it (another release's top 5) are deleted, so that a period never mixes two
            releases.
        """
        table = self.table
        periods = {
            (v.segment, v.area, v.period, v.granularity.value, v.device.value, v.metric.value, v.source.value)
            for v in values
        }
        if not periods:
            return 0
        columns = tuple_(
            table.c.segment,
            table.c.area,
            table.c.period,
            table.c.granularity,
            table.c.device,
            table.c.metric,
            table.c.source,
        )
        try:
            async with self.database.connect() as connection, connection.begin():
                await connection.execute(delete(table).where(columns.in_(list(periods))))
        except SQLAlchemyError as e:
            self.logger.error("The market shares of %d periods cannot be replaced: %s", len(periods), e)
            raise StorageWriteError("market shares", str(e)) from e
        written = await self.upsert(values)
        self.logger.info("%d periods of market shares replaced: %d shares.", len(periods), written)
        return written

    async def read(
        self,
        segment: str,
        area: str,
        device: Device = Device.ALL,
        metric: Optional[ShareMetric] = None,
        source: Optional[ShareSource] = None,
        companies: Optional[Sequence[str]] = None,
    ) -> List[MarketShareValue]:
        """Read the shares of a segment in an area, on a device.

        Args:
            segment (str): The segment.
            area (str): The area.
            device (Device): The devices measured.
            metric (Optional[ShareMetric]): Only this metric, every one when `None`.
            source (Optional[ShareSource]): Only this source, every one when `None`.
            companies (Optional[Sequence[str]]): Only the labels of these companies, every label when `None` or
                empty.

        Returns:
            List[MarketShareValue]: The shares, by period then label.

        Raises:
            StorageReadError: If the shares cannot be read.
        """
        table = self.table
        columns = [column for column in table.c if column.name != "fetched_at"]
        statement = (
            select(*columns)
            .where(table.c.segment == segment, table.c.area == area, table.c.device == device.value)
            .order_by(table.c.period, table.c.label)
        )
        if metric is not None:
            statement = statement.where(table.c.metric == metric.value)
        if source is not None:
            statement = statement.where(table.c.source == source.value)
        if companies:
            statement = statement.where(table.c.company.in_(list(companies)))
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The market shares of %s in %s cannot be read: %s", segment, area, e)
            raise StorageReadError("market shares", str(e)) from e
        values = [MarketShareValue.model_validate(dict(row)) for row in rows]
        self.logger.debug("%d market shares read for %s in %s (%s).", len(values), segment, area, device.value)
        return values

    async def areas_with_data(self, segment: str) -> Dict[str, int]:
        """Count the stored shares of a segment in each area.

        Args:
            segment (str): The segment.

        Returns:
            Dict[str, int]: The number of shares by area, the areas without any left out.

        Raises:
            StorageReadError: If the shares cannot be counted.
        """
        table = self.table
        statement = select(table.c.area, func.count()).where(table.c.segment == segment).group_by(table.c.area)
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The market shares of %s cannot be counted: %s", segment, e)
            raise StorageReadError("market shares", str(e)) from e
        counts = {str(row[0]): int(row[1]) for row in rows}
        self.logger.debug("Market shares of %s stored in %d areas.", segment, len(counts))
        return counts

    async def months(self) -> Dict[Tuple[str, str, str], List[date]]:
        """Get the months with monthly shares of every segment, area and device (the coverage of the guide).

        Returns:
            Dict[Tuple[str, str, str], List[date]]: The months with figures, by segment, area and device.

        Raises:
            StorageReadError: If the shares cannot be read.
        """
        table = self.table
        statement = (
            select(table.c.segment, table.c.area, table.c.device, table.c.period)
            .where(table.c.granularity == Granularity.MONTH.value)
            .group_by(table.c.segment, table.c.area, table.c.device, table.c.period)
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The months of the market shares cannot be read: %s", e)
            raise StorageReadError("market shares", str(e)) from e
        months: Dict[Tuple[str, str, str], List[date]] = {}
        for segment, area, device, period in rows:
            months.setdefault((str(segment), str(area), str(device)), []).append(period)
        self.logger.debug("Months of %d share series read.", len(months))
        return months

    async def quarters(self) -> Dict[Tuple[str, str, str], List[date]]:
        """Get the quarters with quarterly shares of every segment, area and source (the coverage of the guide).

        Returns:
            Dict[Tuple[str, str, str], List[date]]: The quarters with figures, by segment, area and source.

        Raises:
            StorageReadError: If the shares cannot be read.

        Notes:
            The press releases (TrendForce, IDC), Synergy and the dossier publish quarters, each source its own
            series: they are counted apart, never merged with another source.
        """
        table = self.table
        statement = (
            select(table.c.segment, table.c.area, table.c.source, table.c.period)
            .where(table.c.granularity == Granularity.QUARTER.value)
            .group_by(table.c.segment, table.c.area, table.c.source, table.c.period)
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The quarters of the market shares cannot be read: %s", e)
            raise StorageReadError("market shares", str(e)) from e
        quarters: Dict[Tuple[str, str, str], List[date]] = {}
        for segment, area, source, period in rows:
            quarters.setdefault((str(segment), str(area), str(source)), []).append(period)
        self.logger.debug("Quarters of %d share series read.", len(quarters))
        return quarters
