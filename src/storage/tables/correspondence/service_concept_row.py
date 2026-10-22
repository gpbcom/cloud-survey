from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Identity, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class ServiceConceptRow(Base):
    """A service concept shared by the providers (e.g. "Managed Kubernetes"): their equivalent services are its members.

    Attributes:
        id (Mapped[int]): The identifier of the concept.
        name (Mapped[str]): Its short English name.
        description (Mapped[str]): What it stands for, in one line.
        node_slug (Mapped[Optional[str]]): The taxonomy category it was found in (`NULL` once the node is gone).
        source (Mapped[str]): Who created it (see `ConceptSource`).
        edited (Mapped[bool]): Whether a person changed it: the language model no longer renames it.
        created_at (Mapped[datetime]): When it was stored.
        updated_at (Mapped[datetime]): When it was last changed.

    Notes:
        The names are unique within a category, case-insensitive: the language model answers are merged by name.
    """

    __tablename__ = StorageTable.SERVICE_CONCEPTS
    __table_args__ = (
        Index(
            "ix_service_concepts_node_name",
            text("coalesce(node_slug, '')"),
            text("lower(name)"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, server_default="")
    node_slug: Mapped[Optional[str]] = mapped_column(
        String(60), ForeignKey(f"{StorageTable.TAXONOMY_NODES}.slug", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(10), server_default="llm")
    edited: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
