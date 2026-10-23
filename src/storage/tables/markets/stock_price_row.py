from __future__ import annotations

# Standard Library Imports.
from datetime import date, datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import BigInteger, Date, DateTime, Double, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class StockPriceRow(Base):
    """A closing price of a listing, in its currency.

    Attributes:
        listing (Mapped[str]): The listing, `EXCHANGE:SYMBOL`.
        day (Mapped[date]): The trading day.
        source (Mapped[str]): Where it comes from (`google-finance`).
        close (Mapped[float]): The closing price.
        volume (Mapped[Optional[int]]): The shares traded, when given.
        currency (Mapped[str]): The listing currency.
        source_url (Mapped[Optional[str]]): The page or RPC read.
        fetched_at (Mapped[datetime]): When it was read.
    """

    __tablename__ = StorageTable.STOCK_PRICES

    listing: Mapped[str] = mapped_column(String(30), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    source: Mapped[str] = mapped_column(String(16), primary_key=True)
    close: Mapped[float] = mapped_column(Double)
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
