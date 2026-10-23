"""Market shares, stock prices and exchange rates: the evolution of the leaders of the chronology.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-23 10:00:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Optional[str] = "0008"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "market_shares",
        sa.Column("segment", sa.String(length=40), nullable=False),
        sa.Column("area", sa.String(length=12), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("device", sa.String(length=8), nullable=False),
        sa.Column("metric", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=12), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("granularity", sa.String(length=8), nullable=False),
        sa.Column("company", sa.String(length=40), nullable=True),
        sa.Column("value", sa.Double(), nullable=False),
        sa.Column("estimate", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint(
            "segment", "area", "period", "device", "metric", "source", "label", name=op.f("pk_market_shares")
        ),
    )
    op.create_index("ix_market_shares_company", "market_shares", ["company", "segment"], unique=False)
    op.create_table(
        "stock_prices",
        sa.Column("listing", sa.String(length=30), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("close", sa.Double(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("listing", "day", "source", name=op.f("pk_stock_prices")),
    )
    op.create_table(
        "fx_rates",
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("usd_per_unit", sa.Double(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("currency", "day", name=op.f("pk_fx_rates")),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_table("fx_rates")
    op.drop_table("stock_prices")
    op.drop_index("ix_market_shares_company", table_name="market_shares")
    op.drop_table("market_shares")
