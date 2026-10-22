from __future__ import annotations

# Third Party Imports.
from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class LabelLinkRow(Base):
    """A taxonomy node a source label tells (a category, or a domain only), or one it must not tell.

    Attributes:
        label_id (Mapped[int]): The source label.
        node_slug (Mapped[str]): The taxonomy node.
        source (Mapped[str]): What made the link (see `LinkSource`).
        excluded (Mapped[bool]): Whether the label must not tell the node (a person removed the link).

    Notes:
        Recomputing the rule links only replaces the links whose source is `rule`: the seed, language model and user
        links are kept, and a user exclusion survives every recomputation.
    """

    __tablename__ = StorageTable.LABEL_LINKS
    __table_args__ = (Index("ix_label_links_node_slug", "node_slug"),)

    label_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{StorageTable.SOURCE_LABELS}.id", ondelete="CASCADE"), primary_key=True
    )
    node_slug: Mapped[str] = mapped_column(
        String(60), ForeignKey(f"{StorageTable.TAXONOMY_NODES}.slug", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(10))
    excluded: Mapped[bool] = mapped_column(Boolean, server_default="false")
