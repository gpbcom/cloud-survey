from __future__ import annotations

# Standard Library Imports.
from datetime import datetime

# Third Party Imports.
from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class PaperCompanyRow(Base):
    """A company whose institutions a paper is affiliated with.

    Attributes:
        openalex_id (Mapped[str]): The OpenAlex work.
        company (Mapped[str]): The company.
        linked_at (Mapped[datetime]): When a papers search last found the paper among the company's (the links a
            complete search no longer finds are removed after it).
    """

    __tablename__ = StorageTable.PAPER_COMPANIES
    __table_args__ = (Index("ix_paper_companies_company", "company"),)

    openalex_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    company: Mapped[str] = mapped_column(String(40), primary_key=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
