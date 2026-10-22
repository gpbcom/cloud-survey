from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import BigInteger, CheckConstraint, DateTime, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class TaxonomyStateRow(Base):
    """The state of the taxonomy, a single row: its revision and its last seed.

    Attributes:
        id (Mapped[int]): Always 1.
        revision (Mapped[int]): Incremented by every manual or language model edit of the taxonomy or of the labels:
            the writers reload their caches when it changes (the crawls never change it).
        seed_hash (Mapped[Optional[str]]): The hash of the seed files last applied.
        seeded_at (Mapped[Optional[datetime]]): When they were applied.
    """

    __tablename__ = StorageTable.TAXONOMY_STATE
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, server_default="0")
    seed_hash: Mapped[Optional[str]] = mapped_column(Text)
    seeded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
