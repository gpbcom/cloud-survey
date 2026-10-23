from __future__ import annotations

# Standard Library Imports.
from datetime import date, datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import Boolean, Date, DateTime, Double, Index, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class MarketShareRow(Base):
    """A market share: a label's share of a segment, in an area, on a device, for a period, from a source.

    Attributes:
        segment (Mapped[str]): The segment, e.g. `search`.
        area (Mapped[str]): The area, e.g. `ww`, `US` or `eu27`.
        period (Mapped[date]): The first day of the period.
        granularity (Mapped[str]): Whether the period is a month, a quarter or a year (a year and its first quarter
            start the same day).
        device (Mapped[str]): The devices measured.
        metric (Mapped[str]): What the share is a share of (usage, units, revenue).
        source (Mapped[str]): Where it comes from.
        label (Mapped[str]): The label, as the source prints it.
        company (Mapped[Optional[str]]): The company of the chronology behind the label, if any.
        value (Mapped[float]): The share, in percent.
        estimate (Mapped[bool]): Whether it is estimated rather than published.
        source_url (Mapped[Optional[str]]): The document read.
        fetched_at (Mapped[datetime]): When it was read.
    """

    __tablename__ = StorageTable.MARKET_SHARES
    __table_args__ = (Index("ix_market_shares_company", "company", "segment"),)

    segment: Mapped[str] = mapped_column(String(40), primary_key=True)
    area: Mapped[str] = mapped_column(String(12), primary_key=True)
    period: Mapped[date] = mapped_column(Date, primary_key=True)
    granularity: Mapped[str] = mapped_column(String(8), primary_key=True)
    device: Mapped[str] = mapped_column(String(8), primary_key=True)
    metric: Mapped[str] = mapped_column(String(8), primary_key=True)
    source: Mapped[str] = mapped_column(String(12), primary_key=True)
    label: Mapped[str] = mapped_column(String(80), primary_key=True)
    company: Mapped[Optional[str]] = mapped_column(String(40))
    value: Mapped[float] = mapped_column(Double)
    estimate: Mapped[bool] = mapped_column(Boolean, server_default=false())
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
