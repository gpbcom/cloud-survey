"""Initial storage schema: crawls, datasets, catalogue products, marketplace software, their versions, market reports.

Revision ID: 0001
Revises:
Create Date: 2026-10-17 13:19:02.225844
"""

from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Optional[str] = None
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def item_columns() -> List[sa.schema.SchemaItem]:
    """Build the columns shared by the products and the software (see `ItemColumns`).

    Returns:
        List[sa.schema.SchemaItem]: The identity, match keys, content and date columns.
    """
    return [
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("match_hash", sa.LargeBinary(), nullable=False),
        sa.Column("name_hash", sa.LargeBinary(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("added_from", sa.String(length=20), nullable=True),
        sa.Column("added_caveat", sa.String(length=40), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_from", sa.String(length=20), nullable=True),
        sa.Column("updated_caveat", sa.String(length=40), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("first_crawl_id", sa.BigInteger(), nullable=True),
        sa.Column("revision", sa.BigInteger(), server_default=sa.text("nextval('item_revision')"), nullable=False),
    ]


def create_versions_table(table: str, items: str) -> None:
    """Create the versions table of the products or of the software (see `VersionColumns`).

    Args:
        table (str): The versions table.
        items (str): The versioned items table.
    """
    op.create_table(
        table,
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("crawl_id", sa.BigInteger(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["crawl_id"], ["crawls.id"], name=op.f(f"fk_{table}_crawl_id_crawls")),
        sa.ForeignKeyConstraint(
            ["item_id"], [f"{items}.id"], name=op.f(f"fk_{table}_item_id_{items}"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("item_id", "crawl_id", name=op.f(f"pk_{table}")),
    )
    op.create_index(op.f(f"ix_{table}_crawl_id"), table, ["crawl_id"], unique=False)
    # The large versions are compressed with LZ4: faster than the default pglz, for a similar size.
    op.execute(f"ALTER TABLE {table} ALTER COLUMN content SET COMPRESSION lz4")


def upgrade() -> None:
    """Apply the migration."""
    # The trigram indexes make the searches of names fast whatever the number of items.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE SEQUENCE item_revision")
    op.create_table(
        "crawls",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("dataset", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("listed_before", sa.Integer(), server_default="0", nullable=False),
        sa.Column("found", sa.Integer(), server_default="0", nullable=False),
        sa.Column("added", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deleted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crawls")),
    )
    op.create_index("ix_crawls_kind_dataset_started_at", "crawls", ["kind", "dataset", "started_at"], unique=False)
    op.create_table(
        "datasets",
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("dataset", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("crawled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("in_progress", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("current_crawl_id", sa.BigInteger(), nullable=True),
        sa.Column("last_crawl_id", sa.BigInteger(), nullable=True),
        sa.Column("size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default=sa.text("nextval('item_revision')"), nullable=False),
        sa.ForeignKeyConstraint(["current_crawl_id"], ["crawls.id"], name=op.f("fk_datasets_current_crawl_id_crawls")),
        sa.ForeignKeyConstraint(["last_crawl_id"], ["crawls.id"], name=op.f("fk_datasets_last_crawl_id_crawls")),
        sa.PrimaryKeyConstraint("kind", "dataset", name=op.f("pk_datasets")),
    )
    op.create_table(
        "products",
        *item_columns(),
        sa.Column("pricing_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["first_crawl_id"], ["crawls.id"], name=op.f("fk_products_first_crawl_id_crawls")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        postgresql_with={"fillfactor": 85},
    )
    op.create_index("ix_products_provider_match_hash", "products", ["provider", "match_hash"], unique=False)
    op.create_index("ix_products_provider_name_hash", "products", ["provider", "name_hash"], unique=False)
    op.create_index("ix_products_provider_revision", "products", ["provider", "revision"], unique=False)
    op.create_index(
        "ix_products_name_trgm",
        "products",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_table(
        "software",
        *item_columns(),
        sa.Column("publisher", sa.Text(), nullable=True),
        sa.Column("delivery", sa.String(length=20), nullable=False),
        sa.Column("marketplace_categories", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "marketplace_category_paths", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column("categories", postgresql.ARRAY(sa.String(length=40)), nullable=False),
        sa.Column("types", postgresql.ARRAY(sa.String(length=40)), nullable=False),
        sa.ForeignKeyConstraint(["first_crawl_id"], ["crawls.id"], name=op.f("fk_software_first_crawl_id_crawls")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_software")),
        postgresql_with={"fillfactor": 85},
    )
    op.create_index("ix_software_provider_match_hash", "software", ["provider", "match_hash"], unique=False)
    op.create_index("ix_software_provider_name_hash", "software", ["provider", "name_hash"], unique=False)
    op.create_index("ix_software_provider_revision", "software", ["provider", "revision"], unique=False)
    op.create_index("ix_software_types", "software", ["types"], unique=False, postgresql_using="gin")
    op.create_index(
        "ix_software_marketplace_category_paths",
        "software",
        ["marketplace_category_paths"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"marketplace_category_paths": "jsonb_path_ops"},
    )
    op.execute(
        "CREATE INDEX ix_software_search_trgm ON software "
        "USING gin ((name || ' ' || coalesce(publisher, '')) gin_trgm_ops)"
    )
    create_versions_table("product_versions", "products")
    create_versions_table("software_versions", "software")
    op.create_table(
        "market_reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("period", sa.String(length=10), nullable=False),
        sa.Column("region", sa.String(length=40), nullable=False),
        sa.Column("segment", sa.String(length=40), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("market_size_bn", sa.Float(), nullable=True),
        sa.Column("twelve_month_bn", sa.Float(), nullable=True),
        sa.Column("growth_pct", sa.Float(), nullable=True),
        sa.Column("shares", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mentions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("methodology_break", sa.Boolean(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("published", sa.Date(), nullable=False),
        sa.Column("crawl_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["crawl_id"], ["crawls.id"], name=op.f("fk_market_reports_crawl_id_crawls")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_reports")),
        sa.UniqueConstraint(
            "source", "period", "region", "segment", name=op.f("uq_market_reports_source_period_region_segment")
        ),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_table("market_reports")
    op.drop_table("software_versions")
    op.drop_table("product_versions")
    op.drop_table("software")
    op.drop_table("products")
    op.drop_table("datasets")
    op.drop_table("crawls")
    op.execute("DROP SEQUENCE item_revision")
