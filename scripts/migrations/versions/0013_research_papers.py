"""Research papers: the papers of the companies' researchers (OpenAlex), their authors and the researchers' profiles.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-25 12:20:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Optional[str] = "0012"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "research_papers",
        sa.Column("openalex_id", sa.String(length=20), nullable=False),
        sa.Column("doi", sa.String(length=300), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("type", sa.String(length=40), nullable=True),
        sa.Column("venue", sa.String(length=300), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("cited_by_count", sa.Integer(), nullable=False),
        sa.Column("fwci", sa.Double(), nullable=True),
        sa.Column("is_oa", sa.Boolean(), nullable=False),
        sa.Column("topic", sa.String(length=300), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("openalex_id", name=op.f("pk_research_papers")),
    )
    op.create_index("ix_research_papers_publication_year", "research_papers", ["publication_year"], unique=False)
    op.create_table(
        "paper_companies",
        sa.Column("openalex_id", sa.String(length=20), nullable=False),
        sa.Column("company", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("openalex_id", "company", name=op.f("pk_paper_companies")),
    )
    op.create_index("ix_paper_companies_company", "paper_companies", ["company"], unique=False)
    op.create_table(
        "paper_authors",
        sa.Column("openalex_id", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.String(length=20), nullable=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("orcid", sa.String(length=60), nullable=True),
        sa.Column("institutions", sa.Text(), nullable=False),
        sa.Column("company_affiliated", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("openalex_id", "position", name=op.f("pk_paper_authors")),
    )
    op.create_index("ix_paper_authors_author_id", "paper_authors", ["author_id"], unique=False)
    op.create_table(
        "researcher_profiles",
        sa.Column("author_id", sa.String(length=20), nullable=False),
        sa.Column("company", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("orcid", sa.String(length=60), nullable=True),
        sa.Column("works_count", sa.Integer(), nullable=False),
        sa.Column("cited_by_count", sa.Integer(), nullable=False),
        sa.Column("h_index", sa.Integer(), nullable=True),
        sa.Column("institution", sa.String(length=300), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("author_id", "company", name=op.f("pk_researcher_profiles")),
    )
    op.create_index("ix_researcher_profiles_company", "researcher_profiles", ["company"], unique=False)


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index("ix_researcher_profiles_company", table_name="researcher_profiles")
    op.drop_table("researcher_profiles")
    op.drop_index("ix_paper_authors_author_id", table_name="paper_authors")
    op.drop_table("paper_authors")
    op.drop_index("ix_paper_companies_company", table_name="paper_companies")
    op.drop_table("paper_companies")
    op.drop_index("ix_research_papers_publication_year", table_name="research_papers")
    op.drop_table("research_papers")
