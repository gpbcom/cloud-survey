from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import ClassVar

# Third Party Imports.
from pydantic import JsonValue
from sqlalchemy import BigInteger, DateTime, ForeignKey, LargeBinary
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable


class VersionColumns:
    """The columns of the versions of the crawled items: the content of an item each time a crawl changed it.

    Attributes:
        ITEM_TABLE (ClassVar[str]): The table of the versioned items.
        crawl_id (Mapped[int]): The crawl which found the version.
        recorded_at (Mapped[datetime]): When the crawl found the version (the start of the crawl).
        fingerprint (Mapped[bytes]): The hash of the content fields of the version.
        content (Mapped[JsonValue]): The item without its dates, as JSON.

    Notes:
        A version is written when an item is new or its content fields changed,
        at most once per crawl. The versions
        are append-only, they are removed with their item only.
    """

    ITEM_TABLE: ClassVar[str] = ""

    crawl_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{StorageTable.CRAWLS}.id"), primary_key=True, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    content: Mapped[JsonValue] = mapped_column(JSONB, nullable=False)

    ############################
    # Publicly Exposed Methods #
    ############################

    @declared_attr
    def item_id(cls) -> Mapped[int]:
        """Get the column of the versioned item, removed with it.

        Returns:
            Mapped[int]: The identifier of the item, first column of the primary key.
        """
        return mapped_column(
            BigInteger, ForeignKey(f"{cls.ITEM_TABLE}.id", ondelete="CASCADE"), primary_key=True, sort_order=-1
        )
