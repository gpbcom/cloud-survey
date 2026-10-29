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


class InventorProfileRow(Base):
    """The profile of an inventor, derived from the stored publications.

    Attributes:
        name_key (Mapped[str]): The folded name.
        name (Mapped[str]): The most written spelling of the name.
        publications (Mapped[int]): The publications naming them.
        families (Mapped[int]): The families of those publications.
        first_priority (Mapped[Optional[date]]): The earliest priority date.
        last_priority (Mapped[Optional[date]]): The latest priority date.
        companies (Mapped[str]): The companies of the publications, comma-separated.
        top_cpc (Mapped[Optional[str]]): The most frequent main classes, comma-separated.
        co_inventors (Mapped[int]): The other inventors of the same publications.
        citations_received (Mapped[int]): The citations received by the publications whose page was read.
        refreshed_at (Mapped[datetime]): When it was derived.
    """

    __tablename__ = StorageTable.INVENTOR_PROFILES
    __table_args__ = (Index("ix_inventor_profiles_publications", "publications"),)

    name_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    publications: Mapped[int] = mapped_column(Integer)
    families: Mapped[int] = mapped_column(Integer)
    first_priority: Mapped[Optional[date]] = mapped_column(Date)
    last_priority: Mapped[Optional[date]] = mapped_column(Date)
    companies: Mapped[str] = mapped_column(Text)
    top_cpc: Mapped[Optional[str]] = mapped_column(Text)
    co_inventors: Mapped[int] = mapped_column(Integer)
    citations_received: Mapped[int] = mapped_column(Integer)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
