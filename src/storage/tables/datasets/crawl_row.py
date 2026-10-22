from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import BigInteger, DateTime, Identity, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class CrawlRow(Base):
    """A crawl of a dataset: when it ran, how it ended and what it changed.

    Attributes:
        id (Mapped[int]): The crawl identifier.
        kind (Mapped[str]): What was crawled (see `DatasetKind`).
        dataset (Mapped[str]): The cloud provider, or the statistics source.
        status (Mapped[str]): The outcome of the crawl (see `CrawlStatus`).
        started_at (Mapped[datetime]): When the crawl started: the date of its additions, updates and deletions.
        finished_at (Mapped[Optional[datetime]]): When the crawl was over.
        listed_before (Mapped[int]): The number of items listed (not deleted) before the crawl.
        found (Mapped[int]): The number of distinct items crawled.
        added (Mapped[int]): The number of items new since the previous crawl.
        updated (Mapped[int]): The number of items updated since the previous crawl.
        deleted (Mapped[int]): The number of items marked deleted.
        error (Mapped[Optional[str]]): Why the crawl failed, if it did.
    """

    __tablename__ = StorageTable.CRAWLS
    __table_args__ = (Index("ix_crawls_kind_dataset_started_at", "kind", "dataset", "started_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    dataset: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    listed_before: Mapped[int] = mapped_column(Integer, server_default="0")
    found: Mapped[int] = mapped_column(Integer, server_default="0")
    added: Mapped[int] = mapped_column(Integer, server_default="0")
    updated: Mapped[int] = mapped_column(Integer, server_default="0")
    deleted: Mapped[int] = mapped_column(Integer, server_default="0")
    error: Mapped[Optional[str]] = mapped_column(Text)
