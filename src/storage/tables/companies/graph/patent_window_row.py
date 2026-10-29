from __future__ import annotations

# Standard Library Imports.
from datetime import date, datetime

# Third Party Imports.
from sqlalchemy import Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class PatentWindowRow(Base):
    """A window of the patents search: an assignee search over a span of priority dates, maybe one office only.

    Attributes:
        company (Mapped[str]): The company searched.
        query (Mapped[str]): The assignee search.
        after (Mapped[date]): The first priority date of the window.
        before (Mapped[date]): The day after its last priority date.
        country (Mapped[str]): The patent office searched, empty for every office.
        expected (Mapped[int]): The publications Google counts.
        fetched (Mapped[int]): The publications read.
        status (Mapped[str]): Its state: `complete`, `split`, `incomplete` or `pending`.
        searched_at (Mapped[datetime]): When it was searched.
    """

    __tablename__ = StorageTable.PATENT_WINDOWS

    company: Mapped[str] = mapped_column(String(40), primary_key=True)
    query: Mapped[str] = mapped_column(String(120), primary_key=True)
    after: Mapped[date] = mapped_column(Date, primary_key=True)
    before: Mapped[date] = mapped_column(Date, primary_key=True)
    country: Mapped[str] = mapped_column(String(2), primary_key=True)
    expected: Mapped[int] = mapped_column(Integer)
    fetched: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12))
    searched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
