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


class PriceSourceRow(Base):
    """A price source as last read (see `PriceSource`): what an incremental crawl compares to read it again or not.

    Attributes:
        provider (Mapped[str]): The cloud provider.
        source_key (Mapped[str]): The source, its URL or offer code.
        version, etag, last_modified: What the source stated of its version at the last read.
        fetched_at (Mapped[datetime]): When it was read last.
        rows (Mapped[int]): The prices it gave.
        status (Mapped[str]): The outcome of the last read.
    """

    __tablename__ = StorageTable.PRICE_SOURCES

    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_key: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[Optional[str]] = mapped_column(String(200))
    etag: Mapped[Optional[str]] = mapped_column(String(200))
    last_modified: Mapped[Optional[str]] = mapped_column(String(100))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rows: Mapped[int] = mapped_column(Integer, server_default="0")
    status: Mapped[str] = mapped_column(String(12))
