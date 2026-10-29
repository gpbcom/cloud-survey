from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Identity, Index, String, false, func, text
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base
from storage.tables.prices.staging.price_columns import PriceColumns


class ServicePriceRow(PriceColumns, Base):
    """A price of a cloud service, for the time it applied (see `StoredPrice`).

    Attributes:
        id (Mapped[int]): The row identifier.
        product_id (Mapped[Optional[int]]): The catalogue product it prices, once linked.
        origin (Mapped[str]): Who wrote it (`crawler`, `user`).
        edited (Mapped[bool]): Whether a person changed it: a crawl never closes nor replaces it.
        valid_from (Mapped[datetime]): Since when it applies.
        valid_to (Mapped[Optional[datetime]]): Until when it applied, `NULL` while it is current.

    Notes:
        The current prices are the rows without `valid_to`: a partial unique index keeps one per provider and
        `sku_key`, and the indexes of the readings (by service and region, by unit and model, the workload
        candidates by typed attribute) are partial on the current rows too.
    """

    __tablename__ = StorageTable.SERVICE_PRICES
    __table_args__ = (
        Index(
            "ux_service_prices_current",
            "provider",
            "sku_key",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
        Index("ix_service_prices_service", "provider", "service", "region", postgresql_where=text("valid_to IS NULL")),
        Index("ix_service_prices_unit", "unit", "model", "provider", postgresql_where=text("valid_to IS NULL")),
        Index(
            "ix_service_prices_compute",
            "family",
            "vcpu",
            "memory_gib",
            postgresql_where=text("valid_to IS NULL AND vcpu IS NOT NULL"),
        ),
        Index("ix_service_prices_product", "product_id", postgresql_where=text("valid_to IS NULL")),
        Index("ix_service_prices_history", "provider", "sku_key", "valid_from"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    product_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{StorageTable.PRODUCTS}.id", ondelete="SET NULL")
    )
    origin: Mapped[str] = mapped_column(String(12), server_default="crawler")
    edited: Mapped[bool] = mapped_column(Boolean, server_default=false())
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
