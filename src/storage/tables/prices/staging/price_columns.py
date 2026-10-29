from __future__ import annotations

# Standard Library Imports.
from datetime import date
from decimal import Decimal
from typing import Optional

# Third Party Imports.
from pydantic import JsonValue
from sqlalchemy import Date, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class PriceColumns:
    """The columns of a price as published, shared by the stored prices and the prices of a running crawl.

    Attributes:
        provider, sku_key, service, family, region: What is priced, and where.
        instance_type, vcpu, memory_gib, storage_gib, os: The typed attributes of a compute or storage dimension,
            indexed for the workload costing.
        attributes (Mapped[JsonValue]): The other attributes, as JSON.
        unit, unit_raw, unit_factor: The normalized unit, the unit as written, and the normalized units in it.
        price, currency, model, term: The price of a raw unit, how it is charged, the commitment.
        tier_start, tier_end: The consumption range of the price (a free tier is a price of 0 from 0).
        billing_increment_s, minimum_quantity, minimum_duration_days: The consumption triggers.
        effective_from, source_url, source_kind, captured, reason: Its source, and why a service has no price.
        fingerprint (Mapped[str]): The hash of the priced fields, compared from crawl to crawl.
    """

    provider: Mapped[str] = mapped_column(String(40))
    sku_key: Mapped[str] = mapped_column(String(400))
    service: Mapped[str] = mapped_column(String(300))
    family: Mapped[Optional[str]] = mapped_column(String(200))
    region: Mapped[str] = mapped_column(String(80))
    instance_type: Mapped[Optional[str]] = mapped_column(String(120))
    vcpu: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 3))
    memory_gib: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 3))
    storage_gib: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 3))
    os: Mapped[Optional[str]] = mapped_column(String(120))
    attributes: Mapped[JsonValue] = mapped_column(JSONB, nullable=False)
    unit: Mapped[str] = mapped_column(String(20))
    unit_raw: Mapped[str] = mapped_column(String(120))
    unit_factor: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 12))
    currency: Mapped[Optional[str]] = mapped_column(String(3))
    model: Mapped[str] = mapped_column(String(20))
    term: Mapped[str] = mapped_column(String(4))
    tier_start: Mapped[Decimal] = mapped_column(Numeric(28, 6))
    tier_end: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 6))
    billing_increment_s: Mapped[Optional[int]] = mapped_column(Integer)
    minimum_quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 6))
    minimum_duration_days: Mapped[Optional[int]] = mapped_column(Integer)
    effective_from: Mapped[Optional[date]] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(Text)
    source_kind: Mapped[str] = mapped_column(String(12))
    captured: Mapped[Optional[date]] = mapped_column(Date)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(32))
