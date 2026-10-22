from __future__ import annotations

# Standard Library Imports.
from datetime import date
from typing import Optional

# Third Party Imports.
from pydantic import JsonValue
from sqlalchemy import BigInteger, Boolean, Date, Float, ForeignKey, Identity, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class MarketReportRow(Base):
    """A cloud market report of a statistics source (see `MarketReport`).

    Attributes:
        id (Mapped[int]): The report identifier.
        source (Mapped[str]): The statistics source (e.g. `synergy`).
        position (Mapped[int]): The position of the report in the statistics of the source.
        period, region, segment, currency, market_size_bn, twelve_month_bn, growth_pct, methodology_break,
            source_url, title, published: The report fields.
        shares (Mapped[JsonValue]): The market shares of the report, as JSON.
        mentions (Mapped[JsonValue]): The providers named without a share, as JSON.
        crawl_id (Mapped[int]): The crawl which wrote the report.
    """

    __tablename__ = StorageTable.MARKET_REPORTS
    __table_args__ = (UniqueConstraint("source", "period", "region", "segment"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    source: Mapped[str] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(Integer)
    period: Mapped[str] = mapped_column(String(10))
    region: Mapped[str] = mapped_column(String(40))
    segment: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3))
    market_size_bn: Mapped[Optional[float]] = mapped_column(Float)
    twelve_month_bn: Mapped[Optional[float]] = mapped_column(Float)
    growth_pct: Mapped[Optional[float]] = mapped_column(Float)
    shares: Mapped[JsonValue] = mapped_column(JSONB, nullable=False)
    mentions: Mapped[JsonValue] = mapped_column(JSONB, nullable=False)
    methodology_break: Mapped[bool] = mapped_column(Boolean)
    source_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    published: Mapped[date] = mapped_column(Date)
    crawl_id: Mapped[int] = mapped_column(BigInteger, ForeignKey(f"{StorageTable.CRAWLS}.id"))
