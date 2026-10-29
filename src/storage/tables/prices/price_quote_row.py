from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from decimal import Decimal
from typing import Optional

# Third Party Imports.
from pydantic import JsonValue
from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class PriceQuoteRow(Base):
    """The monthly cost of a usage profile at a provider, in a region (see `PriceQuote`): a cache of the costing.

    Attributes:
        profile (Mapped[str]): The usage profile (removed with it).
        provider (Mapped[str]): The cloud provider.
        region (Mapped[str]): The region priced.
        options (Mapped[str]): The options of the costing, as a key.
        currency (Mapped[str]): The currency of the total.
        monthly_total (Mapped[Optional[Decimal]]): The monthly cost.
        breakdown (Mapped[JsonValue]): The cost of each item, as JSON.
        computed_at (Mapped[datetime]): When it was computed.
    """

    __tablename__ = StorageTable.PRICE_QUOTES

    profile: Mapped[str] = mapped_column(
        String(120), ForeignKey(f"{StorageTable.USAGE_PROFILES}.name", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    region: Mapped[str] = mapped_column(String(80), primary_key=True)
    options: Mapped[str] = mapped_column(String(120), primary_key=True)
    currency: Mapped[str] = mapped_column(String(3))
    monthly_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 6))
    breakdown: Mapped[JsonValue] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
