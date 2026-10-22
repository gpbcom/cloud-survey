"""Service correspondences: the concepts shared by the providers, their services, and the checks of the matches.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-19 09:00:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Optional[str] = "0006"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "service_concepts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("node_slug", sa.String(length=60), nullable=True),
        sa.Column("source", sa.String(length=10), server_default="llm", nullable=False),
        sa.Column("edited", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["node_slug"],
            ["taxonomy_nodes.slug"],
            name=op.f("fk_service_concepts_node_slug_taxonomy_nodes"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_concepts")),
    )
    op.create_index(
        "ix_service_concepts_node_name",
        "service_concepts",
        [sa.literal_column("coalesce(node_slug, '')"), sa.literal_column("lower(name)")],
        unique=True,
    )
    op.create_table(
        "concept_members",
        sa.Column("concept_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=12), server_default="equivalent", nullable=False),
        sa.Column("confidence", sa.SmallInteger(), server_default="100", nullable=False),
        sa.Column("source", sa.String(length=10), server_default="llm", nullable=False),
        sa.Column("excluded", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["service_concepts.id"],
            name=op.f("fk_concept_members_concept_id_service_concepts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_concept_members_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("concept_id", "product_id", name=op.f("pk_concept_members")),
    )
    op.create_index("ix_concept_members_product_id", "concept_members", ["product_id"], unique=False)
    op.create_table(
        "correspondence_checks",
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("node_slug", sa.String(length=60), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("llm_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("llm_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["node_slug"],
            ["taxonomy_nodes.slug"],
            name=op.f("fk_correspondence_checks_node_slug_taxonomy_nodes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_correspondence_checks_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("product_id", "node_slug", name=op.f("pk_correspondence_checks")),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_table("correspondence_checks")
    op.drop_index("ix_concept_members_product_id", table_name="concept_members")
    op.drop_table("concept_members")
    op.drop_index("ix_service_concepts_node_name", table_name="service_concepts")
    op.drop_table("service_concepts")
