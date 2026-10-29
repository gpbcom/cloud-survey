"""Record browsing: the indexes of the orders of the Stored data of the Patents & papers tab.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-26 19:30:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
from alembic import op

revision: str = "0015"
down_revision: Optional[str] = "0014"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_index("ix_patents_priority_date", "patents", ["priority_date"])
    op.create_index("ix_patents_publication_date", "patents", ["publication_date"])
    op.create_index("ix_research_papers_publication_date", "research_papers", ["publication_date"])
    op.create_index("ix_research_papers_cited_by_count", "research_papers", ["cited_by_count"])


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index("ix_research_papers_cited_by_count", table_name="research_papers")
    op.drop_index("ix_research_papers_publication_date", table_name="research_papers")
    op.drop_index("ix_patents_publication_date", table_name="patents")
    op.drop_index("ix_patents_priority_date", table_name="patents")
