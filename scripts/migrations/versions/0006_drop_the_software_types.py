"""Drop the software types: the unified categories replace them.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-18 22:30:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Optional[str] = "0005"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.drop_index("ix_software_types", table_name="software", postgresql_using="gin")
    op.drop_column("software", "types")
    op.drop_column("taxonomy_nodes", "software_type")


def downgrade() -> None:
    """Revert the migration: the columns come back, every software typed `other` until it is classified again."""
    op.add_column("taxonomy_nodes", sa.Column("software_type", sa.String(length=40), nullable=True))
    op.add_column(
        "software",
        sa.Column("types", postgresql.ARRAY(sa.String(length=40)), server_default=sa.text("'{other}'"), nullable=False),
    )
    op.alter_column("software", "types", server_default=None)
    op.create_index("ix_software_types", "software", ["types"], unique=False, postgresql_using="gin")
