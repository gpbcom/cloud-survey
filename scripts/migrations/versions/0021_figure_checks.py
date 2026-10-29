"""Figure checks: what the check of a researched fiscal year against its cited document found.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-27 16:00:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Optional[str] = "0020"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.add_column("reported_years", sa.Column("check_note", sa.Text(), nullable=True))


def downgrade() -> None:
    """Revert the migration."""
    op.drop_column("reported_years", "check_note")
