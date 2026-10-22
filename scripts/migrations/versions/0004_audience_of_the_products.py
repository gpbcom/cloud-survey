"""Audience of the products: who each catalogue product is meant for, developer tool, end-user software or both.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-18 17:00:00.000000

"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Optional[str] = "0003"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.add_column(
        "products",
        sa.Column("categories", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    )
    op.create_index("ix_products_categories", "products", ["categories"], unique=False, postgresql_using="gin")


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index("ix_products_categories", table_name="products", postgresql_using="gin")
    op.drop_column("products", "categories")
