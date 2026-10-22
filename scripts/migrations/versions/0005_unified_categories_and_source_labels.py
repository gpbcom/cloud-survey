"""Unified categories: the taxonomy, the source labels with their links, the categorization columns of the items.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-18 18:43:50.657388
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Optional[str] = "0004"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("task", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost", sa.Numeric(precision=14, scale=6), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("called_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_usage")),
    )
    op.create_index("ix_llm_usage_called_at", "llm_usage", ["called_at"], unique=False)
    op.create_table(
        "source_labels",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=True),
        sa.Column("name_key", sa.Text(), nullable=True),
        sa.Column("name_source", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=12), server_default="pending", nullable=False),
        sa.Column("status_source", sa.String(length=10), nullable=True),
        sa.Column("canonical_id", sa.BigInteger(), nullable=True),
        sa.Column("canonical_source", sa.String(length=10), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("translated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("llm_claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("llm_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("llm_error", sa.Text(), nullable=True),
        sa.CheckConstraint("canonical_id <> id", name=op.f("ck_source_labels_not_its_own_canonical")),
        sa.ForeignKeyConstraint(
            ["canonical_id"],
            ["source_labels.id"],
            name=op.f("fk_source_labels_canonical_id_source_labels"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_labels")),
    )
    op.create_index("ix_source_labels_canonical_id", "source_labels", ["canonical_id"], unique=False)
    op.create_index("ix_source_labels_key", "source_labels", ["key"], unique=True)
    op.create_index("ix_source_labels_name_key", "source_labels", ["name_key"], unique=False)
    op.create_index("ix_source_labels_status", "source_labels", ["status"], unique=False)
    op.create_table(
        "taxonomy_nodes",
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("parent_slug", sa.String(length=60), nullable=True),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("name_ru", sa.Text(), server_default="", nullable=False),
        sa.Column("name_zh", sa.Text(), server_default="", nullable=False),
        sa.Column("description_en", sa.Text(), server_default="", nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("audiences", postgresql.ARRAY(sa.String(length=40)), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("software_type", sa.String(length=40), nullable=True),
        sa.Column("umbrella", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("origin", sa.String(length=10), server_default="seed", nullable=False),
        sa.Column("edited", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("hidden", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f("ck_taxonomy_nodes_slug_kebab_case")),
        sa.ForeignKeyConstraint(
            ["parent_slug"],
            ["taxonomy_nodes.slug"],
            name=op.f("fk_taxonomy_nodes_parent_slug_taxonomy_nodes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("slug", name=op.f("pk_taxonomy_nodes")),
    )
    op.create_index(
        "ix_taxonomy_nodes_parent_name",
        "taxonomy_nodes",
        [sa.literal_column("coalesce(parent_slug, '')"), sa.literal_column("lower(name_en)")],
        unique=True,
    )
    op.create_index("ix_taxonomy_nodes_parent_slug", "taxonomy_nodes", ["parent_slug"], unique=False)
    op.create_table(
        "taxonomy_state",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("seed_hash", sa.Text(), nullable=True),
        sa.Column("seeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name=op.f("ck_taxonomy_state_single_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_taxonomy_state")),
    )
    op.create_table(
        "label_links",
        sa.Column("label_id", sa.BigInteger(), nullable=False),
        sa.Column("node_slug", sa.String(length=60), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("excluded", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(
            ["label_id"], ["source_labels.id"], name=op.f("fk_label_links_label_id_source_labels"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["node_slug"],
            ["taxonomy_nodes.slug"],
            name=op.f("fk_label_links_node_slug_taxonomy_nodes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("label_id", "node_slug", name=op.f("pk_label_links")),
    )
    op.create_index("ix_label_links_node_slug", "label_links", ["node_slug"], unique=False)
    op.create_table(
        "label_sightings",
        sa.Column("label_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["label_id"],
            ["source_labels.id"],
            name=op.f("fk_label_sightings_label_id_source_labels"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("label_id", "kind", "provider", name=op.f("pk_label_sightings")),
    )
    op.add_column(
        "products",
        sa.Column(
            "service_categories", postgresql.ARRAY(sa.String(length=60)), server_default=sa.text("'{}'"), nullable=False
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "service_domains", postgresql.ARRAY(sa.String(length=60)), server_default=sa.text("'{}'"), nullable=False
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "source_label_ids", postgresql.ARRAY(sa.BigInteger()), server_default=sa.text("'{}'"), nullable=False
        ),
    )
    op.add_column("products", sa.Column("categories_source", sa.String(length=10), nullable=True))
    op.add_column("products", sa.Column("categories_fingerprint", sa.LargeBinary(), nullable=True))
    op.create_index(
        "ix_products_service_categories", "products", ["service_categories"], unique=False, postgresql_using="gin"
    )
    op.create_index(
        "ix_products_service_domains", "products", ["service_domains"], unique=False, postgresql_using="gin"
    )
    op.create_index(
        "ix_products_source_label_ids", "products", ["source_label_ids"], unique=False, postgresql_using="gin"
    )
    op.add_column(
        "software",
        sa.Column(
            "service_categories", postgresql.ARRAY(sa.String(length=60)), server_default=sa.text("'{}'"), nullable=False
        ),
    )
    op.add_column(
        "software",
        sa.Column(
            "service_domains", postgresql.ARRAY(sa.String(length=60)), server_default=sa.text("'{}'"), nullable=False
        ),
    )
    op.add_column(
        "software",
        sa.Column(
            "source_label_ids", postgresql.ARRAY(sa.BigInteger()), server_default=sa.text("'{}'"), nullable=False
        ),
    )
    op.add_column("software", sa.Column("categories_source", sa.String(length=10), nullable=True))
    op.add_column("software", sa.Column("categories_fingerprint", sa.LargeBinary(), nullable=True))
    op.create_index(
        "ix_software_service_categories", "software", ["service_categories"], unique=False, postgresql_using="gin"
    )
    op.create_index(
        "ix_software_service_domains", "software", ["service_domains"], unique=False, postgresql_using="gin"
    )
    op.create_index(
        "ix_software_source_label_ids", "software", ["source_label_ids"], unique=False, postgresql_using="gin"
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index("ix_software_source_label_ids", table_name="software", postgresql_using="gin")
    op.drop_index("ix_software_service_domains", table_name="software", postgresql_using="gin")
    op.drop_index("ix_software_service_categories", table_name="software", postgresql_using="gin")
    op.drop_column("software", "categories_fingerprint")
    op.drop_column("software", "categories_source")
    op.drop_column("software", "source_label_ids")
    op.drop_column("software", "service_domains")
    op.drop_column("software", "service_categories")
    op.drop_index("ix_products_source_label_ids", table_name="products", postgresql_using="gin")
    op.drop_index("ix_products_service_domains", table_name="products", postgresql_using="gin")
    op.drop_index("ix_products_service_categories", table_name="products", postgresql_using="gin")
    op.drop_column("products", "categories_fingerprint")
    op.drop_column("products", "categories_source")
    op.drop_column("products", "source_label_ids")
    op.drop_column("products", "service_domains")
    op.drop_column("products", "service_categories")
    op.drop_table("label_sightings")
    op.drop_index("ix_label_links_node_slug", table_name="label_links")
    op.drop_table("label_links")
    op.drop_table("taxonomy_state")
    op.drop_index("ix_taxonomy_nodes_parent_slug", table_name="taxonomy_nodes")
    op.drop_index("ix_taxonomy_nodes_parent_name", table_name="taxonomy_nodes")
    op.drop_table("taxonomy_nodes")
    op.drop_index("ix_source_labels_status", table_name="source_labels")
    op.drop_index("ix_source_labels_name_key", table_name="source_labels")
    op.drop_index("ix_source_labels_key", table_name="source_labels")
    op.drop_index("ix_source_labels_canonical_id", table_name="source_labels")
    op.drop_table("source_labels")
    op.drop_index("ix_llm_usage_called_at", table_name="llm_usage")
    op.drop_table("llm_usage")
