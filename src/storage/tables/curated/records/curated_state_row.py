from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class CuratedStateRow(Base):
    """The state of a file of the curated bundle: its last seed and its revision.

    Attributes:
        dataset (Mapped[str]): The bundle file (chronology, markets, companies, figures, launches).
        revision (Mapped[int]): Incremented by every write of its rows: the catalogues read from the database are
            read again when it changes.
        seed_hash (Mapped[Optional[str]]): The hash of the bundle file last applied.
        seeded_at (Mapped[Optional[datetime]]): When it was applied.
    """

    __tablename__ = StorageTable.CURATED_STATE

    dataset: Mapped[str] = mapped_column(String(40), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, server_default="0")
    seed_hash: Mapped[Optional[str]] = mapped_column(Text)
    seeded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
