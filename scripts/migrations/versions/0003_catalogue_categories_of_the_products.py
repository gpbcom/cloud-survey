"""Catalogue categories of the products: the categories the catalogue of each provider files its products under.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-18 11:30:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Optional[str] = "0002"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.add_column(
        "products",
        sa.Column(
            "catalogue_categories", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
    )
    op.create_index(
        "ix_products_catalogue_categories",
        "products",
        ["catalogue_categories"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index("ix_products_catalogue_categories", table_name="products", postgresql_using="gin")
    op.drop_column("products", "catalogue_categories")
