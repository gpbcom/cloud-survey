from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class CompanyIdentifierRow(Base):
    """An identifier of a company at a source (a SEC filer, an OpenAlex institution, an assignee).

    Attributes:
        company (Mapped[str]): The company key.
        kind (Mapped[str]): What it identifies the company at.
        value (Mapped[str]): The identifier.
        position (Mapped[int]): Its rank among the identifiers of its kind.
        status (Mapped[str]): Whether it is used (confirmed, candidate, rejected).
        evidence_url (Mapped[Optional[str]]): The page that shows it.
        checked_at (Mapped[Optional[datetime]]): When a resolver checked it last.
        note (Mapped[Optional[str]]): What the research noted about it.
        origin (Mapped[str]): Where it comes from (seed, user, resolver, parser).
        edited (Mapped[bool]): Whether a person changed it (a reseed never overwrites it).
        updated_at (Mapped[datetime]): When it was written last.
    """

    __tablename__ = StorageTable.COMPANY_IDENTIFIERS
    __table_args__ = (Index("ix_company_identifiers_status", "status"),)

    company: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[str] = mapped_column(String(300), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), server_default="confirmed")
    evidence_url: Mapped[Optional[str]] = mapped_column(Text)
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    note: Mapped[Optional[str]] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16), server_default="seed")
    edited: Mapped[bool] = mapped_column(Boolean, server_default=false())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
