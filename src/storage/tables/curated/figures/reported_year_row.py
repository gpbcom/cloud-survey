from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from pydantic import JsonValue
from sqlalchemy import Boolean, DateTime, Integer, SmallInteger, String, Text, false, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class ReportedYearRow(Base):
    """A fiscal year researched by hand.

    Attributes:
        company (Mapped[str]): The company key.
        fiscal_year (Mapped[int]): The fiscal year.
        position (Mapped[int]): Its rank among the company's years.
        body (Mapped[JsonValue]): The year, as its researched model writes it.
        check_status (Mapped[str]): What a parser of the cited document found.
        checked_at (Mapped[Optional[datetime]]): When a parser read the document last.
        check_note (Mapped[Optional[str]]): What the check found (the figures the document does not state).
        note (Mapped[Optional[str]]): What the research noted about it.
        origin (Mapped[str]): Where it comes from (seed, user, resolver, parser).
        edited (Mapped[bool]): Whether a person changed it (a reseed never overwrites it).
        updated_at (Mapped[datetime]): When it was written last.
    """

    __tablename__ = StorageTable.REPORTED_YEARS

    company: Mapped[str] = mapped_column(String(40), primary_key=True)
    fiscal_year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    body: Mapped[JsonValue] = mapped_column(JSONB, nullable=False)
    check_status: Mapped[str] = mapped_column(String(16), server_default="unchecked")
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    check_note: Mapped[Optional[str]] = mapped_column(Text)
    note: Mapped[Optional[str]] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16), server_default="seed")
    edited: Mapped[bool] = mapped_column(Boolean, server_default=false())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
