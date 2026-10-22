from __future__ import annotations

# Standard Library Imports.
from datetime import datetime

# Third Party Imports.
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class ConceptMemberRow(Base):
    """A catalogue service filed under a service concept, or one a person removed from it.

    Attributes:
        concept_id (Mapped[int]): The concept.
        product_id (Mapped[int]): The catalogue product.
        role (Mapped[str]): Whether the service does what the concept stands for, or part of it (see `MemberRole`).
        confidence (Mapped[int]): How sure the language model is, from 0 to 100.
        source (Mapped[str]): Who filed it (see `ConceptSource`).
        excluded (Mapped[bool]): Whether a person removed it: the language model never files it there again.
        created_at (Mapped[datetime]): When it was stored.
    """

    __tablename__ = StorageTable.CONCEPT_MEMBERS
    __table_args__ = (Index("ix_concept_members_product_id", "product_id"),)

    concept_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{StorageTable.SERVICE_CONCEPTS}.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{StorageTable.PRODUCTS}.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(12), server_default="equivalent")
    confidence: Mapped[int] = mapped_column(SmallInteger, server_default="100")
    source: Mapped[str] = mapped_column(String(10), server_default="llm")
    excluded: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
