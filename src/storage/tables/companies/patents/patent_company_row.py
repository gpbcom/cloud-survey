from __future__ import annotations

# Third Party Imports.
from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class PatentCompanyRow(Base):
    """A company whose assignee search returned a publication.

    Attributes:
        publication_number (Mapped[str]): The publication.
        company (Mapped[str]): The company.
        query (Mapped[str]): The assignee search that first returned it.
    """

    __tablename__ = StorageTable.PATENT_COMPANIES
    __table_args__ = (Index("ix_patent_companies_company", "company"),)

    publication_number: Mapped[str] = mapped_column(String(32), primary_key=True)
    company: Mapped[str] = mapped_column(String(40), primary_key=True)
    query: Mapped[str] = mapped_column(String(120))
