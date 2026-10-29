"""Patents: the publications of the companies' assignees, their inventors, assignees, classes and citations.

The search windows and the derived inventor and assignee profiles are stored too.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-25 12:10:00.000000
"""

from __future__ import annotations

# Standard Library Imports.
from typing import Optional, Sequence, Union

# Third Party Imports.
import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Optional[str] = "0011"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "patents",
        sa.Column("publication_number", sa.String(length=32), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("assignee", sa.String(length=300), nullable=True),
        sa.Column("priority_date", sa.Date(), nullable=True),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("grant_date", sa.Date(), nullable=True),
        sa.Column("family_id", sa.String(length=20), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("claims", sa.Integer(), nullable=True),
        sa.Column("detail_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("publication_number", name=op.f("pk_patents")),
    )
    op.create_index("ix_patents_family_id", "patents", ["family_id"], unique=False)
    op.create_index("ix_patents_detail_fetched_at", "patents", ["detail_fetched_at"], unique=False)
    op.create_table(
        "patent_companies",
        sa.Column("publication_number", sa.String(length=32), nullable=False),
        sa.Column("company", sa.String(length=40), nullable=False),
        sa.Column("query", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("publication_number", "company", name=op.f("pk_patent_companies")),
    )
    op.create_index("ix_patent_companies_company", "patent_companies", ["company"], unique=False)
    op.create_table(
        "patent_inventors",
        sa.Column("publication_number", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_key", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("publication_number", "position", name=op.f("pk_patent_inventors")),
    )
    op.create_index("ix_patent_inventors_name_key", "patent_inventors", ["name_key"], unique=False)
    op.create_table(
        "patent_assignees",
        sa.Column("publication_number", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("original", sa.Boolean(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.PrimaryKeyConstraint("publication_number", "position", "original", name=op.f("pk_patent_assignees")),
    )
    op.create_index("ix_patent_assignees_name", "patent_assignees", ["name"], unique=False)
    op.create_table(
        "patent_classifications",
        sa.Column("publication_number", sa.String(length=32), nullable=False),
        sa.Column("cpc", sa.String(length=20), nullable=False),
        sa.Column("main", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("publication_number", "cpc", name=op.f("pk_patent_classifications")),
    )
    op.create_index("ix_patent_classifications_cpc", "patent_classifications", ["cpc"], unique=False)
    op.create_table(
        "patent_citations",
        sa.Column("publication_number", sa.String(length=32), nullable=False),
        sa.Column("other", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("examiner", sa.Boolean(), nullable=False),
        sa.Column("other_priority_date", sa.Date(), nullable=True),
        sa.Column("other_publication_date", sa.Date(), nullable=True),
        sa.Column("other_assignee", sa.String(length=300), nullable=True),
        sa.Column("other_title", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("publication_number", "other", "kind", name=op.f("pk_patent_citations")),
    )
    op.create_index("ix_patent_citations_other", "patent_citations", ["other"], unique=False)
    op.create_table(
        "patent_windows",
        sa.Column("company", sa.String(length=40), nullable=False),
        sa.Column("query", sa.String(length=120), nullable=False),
        sa.Column("after", sa.Date(), nullable=False),
        sa.Column("before", sa.Date(), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("expected", sa.Integer(), nullable=False),
        sa.Column("fetched", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("searched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("company", "query", "after", "before", "country", name=op.f("pk_patent_windows")),
    )
    op.create_table(
        "inventor_profiles",
        sa.Column("name_key", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("publications", sa.Integer(), nullable=False),
        sa.Column("families", sa.Integer(), nullable=False),
        sa.Column("first_priority", sa.Date(), nullable=True),
        sa.Column("last_priority", sa.Date(), nullable=True),
        sa.Column("companies", sa.Text(), nullable=False),
        sa.Column("top_cpc", sa.Text(), nullable=True),
        sa.Column("co_inventors", sa.Integer(), nullable=False),
        sa.Column("citations_received", sa.Integer(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("name_key", name=op.f("pk_inventor_profiles")),
    )
    op.create_index("ix_inventor_profiles_publications", "inventor_profiles", ["publications"], unique=False)
    op.create_table(
        "assignee_profiles",
        sa.Column("company", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("publications", sa.Integer(), nullable=False),
        sa.Column("first_year", sa.Integer(), nullable=True),
        sa.Column("last_year", sa.Integer(), nullable=True),
        sa.Column("countries", sa.Text(), nullable=False),
        sa.Column("top_cpc", sa.Text(), nullable=True),
        sa.Column("top_inventors", sa.Text(), nullable=True),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("company", "name", name=op.f("pk_assignee_profiles")),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_table("assignee_profiles")
    op.drop_index("ix_inventor_profiles_publications", table_name="inventor_profiles")
    op.drop_table("inventor_profiles")
    op.drop_table("patent_windows")
    op.drop_index("ix_patent_citations_other", table_name="patent_citations")
    op.drop_table("patent_citations")
    op.drop_index("ix_patent_classifications_cpc", table_name="patent_classifications")
    op.drop_table("patent_classifications")
    op.drop_index("ix_patent_assignees_name", table_name="patent_assignees")
    op.drop_table("patent_assignees")
    op.drop_index("ix_patent_inventors_name_key", table_name="patent_inventors")
    op.drop_table("patent_inventors")
    op.drop_index("ix_patent_companies_company", table_name="patent_companies")
    op.drop_table("patent_companies")
    op.drop_index("ix_patents_family_id", table_name="patents")
    op.drop_index("ix_patents_detail_fetched_at", table_name="patents")
    op.drop_table("patents")
