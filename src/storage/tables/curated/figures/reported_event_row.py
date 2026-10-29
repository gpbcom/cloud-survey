from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from pydantic import JsonValue
from sqlalchemy import Boolean, DateTime, Integer, String, Text, false, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class ReportedEventRow(Base):
    """A dated figure researched by hand (a private company's funding round or run rate).

    Attributes:
        company (Mapped[str]): The company key.
        position (Mapped[int]): Its rank among the company's events.
        body (Mapped[JsonValue]): The event, as its researched model writes it.
        note (Mapped[Optional[str]]): What the research noted about it.
        origin (Mapped[str]): Where it comes from (seed, user, resolver, parser).
        edited (Mapped[bool]): Whether a person changed it (a reseed never overwrites it).
        updated_at (Mapped[datetime]): When it was written last.
    """

    __tablename__ = StorageTable.REPORTED_EVENTS

    company: Mapped[str] = mapped_column(String(40), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    body: Mapped[JsonValue] = mapped_column(JSONB, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16), server_default="seed")
    edited: Mapped[bool] = mapped_column(Boolean, server_default=false())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
