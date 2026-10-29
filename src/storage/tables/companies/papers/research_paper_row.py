from __future__ import annotations

# Standard Library Imports.
from datetime import date, datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import Boolean, Date, DateTime, Double, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class ResearchPaperRow(Base):
    """A research paper of a company's researchers, as OpenAlex describes the work.

    Attributes:
        openalex_id (Mapped[str]): The OpenAlex work.
        doi (Mapped[Optional[str]]): Its DOI.
        title (Mapped[Optional[str]]): Its title.
        publication_year (Mapped[Optional[int]]): The year it was published.
        publication_date (Mapped[Optional[date]]): The day it was published.
        type (Mapped[Optional[str]]): Its type.
        venue (Mapped[Optional[str]]): Where it appeared.
        language (Mapped[Optional[str]]): Its language.
        cited_by_count (Mapped[int]): The citations it received.
        fwci (Mapped[Optional[float]]): Its field-weighted citation impact.
        is_oa (Mapped[bool]): Whether it is open access.
        topic (Mapped[Optional[str]]): Its main topic.
        source_url (Mapped[Optional[str]]): The request it was read from.
        fetched_at (Mapped[datetime]): When it was written.
    """

    __tablename__ = StorageTable.RESEARCH_PAPERS
    __table_args__ = (
        Index("ix_research_papers_publication_year", "publication_year"),
        Index("ix_research_papers_publication_date", "publication_date"),
        Index("ix_research_papers_cited_by_count", "cited_by_count"),
    )

    openalex_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    doi: Mapped[Optional[str]] = mapped_column(String(300))
    title: Mapped[Optional[str]] = mapped_column(Text)
    publication_year: Mapped[Optional[int]] = mapped_column(Integer)
    publication_date: Mapped[Optional[date]] = mapped_column(Date)
    type: Mapped[Optional[str]] = mapped_column(String(40))
    venue: Mapped[Optional[str]] = mapped_column(String(300))
    language: Mapped[Optional[str]] = mapped_column(String(8))
    cited_by_count: Mapped[int] = mapped_column(Integer)
    fwci: Mapped[Optional[float]] = mapped_column(Double)
    is_oa: Mapped[bool] = mapped_column(Boolean)
    topic: Mapped[Optional[str]] = mapped_column(String(300))
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
