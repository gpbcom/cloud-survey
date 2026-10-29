from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from pydantic import JsonValue
from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, false, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class CuratedRecordRow(Base):
    """An entry of a section of the chronology or of the markets catalogue.

    Attributes:
        dataset (Mapped[str]): The section.
        key (Mapped[str]): The natural key of the entry.
        position (Mapped[int]): Its rank in the section.
        body (Mapped[JsonValue]): The entry, as its catalogue model writes it.
        note (Mapped[Optional[str]]): What the research noted about it.
        origin (Mapped[str]): Where it comes from (seed, user, resolver, parser).
        edited (Mapped[bool]): Whether a person changed it (a reseed never overwrites it).
        updated_at (Mapped[datetime]): When it was written last.
    """

    __tablename__ = StorageTable.CURATED_RECORDS
    __table_args__ = (Index("ix_curated_records_order", "dataset", "position"),)

    dataset: Mapped[str] = mapped_column(String(40), primary_key=True)
    key: Mapped[str] = mapped_column(String(300), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    body: Mapped[JsonValue] = mapped_column(JSONB, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16), server_default="seed")
    edited: Mapped[bool] = mapped_column(Boolean, server_default=false())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
