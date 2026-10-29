from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class AssigneeProfileRow(Base):
    """The profile of an assignee name of a company, derived from the stored publications.

    Attributes:
        company (Mapped[str]): The company.
        name (Mapped[str]): The assignee name, as the search writes it.
        publications (Mapped[int]): The publications filed under the name.
        first_year (Mapped[Optional[int]]): The earliest priority year.
        last_year (Mapped[Optional[int]]): The latest priority year.
        countries (Mapped[str]): The patent offices, comma-separated, the busiest first.
        top_cpc (Mapped[Optional[str]]): The most frequent main classes, comma-separated.
        top_inventors (Mapped[Optional[str]]): The most frequent inventors, comma-separated.
        refreshed_at (Mapped[datetime]): When it was derived.
    """

    __tablename__ = StorageTable.ASSIGNEE_PROFILES

    company: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(300), primary_key=True)
    publications: Mapped[int] = mapped_column(Integer)
    first_year: Mapped[Optional[int]] = mapped_column(Integer)
    last_year: Mapped[Optional[int]] = mapped_column(Integer)
    countries: Mapped[str] = mapped_column(Text)
    top_cpc: Mapped[Optional[str]] = mapped_column(Text)
    top_inventors: Mapped[Optional[str]] = mapped_column(Text)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
