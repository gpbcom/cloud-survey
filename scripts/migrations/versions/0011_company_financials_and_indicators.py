"""Company financials: the statement lines of the chronology's companies and the time series of their indicators.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-25 12:00:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Optional[str] = "0010"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "company_financials",
        sa.Column("company", sa.String(length=40), nullable=False),
        sa.Column("metric", sa.String(length=40), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("granularity", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=12), nullable=False),
        sa.Column("value", sa.Double(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("concept", sa.String(length=160), nullable=False),
        sa.Column("form", sa.String(length=12), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_period", sa.String(length=4), nullable=True),
        sa.Column("filed", sa.Date(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint(
            "company", "metric", "period_end", "granularity", "source", name=op.f("pk_company_financials")
        ),
    )
    op.create_index("ix_company_financials_company_metric", "company_financials", ["company", "metric"], unique=False)
    op.create_table(
        "company_indicators",
        sa.Column("company", sa.String(length=40), nullable=False),
        sa.Column("indicator", sa.String(length=40), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("granularity", sa.String(length=8), nullable=False),
        sa.Column("value", sa.Double(), nullable=False),
        sa.Column("unit", sa.String(length=12), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("value_usd", sa.Double(), nullable=True),
        sa.Column("inputs", sa.String(length=300), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint(
            "company", "indicator", "period_end", "granularity", name=op.f("pk_company_indicators")
        ),
    )
    op.create_index("ix_company_indicators_indicator", "company_indicators", ["indicator", "granularity"], unique=False)


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index("ix_company_indicators_indicator", table_name="company_indicators")
    op.drop_table("company_indicators")
    op.drop_index("ix_company_financials_company_metric", table_name="company_financials")
    op.drop_table("company_financials")
