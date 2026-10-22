from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import List, Optional

# Third Party Imports.
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class TaxonomyNodeRow(Base):
    """A node of the unified taxonomy: a domain (no parent) or a category (under a domain), two levels only.

    Attributes:
        slug (Mapped[str]): The identifier of the node, kebab-case, never changed (the items store it).
        parent_slug (Mapped[Optional[str]]): The domain of a category, `NULL` for a domain.
        name_en (Mapped[str]): The English name.
        name_ru (Mapped[str]): The Russian name.
        name_zh (Mapped[str]): The Chinese name.
        description_en (Mapped[str]): A one-line English description (picker tooltips, language model prompts).
        position (Mapped[int]): The display order.
        audiences (Mapped[List[str]]): Who the items of the node are meant for (empty: those of its domain).
        umbrella (Mapped[bool]): Whether the category is the generic one of its domain.
        origin (Mapped[str]): Where the node comes from (see `NodeOrigin`).
        edited (Mapped[bool]): Whether a person edited it: the seed no longer overwrites it.
        hidden (Mapped[bool]): Whether it is hidden from the pickers (a seed node is hidden, never deleted).
        created_at (Mapped[datetime]): When it was stored.
        updated_at (Mapped[datetime]): When it was last changed.

    Notes:
        The English names are unique among the children of a parent (and among the domains), case-insensitive.
    """

    __tablename__ = StorageTable.TAXONOMY_NODES
    __table_args__ = (
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_kebab_case"),
        Index("ix_taxonomy_nodes_parent_slug", "parent_slug"),
        Index(
            "ix_taxonomy_nodes_parent_name",
            text("coalesce(parent_slug, '')"),
            text("lower(name_en)"),
            unique=True,
        ),
    )

    slug: Mapped[str] = mapped_column(String(60), primary_key=True)
    parent_slug: Mapped[Optional[str]] = mapped_column(
        String(60), ForeignKey(f"{StorageTable.TAXONOMY_NODES}.slug", ondelete="RESTRICT")
    )
    name_en: Mapped[str] = mapped_column(Text)
    name_ru: Mapped[str] = mapped_column(Text, server_default="")
    name_zh: Mapped[str] = mapped_column(Text, server_default="")
    description_en: Mapped[str] = mapped_column(Text, server_default="")
    position: Mapped[int] = mapped_column(Integer, server_default="0")
    audiences: Mapped[List[str]] = mapped_column(ARRAY(String(40)), server_default=text("'{}'"))
    umbrella: Mapped[bool] = mapped_column(Boolean, server_default="false")
    origin: Mapped[str] = mapped_column(String(10), server_default="seed")
    edited: Mapped[bool] = mapped_column(Boolean, server_default="false")
    hidden: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
