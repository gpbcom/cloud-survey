from __future__ import annotations

# Standard Library Imports.
from datetime import date, datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import Date, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class PatentRow(Base):
    """A patent publication of a company's assignees (one per publication, its page details once read).

    Attributes:
        publication_number (Mapped[str]): The publication, e.g. `US10000000B2`.
        country (Mapped[str]): Its patent office.
        title (Mapped[Optional[str]]): Its title.
        assignee (Mapped[Optional[str]]): Its assignee, as the search writes it.
        priority_date (Mapped[Optional[date]]): The date of its first filing.
        filing_date (Mapped[Optional[date]]): The date it was filed.
        publication_date (Mapped[Optional[date]]): The date it was published.
        grant_date (Mapped[Optional[date]]): The date it was granted, none for an application.
        family_id (Mapped[Optional[str]]): Its DOCDB family, once its page is read.
        abstract (Mapped[Optional[str]]): Its abstract, once its page is read.
        claims (Mapped[Optional[int]]): The number of its claims, once its page is read.
        detail_fetched_at (Mapped[Optional[datetime]]): When its page was read, none while it waits.
        source_url (Mapped[Optional[str]]): Its page.
        fetched_at (Mapped[datetime]): When it was written.
    """

    __tablename__ = StorageTable.PATENTS
    __table_args__ = (
        Index("ix_patents_family_id", "family_id"),
        Index("ix_patents_detail_fetched_at", "detail_fetched_at"),
        Index("ix_patents_priority_date", "priority_date"),
        Index("ix_patents_publication_date", "publication_date"),
    )

    publication_number: Mapped[str] = mapped_column(String(32), primary_key=True)
    country: Mapped[str] = mapped_column(String(2))
    title: Mapped[Optional[str]] = mapped_column(Text)
    assignee: Mapped[Optional[str]] = mapped_column(String(300))
    priority_date: Mapped[Optional[date]] = mapped_column(Date)
    filing_date: Mapped[Optional[date]] = mapped_column(Date)
    publication_date: Mapped[Optional[date]] = mapped_column(Date)
    grant_date: Mapped[Optional[date]] = mapped_column(Date)
    family_id: Mapped[Optional[str]] = mapped_column(String(20))
    abstract: Mapped[Optional[str]] = mapped_column(Text)
    claims: Mapped[Optional[int]] = mapped_column(Integer)
    detail_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
