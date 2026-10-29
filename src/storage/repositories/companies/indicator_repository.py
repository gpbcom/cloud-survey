from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Tuple, Union

# Third Party Imports.
from sqlalchemy import Table, delete, func, select
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.companies.enums import CompanyIndicator, FinancialGranularity
from models.companies.values.indicator_value import IndicatorValue
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.mappers.row_store import RowStore
from storage.tables.base import Base
from storage.tables.companies.financials.company_indicator_row import CompanyIndicatorRow

type IndicatorKey = Tuple[str, str, date, str]
type CoverageKey = Tuple[str, str, str]
type IndicatorRow = Dict[str, Optional[Union[str, float, date]]]


class CompanyIndicatorRepository:
    """Read and write the time series of the companies' indicators.

    Attributes:
        CHUNK (int): The rows written per statement.
        database (Database): The open database.
        table (Table): The `company_indicators` table.
        rows (RowStore[IndicatorValue]): The single-point operations on the table.
        logger (Logger): The repository logger.

    Notes:
        The indicators are derived from the stored statements, prices, patents and papers: a run replaces the
        indicators it derived for the companies it read, each point keyed by its period end and granularity.
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
        self.table: Table = Base.metadata.tables[CompanyIndicatorRow.__tablename__]
        self.rows = RowStore(database, self.table, IndicatorValue, "company indicator point")
        self.logger.debug("Repository of the company indicators ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _rows(self, values: Sequence[IndicatorValue]) -> List[IndicatorRow]:
        """Write the points as rows, each key once (the last point wins).

        Args:
            values (Sequence[IndicatorValue]): The points.

        Returns:
            List[IndicatorRow]: The rows.
        """
        unique: Dict[IndicatorKey, IndicatorValue] = {
            (value.company, value.indicator.value, value.period_end, value.granularity.value): value for value in values
        }
        return [
            {
                "company": value.company,
                "indicator": value.indicator.value,
                "period_end": value.period_end,
                "granularity": value.granularity.value,
                "value": value.value,
                "unit": value.unit.value,
                "currency": value.currency,
                "value_usd": value.value_usd,
                "inputs": value.inputs,
            }
            for value in unique.values()
        ]

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: IndicatorValue) -> IndicatorValue:
        """Insert one indicator point.

        Args:
            value (IndicatorValue): The point.

        Returns:
            IndicatorValue: The point, as stored.

        Raises:
            StorageWriteError: If a point has the same company, indicator, period end and granularity.
        """
        self.logger.debug("Creating a %s point of %s.", value.indicator.value, value.company)
        return await self.rows.create(value)

    async def read(
        self, company: str, indicator: CompanyIndicator, period_end: date, granularity: FinancialGranularity
    ) -> Optional[IndicatorValue]:
        """Read one indicator point.

        Args:
            company (str): The company.
            indicator (CompanyIndicator): The indicator.
            period_end (date): The last day of the period.
            granularity (FinancialGranularity): The period length.

        Returns:
            Optional[IndicatorValue]: The point, `None` when there is none.

        Raises:
            StorageReadError: If the point cannot be read.
        """
        return await self.rows.read(
            {
                "company": company,
                "indicator": indicator.value,
                "period_end": period_end,
                "granularity": granularity.value,
            }
        )

    async def update(self, value: IndicatorValue) -> bool:
        """Replace one indicator point (that of the same company, indicator, period end and granularity).

        Args:
            value (IndicatorValue): The point.

        Returns:
            bool: Whether the point existed (none is created otherwise).

        Raises:
            StorageWriteError: If the point cannot be written.
        """
        self.logger.debug("Updating a %s point of %s.", value.indicator.value, value.company)
        return await self.rows.update(value)

    async def delete(
        self, company: str, indicator: CompanyIndicator, period_end: date, granularity: FinancialGranularity
    ) -> bool:
        """Delete one indicator point.

        Args:
            company (str): The company.
            indicator (CompanyIndicator): The indicator.
            period_end (date): The last day of the period.
            granularity (FinancialGranularity): The period length.

        Returns:
            bool: Whether a point was deleted.

        Raises:
            StorageWriteError: If the point cannot be deleted.
        """
        return await self.rows.delete(
            {
                "company": company,
                "indicator": indicator.value,
                "period_end": period_end,
                "granularity": granularity.value,
            }
        )

    async def replace(
        self, companies: Sequence[str], indicators: Sequence[CompanyIndicator], values: Sequence[IndicatorValue]
    ) -> int:
        """Replace the points of some indicators of some companies.

        Args:
            companies (Sequence[str]): The companies whose points are replaced.
            indicators (Sequence[CompanyIndicator]): The indicators replaced.
            values (Sequence[IndicatorValue]): The new points.

        Returns:
            int: The number of points written.

        Raises:
            StorageWriteError: If the points cannot be written.
        """
        rows = self._rows(values)
        table = self.table
        try:
            async with self.database.connect() as connection, connection.begin():
                if companies and indicators:
                    await connection.execute(
                        delete(table).where(
                            table.c.company.in_(list(companies)),
                            table.c.indicator.in_([indicator.value for indicator in indicators]),
                        )
                    )
                for start in range(0, len(rows), self.CHUNK):
                    statement = upsert(table).values(rows[start : start + self.CHUNK])
                    excluded = statement.excluded
                    await connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=[
                                table.c.company,
                                table.c.indicator,
                                table.c.period_end,
                                table.c.granularity,
                            ],
                            set_={
                                "value": excluded.value,
                                "unit": excluded.unit,
                                "currency": excluded.currency,
                                "value_usd": excluded.value_usd,
                                "inputs": excluded.inputs,
                                "computed_at": func.now(),
                            },
                        )
                    )
        except SQLAlchemyError as e:
            self.logger.error("The company indicators cannot be written: %s", e)
            raise StorageWriteError("company indicators", str(e)) from e
        self.logger.info("%d indicator points written for %d companies.", len(rows), len(companies))
        return len(rows)

    async def series(
        self,
        company: str,
        indicator: CompanyIndicator,
        granularity: Optional[FinancialGranularity] = None,
    ) -> List[IndicatorValue]:
        """Read the time series of an indicator of a company.

        Args:
            company (str): The company.
            indicator (CompanyIndicator): The indicator.
            granularity (Optional[FinancialGranularity]): Only this period, every one when `None`.

        Returns:
            List[IndicatorValue]: The points, by granularity then period, the oldest first.

        Raises:
            StorageReadError: If the points cannot be read.
        """
        table = self.table
        statement = (
            select(table)
            .where(table.c.company == company, table.c.indicator == indicator.value)
            .order_by(table.c.granularity, table.c.period_end)
        )
        if granularity is not None:
            statement = statement.where(table.c.granularity == granularity.value)
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The %s series of %s cannot be read: %s", indicator.value, company, e)
            raise StorageReadError("company indicators", str(e)) from e
        points = [IndicatorValue(**{key: row[key] for key in IndicatorValue.model_fields}) for row in rows]
        self.logger.debug("%d points of the %s series of %s read.", len(points), indicator.value, company)
        return points

    async def list(
        self,
        companies: Sequence[str],
        indicator: CompanyIndicator,
        granularities: Sequence[FinancialGranularity] = (),
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> List[IndicatorValue]:
        """List the time series of an indicator of several companies at once.

        Args:
            companies (Sequence[str]): The companies (none read when empty).
            indicator (CompanyIndicator): The indicator.
            granularities (Sequence[FinancialGranularity]): Only these periods, every one when empty.
            offset (int): The points skipped.
            limit (Optional[int]): The most points returned, every one when `None`.

        Returns:
            List[IndicatorValue]: The points, by company, granularity then period, the oldest first.

        Raises:
            StorageReadError: If the points cannot be read.
        """
        if not companies:
            self.logger.debug("No company asked: no %s point read.", indicator.value)
            return []
        table = self.table
        statement = (
            select(table)
            .where(table.c.company.in_(list(companies)), table.c.indicator == indicator.value)
            .order_by(table.c.company, table.c.granularity, table.c.period_end)
        )
        if granularities:
            statement = statement.where(table.c.granularity.in_([item.value for item in granularities]))
        statement = statement.offset(offset).limit(limit)
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The %s series of %d companies cannot be read: %s", indicator.value, len(companies), e)
            raise StorageReadError("company indicators", str(e)) from e
        points = [IndicatorValue(**{key: row[key] for key in IndicatorValue.model_fields}) for row in rows]
        if not points:
            self.logger.info("No %s point stored for %s.", indicator.value, ", ".join(companies))
        self.logger.debug("%d %s points of %d companies read.", len(points), indicator.value, len(companies))
        return points

    async def latest(self, companies: Sequence[str], indicators: Sequence[CompanyIndicator]) -> List[IndicatorValue]:
        """Read the latest point of each series of some companies and indicators.

        Args:
            companies (Sequence[str]): The companies (none read when empty).
            indicators (Sequence[CompanyIndicator]): The indicators (none read when empty).

        Returns:
            List[IndicatorValue]: The last point of each company, indicator and granularity.

        Raises:
            StorageReadError: If the points cannot be read.
        """
        if not companies or not indicators:
            self.logger.debug("No company or indicator asked: no latest point read.")
            return []
        table = self.table
        statement = (
            select(table)
            .where(table.c.company.in_(list(companies)), table.c.indicator.in_([item.value for item in indicators]))
            .distinct(table.c.company, table.c.indicator, table.c.granularity)
            .order_by(table.c.company, table.c.indicator, table.c.granularity, table.c.period_end.desc())
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The latest indicator points cannot be read: %s", e)
            raise StorageReadError("company indicators", str(e)) from e
        points = [IndicatorValue(**{key: row[key] for key in IndicatorValue.model_fields}) for row in rows]
        self.logger.debug("%d latest indicator points read.", len(points))
        return points

    async def coverage(self) -> Dict[CoverageKey, Tuple[date, date, int]]:
        """Get the stored span of every series.

        Returns:
            Dict[CoverageKey, Tuple[date, date, int]]: The first period, the last one and the number of points, by
                company, indicator and granularity.

        Raises:
            StorageReadError: If the points cannot be read.
        """
        table = self.table
        statement = select(
            table.c.company,
            table.c.indicator,
            table.c.granularity,
            func.min(table.c.period_end),
            func.max(table.c.period_end),
            func.count(),
        ).group_by(table.c.company, table.c.indicator, table.c.granularity)
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The coverage of the company indicators cannot be read: %s", e)
            raise StorageReadError("company indicators", str(e)) from e
        spans = {(str(row[0]), str(row[1]), str(row[2])): (row[3], row[4], int(row[5])) for row in rows}
        self.logger.debug("%d indicator series stored.", len(spans))
        return spans
