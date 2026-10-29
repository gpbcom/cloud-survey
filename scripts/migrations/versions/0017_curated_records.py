"""Curated records: the chronology and the markets catalogue, moved from YAML into the database.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-27 10:00:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: Optional[str] = "0016"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "curated_records",
        sa.Column("dataset", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=300), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("origin", sa.String(length=16), server_default="seed", nullable=False),
        sa.Column("edited", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("dataset", "key"),
    )
    op.create_index("ix_curated_records_order", "curated_records", ["dataset", "position"])
    op.create_table(
        "curated_state",
        sa.Column("dataset", sa.String(length=40), nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("seed_hash", sa.Text(), nullable=True),
        sa.Column("seeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("dataset"),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_table("curated_state")
    op.drop_index("ix_curated_records_order", table_name="curated_records")
    op.drop_table("curated_records")
