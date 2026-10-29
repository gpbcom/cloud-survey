from __future__ import annotations

# Standard Library Imports.
from datetime import date, datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import Date, DateTime, Double, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class CompanyIndicatorRow(Base):
    """A point of an indicator's time series: the value of an indicator of a company for one period.

    Attributes:
        company (Mapped[str]): The company of the chronology.
        indicator (Mapped[str]): The indicator, e.g. `rd-intensity`.
        period_end (Mapped[date]): The last day of the period.
        granularity (Mapped[str]): The period: `week`, `quarter`, `year` or `ttm`.
        value (Mapped[float]): The value, in its unit.
        unit (Mapped[str]): The unit: `currency`, `ratio`, `percent` or `count`.
        currency (Mapped[Optional[str]]): The currency of an amount.
        value_usd (Mapped[Optional[float]]): The amount in US dollars.
        inputs (Mapped[str]): How it was computed.
        computed_at (Mapped[datetime]): When it was computed.
    """

    __tablename__ = StorageTable.COMPANY_INDICATORS
    __table_args__ = (Index("ix_company_indicators_indicator", "indicator", "granularity"),)

    company: Mapped[str] = mapped_column(String(40), primary_key=True)
    indicator: Mapped[str] = mapped_column(String(40), primary_key=True)
    period_end: Mapped[date] = mapped_column(Date, primary_key=True)
    granularity: Mapped[str] = mapped_column(String(8), primary_key=True)
    value: Mapped[float] = mapped_column(Double)
    unit: Mapped[str] = mapped_column(String(12))
    currency: Mapped[Optional[str]] = mapped_column(String(3))
    value_usd: Mapped[Optional[float]] = mapped_column(Double)
    inputs: Mapped[str] = mapped_column(String(300))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
