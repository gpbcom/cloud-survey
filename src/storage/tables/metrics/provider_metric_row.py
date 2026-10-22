from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import DateTime, Double, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class ProviderMetricRow(Base):
    """A measure of a provider for a quarter (a criterion or a target of the driver analysis), with its source.

    Attributes:
        provider (Mapped[str]): The provider.
        period (Mapped[str]): The quarter, written `YYYYQn`.
        metric (Mapped[str]): What is measured (see `ProviderMetric`).
        source (Mapped[str]): Where it comes from (see `MetricSource`).
        value (Mapped[float]): The measure.
        source_url (Mapped[Optional[str]]): The page or document it was read from.
        fetched_at (Mapped[datetime]): When it was read.

    Notes:
        Several sources may give the same measure: each is kept, the analysis prefers the most reliable one.
    """

    __tablename__ = StorageTable.PROVIDER_METRICS
    __table_args__ = (Index("ix_provider_metrics_metric", "metric"),)

    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    period: Mapped[str] = mapped_column(String(6), primary_key=True)
    metric: Mapped[str] = mapped_column(String(40), primary_key=True)
    source: Mapped[str] = mapped_column(String(12), primary_key=True)
    value: Mapped[float] = mapped_column(Double)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
