"""Market shares: the granularity joins the key, so that a year and its first quarter never collide.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-23 13:00:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
from alembic import op

revision: str = "0010"
down_revision: Optional[str] = "0009"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

KEY_WITHOUT: Sequence[str] = ("segment", "area", "period", "device", "metric", "source", "label")
KEY_WITH: Sequence[str] = ("segment", "area", "period", "granularity", "device", "metric", "source", "label")


def upgrade() -> None:
    """Apply the migration."""
    op.drop_constraint("pk_market_shares", "market_shares", type_="primary")
    op.create_primary_key("pk_market_shares", "market_shares", list(KEY_WITH))


def downgrade() -> None:
    """Revert the migration (the shares of a year and of its first quarter must not both be stored)."""
    op.execute(
        "DELETE FROM market_shares a USING market_shares b WHERE a.granularity = 'year' AND b.granularity <> 'year' "
        "AND a.segment = b.segment AND a.area = b.area AND a.period = b.period AND a.device = b.device "
        "AND a.metric = b.metric AND a.source = b.source AND a.label = b.label"
    )
    op.drop_constraint("pk_market_shares", "market_shares", type_="primary")
    op.create_primary_key("pk_market_shares", "market_shares", list(KEY_WITHOUT))
