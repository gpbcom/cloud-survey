from __future__ import annotations

from datetime import UTC, datetime
from typing import List

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from models.cloud.enums import (
    CloudProvider,
    DateCaveat,
    DateSource,
    DeliveryMethod,
    SoftwareAudience,
    SoftwareCategory,
)
from models.storage.enums import ItemSort
from models.storage.filters.date_filter import DateFilter
from models.storage.pages.item_query import ItemQuery
from storage.mappers.item_query_builder import ItemQueryBuilder
from storage.tables.base import Base

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def sql(table: str, query: ItemQuery) -> str:
    builder = ItemQueryBuilder(Base.metadata.tables[table])
    statement = select(builder.table.c.id).where(*builder.filters(query)).order_by(*builder.order(query))
    return str(statement.compile(dialect=postgresql.dialect()))


def test_the_listed_items_are_read_by_default() -> None:
    assert "software.deleted_at IS NULL" in sql("software", ItemQuery())
    assert "deleted_at IS NULL" not in sql("software", ItemQuery(include_deleted=True))


def test_the_search_uses_the_indexed_expression() -> None:
    statement = sql("software", ItemQuery(search="redis"))

    assert "(software.name || ' ' || coalesce(software.publisher, '')) ILIKE" in statement
    assert "software.description ILIKE" not in statement
    assert "software.description ILIKE" in sql("software", ItemQuery(search="redis", search_description=True))
    assert "products.name ILIKE" in sql("products", ItemQuery(search="vm"))


@pytest.mark.parametrize(
    ("query", "fragment"),
    [
        (ItemQuery(providers=[CloudProvider.CIVO]), "software.provider IN"),
        (ItemQuery(categories=[SoftwareCategory.DEVELOPER_TOOL]), "software.categories && ARRAY"),
        (ItemQuery(deliveries=[DeliveryMethod.SAAS]), "software.delivery IN"),
    ],
)
def test_the_software_filters(query: ItemQuery, fragment: str) -> None:
    assert fragment in sql("software", query)


def test_the_software_filters_are_ignored_for_the_products() -> None:
    query = ItemQuery(categories=[SoftwareCategory.DEVELOPER_TOOL], deliveries=[DeliveryMethod.SAAS])

    assert sql("products", query).count("AND") == 0


@pytest.mark.parametrize(
    ("sort", "descending", "order"),
    [
        (ItemSort.ID, False, ["products.id ASC NULLS LAST"]),
        (ItemSort.NAME, True, ["products.name DESC NULLS LAST", "products.id DESC"]),
        (
            ItemSort.PROVIDER,
            False,
            ["products.provider ASC NULLS LAST", "products.name ASC NULLS LAST", "products.id ASC"],
        ),
        (
            ItemSort.PUBLISHER,
            False,
            ["products.name ASC NULLS LAST", "products.name ASC NULLS LAST", "products.id ASC"],
        ),
        (ItemSort.UPDATED_AT, False, ["products.updated_at ASC NULLS LAST", "products.id ASC"]),
    ],
)
def test_the_orders_end_with_the_identifier(sort: ItemSort, descending: bool, order: List[str]) -> None:
    statement = sql("products", ItemQuery(sort=sort, descending=descending))

    assert statement.split("ORDER BY ")[1] == ", ".join(order)


@pytest.mark.parametrize(
    ("query", "fragment"),
    [
        (ItemQuery(name="graf"), "software.name ILIKE"),
        (ItemQuery(description="dash"), "software.description ILIKE"),
        (ItemQuery(url="example"), "software.url ILIKE"),
        (ItemQuery(publishers=["ACME"]), "software.publisher IN"),
        (
            ItemQuery(added=DateFilter(after=T0, before=T0, sources=[DateSource.WEBSITE])),
            "AND software.added_from IN",
        ),
        (ItemQuery(updated=DateFilter(known=False)), "software.updated_at IS NULL"),
        (ItemQuery(updated=DateFilter(known=True)), "software.updated_at IS NOT NULL"),
        (ItemQuery(approximate=True), "software.added_caveat IS NOT NULL OR software.updated_caveat IS NOT NULL"),
        (ItemQuery(approximate=False), "software.added_caveat IS NULL AND software.updated_caveat IS NULL"),
        (ItemQuery(caveats=[DateCaveat.YEAR_ONLY]), "software.added_caveat IN"),
    ],
)
def test_the_field_filters(query: ItemQuery, fragment: str) -> None:
    assert fragment in sql("software", query)


def test_a_deletion_range_reads_the_deleted_items() -> None:
    statement = sql("software", ItemQuery(deleted=DateFilter(after=T0)))

    assert "deleted_at IS NULL" not in statement
    assert "software.deleted_at >=" in statement


def test_the_publisher_filter_is_ignored_for_the_products() -> None:
    assert "publisher" not in sql("products", ItemQuery(publishers=["ACME"]))


@pytest.mark.parametrize("table", ["products", "software"])
def test_the_service_category_filter_matches_the_categories_or_the_domains(table: str) -> None:
    statement = sql(table, ItemQuery(service_categories=["databases"]))

    assert f"{table}.service_categories && CAST(ARRAY" in statement
    assert f" OR {table}.service_domains && CAST(ARRAY" in statement


@pytest.mark.parametrize("table", ["products", "software"])
def test_the_source_label_filter_reads_the_aliases(table: str) -> None:
    statement = sql(table, ItemQuery(source_labels=[3]))

    assert f"{table}.source_label_ids && (SELECT array_agg(source_labels.id)" in statement
    assert "source_labels.canonical_id IN" in statement
    assert "source_labels.name_key IN" in statement


@pytest.mark.parametrize("table", ["products", "software"])
def test_the_audience_filter_applies_to_both_tables(table: str) -> None:
    both = sql(table, ItemQuery(audiences=[SoftwareAudience.BOTH]))
    developer = sql(table, ItemQuery(audiences=[SoftwareAudience.DEVELOPER_TOOL]))

    assert f"{table}.categories @>" in both
    assert "NOT (" not in both
    assert f"NOT (({table}.categories @>" in developer


def test_the_audiences_are_combined_with_or() -> None:
    statement = sql("products", ItemQuery(audiences=[SoftwareAudience.END_USER_SOFTWARE, SoftwareAudience.BOTH]))

    assert statement.count("products.categories @>") == 3
    assert " OR " in statement


def test_a_repeated_audience_is_filtered_once() -> None:
    statement = sql("products", ItemQuery(audiences=[SoftwareAudience.BOTH, SoftwareAudience.BOTH]))

    assert statement.count("products.categories @>") == 1
