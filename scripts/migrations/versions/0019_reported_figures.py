"""Reported figures: the companies' figures researched by hand, moved from YAML.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-27 10:00:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: Optional[str] = "0018"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "reported_companies",
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
        "reported_years",
        sa.Column("company", sa.String(length=40), nullable=False),
        sa.Column("fiscal_year", sa.SmallInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("check_status", sa.String(length=16), server_default="unchecked", nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("origin", sa.String(length=16), server_default="seed", nullable=False),
        sa.Column("edited", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("company", "fiscal_year"),
    )
    op.create_table(
        "reported_events",
        sa.Column("company", sa.String(length=40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("origin", sa.String(length=16), server_default="seed", nullable=False),
        sa.Column("edited", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("company", "position"),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_table("reported_events")
    op.drop_table("reported_years")
    op.drop_table("reported_companies")
