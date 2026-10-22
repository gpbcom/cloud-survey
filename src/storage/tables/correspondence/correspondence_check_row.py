from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class CorrespondenceCheckRow(Base):
    """The last time the language model matched a catalogue service within a taxonomy category.

    Attributes:
        product_id (Mapped[int]): The catalogue product.
        node_slug (Mapped[str]): The taxonomy category it was matched in.
        fingerprint (Mapped[Optional[bytes]]): The content of the product the match was made for, `NULL` while it
            waits for another attempt.
        checked_at (Mapped[datetime]): When it was last matched, or tried.
        llm_attempts (Mapped[int]): The failed attempts since the last match.
        llm_error (Mapped[Optional[str]]): Why the last attempt failed.

    Notes:
        A listed product filed under a category is pending there until a check holds its current fingerprint: a new
        product, a changed one, and one moved to another category are matched again.
    """

    __tablename__ = StorageTable.CORRESPONDENCE_CHECKS

    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{StorageTable.PRODUCTS}.id", ondelete="CASCADE"), primary_key=True
    )
    node_slug: Mapped[str] = mapped_column(
        String(60), ForeignKey(f"{StorageTable.TAXONOMY_NODES}.slug", ondelete="CASCADE"), primary_key=True
    )
    fingerprint: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    llm_attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    llm_error: Mapped[Optional[str]] = mapped_column(Text)
