from __future__ import annotations

# Standard Library Imports.
from datetime import date, datetime

# Third Party Imports.
from sqlalchemy import Date, DateTime, Double, String, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class FxRateRow(Base):
    """An exchange rate: the US dollars one unit of a currency was worth on a day.

    Attributes:
        currency (Mapped[str]): The currency, e.g. `EUR`.
        day (Mapped[date]): The day.
        usd_per_unit (Mapped[float]): The US dollars for one unit of the currency.
        source (Mapped[str]): Where it comes from (`fred`).
        fetched_at (Mapped[datetime]): When it was read.
    """

    __tablename__ = StorageTable.FX_RATES

    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    usd_per_unit: Mapped[float] = mapped_column(Double)
    source: Mapped[str] = mapped_column(String(16))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
