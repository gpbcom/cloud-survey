from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class SourceLabelRow(Base):
    """A category of a provider (a source label), in any language, with its English name.

    Attributes:
        id (Mapped[int]): The label identifier (the items store it).
        key (Mapped[str]): The normalized text (see `LabelNormalizer.key`): the spellings of a label share it.
        text (Mapped[str]): The first text seen with the key.
        language (Mapped[str]): The language of the text (see `Language`).
        name_en (Mapped[Optional[str]]): The English name, `NULL` while a non-English label is not translated.
        name_key (Mapped[Optional[str]]): The normalized English name: the labels sharing it are aliases.
        name_source (Mapped[Optional[str]]): Where the English name comes from (see `NameSource`).
        status (Mapped[str]): The translation status (see `LabelStatus`).
        status_source (Mapped[Optional[str]]): Where the status comes from (see `NameSource`).
        canonical_id (Mapped[Optional[int]]): The label this one was merged into (one level only).
        canonical_source (Mapped[Optional[str]]): Where the merge comes from (see `NameSource`).
        first_seen_at (Mapped[datetime]): When the label was first stored.
        last_seen_at (Mapped[datetime]): When a crawl last gave it.
        translated_at (Mapped[Optional[datetime]]): When it was translated.
        llm_claimed_at (Mapped[Optional[datetime]]): When a language model run claimed it.
        llm_attempts (Mapped[int]): The number of language model attempts.
        llm_error (Mapped[Optional[str]]): The last language model error.

    Notes:
        A crawl inserts the keys it does not know concurrently with the others: `INSERT ... ON CONFLICT (key) DO
        NOTHING`, the keys sorted.
    """

    __tablename__ = StorageTable.SOURCE_LABELS
    __table_args__ = (
        CheckConstraint("canonical_id <> id", name="not_its_own_canonical"),
        Index("ix_source_labels_key", "key", unique=True),
        Index("ix_source_labels_name_key", "name_key"),
        Index("ix_source_labels_canonical_id", "canonical_id"),
        Index("ix_source_labels_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    key: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(2))
    name_en: Mapped[Optional[str]] = mapped_column(Text)
    name_key: Mapped[Optional[str]] = mapped_column(Text)
    name_source: Mapped[Optional[str]] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(12), server_default="pending")
    status_source: Mapped[Optional[str]] = mapped_column(String(10))
    canonical_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{StorageTable.SOURCE_LABELS}.id", ondelete="SET NULL")
    )
    canonical_source: Mapped[Optional[str]] = mapped_column(String(10))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    translated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    llm_claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    llm_attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    llm_error: Mapped[Optional[str]] = mapped_column(Text)
