from __future__ import annotations

# Standard Library Imports.
from decimal import Decimal
from typing import Optional

# Third Party Imports.
from sqlalchemy import Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class FreeTierColumns:
    """The columns of a free offer as published, shared by the stored offers and those of a running crawl.

    Attributes:
        provider, free_key, service, kind: What is free, and how.
        quantity, unit, unit_raw, currency, period, duration_days: How much, per what, for how long.
        region_scope, conditions, source_url, source_kind: Where it applies, on what conditions, its source.
        fingerprint (Mapped[str]): The hash of its fields, compared from crawl to crawl.
    """

    provider: Mapped[str] = mapped_column(String(40))
    free_key: Mapped[str] = mapped_column(String(400))
    service: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 6))
    unit: Mapped[Optional[str]] = mapped_column(String(20))
    unit_raw: Mapped[Optional[str]] = mapped_column(String(120))
    currency: Mapped[Optional[str]] = mapped_column(String(3))
    period: Mapped[Optional[str]] = mapped_column(String(20))
    duration_days: Mapped[Optional[int]] = mapped_column(Integer)
    region_scope: Mapped[str] = mapped_column(String(80))
    conditions: Mapped[Optional[str]] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    source_kind: Mapped[str] = mapped_column(String(12))
    fingerprint: Mapped[str] = mapped_column(String(32))
