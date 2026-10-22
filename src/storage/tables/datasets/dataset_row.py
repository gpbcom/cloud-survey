from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import ITEM_REVISION, Base


class DatasetRow(Base):
    """A stored dataset: the catalogue or marketplace of a cloud provider, or the statistics of a source.

    Attributes:
        kind (Mapped[str]): What the dataset holds (see `DatasetKind`).
        dataset (Mapped[str]): The cloud provider, or the statistics source.
        label (Mapped[Optional[str]]): A readable name of the dataset source.
        crawled_at (Mapped[datetime]): When the last crawl of the dataset started.
        in_progress (Mapped[bool]): Whether a crawl is writing the dataset.
        current_crawl_id (Mapped[Optional[int]]): The crawl writing the dataset.
        last_crawl_id (Mapped[Optional[int]]): The last crawl over.
        size (Mapped[int]): The number of items still listed by the website.
        revision (Mapped[int]): The value of the `item_revision` sequence when the dataset was last written.

    Notes:
        It is the cheap stamp of the dataset: its readers read the dataset again when its revision changes.
    """

    __tablename__ = StorageTable.DATASETS

    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    dataset: Mapped[str] = mapped_column(String(100), primary_key=True)
    label: Mapped[Optional[str]] = mapped_column(String(200))
    crawled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    in_progress: Mapped[bool] = mapped_column(Boolean, server_default="false")
    current_crawl_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey(f"{StorageTable.CRAWLS}.id"))
    last_crawl_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey(f"{StorageTable.CRAWLS}.id"))
    size: Mapped[int] = mapped_column(Integer, server_default="0")
    revision: Mapped[int] = mapped_column(BigInteger, server_default=ITEM_REVISION.next_value())
