"""Company financials note: what the source says about a figure (the researched figures of the annual reports).

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-26 12:00:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Optional[str] = "0013"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.add_column("company_financials", sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    """Revert the migration."""
    op.drop_column("company_financials", "note")
