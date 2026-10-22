from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional

# Third Party Imports.
from sqlalchemy import (
    Column,
    ColumnElement,
    String,
    Table,
    UnaryExpression,
    and_,
    cast,
    literal_column,
    not_,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import ARRAY, array, array_agg

# First Party Imports.
from models.cloud.enums import SoftwareAudience, SoftwareCategory
from models.storage.enums import ItemFilter, ItemSort, StorageTable
from models.storage.filters.date_filter import DateFilter
from models.storage.pages.item_query import ItemQuery
from storage.tables.base import Base
from storage.tables.taxonomy.source_label_row import SourceLabelRow


class ItemQueryBuilder:
    """Translate the queries of pages of stored items into SQL filters and orders.

    Attributes:
        SEARCH_EXPRESSIONS (ClassVar[Dict[StorageTable, str]]): The searched text of each items table, as indexed
            by its trigram index (the expression must stay the same for the index to be used).
        table (Table): The items table.
        is_software (bool): Whether the table holds the marketplace software (with its software filters).
        logger (Logger): The builder logger.
        search_text (ColumnElement[str]): The searched text of the table.

    Notes:
        - The software filters (audiences, deliveries, publishers) apply to the software table only: they are ignored
          for the products.
        - The audiences filter both tables, the products being classified too.
        - A bound on the deletion date reads the deleted items, whatever `include_deleted`.
    """

    SEARCH_EXPRESSIONS: ClassVar[Dict[StorageTable, str]] = {
        StorageTable.PRODUCTS: "products.name",
        StorageTable.SOFTWARE: "(software.name || ' ' || coalesce(software.publisher, ''))",
    }

    def __init__(self, table: Table, logger: Optional[Logger] = None) -> None:
        """Initialize the builder.

        Args:
            table (Table): The items table.
            logger (Optional[Logger]): The builder logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.table = table
        self.is_software = table.name == StorageTable.SOFTWARE
        self.search_text: ColumnElement[str] = literal_column(self.SEARCH_EXPRESSIONS[StorageTable(table.name)])
        self.logger.debug("Query builder of the table %s ready.", table.name)

    ############################
    # Internal Helpers Methods #
    ############################

    def _dated(
        self,
        date: Column[datetime],
        source: Optional[Column[str]],
        date_filter: DateFilter,
    ) -> Optional[ColumnElement[bool]]:
        """Build the filter of a history date.

        Args:
            date (Column[datetime]): The date column.
            source (Optional[Column[str]]): The column of the source of the date, `None` for the deletion date.
            date_filter (DateFilter): The filter of the date.

        Returns:
            Optional[ColumnElement[bool]]: The conditions the date must meet,
                `None` when the filter is inactive.
        """
        conditions: List[ColumnElement[bool]] = []
        if date_filter.after is not None:
            conditions.append(date >= date_filter.after)
        if date_filter.before is not None:
            conditions.append(date < date_filter.before)
        if source is not None and date_filter.sources:
            conditions.append(source.in_([origin.value for origin in date_filter.sources]))
        if date_filter.known is not None:
            conditions.append(date.is_not(None) if date_filter.known else date.is_(None))
        self.logger.debug("Filter on %s: %d conditions.", date.name, len(conditions))
        return and_(*conditions) if conditions else None

    def _audience(self, audience: SoftwareAudience) -> ColumnElement[bool]:
        """Build the filter of an audience.

        Args:
            audience (SoftwareAudience): The audience.

        Returns:
            ColumnElement[bool]: The items of both categories for `BOTH`, else the items of the one category only.
        """
        categories = self.table.c.categories
        developer, end_user = SoftwareCategory.DEVELOPER_TOOL.value, SoftwareCategory.END_USER_SOFTWARE.value
        self.logger.debug("Filter on the audience %s.", audience.value)
        match audience:
            case SoftwareAudience.BOTH:
                return categories.contains([developer, end_user])
            case SoftwareAudience.DEVELOPER_TOOL:
                return and_(categories.contains([developer]), not_(categories.contains([end_user])))
            case _:
                return and_(categories.contains([end_user]), not_(categories.contains([developer])))

    def _aliases(self, label_ids: List[int]) -> ColumnElement[List[int]]:
        """Get the source labels of some labels and of their aliases (the same English name, or merged).

        Args:
            label_ids (List[int]): The chosen labels.

        Returns:
            ColumnElement[List[int]]: The array of the identifiers of the chosen labels and of their aliases.
        """
        labels = Base.metadata.tables[SourceLabelRow.__tablename__]
        chosen = labels.c.id.in_(label_ids)
        names = select(labels.c.name_key).where(chosen, labels.c.name_key.is_not(None))
        canonicals = select(labels.c.canonical_id).where(chosen, labels.c.canonical_id.is_not(None))
        members = or_(
            chosen,
            labels.c.canonical_id.in_(label_ids),
            labels.c.name_key.in_(names),
            labels.c.id.in_(canonicals),
            labels.c.canonical_id.in_(canonicals),
        )
        return select(array_agg(labels.c.id)).where(members).scalar_subquery()

    ############################
    # Publicly Exposed Methods #
    ############################

    def filter(self, item_filter: ItemFilter, query: ItemQuery) -> Optional[ColumnElement[bool]]:
        """Build a filter of a query.

        Args:
            item_filter (ItemFilter): The filter.
            query (ItemQuery): The query.

        Returns:
            Optional[ColumnElement[bool]]: The condition of the filter,
                `None` when the query does not filter on it
                (or when it is a software filter of the products).
        """
        columns = self.table.c
        match item_filter:
            case ItemFilter.PROVIDERS if query.providers or query.restrict_providers:
                return columns.provider.in_([provider.value for provider in query.providers])
            case ItemFilter.LISTED if not query.include_deleted and not query.deleted.is_active:
                return columns.deleted_at.is_(None)
            case ItemFilter.SEARCH if query.search and query.search_description:
                return or_(
                    self.search_text.icontains(query.search, autoescape=True),
                    columns.description.icontains(query.search, autoescape=True),
                )
            case ItemFilter.SEARCH if query.search:
                return self.search_text.icontains(query.search, autoescape=True)
            case ItemFilter.CATEGORIES if self.is_software and query.categories:
                return columns.categories.overlap(array([category.value for category in query.categories]))
            case ItemFilter.DELIVERIES if self.is_software and query.deliveries:
                return columns.delivery.in_([delivery.value for delivery in query.deliveries])
            case ItemFilter.NAME if query.name:
                return columns.name.icontains(query.name, autoescape=True)
            case ItemFilter.DESCRIPTION if query.description:
                return columns.description.icontains(query.description, autoescape=True)
            case ItemFilter.URL if query.url:
                return columns.url.icontains(query.url, autoescape=True)
            case ItemFilter.PUBLISHERS if self.is_software and query.publishers:
                return columns.publisher.in_(query.publishers)
            case ItemFilter.ADDED if query.added.is_active:
                return self._dated(columns.added_at, columns.added_from, query.added)
            case ItemFilter.UPDATED if query.updated.is_active:
                return self._dated(columns.updated_at, columns.updated_from, query.updated)
            case ItemFilter.DELETED if query.deleted.is_active:
                return self._dated(columns.deleted_at, None, query.deleted)
            case ItemFilter.APPROXIMATE if query.approximate is True:
                return or_(columns.added_caveat.is_not(None), columns.updated_caveat.is_not(None))
            case ItemFilter.APPROXIMATE if query.approximate is False:
                return and_(columns.added_caveat.is_(None), columns.updated_caveat.is_(None))
            case ItemFilter.AUDIENCES if query.audiences:
                return or_(*(self._audience(audience) for audience in dict.fromkeys(query.audiences)))
            case ItemFilter.SERVICE_CATEGORIES if query.service_categories:
                slugs = cast(array(query.service_categories), ARRAY(String))
                return or_(columns.service_categories.overlap(slugs), columns.service_domains.overlap(slugs))
            case ItemFilter.SOURCE_LABELS if query.source_labels:
                return columns.source_label_ids.overlap(self._aliases(query.source_labels))
            case ItemFilter.CAVEATS if query.caveats:
                caveats = [caveat.value for caveat in query.caveats]
                return or_(columns.added_caveat.in_(caveats), columns.updated_caveat.in_(caveats))
            case _:
                return None

    def filters(self, query: ItemQuery) -> List[ColumnElement[bool]]:
        """Build the filters of a query.

        Args:
            query (ItemQuery): The query.

        Returns:
            List[ColumnElement[bool]]: The conditions the items must all meet.
        """
        self.logger.debug("Building the filters of a %s query.", self.table.name)
        conditions = [self.filter(item_filter, query) for item_filter in ItemFilter]
        return [condition for condition in conditions if condition is not None]

    def order(self, query: ItemQuery) -> List[UnaryExpression[str]]:
        """Build the order of a query, the identifier last so that the pages never overlap.

        Args:
            query (ItemQuery): The query.

        Returns:
            List[UnaryExpression[str]]: The order of the items.
        """
        self.logger.debug(
            "Ordering the %s by %s (%s).",
            self.table.name,
            query.sort.value,
            "descending" if query.descending else "ascending",
        )
        columns = self.table.c
        keys = {
            ItemSort.ID: [columns.id],
            ItemSort.NAME: [columns.name],
            ItemSort.PROVIDER: [columns.provider, columns.name],
            ItemSort.PUBLISHER: [columns.publisher if self.is_software else columns.name, columns.name],
            ItemSort.ADDED_AT: [columns.added_at],
            ItemSort.UPDATED_AT: [columns.updated_at],
            ItemSort.DELETED_AT: [columns.deleted_at],
        }[query.sort]
        ordered = [key.desc().nulls_last() if query.descending else key.asc().nulls_last() for key in keys]
        if query.sort is not ItemSort.ID:
            ordered.append(columns.id.desc() if query.descending else columns.id.asc())
        return ordered
