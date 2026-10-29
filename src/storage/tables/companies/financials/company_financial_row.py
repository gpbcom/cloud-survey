from __future__ import annotations

# Standard Library Imports.
from datetime import date, datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import Date, DateTime, Double, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class CompanyFinancialRow(Base):
    """A statement line of a company for one period, as one source states it (the quarters derived when needed).

    Attributes:
        company (Mapped[str]): The company of the chronology.
        metric (Mapped[str]): The statement line, e.g. `revenue`.
        period_end (Mapped[date]): The last day of the period, or the date of the balance.
        granularity (Mapped[str]): The period: `quarter`, `year` or `instant`.
        source (Mapped[str]): Where it was read: `edgar`, `gfinance`, `edgar-fds` or `reported`.
        value (Mapped[float]): The figure, signed.
        currency (Mapped[Optional[str]]): Its currency, none for shares.
        concept (Mapped[str]): The XBRL concept or Google position it was read from (`derived` for a derived quarter).
        form (Mapped[Optional[str]]): The filing form.
        fiscal_year (Mapped[Optional[int]]): The fiscal year the filing states.
        fiscal_period (Mapped[Optional[str]]): The fiscal period the filing states.
        filed (Mapped[Optional[date]]): The day of the filing.
        source_url (Mapped[Optional[str]]): The document read.
        note (Mapped[Optional[str]]): What the source says about the figure (a researched figure's scope).
        fetched_at (Mapped[datetime]): When it was written.
    """

    __tablename__ = StorageTable.COMPANY_FINANCIALS
    __table_args__ = (Index("ix_company_financials_company_metric", "company", "metric"),)

    company: Mapped[str] = mapped_column(String(40), primary_key=True)
    metric: Mapped[str] = mapped_column(String(40), primary_key=True)
    period_end: Mapped[date] = mapped_column(Date, primary_key=True)
    granularity: Mapped[str] = mapped_column(String(8), primary_key=True)
    source: Mapped[str] = mapped_column(String(12), primary_key=True)
    value: Mapped[float] = mapped_column(Double)
    currency: Mapped[Optional[str]] = mapped_column(String(3))
    concept: Mapped[str] = mapped_column(String(160))
    form: Mapped[Optional[str]] = mapped_column(String(12))
    fiscal_year: Mapped[Optional[int]] = mapped_column(Integer)
    fiscal_period: Mapped[Optional[str]] = mapped_column(String(4))
    filed: Mapped[Optional[date]] = mapped_column(Date)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    note: Mapped[Optional[str]] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
