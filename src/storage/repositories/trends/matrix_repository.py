from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence

# Third Party Imports.
from sqlalchemy import ColumnElement, Row, Select, distinct, func, literal_column, select
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.storage.enums import DatasetKind
from models.storage.pages.item_query import ItemQuery
from models.trends.enums import MatrixCell, SeriesGrouping
from models.trends.matrix.metric_matrix import MetricMatrix
from storage.engine.database import Database
from storage.exception import StorageReadError
from storage.mappers.item_query_builder import ItemQueryBuilder
from storage.repositories.trends.trend_statements import TrendStatements
from storage.tables.base import Base
from storage.tables.datasets.crawl_row import CrawlRow
from storage.tables.items.product_row import ProductRow
from storage.tables.items.software_row import SoftwareRow

CellRow = Row[str, str, int]


class MatrixRepository:
    """Read the matrices of the listed marketplace software: counts per row and column grouping.

    Attributes:
        LIMIT (ClassVar[int]): The default largest number of rows and columns kept, the largest first.
        database (Database): The open database.
        statements (TrendStatements): The statement builder of the software table.
        builder (ItemQueryBuilder): The filter builder of the software table.
        product_statements (TrendStatements): The statement builder of the products table.
        product_builder (ItemQueryBuilder): The filter builder of the products table.
        logger (Logger): The repository logger.

    Notes:
        - The cells count the software, or the catalogue products (`kind`), which have no publisher.
        - Only the listed software is counted, whatever the query says about the deleted ones.
        - The publishers are compared case and spaces aside.
    """

    LIMIT: ClassVar[int] = 12

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.database = database
        tables = Base.metadata.tables
        software = tables[SoftwareRow.__tablename__]
        self.statements = TrendStatements(software, tables[CrawlRow.__tablename__], self.logger)
        self.builder = ItemQueryBuilder(software, self.logger)
        products = tables[ProductRow.__tablename__]
        self.product_statements = TrendStatements(products, tables[CrawlRow.__tablename__], self.logger)
        self.product_builder = ItemQueryBuilder(products, self.logger)
        self.logger.debug("Repository of the marketplace matrices ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _conditions(self, query: ItemQuery, builder: Optional[ItemQueryBuilder] = None) -> List[ColumnElement[bool]]:
        """Build the filters of a query, on the listed items only.

        Args:
            query (ItemQuery): The query.
            builder (Optional[ItemQueryBuilder]): The filter builder of the items table, the software one by default.

        Returns:
            List[ColumnElement[bool]]: The conditions the items must meet.
        """
        chosen = builder if builder is not None else self.builder
        return chosen.filters(query.model_copy(update={"include_deleted": False}))

    def _publisher(self) -> ColumnElement[str]:
        """Get the publisher of the software, compared case and spaces aside.

        Returns:
            ColumnElement[str]: The normalized publisher expression.
        """
        return func.lower(func.trim(self.statements.table.c.publisher))

    def _largest(self, totals: Dict[str, float], limit: Optional[int]) -> List[str]:
        """Keep the largest keys.

        Args:
            totals (Dict[str, float]): The total of each key.
            limit (Optional[int]): The largest number of keys kept, `None` to keep every key.

        Returns:
            List[str]: The kept keys, the largest first.
        """
        ordered = sorted(totals, key=lambda key: (-totals[key], key))
        return ordered if limit is None else ordered[:limit]

    async def _read(self, statement: Select[str, str, int], what: str) -> Sequence[CellRow]:
        """Run a matrix statement.

        Args:
            statement (Select[str, str, int]): The row key, column key and count statement.
            what (str): What is counted, for the logs and errors.

        Returns:
            Sequence[CellRow]: The rows.

        Raises:
            StorageReadError: If the software cannot be counted.
        """
        try:
            async with self.database.connect() as connection:
                return (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The %s cannot be counted: %s", what, e)
            raise StorageReadError(what, str(e)) from e

    ############################
    # Publicly Exposed Methods #
    ############################

    async def cells(
        self,
        query: ItemQuery,
        rows: SeriesGrouping,
        columns: SeriesGrouping,
        cell: MatrixCell,
        limit: Optional[int] = LIMIT,
        kind: DatasetKind = DatasetKind.MARKETPLACE,
    ) -> MetricMatrix:
        """Count the listed software (or their publishers), or the listed products, of each row and column.

        Args:
            query (ItemQuery): The filters of the software.
            rows (SeriesGrouping): The grouping of the rows.
            columns (SeriesGrouping): The grouping of the columns (another one).
            cell (MatrixCell): `LISTED`, `ROW_SHARE` or `PUBLISHERS`.
            limit (Optional[int]): The largest number of rows and columns kept, `None` to keep every one.
            kind (DatasetKind): The items counted: the marketplace software or the catalogue products (which have no
                publisher: `PUBLISHERS` counts nothing for them).

        Returns:
            MetricMatrix: The cells of the largest rows and columns, the row shares computed over every column.

        Raises:
            StorageReadError: If the software cannot be counted.
        """
        products = kind is DatasetKind.CATALOGUE
        statements = self.product_statements if products else self.statements
        source, row_key, column_key = statements.keys(rows, columns)
        publisher: ColumnElement[str] = literal_column("NULL") if products else self._publisher()
        base = (
            select(
                row_key.label("row"),
                (column_key if column_key is not None else row_key).label("column"),
                publisher.label("publisher"),
            )
            .select_from(source)
            .where(*self._conditions(query, self.product_builder if products else None))
            .subquery()
        )
        value = func.count(distinct(base.c.publisher)) if cell is MatrixCell.PUBLISHERS else func.count()
        statement = select(base.c.row, base.c.column, value).group_by(base.c.row, base.c.column)
        found = await self._read(statement, f"{kind.value} matrix")
        counts: Dict[str, Dict[str, float]] = {}
        for row, column, count in found:
            if row is not None and column is not None:
                counts.setdefault(str(row), {})[str(column)] = float(count)
        row_totals = {row: sum(values.values()) for row, values in counts.items()}
        column_totals: Dict[str, float] = {}
        for values in counts.values():
            for column, amount in values.items():
                column_totals[column] = column_totals.get(column, 0.0) + amount
        kept_rows, kept_columns = self._largest(row_totals, limit), self._largest(column_totals, limit)
        cells = {
            row: {
                column: counts[row][column] / row_totals[row] * 100
                if cell is MatrixCell.ROW_SHARE
                else counts[row][column]
                for column in kept_columns
                if column in counts[row]
            }
            for row in kept_rows
        }
        self.logger.debug(
            "Marketplace matrix counted: %d rows by %d columns (%s).", len(kept_rows), len(kept_columns), cell.value
        )
        return MetricMatrix(
            rows=kept_rows,
            columns=kept_columns,
            cells=cells,
            total_rows=len(row_totals),
            total_columns=len(column_totals),
        )

    async def publisher_overlap(self, query: ItemQuery, jaccard: bool, limit: Optional[int] = LIMIT) -> MetricMatrix:
        """Count the publishers listed by each pair of marketplaces.

        Args:
            query (ItemQuery): The filters of the software.
            jaccard (bool): Whether the cells are the Jaccard overlap (shared publishers over the publishers of
                either marketplace, in percent) rather than the number of shared publishers.
            limit (Optional[int]): The largest number of marketplaces kept, those with the most publishers first,
                `None` to keep every marketplace.

        Returns:
            MetricMatrix: The marketplaces by marketplaces, the diagonal holding each marketplace's own publishers
                (100% for the overlap).

        Raises:
            StorageReadError: If the publishers cannot be counted.
        """
        table = self.statements.table
        publisher = self._publisher()
        listed = (
            select(table.c.provider.label("provider"), publisher.label("publisher"))
            .where(*self._conditions(query), table.c.publisher.is_not(None), func.trim(table.c.publisher) != "")
            .distinct()
        )
        first, second = listed.subquery("first"), listed.subquery("second")
        statement = (
            select(first.c.provider, second.c.provider, func.count())
            .select_from(first.join(second, first.c.publisher == second.c.publisher))
            .group_by(first.c.provider, second.c.provider)
        )
        found = await self._read(statement, "marketplace publishers")
        shared: Dict[str, Dict[str, float]] = {}
        for left, right, count in found:
            shared.setdefault(str(left), {})[str(right)] = float(count)
        totals = {provider: values.get(provider, 0.0) for provider, values in shared.items()}
        kept = self._largest(totals, limit)
        cells: Dict[str, Dict[str, float]] = {}
        for left in kept:
            cells[left] = {}
            for right in kept:
                common = shared[left].get(right, 0.0)
                union = totals[left] + totals[right] - common
                cells[left][right] = (common / union * 100 if union else 0.0) if jaccard else common
        self.logger.debug("Publisher overlap of %d marketplaces counted.", len(kept))
        return MetricMatrix(rows=kept, columns=kept, cells=cells, total_rows=len(totals), total_columns=len(totals))
