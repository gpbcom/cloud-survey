"""Paper affiliation checks: the researchers' affiliation evidence and the papers search's last sight of a link.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-26 21:00:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Optional[str] = "0015"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.add_column(
        "researcher_profiles",
        sa.Column("current_affiliation", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "researcher_profiles", sa.Column("affiliation_years", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("researcher_profiles", sa.Column("confirmed", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column(
        "paper_companies",
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_column("paper_companies", "linked_at")
    op.drop_column("researcher_profiles", "confirmed")
    op.drop_column("researcher_profiles", "affiliation_years")
    op.drop_column("researcher_profiles", "current_affiliation")
