from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import BigInteger, Boolean, DateTime, Identity, Index, String, false, func, text
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base
from storage.tables.prices.staging.free_tier_columns import FreeTierColumns


class FreeTierRow(FreeTierColumns, Base):
    """A free offer of a cloud provider, for the time it applied (see `StoredFreeTier`).

    Attributes:
        id (Mapped[int]): The row identifier.
        origin (Mapped[str]): Who wrote it (`crawler`, `user`).
        edited (Mapped[bool]): Whether a person changed it: a crawl never closes nor replaces it.
        valid_from (Mapped[datetime]): Since when it applies.
        valid_to (Mapped[Optional[datetime]]): Until when it applied, `NULL` while it is current.
    """

    __tablename__ = StorageTable.FREE_TIERS
    __table_args__ = (
        Index("ux_free_tiers_current", "provider", "free_key", unique=True, postgresql_where=text("valid_to IS NULL")),
        Index("ix_free_tiers_service", "provider", "service", postgresql_where=text("valid_to IS NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    origin: Mapped[str] = mapped_column(String(12), server_default="crawler")
    edited: Mapped[bool] = mapped_column(Boolean, server_default=false())
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
