from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Tuple

# Third Party Imports.
from sqlalchemy import Table, delete, func, select
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.companies.enums import FinancialGranularity, FinancialMetric, FinancialSource
from models.companies.values.financial_value import FinancialValue
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.mappers.row_store import RowStore
from storage.tables.base import Base
from storage.tables.companies.financials.company_financial_row import CompanyFinancialRow

type FinancialKey = Tuple[str, str, date, str, str]
type DocumentKey = Tuple[str, str, date]
type Document = Tuple[FinancialSource, Optional[str], Optional[str]]


class CompanyFinancialRepository:
    """Read and write the statement lines of the companies, one per company, line, period and source.

    Attributes:
        CHUNK (int): The rows written per statement.
        PREFERENCE (Tuple[FinancialSource, ...]): The sources from the least to the most trusted (the document of a
            line is that of its most trusted source).
        database (Database): The open database.
        table (Table): The `company_financials` table.
        rows (RowStore[FinancialValue]): The single-line operations on the table.
        logger (Logger): The repository logger.

    Notes:
        A line is identified by its company, metric, period end, granularity and source: a crawl rewrites the
        periods it read (a restatement replaces the figure) and never deletes the others, so the history of a source
        showing only its last years grows run after run.
    """

    CHUNK = 2000
    PREFERENCE: Tuple[FinancialSource, ...] = (
        FinancialSource.REPORTED,
        FinancialSource.EDGAR_FDS,
        FinancialSource.GOOGLE_FINANCE,
        FinancialSource.EDGAR,
    )

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.logger = logger if logger else getLogger(__name__)
        self.table: Table = Base.metadata.tables[CompanyFinancialRow.__tablename__]
        self.rows = RowStore(database, self.table, FinancialValue, "company financial line")
        self.logger.debug("Repository of the company financials ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: FinancialValue) -> FinancialValue:
        """Insert one statement line.

        Args:
            value (FinancialValue): The line.

        Returns:
            FinancialValue: The line, as stored.

        Raises:
            StorageWriteError: If a line has the same company, metric, period end, granularity and source.
        """
        self.logger.debug("Creating the %s %s line of %s.", value.source.value, value.metric.value, value.company)
        return await self.rows.create(value)

    async def read(
        self,
        company: str,
        metric: FinancialMetric,
        period_end: date,
        granularity: FinancialGranularity,
        source: FinancialSource,
    ) -> Optional[FinancialValue]:
        """Read one statement line.

        Args:
            company (str): The company.
            metric (FinancialMetric): The line.
            period_end (date): The last day of the period.
            granularity (FinancialGranularity): The period length.
            source (FinancialSource): The source.

        Returns:
            Optional[FinancialValue]: The line, `None` when there is none.

        Raises:
            StorageReadError: If the line cannot be read.
        """
        return await self.rows.read(
            {
                "company": company,
                "metric": metric.value,
                "period_end": period_end,
                "granularity": granularity.value,
                "source": source.value,
            }
        )

    async def update(self, value: FinancialValue) -> bool:
        """Replace one statement line (that of the same company, metric, period end, granularity and source).

        Args:
            value (FinancialValue): The line.

        Returns:
            bool: Whether the line existed (none is created otherwise).

        Raises:
            StorageWriteError: If the line cannot be written.
        """
        self.logger.debug("Updating the %s %s line of %s.", value.source.value, value.metric.value, value.company)
        return await self.rows.update(value)

    async def delete(
        self,
        company: str,
        metric: FinancialMetric,
        period_end: date,
        granularity: FinancialGranularity,
        source: FinancialSource,
    ) -> bool:
        """Delete one statement line.

        Args:
            company (str): The company.
            metric (FinancialMetric): The line.
            period_end (date): The last day of the period.
            granularity (FinancialGranularity): The period length.
            source (FinancialSource): The source.

        Returns:
            bool: Whether a line was deleted.

        Raises:
            StorageWriteError: If the line cannot be deleted.
        """
        return await self.rows.delete(
            {
                "company": company,
                "metric": metric.value,
                "period_end": period_end,
                "granularity": granularity.value,
                "source": source.value,
            }
        )

    async def upsert(self, values: Sequence[FinancialValue]) -> int:
        """Write statement lines, replacing those of the same company, line, period and source.

        Args:
            values (Sequence[FinancialValue]): The lines.

        Returns:
            int: The number of lines written.

        Raises:
            StorageWriteError: If the lines cannot be written.
        """
        unique: Dict[FinancialKey, FinancialValue] = {
            (value.company, value.metric.value, value.period_end, value.granularity.value, value.source.value): value
            for value in values
        }
        rows = [
            {
                "company": value.company,
                "metric": value.metric.value,
                "period_end": value.period_end,
                "granularity": value.granularity.value,
                "source": value.source.value,
                "value": value.value,
                "currency": value.currency,
                "concept": value.concept,
                "form": value.form,
                "fiscal_year": value.fiscal_year,
                "fiscal_period": value.fiscal_period,
                "filed": value.filed,
                "source_url": value.source_url,
                "note": value.note,
            }
            for value in unique.values()
        ]
        if not rows:
            return 0
        table = self.table
        try:
            async with self.database.connect() as connection, connection.begin():
                for start in range(0, len(rows), self.CHUNK):
                    statement = upsert(table).values(rows[start : start + self.CHUNK])
                    excluded = statement.excluded
                    await connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=[
                                table.c.company,
                                table.c.metric,
                                table.c.period_end,
                                table.c.granularity,
                                table.c.source,
                            ],
                            set_={
                                "value": excluded.value,
                                "currency": excluded.currency,
                                "concept": excluded.concept,
                                "form": excluded.form,
                                "fiscal_year": excluded.fiscal_year,
                                "fiscal_period": excluded.fiscal_period,
                                "filed": excluded.filed,
                                "source_url": excluded.source_url,
                                "note": excluded.note,
                                "fetched_at": func.now(),
                            },
                        )
                    )
        except SQLAlchemyError as e:
            self.logger.error("The company financials cannot be written: %s", e)
            raise StorageWriteError("company financials", str(e)) from e
        self.logger.info("%d company financial lines written.", len(rows))
        return len(rows)

    async def replace(self, company: str, source: FinancialSource, values: Sequence[FinancialValue]) -> int:
        """Replace every line of a company from a source (a source restating its whole history each time).

        Args:
            company (str): The company.
            source (FinancialSource): The source.
            values (Sequence[FinancialValue]): The new lines (nothing is deleted when there is none).

        Returns:
            int: The number of lines written.

        Raises:
            StorageWriteError: If the lines cannot be written.
        """
        if not values:
            self.logger.warning("No %s line for %s: its stored lines are kept.", source.value, company)
            return 0
        table = self.table
        try:
            async with self.database.connect() as connection, connection.begin():
                removed = await connection.execute(
                    delete(table).where(table.c.company == company, table.c.source == source.value)
                )
        except SQLAlchemyError as e:
            self.logger.error("The %s lines of %s cannot be replaced: %s", source.value, company, e)
            raise StorageWriteError("company financials", str(e)) from e
        self.logger.debug("%d stored %s lines of %s removed.", removed.rowcount, source.value, company)
        return await self.upsert(values)

    async def delete_source(self, company: str, source: FinancialSource) -> int:
        """Delete every line of a company from a source (a researched company whose figures were all removed).

        Args:
            company (str): The company.
            source (FinancialSource): The source.

        Returns:
            int: The number of lines deleted.

        Raises:
            StorageWriteError: If the lines cannot be deleted.
        """
        table = self.table
        try:
            async with self.database.connect() as connection, connection.begin():
                removed = await connection.execute(
                    delete(table).where(table.c.company == company, table.c.source == source.value)
                )
        except SQLAlchemyError as e:
            self.logger.error("The %s lines of %s cannot be deleted: %s", source.value, company, e)
            raise StorageWriteError("company financials", str(e)) from e
        count = int(removed.rowcount or 0)
        if count:
            self.logger.info("%d %s lines of %s deleted.", count, source.value, company)
        else:
            self.logger.debug("No %s line of %s to delete.", source.value, company)
        return count

    async def documents(self, companies: Sequence[str]) -> Dict[DocumentKey, Document]:
        """Read where each stored line was read: the document, its source and its note.

        Args:
            companies (Sequence[str]): The companies (none read when empty).

        Returns:
            Dict[DocumentKey, Document]: The source, document and note of each line, by company, metric and period
                end (the filed sources preferred over the researched figures).

        Raises:
            StorageReadError: If the lines cannot be read.
        """
        if not companies:
            return {}
        table = self.table
        statement = select(
            table.c.company, table.c.metric, table.c.period_end, table.c.source, table.c.source_url, table.c.note
        ).where(table.c.company.in_(list(companies)))
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The documents of the company financials cannot be read: %s", e)
            raise StorageReadError("company financials", str(e)) from e
        documents: Dict[DocumentKey, Document] = {}
        for company, metric, end, source, url, note in rows:
            key = (str(company), str(metric), end)
            kept = documents.get(key)
            if kept is None or self.PREFERENCE.index(FinancialSource(source)) > self.PREFERENCE.index(kept[0]):
                documents[key] = (FinancialSource(source), url, note)
        self.logger.debug("%d documents of %d companies read.", len(documents), len(companies))
        return documents

    async def list(
        self, companies: Optional[Sequence[str]] = None, offset: int = 0, limit: Optional[int] = None
    ) -> List[FinancialValue]:
        """List statement lines.

        Args:
            companies (Optional[Sequence[str]]): Only these companies, every one when `None` or empty.
            offset (int): The lines skipped.
            limit (Optional[int]): The most lines returned, every one when `None`.

        Returns:
            List[FinancialValue]: The lines, by company, line, granularity, then period.

        Raises:
            StorageReadError: If the lines cannot be read.
        """
        table = self.table
        statement = select(table).order_by(table.c.company, table.c.metric, table.c.granularity, table.c.period_end)
        if companies:
            statement = statement.where(table.c.company.in_(list(companies)))
        statement = statement.offset(offset).limit(limit)
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The company financials cannot be read: %s", e)
            raise StorageReadError("company financials", str(e)) from e
        values = [
            FinancialValue(**{key: row[key] for key in FinancialValue.model_fields if key in row}) for row in rows
        ]
        self.logger.debug("%d company financial lines read.", len(values))
        return values
