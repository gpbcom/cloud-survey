from __future__ import annotations

# Standard Library Imports.
from datetime import datetime

# Third Party Imports.
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class LabelSightingRow(Base):
    """Where a source label was seen: a kind of dataset of a provider.

    Attributes:
        label_id (Mapped[int]): The source label.
        kind (Mapped[str]): The kind of dataset (see `DatasetKind`).
        provider (Mapped[str]): The cloud provider.
        first_seen_at (Mapped[datetime]): When the label was first seen there.
        last_seen_at (Mapped[datetime]): When it was last seen there.
    """

    __tablename__ = StorageTable.LABEL_SIGHTINGS

    label_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{StorageTable.SOURCE_LABELS}.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
