"""Indexes of the software filters: publisher, marketplace categories, name trigrams and history dates.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-17 15:45:52.537863
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
from alembic import op

revision: str = "0002"
down_revision: Optional[str] = "0001"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_index("ix_software_added_at", "software", ["added_at"], unique=False)
    op.create_index(
        "ix_software_marketplace_categories",
        "software",
        ["marketplace_categories"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_software_name_trgm",
        "software",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index("ix_software_publisher", "software", ["publisher"], unique=False)
    op.create_index("ix_software_updated_at", "software", ["updated_at"], unique=False)


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index("ix_software_updated_at", table_name="software")
    op.drop_index("ix_software_publisher", table_name="software")
    op.drop_index(
        "ix_software_name_trgm", table_name="software", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}
    )
    op.drop_index("ix_software_marketplace_categories", table_name="software", postgresql_using="gin")
    op.drop_index("ix_software_added_at", table_name="software")
