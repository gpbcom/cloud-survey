"""Provider metrics: the measures of the providers per quarter, the criteria of the driver analysis.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-20 10:00:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Optional[str] = "0007"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "provider_metrics",
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("period", sa.String(length=6), nullable=False),
        sa.Column("metric", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=12), nullable=False),
        sa.Column("value", sa.Double(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("provider", "period", "metric", "source", name=op.f("pk_provider_metrics")),
    )
    op.create_index("ix_provider_metrics_metric", "provider_metrics", ["metric"], unique=False)


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index("ix_provider_metrics_metric", table_name="provider_metrics")
    op.drop_table("provider_metrics")
