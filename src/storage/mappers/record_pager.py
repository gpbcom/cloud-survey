from __future__ import annotations

# Standard Library Imports.
from datetime import date, datetime
from logging import Logger, getLogger
from typing import List, Mapping, Optional, Sequence, Tuple, Union

# Third Party Imports.
from sqlalchemy import ColumnElement, RowMapping, Select, UnaryExpression, func, or_, select
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.storage.records.enums import RecordSort
from models.storage.records.record_query import RecordQuery

type SortKey = ColumnElement[Union[str, int, float, bool, date, datetime]]
type RecordValue = Optional[Union[str, int, float, bool, date, datetime]]


class RecordPager:
    """Read one page of stored research records: the text filter, the order, the bounds and the count.

    Attributes:
        logger (Logger): The pager logger.

    Notes:
        - The records are sorted with the empty values last and the primary key after the column sorted by, so
          that two pages never overlap.
        - The records matching are counted only when the query asks for it (its first page): a count reads every
          record matching, a page only its own.
        - The text matches when one of the searched columns contains it, whatever the case (`%` and `_` are
          matched as such).
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the pager.

        Args:
            logger (Optional[Logger]): The pager logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _order(
        self,
        query: RecordQuery,
        sorts: Mapping[RecordSort, SortKey],
        default: RecordSort,
        keys: Sequence[SortKey],
    ) -> List[UnaryExpression[Union[str, int, float, bool, date, datetime]]]:
        """Build the order of a page.

        Args:
            query (RecordQuery): The query.
            sorts (Mapping[RecordSort, SortKey]): The columns the dataset can be sorted by.
            default (RecordSort): The column sorted by when the query names none of the dataset's.
            keys (Sequence[SortKey]): The primary key of the dataset.

        Returns:
            List[UnaryExpression[Union[str, int, float, bool, date, datetime]]]: The order, the primary key last.
        """
        sort = query.sort if query.sort is not None and query.sort in sorts else default
        if query.sort is not None and sort is not query.sort:
            self.logger.warning("The records cannot be sorted by %s: sorted by %s.", query.sort.value, sort.value)
        columns = [sorts[sort], *(key for key in keys if key is not sorts[sort])]
        return [column.desc().nulls_last() if query.descending else column.asc().nulls_last() for column in columns]

    ############################
    # Publicly Exposed Methods #
    ############################

    async def read(
        self,
        connection: AsyncConnection,
        statement: Select[Tuple[RecordValue, ...]],
        query: RecordQuery,
        sorts: Mapping[RecordSort, SortKey],
        default: RecordSort,
        keys: Sequence[SortKey],
        searched: Sequence[ColumnElement[str]],
    ) -> Tuple[Sequence[RowMapping], Optional[int]]:
        """Read one page of records.

        Args:
            connection (AsyncConnection): The open connection.
            statement (Select[Tuple[RecordValue, ...]]): The records of the companies asked, unordered and unbounded.
            query (RecordQuery): The text, the order and the bounds of the page.
            sorts (Mapping[RecordSort, SortKey]): The columns the dataset can be sorted by.
            default (RecordSort): The column sorted by when the query names none of the dataset's.
            keys (Sequence[SortKey]): The primary key of the dataset.
            searched (Sequence[ColumnElement[str]]): The columns the text is looked for in.

        Returns:
            Tuple[Sequence[RowMapping], Optional[int]]: The rows of the page, then the records matching (`None`
                when not counted).

        Raises:
            SQLAlchemyError: If the records cannot be read (the repository reports it).
        """
        if query.text and searched:
            statement = statement.where(or_(*(column.icontains(query.text, autoescape=True) for column in searched)))
        total: Optional[int] = None
        if query.with_total:
            counted = select(func.count()).select_from(statement.order_by(None).subquery())
            total = int((await connection.execute(counted)).scalar_one())
        page = statement.order_by(*self._order(query, sorts, default, keys)).offset(query.offset).limit(query.limit)
        rows = (await connection.execute(page)).mappings().all()
        self.logger.debug(
            "%d records read from %d (%s matching).", len(rows), query.offset, "?" if total is None else total
        )
        return rows, total
