from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from sqlalchemy import (
    ColumnElement,
    FromClause,
    Select,
    Table,
    case,
    func,
    literal,
    literal_column,
    select,
    true,
    union_all,
)

# First Party Imports.
from models.cloud.enums import CloudProvider, GeoBloc, SoftwareAudience, SoftwareCategory
from models.trends.enums import ChartMetric, SeriesGrouping


class TrendStatements:
    """Build the SQL statements of the chart trends of an items table: counts per series key and calendar bucket.

    Attributes:
        GRAINS (ClassVar[Dict[ChartMetric, str]]): The `date_trunc` unit of each calendar bucket.
        table (Table): The items table (products or software).
        crawls (Table): The crawls table, dating the items without a published added date.
        logger (Logger): The builder logger.

    Notes:
        - An item without a published added date is dated by the crawl which first found it, so that the running
          totals reach the number of items listed today.
        - The buckets are truncated in UTC and named by their first day, the series keys by their grouping value.
        - The keys and buckets are computed in a subquery and grouped outside of it: grouping on expressions with
          bound parameters (the bloc of each provider) would not match them.
    """

    GRAINS: ClassVar[Dict[ChartMetric, str]] = {
        ChartMetric.YEAR: "year",
        ChartMetric.QUARTER: "quarter",
        ChartMetric.MONTH: "month",
    }

    def __init__(self, table: Table, crawls: Table, logger: Optional[Logger] = None) -> None:
        """Initialize the builder.

        Args:
            table (Table): The items table.
            crawls (Table): The crawls table.
            logger (Optional[Logger]): The builder logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.table = table
        self.crawls = crawls

    ############################
    # Internal Helpers Methods #
    ############################

    def _added_at(self) -> ColumnElement[datetime]:
        """Get when each item was added: its published date, or when it was first crawled.

        Returns:
            ColumnElement[datetime]: The added date expression.
        """
        return func.coalesce(self.table.c.added_at, self.crawls.c.started_at)

    def _bucket(self, moment: ColumnElement[datetime], grain: ChartMetric) -> ColumnElement[datetime]:
        """Truncate a date to its calendar bucket, in UTC.

        Args:
            moment (ColumnElement[datetime]): The date expression.
            grain (ChartMetric): The bucket: `YEAR`, `QUARTER` or `MONTH`.

        Returns:
            ColumnElement[datetime]: The first moment of the bucket.
        """
        unit: ColumnElement[str] = literal_column(f"'{self.GRAINS[grain]}'")
        return func.date_trunc(unit, func.timezone(literal_column("'UTC'"), moment))

    def _grouping_key(self, grouping: SeriesGrouping, source: FromClause) -> Tuple[FromClause, ColumnElement[str]]:
        """Get the series key of each item for a grouping.

        Args:
            grouping (SeriesGrouping): `PROVIDER`, `BLOC`, `DELIVERY` or `TYPE` (the last two for software only),
                `AUDIENCE`, `CATEGORY` or `DOMAIN`.
            source (FromClause): The rows the key is read from.

        Returns:
            Tuple[FromClause, ColumnElement[str]]: The rows (with one row per type, category or domain of an item
                when grouping by them)
                and the key expression (the audience of a software: developer tool only, end-user software only, or
                both).
        """
        columns = self.table.c
        match grouping:
            case SeriesGrouping.BLOC:
                blocs = {provider.value: provider.bloc.value for provider in CloudProvider}
                return source, case(blocs, value=columns.provider, else_=literal(GeoBloc.OTHER.value))
            case SeriesGrouping.DELIVERY:
                return source, columns.delivery
            case SeriesGrouping.CATEGORY:
                category = func.unnest(columns.service_categories).table_valued("category").render_derived()
                return source.join(category, true()), category.c.category
            case SeriesGrouping.DOMAIN:
                domain = func.unnest(columns.service_domains).table_valued("domain").render_derived()
                return source.join(domain, true()), domain.c.domain
            case SeriesGrouping.AUDIENCE:
                developer, end_user = SoftwareCategory.DEVELOPER_TOOL.value, SoftwareCategory.END_USER_SOFTWARE.value
                audience = case(
                    (columns.categories.contains([developer, end_user]), literal(SoftwareAudience.BOTH.value)),
                    (columns.categories.contains([developer]), literal(SoftwareAudience.DEVELOPER_TOOL.value)),
                    else_=literal(SoftwareAudience.END_USER_SOFTWARE.value),
                )
                return source, audience
            case _:
                return source, columns.provider

    def _facet_column(self, facet_key: Optional[ColumnElement[str]]) -> ColumnElement[str]:
        """Get the facet key of each item, an empty text without facets.

        Args:
            facet_key (Optional[ColumnElement[str]]): The key expression of the facet grouping, `None` without facets.

        Returns:
            ColumnElement[str]: The facet key expression (a constant without facets, never a bound parameter).
        """
        return facet_key if facet_key is not None else literal_column("''")

    ############################
    # Publicly Exposed Methods #
    ############################

    def source(self) -> FromClause:
        """Get the items with the crawl which first found them.

        Returns:
            FromClause: The items outer-joined to their first crawl.
        """
        return self.table.outerjoin(self.crawls, self.crawls.c.id == self.table.c.first_crawl_id)

    def keys(
        self, rows: SeriesGrouping, columns: Optional[SeriesGrouping] = None
    ) -> Tuple[FromClause, ColumnElement[str], Optional[ColumnElement[str]]]:
        """Get the series key (and matrix column key) of each item.

        Args:
            rows (SeriesGrouping): The grouping of the series (or matrix rows).
            columns (Optional[SeriesGrouping]): The grouping of the matrix columns, `None` for series.

        Returns:
            Tuple[FromClause, ColumnElement[str], Optional[ColumnElement[str]]]: The rows to read, the row key and the
                column key expressions.
        """
        source, row = self._grouping_key(rows, self.source())
        column: Optional[ColumnElement[str]] = None
        if columns is not None:
            source, column = self._grouping_key(columns, source)
        return source, row, column

    def events(
        self,
        grouping: SeriesGrouping,
        grain: ChartMetric,
        conditions: List[ColumnElement[bool]],
        deleted: bool,
        facet: Optional[SeriesGrouping] = None,
    ) -> Select[str, str, datetime, int]:
        """Count the items added (or deleted) per facet, series key and bucket.

        Args:
            grouping (SeriesGrouping): The grouping of the series.
            grain (ChartMetric): The calendar bucket.
            conditions (List[ColumnElement[bool]]): The filters the items must meet.
            deleted (bool): Whether the deletions are counted rather than the additions.
            facet (Optional[SeriesGrouping]): The grouping of the facets (one small chart each), `None` for none.

        Returns:
            Select[str, str, datetime, int]: The facet (empty without facets), key, bucket and count rows.
        """
        source, key, facet_key = self.keys(grouping, facet)
        moment = self.table.c.deleted_at if deleted else self._added_at()
        filters = [*conditions, self.table.c.deleted_at.is_not(None)] if deleted else conditions
        inner = (
            select(
                self._facet_column(facet_key).label("facet"),
                key.label("key"),
                self._bucket(moment, grain).label("bucket"),
            )
            .select_from(source)
            .where(*filters)
            .subquery()
        )
        return select(inner.c.facet, inner.c.key, inner.c.bucket, func.count().label("value")).group_by(
            inner.c.facet, inner.c.key, inner.c.bucket
        )

    def listed(
        self,
        grouping: SeriesGrouping,
        grain: ChartMetric,
        conditions: List[ColumnElement[bool]],
        facet: Optional[SeriesGrouping] = None,
    ) -> Select[str, str, datetime, int]:
        """Count the items listed at the end of each bucket, per facet and series key.

        Args:
            grouping (SeriesGrouping): The grouping of the series.
            grain (ChartMetric): The calendar bucket.
            conditions (List[ColumnElement[bool]]): The filters the items must meet (deleted ones included).
            facet (Optional[SeriesGrouping]): The grouping of the facets (one small chart each), `None` for none.

        Returns:
            Select[str, str, datetime, int]: The facet (empty without facets), key, bucket and running total rows, for
                the buckets where the total changed.

        Notes:
            The listed items are the running total of the additions minus the deletions.
        """
        source, key, facet_key = self.keys(grouping, facet)
        facet_column = self._facet_column(facet_key)
        deleted_at = self.table.c.deleted_at
        added = (
            select(
                facet_column.label("facet"),
                key.label("key"),
                self._bucket(self._added_at(), grain).label("bucket"),
                literal(1).label("delta"),
            )
            .select_from(source)
            .where(*conditions)
        )
        removed = (
            select(
                facet_column.label("facet"),
                key.label("key"),
                self._bucket(deleted_at, grain).label("bucket"),
                literal(-1).label("delta"),
            )
            .select_from(source)
            .where(*conditions, deleted_at.is_not(None))
        )
        changes = union_all(added, removed).subquery()
        per_bucket = (
            select(changes.c.facet, changes.c.key, changes.c.bucket, func.sum(changes.c.delta).label("delta"))
            .group_by(changes.c.facet, changes.c.key, changes.c.bucket)
            .subquery()
        )
        total = func.sum(per_bucket.c.delta).over(
            partition_by=(per_bucket.c.facet, per_bucket.c.key), order_by=per_bucket.c.bucket
        )
        return select(per_bucket.c.facet, per_bucket.c.key, per_bucket.c.bucket, total.label("value"))

    def publishers(
        self,
        grouping: SeriesGrouping,
        grain: ChartMetric,
        conditions: List[ColumnElement[bool]],
        facet: Optional[SeriesGrouping] = None,
    ) -> Select[str, str, datetime, int]:
        """Count the distinct publishers ever listed at the end of each bucket, per facet and series key.

        Args:
            grouping (SeriesGrouping): The grouping of the series.
            grain (ChartMetric): The calendar bucket.
            conditions (List[ColumnElement[bool]]): The filters the software must meet.
            facet (Optional[SeriesGrouping]): The grouping of the facets (one small chart each), `None` for none.

        Returns:
            Select[str, str, datetime, int]: The facet (empty without facets), key, bucket and running total rows.

        Notes:
            A publisher counts from the first software it listed, case and spaces aside, and is never removed.
        """
        source, key, facet_key = self.keys(grouping, facet)
        publisher = self.table.c.publisher
        listings = (
            select(
                self._facet_column(facet_key).label("facet"),
                key.label("key"),
                func.lower(func.trim(publisher)).label("publisher"),
                self._added_at().label("moment"),
            )
            .select_from(source)
            .where(*conditions, publisher.is_not(None), func.trim(publisher) != "")
            .subquery()
        )
        first = (
            select(listings.c.facet, listings.c.key, listings.c.publisher, func.min(listings.c.moment).label("moment"))
            .group_by(listings.c.facet, listings.c.key, listings.c.publisher)
            .subquery()
        )
        bucketed = select(first.c.facet, first.c.key, self._bucket(first.c.moment, grain).label("bucket")).subquery()
        per_bucket = (
            select(bucketed.c.facet, bucketed.c.key, bucketed.c.bucket, func.count().label("count"))
            .group_by(bucketed.c.facet, bucketed.c.key, bucketed.c.bucket)
            .subquery()
        )
        total = func.sum(per_bucket.c.count).over(
            partition_by=(per_bucket.c.facet, per_bucket.c.key), order_by=per_bucket.c.bucket
        )
        return select(per_bucket.c.facet, per_bucket.c.key, per_bucket.c.bucket, total.label("value"))

    def undated(self, conditions: List[ColumnElement[bool]]) -> Select[int, int]:
        """Count the items without a published added date, and every item.

        Args:
            conditions (List[ColumnElement[bool]]): The filters the items must meet.

        Returns:
            Select[int, int]: The undated and total counts.
        """
        undated = func.count().filter(self.table.c.added_at.is_(None))
        return select(undated, func.count()).select_from(self.table).where(*conditions)
