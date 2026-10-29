"""Company identities: the companies crawled and their identifiers at the sources, moved from YAML.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-27 10:00:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: Optional[str] = "0017"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "company_profiles",
        sa.Column("company", sa.String(length=40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("origin", sa.String(length=16), server_default="seed", nullable=False),
        sa.Column("edited", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("company"),
    )
    op.create_table(
        "company_identifiers",
        sa.Column("company", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=300), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="confirmed", nullable=False),
        sa.Column("evidence_url", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("origin", sa.String(length=16), server_default="seed", nullable=False),
        sa.Column("edited", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("company", "kind", "value"),
    )
    op.create_index("ix_company_identifiers_status", "company_identifiers", ["status"])


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index("ix_company_identifiers_status", table_name="company_identifiers")
    op.drop_table("company_identifiers")
    op.drop_table("company_profiles")
